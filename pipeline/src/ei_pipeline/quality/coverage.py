"""Reporting-coverage analysis: reference week, provisional weeks and forecast tiers.

Shared by the FluNet profiler script and the ingestion job so both use identical rules.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

WINDOW_WEEKS = 260  # five years ending at the reference week
LOW_TEST_THRESHOLD = 10

TIERS = {
    "A": (
        "Forecast-ready: >=85% weeks reported, longest gap <=8 weeks, "
        "median >=30 tests/week, last report <=8 weeks old"
    ),
    "B": (
        "Forecast with caution: >=60% weeks reported, median >=10 tests/week, "
        "last report <=26 weeks old"
    ),
    "C": "Map and trends only: some data in the 5-year window",
    "D": "Historical only: no data in the 5-year window",
}


@dataclass
class CoverageResult:
    reference_week: pd.Timestamp
    provisional: pd.Series  # week_start -> number of reporting countries, after reference
    window: pd.DatetimeIndex
    profiles: pd.DataFrame  # one row per country


def reference_week(weekly: pd.DataFrame, share: float = 0.8) -> tuple[pd.Timestamp, pd.Series]:
    """Last week whose reporting count reaches `share` of the typical weekly count.

    Countries report with a delay, so the newest weeks look artificially empty. Weeks
    after the reference week are provisional. "Typical" is the median count over the
    year before the most recent 8 weeks (or all weeks, for short series).
    """
    counts = weekly[weekly["reported"]].groupby("week_start")["country_code"].nunique()
    if counts.empty:
        raise ValueError("No reported weeks in the data.")
    baseline = counts.iloc[-60:-8] if len(counts) >= 30 else counts
    complete = counts[counts >= share * baseline.median()]
    ref = complete.index.max()
    return ref, counts[counts.index > ref]


def longest_run(flags: pd.Series, value: bool) -> int:
    best = cur = 0
    for f in flags:
        cur = cur + 1 if f == value else 0
        best = max(best, cur)
    return best


def assign_tier(r: dict) -> str:
    if r["window_weeks_reported"] == 0:
        return "D"
    med = r["median_tests_per_week"] or 0
    since = r["weeks_since_last_report"]
    if (r["window_completeness"] >= 0.85 and r["window_longest_gap"] <= 8
            and med >= 30 and since <= 8):
        return "A"
    if r["window_completeness"] >= 0.60 and med >= 10 and since <= 26:
        return "B"
    return "C"


def profile_country(g: pd.DataFrame, window: pd.DatetimeIndex, latest: pd.Timestamp) -> dict:
    rep = g[g["reported"] & (g["week_start"] <= latest)]
    in_win = rep[rep["week_start"].isin(window)]
    flags = pd.Series(window.isin(in_win["week_start"]), index=window)

    row = {
        "country_code": g["country_code"].iat[0],
        "country_name": next(iter(g["country_name"].dropna()), ""),
        "who_region": g["who_region"].iat[0],
        "hemisphere": g["hemisphere"].iat[0],
        "transmission_zone": g["transmission_zone"].iat[0],
        "first_week": rep["week_start"].min(),
        "last_week": rep["week_start"].max(),
        "weeks_reported_all_time": len(rep),
        "window_weeks_reported": int(flags.sum()),
        "window_completeness": round(flags.mean(), 3),
        "window_longest_gap": longest_run(flags, False),
        "window_longest_run": longest_run(flags, True),
        "median_tests_per_week": in_win["specimens_tested"].median(),
        "share_low_test_weeks": round((in_win["specimens_tested"] < LOW_TEST_THRESHOLD).mean(), 3)
        if len(in_win) else None,
        "mean_positivity": round(in_win["positivity"].mean(), 3) if len(in_win) else None,
        "positives_in_window": in_win["positives"].sum(),
        "avg_weeks_per_year": round(flags.sum() / (len(window) / 52), 1),
    }
    row["weeks_since_last_report"] = (
        int((latest - row["last_week"]).days // 7) if pd.notna(row["last_week"]) else None
    )
    row["tier"] = assign_tier(row)
    return row


def analyse(weekly: pd.DataFrame, window_weeks: int = WINDOW_WEEKS) -> CoverageResult:
    ref, provisional = reference_week(weekly)
    window = pd.date_range(end=ref, periods=window_weeks, freq="W-MON")
    profiles = pd.DataFrame(
        profile_country(g, window, ref) for _, g in weekly.groupby("country_code")
    )
    return CoverageResult(ref, provisional, window, profiles)
