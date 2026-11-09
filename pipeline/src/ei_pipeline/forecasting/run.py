"""`ei forecast run`: backtest → evaluate → select → final fit → forecasts → registry."""

from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sqlalchemy import Engine, delete, insert, update

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
from ei_pipeline.forecasting.backtest import (
    add_sequential_intervals,
    common_rows,
    group_quantiles,
    run_backtest,
    volume_group,
)
from ei_pipeline.forecasting.data import load_panel
from ei_pipeline.forecasting.evaluation import evaluate, mase_scales, select
from ei_pipeline.forecasting.explain import explain, global_importance, top_contributors
from ei_pipeline.forecasting.features import FEATURES, build_frames
from ei_pipeline.forecasting.models import fit, interval, predict_p, to_logit
from ei_pipeline.forecasting.report import write_model_card

log = logging.getLogger(__name__)


def _git_sha() -> str | None:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True,
                              text=True, check=True, timeout=10).stdout.strip() or None
    except Exception:  # noqa: BLE001 - not a git checkout
        return None


def _final_forecasts(frames, bt, panel, hp, ml_models):
    """Forecast rows from origin = reference week, for every model and horizon."""
    ref = pd.Timestamp(panel.reference_week)
    out, fitted, shap_out = [], {}, {}
    for h, frame in frames.items():
        rows = frame[(frame["origin"] == ref) & frame["y_lag0"].notna()].copy()
        if rows.empty:
            continue
        scale = np.maximum(rows["y_std8"].fillna(cfg.SCALE_FLOOR), cfg.SCALE_FLOOR)
        preds = {name: rows[f"bl_{name}"].to_numpy(dtype=float) for name in cfg.BASELINES}
        for name in ml_models:
            model, train = fit(name, frame, ref, hp)
            fitted[(name, h)] = (model, len(train), train["target_week"].min())
            preds[name] = predict_p(model, rows)
            values, base = explain(model, rows)
            shap_out[(name, h)] = (values, base, top_contributors(values, rows))
        groups = volume_group(rows["tests_mean4"])
        for name, p in preds.items():
            qs = group_quantiles(bt[(bt["model"] == name) & (bt["horizon"] == h)])
            df = rows[["iso3", "origin", "target_week"]].assign(
                model=name, horizon=h, point=p, point_y=to_logit(p), scale=scale.to_numpy(),
                volume_group=groups)
            for a, tag in ((0.80, "80"), (0.95, "95")):
                q = df["volume_group"].map({g: v[a] for g, v in qs.items()})
                df[f"lo{tag}"], df[f"hi{tag}"] = interval(df["point_y"], q * df["scale"])
            if name in ml_models:
                df["explanation_idx"] = range(len(df))
            out.append(df.dropna(subset=["point"]))
    return pd.concat(out, ignore_index=True), fitted, shap_out


def _save_artefacts(run_key, fitted, hp, selection, root: Path) -> Path:
    folder = root / "influenza" / cfg.TARGET / run_key
    folder.mkdir(parents=True, exist_ok=True)
    for (name, h), (model, _, _) in fitted.items():
        if name == "xgboost":
            model.save_model(folder / f"{name}_h{h}.json")
        else:
            joblib.dump(model, folder / f"{name}_h{h}.joblib", compress=3)
    (folder / "config.json").write_text(json.dumps({
        "run_key": run_key, "target": cfg.TARGET, "features": FEATURES,
        "hyperparams": asdict(hp), "horizons": list(cfg.HORIZONS),
        "selection": {h: s.active for h, s in selection.items()},
    }, indent=2), encoding="utf-8")
    return folder


def run_forecast(engine: Engine, *, fast: bool = False, artefact_root: Path | None = None,
                 card_path: Path | None = ROOT / "docs" / "models" / "influenza-positivity.md",
                 ml_models=cfg.ML_MODELS) -> dict:
    hp = cfg.FAST if fast else cfg.Hyperparams()
    panel = load_panel(engine)
    log.info("Panel: %d countries, reference week %s", len(panel.countries),
             panel.reference_week)
    frames = build_frames(panel, cfg.HORIZONS)

    bt = add_sequential_intervals(common_rows(run_backtest(frames, panel.reference_week, hp,
                                                           ml_models)))
    evals = evaluate(bt, mase_scales(panel.weekly))
    selection = select(evals)
    fc, fitted, shap_out = _final_forecasts(frames, bt, panel, hp, ml_models)

    run_key = f"{panel.reference_week:%Y%m%d}-{datetime.now(UTC):%H%M%S}"
    artefacts = _save_artefacts(run_key, fitted, hp, selection,
                                artefact_root or ROOT / "models")
    sha = _git_sha()

    with session_scope(engine) as s:
        s.execute(update(ModelVersion)
                  .where(ModelVersion.disease_id == panel.disease_id,
                         ModelVersion.target == cfg.TARGET)
                  .values(is_active=False))
        # Keep backtest detail only for the latest run (metrics stay for every run).
        s.execute(delete(BacktestPrediction))
        version_ids = {}
        for h in cfg.HORIZONS:
            for name in (*cfg.BASELINES, *ml_models):
                is_ml = name in ml_models
                n_rows, first = (fitted[(name, h)][1:] if (name, h) in fitted else (None, None))
                imp = global_importance(shap_out[(name, h)][0]) if (name, h) in shap_out else None
                active = selection.get(h) is not None and selection[h].active == name
                vid = s.execute(insert(ModelVersion).returning(ModelVersion.id).values(
                    disease_id=panel.disease_id, run_key=run_key, model_type=name,
                    kind="ml" if is_ml else "baseline", target=cfg.TARGET, horizon_weeks=h,
                    train_start=first.date() if first is not None else None,
                    train_end=panel.reference_week,
                    features=FEATURES if is_ml else None,
                    hyperparams=({**(hp.rf if name == "random_forest" else hp.xgb),
                                  "training_rows": n_rows} if is_ml else None),
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
            base = shap_out[(name, h)][1] if (name, h) in shap_out else None
            recs = [{
                "model_version_id": vid, "disease_id": panel.disease_id, "iso3": r.iso3,
                "origin_week": r.origin.date(), "target_week": r.target_week.date(),
                "horizon_weeks": h, "target": cfg.TARGET, "point": float(r.point),
                "lo80": float(r.lo80), "hi80": float(r.hi80), "lo95": float(r.lo95),
                "hi95": float(r.hi95), "explanation_base": base,
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
        "run_key": run_key, "reference_week": str(panel.reference_week),
        "countries": len(panel.countries),
        "backtest_rows": len(bt), "forecasts": len(fc), "explanations": n_expl,
        "active": {h: s.active for h, s in selection.items()},
        "artefacts": str(artefacts),
    }
    if card_path is not None:
        write_model_card(card_path, summary, evals, selection, shap_out, panel, bt)
        summary["model_card"] = str(card_path)
    return summary
