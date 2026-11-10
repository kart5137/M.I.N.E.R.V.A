"""`ei forecast run`: backtest → evaluate → select → final fit → forecasts → registry.

One run per disease target (forecasting/spec.py): influenza positivity (M5) and dengue
incidence (D4). Each run replaces only its own disease's backtest detail.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sqlalchemy import Engine, delete, insert, select, update

from ei_db.catalog import MODEL_LABELS
from ei_db.models import (
    BacktestPrediction,
    Forecast,
    ForecastExplanation,
    ModelEvaluation,
    ModelVersion,
)
from ei_pipeline.config import ROOT
from ei_pipeline.db import session_scope
from ei_pipeline.forecasting import config as cfg
from ei_pipeline.forecasting import spec as specs
from ei_pipeline.forecasting.backtest import (
    add_sequential_intervals,
    common_rows,
    group_quantiles,
    run_backtest,
    volume_group,
)
from ei_pipeline.forecasting.data import Panel, load_dengue_panel, load_panel
from ei_pipeline.forecasting.evaluation import Selection, evaluate, mase_scales
from ei_pipeline.forecasting.evaluation import select as select_models
from ei_pipeline.forecasting.explain import explain, global_importance, top_contributors
from ei_pipeline.forecasting.features import WEATHER_FEATURES, build_frames
from ei_pipeline.forecasting.models import fit, offset, predict_p, row_offset
from ei_pipeline.forecasting.report import weather_comparison, weather_verdict, write_model_card

log = logging.getLogger(__name__)

CARDS = ROOT / "docs" / "models"


def _git_sha() -> str | None:
    # Containers and CI have no .git: the image / workflow passes the commit instead.
    if sha := os.environ.get("EI_GIT_SHA") or os.environ.get("GITHUB_SHA"):
        return sha
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True,
                              text=True, check=True, timeout=10).stdout.strip() or None
    except Exception:  # noqa: BLE001 - not a git checkout
        return None


def _final_forecasts(frames, bt, panel, hp, spec: specs.TargetSpec, ml_models):
    """Forecast rows from origin = reference week, for every model and horizon."""
    ref = pd.Timestamp(panel.reference_week)
    out, fitted, shap_out, bases = [], {}, {}, {}
    for h, frame in frames.items():
        rows = frame[(frame["origin"] == ref) & frame["y_lag0"].notna()].copy()
        if rows.empty:
            continue
        scale = np.maximum(rows["y_std8"].fillna(spec.scale_floor), spec.scale_floor)
        preds = {name: rows[f"bl_{name}"].to_numpy(dtype=float) for name in cfg.BASELINES}
        for name in ml_models:
            model, train = fit(name, frame, ref, hp, spec)
            fitted[(name, h)] = (model, len(train), train["target_week"].min())
            preds[name] = predict_p(model, rows, spec)
            values, base = explain(model, rows)
            # Per-forecast starting point of the explanation (model scale): the model's
            # average output, plus this week's value for change targets.
            bases[(name, h)] = base + offset(model, rows)
            shap_out[(name, h)] = (values, base,
                                   top_contributors(values, rows, model.ei_features),
                                   model.ei_features)
        groups = volume_group(rows["volume_mean4"], spec.volume_edges)
        for name, p in preds.items():
            qs = group_quantiles(bt[(bt["model"] == name) & (bt["horizon"] == h)],
                                 spec.volume_edges)
            off = row_offset(rows)
            df = rows[["iso3", "origin", "target_week"]].assign(
                model=name, horizon=h, point=p, point_y=spec.to_y(p, off),
                scale=scale.to_numpy(), volume_group=groups)
            for a, tag in ((0.80, "80"), (0.95, "95")):
                q = df["volume_group"].map({g: v[a] for g, v in qs.items()})
                df[f"lo{tag}"], df[f"hi{tag}"] = spec.interval(df["point_y"], q * df["scale"],
                                                               off)
            if name in ml_models:
                df["explanation_idx"] = range(len(df))
                df["explanation_base"] = bases[(name, h)]
            out.append(df.dropna(subset=["point"]))
    return pd.concat(out, ignore_index=True), fitted, shap_out


def _save_artefacts(run_key, fitted, hp, selection, spec: specs.TargetSpec,
                    root: Path) -> Path:
    folder = root / spec.disease / spec.target / run_key
    folder.mkdir(parents=True, exist_ok=True)
    for (name, h), (model, _, _) in fitted.items():
        if name.startswith("xgboost"):
            model.save_model(folder / f"{name}_h{h}.json")
        else:
            joblib.dump(model, folder / f"{name}_h{h}.joblib", compress=3)
    (folder / "config.json").write_text(json.dumps({
        "run_key": run_key, "disease": spec.disease, "target": spec.target,
        "features": {m: list(spec.features_for(m)) for m in spec.ml_models},
        "hyperparams": asdict(hp), "horizons": list(cfg.HORIZONS),
        "selection": {h: s.active for h, s in selection.items()},
    }, indent=2), encoding="utf-8")
    return folder


def weather_coverage(frames, bt: pd.DataFrame, panel: Panel) -> dict:
    """How much of the comparison had weather: share of scored backtest rows with the
    first weather feature, and countries with it at the latest origin."""
    col = WEATHER_FEATURES[0]
    h = min(frames)
    f = frames[h].set_index(["iso3", "origin"])[col]
    scored = bt[(bt["horizon"] == h)][["iso3", "origin"]].drop_duplicates()
    have = f.reindex(pd.MultiIndex.from_frame(scored)).notna()
    at_ref = frames[h][frames[h]["origin"] == pd.Timestamp(panel.reference_week)]
    return {"rows_with_weather": float(have.mean()) if len(have) else 0.0,
            "countries_at_origin": int(at_ref[col].notna().sum()),
            "countries": len(panel.countries), "feature_checked": col}


def require_weather_benefit(selection: dict, bt: pd.DataFrame) -> dict:
    """A `*_weather` model stays active only if the paired comparison with its twin
    (same algorithm without weather) shows weather helps: the 95% bootstrap interval of
    the MAE change is entirely below zero (DENGUE_PLAN §2.5). Otherwise the twin is used,
    so a weather model never wins on noise in MASE."""
    cmp_ = weather_comparison(bt)
    out = {}
    for h, sel in selection.items():
        if not sel.active.endswith("_weather"):
            out[h] = sel
            continue
        twin = sel.active.removesuffix("_weather")
        row = cmp_[(cmp_["algorithm"] == twin) & (cmp_["horizon"] == h)]
        if len(row) and weather_verdict(row.iloc[0]) == "weather helps":
            out[h] = sel
            continue
        r = row.iloc[0] if len(row) else None
        why = (f"weather changed its MAE by {r['change']:+.1%} (95% interval "
               f"{r['ci_low']:+.1%} to {r['ci_high']:+.1%}), not a clear improvement"
               if r is not None else "no paired comparison was possible")
        out[h] = Selection(h, twin, f"{MODEL_LABELS[sel.active]} had the lowest backtest MASE, "
                           f"but {why}, so {MODEL_LABELS[twin]} without weather is used. "
                           f"Selection detail: {sel.note}")
    return out


def _load(engine: Engine, spec: specs.TargetSpec) -> Panel:
    return load_panel(engine) if spec.disease == "influenza" else load_dengue_panel(engine)


def run_forecast(engine: Engine, *, disease: str = "influenza", fast: bool = False,
                 artefact_root: Path | None = None, card_path: Path | None | str = "default",
                 ml_models=None) -> dict:
    spec = specs.get(disease)
    ml_models = spec.ml_models if ml_models is None else tuple(ml_models)
    if card_path == "default":
        card_path = CARDS / spec.card_name
    hp = cfg.FAST if fast else cfg.Hyperparams()
    panel = _load(engine, spec)
    log.info("%s panel: %d countries, reference week %s", disease, len(panel.countries),
             panel.reference_week)
    frames = build_frames(panel, cfg.HORIZONS, disease, spec.all_features)

    bt = add_sequential_intervals(common_rows(run_backtest(
        frames, panel.reference_week, hp, ml_models, spec)), spec)
    evals = evaluate(bt, mase_scales(panel.weekly))
    selection = select_models(evals)
    if any(m.endswith("_weather") for m in ml_models):
        selection = require_weather_benefit(selection, bt)
    fc, fitted, shap_out = _final_forecasts(frames, bt, panel, hp, spec, ml_models)

    run_key = f"{panel.reference_week:%Y%m%d}-{datetime.now(UTC):%H%M%S}"
    if spec.disease != "influenza":
        run_key = f"{spec.disease[:3]}-{run_key}"
    artefacts = _save_artefacts(run_key, fitted, hp, selection, spec,
                                artefact_root or ROOT / "models")
    sha = _git_sha()

    with session_scope(engine) as s:
        s.execute(update(ModelVersion)
                  .where(ModelVersion.disease_id == panel.disease_id,
                         ModelVersion.target == spec.target)
                  .values(is_active=False))
        # Keep backtest detail only for the latest run of this disease (metrics stay for
        # every run).
        s.execute(delete(BacktestPrediction).where(BacktestPrediction.model_version_id.in_(
            select(ModelVersion.id).where(ModelVersion.disease_id == panel.disease_id))))
        version_ids = {}
        for h in cfg.HORIZONS:
            for name in (*cfg.BASELINES, *ml_models):
                is_ml = name in ml_models
                n_rows, first = (fitted[(name, h)][1:] if (name, h) in fitted else (None, None))
                imp = (global_importance(shap_out[(name, h)][0], shap_out[(name, h)][3])
                       if (name, h) in shap_out else None)
                active = selection.get(h) is not None and selection[h].active == name
                hparams = hp.rf if name.startswith("random_forest") else hp.xgb
                vid = s.execute(insert(ModelVersion).returning(ModelVersion.id).values(
                    disease_id=panel.disease_id, run_key=run_key, model_type=name,
                    kind="ml" if is_ml else "baseline", target=spec.target, horizon_weeks=h,
                    train_start=first.date() if first is not None else None,
                    train_end=panel.reference_week,
                    features=list(spec.features_for(name)) if is_ml else None,
                    hyperparams=({**hparams, "training_rows": n_rows} if is_ml else None),
                    global_importance=imp,
                    artefact_uri=str(artefacts.relative_to(ROOT)) if is_ml and
                    artefacts.is_relative_to(ROOT) else (str(artefacts) if is_ml else None),
                    git_sha=sha, is_active=active,
                    selection_note=selection[h].note if active else None,
                )).scalar_one()
                version_ids[(name, h)] = vid

        ev = evals.assign(model_version_id=[version_ids[(m, h)] for m, h in
                                            zip(evals["model"], evals["horizon"], strict=True)])
        ev = ev.astype(object).where(ev.notna(), None)
        s.execute(insert(ModelEvaluation), ev[[
            "model_version_id", "iso3", "metric", "value", "n_obs", "n_origins", "eval_start",
            "eval_end"]].to_dict("records"))

        btw = bt.assign(model_version_id=[version_ids[(m, h)] for m, h in
                                          zip(bt["model"], bt["horizon"], strict=True)],
                        origin_week=bt["origin"].dt.date, target_week=bt["target_week"].dt.date,
                        actual=bt["actual_p"])
        btw = btw[["model_version_id", "iso3", "origin_week", "target_week", "point", "lo80",
                   "hi80", "lo95", "hi95", "actual"]]
        s.execute(insert(BacktestPrediction), btw.astype(object).where(btw.notna(), None)
                  .to_dict("records"))

        n_expl = 0
        for (name, h), grp in fc.groupby(["model", "horizon"]):
            vid = version_ids[(name, h)]
            recs = [{
                "model_version_id": vid, "disease_id": panel.disease_id, "iso3": r.iso3,
                "origin_week": r.origin.date(), "target_week": r.target_week.date(),
                "horizon_weeks": h, "target": spec.target, "point": float(r.point),
                "lo80": float(r.lo80), "hi80": float(r.hi80), "lo95": float(r.lo95),
                "hi95": None if pd.isna(r.hi95) else float(r.hi95),
                "explanation_base": (float(r.explanation_base) if (name, h) in shap_out
                                     else None),
            } for r in grp.itertuples()]
            ids = s.execute(insert(Forecast).returning(Forecast.id, sort_by_parameter_order=True),
                            recs).scalars().all()
            if (name, h) in shap_out:
                contribs = shap_out[(name, h)][2]
                expl = [{"forecast_id": fid, **c}
                        for fid, idx in zip(ids, grp["explanation_idx"].astype(int), strict=True)
                        for c in contribs[idx]]
                s.execute(insert(ForecastExplanation), expl)
                n_expl += len(expl)

    summary = {
        "disease": spec.disease, "target": spec.target,
        "run_key": run_key, "reference_week": str(panel.reference_week),
        "countries": len(panel.countries),
        "backtest_rows": len(bt), "forecasts": len(fc), "explanations": n_expl,
        "active": {h: s.active for h, s in selection.items()},
        "artefacts": str(artefacts),
    }
    if any(m.endswith("_weather") for m in ml_models):
        summary["weather_coverage"] = weather_coverage(frames, bt, panel)
    if card_path is not None:
        write_model_card(Path(card_path), summary, evals, selection, shap_out, panel, bt, spec)
        summary["model_card"] = str(card_path)
    return summary
