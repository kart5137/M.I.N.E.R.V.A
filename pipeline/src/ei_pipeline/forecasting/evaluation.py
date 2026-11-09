"""Backtest metrics and model selection.

Errors are on the positivity scale (0–1). All models are scored on the same rows.
- MASE: |error| ÷ the country's in-sample seasonal-naive MAE (weeks before the backtest).
- Skill vs seasonal-naive: 1 − MAE(model) / MAE(seasonal-naive) on the same rows.
- Coverage: share of actuals inside the 80% / 95% interval (rows with an interval).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from ei_pipeline.forecasting import config as cfg

METRICS = ("mae", "rmse", "mase", "skill_vs_snaive", "coverage_80", "coverage_95")


def mase_scales(weekly: pd.DataFrame) -> pd.Series:
    """Per-country seasonal-naive MAE on training history (before the backtest)."""
    df = weekly.sort_values(["iso3", "week_start"])
    usable = df["p"].where(df["trainable"])
    prev_year = usable.groupby(df["iso3"]).shift(52)
    in_sample = df["week_start"].between(pd.Timestamp(cfg.TRAIN_START),
                                         pd.Timestamp(cfg.BACKTEST_START) - pd.Timedelta(days=1))
    err = (usable - prev_year).abs().where(in_sample)
    scale = err.groupby(df["iso3"]).mean()
    return scale[scale > 0]


def _metrics(g: pd.DataFrame, snaive_mae: float | None) -> dict[str, float | None]:
    e = g["point"] - g["actual_p"]
    mae = float(e.abs().mean())
    with_scale = g.dropna(subset=["mase_scale"])
    covered = g.dropna(subset=["lo80"])
    return {
        "mae": mae,
        "rmse": float(np.sqrt((e ** 2).mean())),
        "mase": float(((with_scale["point"] - with_scale["actual_p"]).abs()
                       / with_scale["mase_scale"]).mean()) if len(with_scale) else None,
        "skill_vs_snaive": (1 - mae / snaive_mae) if snaive_mae else None,
        "coverage_80": float(covered["actual_p"].between(covered["lo80"], covered["hi80"]).mean())
        if len(covered) else None,
        "coverage_95": float(covered["actual_p"].between(covered["lo95"], covered["hi95"]).mean())
        if len(covered) else None,
    }


def evaluate(bt: pd.DataFrame, scales: pd.Series) -> pd.DataFrame:
    """Rows: model, horizon, iso3 (None = pooled), metric, value, n_obs, n_origins,
    eval_start, eval_end."""
    bt = bt.assign(mase_scale=bt["iso3"].map(scales))
    records = []
    for h, hb in bt.groupby("horizon"):
        sn = hb[hb["model"] == cfg.REFERENCE_BASELINE]
        sn_pooled = (sn["point"] - sn["actual_p"]).abs().mean()
        sn_country = (sn["point"] - sn["actual_p"]).abs().groupby(sn["iso3"]).mean()
        for model, mb in hb.groupby("model"):
            groups = [(None, mb, sn_pooled)] + [
                (iso3, cb, sn_country.get(iso3)) for iso3, cb in mb.groupby("iso3")]
            for iso3, g, sn_mae in groups:
                for metric, value in _metrics(g, sn_mae).items():
                    records.append({
                        "model": model, "horizon": h, "iso3": iso3, "metric": metric,
                        "value": None if value is None or not np.isfinite(value) else value,
                        "n_obs": len(g), "n_origins": g["origin"].nunique(),
                        "eval_start": g["origin"].min().date(),
                        "eval_end": g["origin"].max().date(),
                    })
    return pd.DataFrame.from_records(records)


@dataclass(frozen=True)
class Selection:
    horizon: int
    active: str
    note: str


def select(evals: pd.DataFrame) -> dict[int, Selection]:
    """Per horizon: lowest pooled MASE; a model other than seasonal-naive is active only
    if it also beats seasonal-naive (positive skill)."""
    pooled = evals[evals["iso3"].isna()].pivot_table(
        index=["horizon", "model"], columns="metric", values="value")
    out = {}
    for h in sorted(pooled.index.get_level_values(0).unique()):
        m = pooled.loc[h].dropna(subset=["mase"]).sort_values("mase")
        best = m.index[0]
        sn_mase = m.loc[cfg.REFERENCE_BASELINE, "mase"]
        if best != cfg.REFERENCE_BASELINE and m.loc[best, "skill_vs_snaive"] > 0:
            note = (f"Lowest backtest MASE ({m.loc[best, 'mase']:.3f} vs seasonal-naive "
                    f"{sn_mase:.3f}); skill vs seasonal-naive "
                    f"{m.loc[best, 'skill_vs_snaive']:+.1%}.")
            baselines = m.loc[m.index.isin(cfg.BASELINES)]
            if best not in cfg.BASELINES and len(baselines):
                strongest = baselines["mae"].idxmin()
                gain = 1 - m.loc[best, "mae"] / baselines.loc[strongest, "mae"]
                note += (f" Against the strongest baseline ({strongest.replace('_', ' ')}) "
                         f"the MAE is {gain:.1%} lower.")
            out[h] = Selection(h, best, note)
        else:
            out[h] = Selection(h, cfg.REFERENCE_BASELINE,
                               "No model beat seasonal-naive on backtest MASE; the baseline "
                               "stays active.")
    return out
