"""Weather processing (phase D3): daily plausibility checks, ISO-week aggregation and the
lagged weekly features used by dengue forecasting (D4). Pure functions, no I/O."""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

VARIABLES = ("temperature", "precipitation", "humidity")
#: Plausible daily values; anything outside is treated as missing and counted.
PLAUSIBLE = {"temperature": (-60.0, 60.0), "precipitation": (0.0, 500.0),
             "humidity": (0.0, 100.0)}
#: A week is kept only when all 7 days have all three variables.
DAYS_PER_WEEK = 7

#: Feature defaults (DENGUE_PLAN.md §2.4: dengue follows weather by roughly 1–3 months).
FEATURE_WINDOW = 4
FEATURE_LAGS = (4, 8, 12)


@dataclass
class DailyReport:
    days: int = 0
    missing: dict[str, int] = field(default_factory=dict)
    implausible: dict[str, int] = field(default_factory=dict)


def check_daily(daily: pd.DataFrame) -> tuple[pd.DataFrame, DailyReport]:
    """Blank implausible values (they become missing) and count both kinds of gap."""
    out = daily.copy()
    rep = DailyReport(days=len(out))
    for col, (lo, hi) in PLAUSIBLE.items():
        bad = out[col].notna() & ~out[col].between(lo, hi)
        rep.implausible[col] = int(bad.sum())
        out.loc[bad, col] = float("nan")
        rep.missing[col] = int(out[col].isna().sum())
    return out, rep


def to_weeks(daily: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Aggregate daily values to ISO weeks (Monday start): mean temperature, total
    precipitation, mean humidity. Returns (complete weeks, incomplete weeks dropped)."""
    if daily.empty:
        return pd.DataFrame(columns=["week_start", "iso_year", "iso_week", *VARIABLES]), 0
    d = daily.assign(
        week_start=daily["date"] - pd.to_timedelta(daily["date"].dt.weekday, unit="D"),
        complete=daily[list(VARIABLES)].notna().all(axis=1),
    )
    g = d.groupby("week_start").agg(
        complete=("complete", "sum"),
        temperature=("temperature", "mean"),
        precipitation=("precipitation", "sum"),
        humidity=("humidity", "mean"),
    )
    full = g[g["complete"] == DAYS_PER_WEEK].drop(columns="complete").reset_index()
    iso = full["week_start"].dt.isocalendar()
    full.insert(1, "iso_year", iso["year"].astype(int))
    full.insert(2, "iso_week", iso["week"].astype(int))
    return full, int(len(g) - len(full))


def lagged_features(weekly: pd.DataFrame, *, window: int = FEATURE_WINDOW,
                    lags: tuple[int, ...] = FEATURE_LAGS) -> pd.DataFrame:
    """Weather features for each (iso3, week_start): the `window`-week mean temperature,
    mean humidity and total precipitation ending `lag` weeks before the week.

    Weeks missing from the input are gaps (NaN), never interpolated; a window needs all
    of its weeks. Output columns: e.g. `temperature_mean4_lag8`, `precipitation_sum4_lag4`.
    """
    frames = []
    for iso3, g in weekly.groupby("iso3", sort=True):
        g = g.set_index("week_start").sort_index()
        cal = pd.date_range(g.index.min(), g.index.max(), freq="W-MON")
        g = g.reindex(cal)[list(VARIABLES)]
        roll = g.rolling(window, min_periods=window)
        base = pd.DataFrame({
            f"temperature_mean{window}": roll["temperature"].mean(),
            f"precipitation_sum{window}": roll["precipitation"].sum(),
            f"humidity_mean{window}": roll["humidity"].mean(),
        })
        out = pd.concat([base.shift(lag).add_suffix(f"_lag{lag}") for lag in lags], axis=1)
        out.insert(0, "iso3", iso3)
        frames.append(out.rename_axis("week_start").reset_index())
    if not frames:
        return pd.DataFrame(columns=["iso3", "week_start"])
    return pd.concat(frames, ignore_index=True)
