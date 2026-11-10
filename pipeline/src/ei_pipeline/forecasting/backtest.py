"""Rolling-origin, expanding-window backtest with sequential conformal intervals.

At each origin o (every ORIGIN_STEP weeks from BACKTEST_START to the last origin whose
target is settled), every model forecasts t = o + h for every eligible country. ML models
are refitted every REFIT_EVERY weeks on rows whose target week ≤ the refit origin, so no
prediction ever sees its own target or anything after its origin.

Limitation: features use today's (revised) data, not the data as first published.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from ei_pipeline.forecasting import config as cfg
from ei_pipeline.forecasting.models import fit, predict_p, row_offset
from ei_pipeline.forecasting.spec import TargetSpec, influenza

log = logging.getLogger(__name__)


def origins(reference_week, horizon: int) -> list[pd.Timestamp]:
    last = pd.Timestamp(reference_week) - pd.Timedelta(weeks=horizon)
    return list(pd.date_range(cfg.BACKTEST_START, last, freq=f"{7 * cfg.ORIGIN_STEP}D"))


def run_backtest(frames: dict[int, pd.DataFrame], reference_week, hp: cfg.Hyperparams,
                 ml_models=None, spec: TargetSpec | None = None) -> pd.DataFrame:
    """Long table: model, horizon, iso3, origin, target_week, point (natural scale),
    actual_p, point_y, actual_y, scale, volume_group. Only rows with a usable actual are
    kept."""
    spec = spec or influenza()
    ml_models = spec.ml_models if ml_models is None else ml_models
    out = []
    for h, frame in frames.items():
        os_ = origins(reference_week, h)
        if not os_:
            continue
        at = frame[frame["origin"].isin(os_) & frame["trainable"]]
        common = at[["iso3", "origin", "target_week", "actual_p", "actual_y", "y_std8",
                     "volume_mean4", *(["offset"] if "offset" in at else [])]]
        for name in cfg.BASELINES:
            out.append(common.assign(model=name, horizon=h, point=at[f"bl_{name}"]))

        for name in ml_models:
            preds = []
            fitted_at = None
            model = None
            for o in os_:
                if fitted_at is None or (o - fitted_at).days >= 7 * cfg.REFIT_EVERY:
                    model, rows = fit(name, frame, o, hp, spec)
                    fitted_at = o
                    log.info("backtest h=%d %s refit at %s on %d rows", h, name, o.date(),
                             len(rows))
                cur = at[at["origin"] == o]
                if len(cur):
                    preds.append(cur[["iso3", "origin"]].assign(
                        point=predict_p(model, cur, spec)))
            if preds:
                p = pd.concat(preds)
                out.append(common.merge(p, on=["iso3", "origin"]).assign(model=name, horizon=h))

    bt = pd.concat(out, ignore_index=True).dropna(subset=["point", "actual_p"])
    bt["point_y"] = spec.to_y(bt["point"], row_offset(bt))
    bt["scale"] = np.maximum(bt["y_std8"].fillna(spec.scale_floor), spec.scale_floor)
    bt["volume_group"] = volume_group(bt["volume_mean4"], spec.volume_edges)
    return bt.drop(columns=["y_std8", "volume_mean4"])


def volume_group(volume_mean4, edges=cfg.CONFORMAL_GROUP_EDGES) -> np.ndarray:
    """0 = lowest volume (specimens or cases per week) ... len(edges) = highest."""
    return np.digitize(np.nan_to_num(np.asarray(volume_mean4, dtype=float)), edges)


def group_quantiles(scores: pd.DataFrame, edges=cfg.CONFORMAL_GROUP_EDGES
                    ) -> dict[int, dict[float, float]]:
    """Conformal quantiles per volume group, from a frame with `score` and
    `volume_group`; groups with too few scores use the pooled quantiles."""
    pooled = conformal_quantiles(scores["score"].to_numpy())
    out = {}
    for g in range(len(edges) + 1):
        s = scores.loc[scores["volume_group"] == g, "score"].to_numpy()
        out[g] = conformal_quantiles(s) if len(s) >= cfg.CONFORMAL_MIN_GROUP else pooled
    return out


def common_rows(bt: pd.DataFrame) -> pd.DataFrame:
    """Keep (horizon, iso3, origin) rows where every model has a forecast, so all models
    are scored on exactly the same cases."""
    n_models = bt["model"].nunique()
    key = ["horizon", "iso3", "origin"]
    counts = bt.groupby(key)["model"].transform("nunique")
    return bt[counts == n_models].copy() if n_models else bt


def conformal_quantiles(scores: np.ndarray, levels=cfg.INTERVAL_LEVELS) -> dict[float, float]:
    """Finite-sample split-conformal quantile of normalised absolute scores."""
    n = len(scores)
    out = {}
    for a in levels:
        k = min(n, int(np.ceil((n + 1) * a)))
        out[a] = float(np.sort(scores)[k - 1]) if n else np.nan
    return out


def add_sequential_intervals(bt: pd.DataFrame, spec: TargetSpec | None = None
                             ) -> pd.DataFrame:
    """Intervals for each backtest origin from residuals of strictly earlier origins
    (same model, horizon and volume group).
    Score = |y(actual) − y(forecast)| / scale on the model scale, with the observed value
    transformed directly (influenza: positivity clipped to [0.1%, 99.9%]), the same
    values the intervals are checked against (a smoothed target would never let a 0%
    week fall inside an interval)."""
    spec = spec or influenza()
    bt = bt.sort_values(["model", "horizon", "origin"]).copy()
    bt["score"] = (np.abs(spec.to_y(bt["actual_p"], row_offset(bt)) - bt["point_y"])
                   / bt["scale"])
    for col in ("lo80", "hi80", "lo95", "hi95"):
        bt[col] = np.nan
    for (_, _), grp in bt.groupby(["model", "horizon"]):
        uniq = sorted(grp["origin"].unique())
        for i, o in enumerate(uniq):
            if i < cfg.CONFORMAL_MIN_ORIGINS:
                continue
            qs = group_quantiles(grp.loc[grp["origin"] < o], spec.volume_edges)
            cur = grp.loc[grp["origin"] == o]
            for vg, cg in cur.groupby("volume_group"):
                q = qs[vg]
                for a, tag in ((0.80, "80"), (0.95, "95")):
                    lo, hi = spec.interval(cg["point_y"], q[a] * cg["scale"],
                                           row_offset(cg))
                    bt.loc[cg.index, f"lo{tag}"] = lo
                    bt.loc[cg.index, f"hi{tag}"] = hi
    return bt
