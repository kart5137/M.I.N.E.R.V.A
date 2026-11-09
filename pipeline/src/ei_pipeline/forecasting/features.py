"""Feature builder. Every feature for origin week t uses data from weeks ≤ t only.

One frame per horizon h: a row per (country, origin t) with features, the baseline
forecasts, and the target at t + h. Shifts are exact week offsets because the panel is
on a complete weekly calendar.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ei_db.catalog import FEATURE_LABELS  # noqa: F401  (re-exported for reports)
from ei_pipeline.detection.weights import neighbour_mean
from ei_pipeline.forecasting.data import Panel

AUTOREGRESSIVE = ["y_lag0", "y_lag1", "y_lag2", "y_lag3", "y_mean4", "y_std4", "y_mean8",
                  "y_std8", "y_diff1", "y_diff2", "y_diff4", "y_peak52"]
SEASONAL = ["y_last_year"]
CALENDAR = ["woy_sin", "woy_cos", "weeks_into_season"]
TESTING = ["log_tests_lag0", "tests_trend"]
SPATIAL = ["zone_mean_lag0", "nbr_mean_lag0", "nbr_diff2"]
STATIC = ["season_nh", "season_sh", "season_yr", "lat", "abs_lat"]
FEATURES = AUTOREGRESSIVE + SEASONAL + CALENDAR + TESTING + SPATIAL + STATIC

def _base(panel: Panel) -> pd.DataFrame:
    df = panel.weekly.sort_values(["iso3", "week_start"]).reset_index(drop=True)
    g = df.groupby("iso3", sort=False)
    y = g["y"]
    for k in range(4):
        df[f"y_lag{k}"] = y.shift(k)
    for w in (4, 8):
        roll = y.rolling(w, min_periods=2)
        df[f"y_mean{w}"] = roll.mean().reset_index(level=0, drop=True)
        df[f"y_std{w}"] = roll.std().reset_index(level=0, drop=True)
    for k in (1, 2, 4):
        df[f"y_diff{k}"] = df["y_lag0"] - y.shift(k)
    df["y_peak52"] = y.rolling(52, min_periods=8).max().reset_index(level=0, drop=True)

    # Testing volume at the origin (not a model feature): selects the conformal group.
    df["tests_mean4"] = (
        g["tests"].rolling(4, min_periods=1).mean().reset_index(level=0, drop=True)
    )

    log_tests = np.log1p(df["tests"])
    df["log_tests_lag0"] = log_tests
    t = g["tests"]
    recent = t.rolling(4, min_periods=2).mean().reset_index(level=0, drop=True)
    earlier = t.shift(4).rolling(8, min_periods=4).mean().reset_index(level=0, drop=True)
    df["tests_trend"] = np.log1p(recent) - np.log1p(earlier)

    # Leave-one-out mean positivity of the other countries in the transmission zone.
    meta = panel.countries.set_index("iso3")
    df["zone"] = df["iso3"].map(meta["transmission_zone"])
    zs = df.groupby(["zone", "week_start"])["y"].agg(["sum", "count"])
    joined = df.join(zs, on=["zone", "week_start"])
    own = df["y"].notna()
    loo_sum = joined["sum"] - df["y"].fillna(0)
    loo_n = joined["count"] - own.astype(int)
    df["zone_mean_lag0"] = (loo_sum / loo_n).where(loo_n > 0)

    # Neighbours (M6): mean logit positivity of the country's spatial neighbours among the
    # modelled countries (queen contiguity, else 4 nearest; detection/weights.py) at the
    # origin, and its 2-week change.
    if panel.neighbours is not None:
        idx = df.set_index(["iso3", "week_start"])
        nbr = neighbour_mean(idx, panel.neighbours, "y")
        df["nbr_mean_lag0"] = nbr.reindex(pd.MultiIndex.from_frame(
            df[["iso3", "week_start"]])).to_numpy()
        df["nbr_diff2"] = df["nbr_mean_lag0"] - df.groupby("iso3", sort=False)[
            "nbr_mean_lag0"].shift(2)
    else:
        df["nbr_mean_lag0"] = np.nan
        df["nbr_diff2"] = np.nan

    season = df["iso3"].map(meta["flu_season"])
    df["season_type"] = season
    for s in ("NH", "SH", "YR"):
        df[f"season_{s.lower()}"] = (season == s).astype(float)
    df["lat"] = df["iso3"].map(meta["lat"])
    df["abs_lat"] = df["lat"].abs()
    return df


def build_frames(panel: Panel, horizons) -> dict[int, pd.DataFrame]:
    """Feature frame per horizon. Columns: iso3, origin (= week t), target_week,
    FEATURES, baselines (`bl_*`, positivity scale), `actual_p`, `actual_y`, `trainable`."""
    base = _base(panel)
    g = base.groupby("iso3", sort=False)
    frames = {}
    for h in horizons:
        f = base[["iso3", "week_start", "season_type", "tests_mean4",
                  *[c for c in FEATURES if c in base]]].copy()
        f = f.rename(columns={"week_start": "origin"})
        f["target_week"] = f["origin"] + pd.Timedelta(weeks=h)

        # Same week last year (relative to the target week), mean of ±1 week. Needs
        # lags of 51-h .. 53-h, all ≥ 47 weeks, so always before the origin.
        last_year = pd.concat([g["y"].shift(52 - h + d) for d in (-1, 0, 1)], axis=1)
        f["y_last_year"] = last_year.mean(axis=1, skipna=True)

        iso_week = f["target_week"].dt.isocalendar().week.astype(float)
        f["woy_sin"] = np.sin(2 * np.pi * iso_week / 52.18)
        f["woy_cos"] = np.cos(2 * np.pi * iso_week / 52.18)
        f["weeks_into_season"] = np.where(f["season_type"] == "NH", (iso_week - 40) % 52,
                                          iso_week - 1)

        # Baselines on the observed-positivity scale.
        p = g["p"]
        f["bl_last_value"] = p.shift(0)
        f["bl_seasonal_naive"] = p.shift(52 - h)
        f["bl_moving_average_4"] = (
            p.rolling(4, min_periods=2).mean().reset_index(level=0, drop=True)
        )

        # Target
        f["actual_p"] = p.shift(-h)
        f["actual_y"] = g["y"].shift(-h)
        f["trainable"] = g["trainable"].shift(-h).astype("boolean").fillna(False).astype(bool)
        frames[h] = f
    return frames
