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
    return _reference(counts, share, recent=8, span=52)


def _reference(counts: pd.Series, share: float, *, recent: int,
               span: int) -> tuple[pd.Timestamp, pd.Series]:
    """Last period whose reporting count reaches `share` of the median count over the
    `span` periods before the most recent `recent` ones (all periods for short series)."""
    if counts.empty:
        raise ValueError("No reported periods in the data.")
    baseline = counts.iloc[-(span + recent):-recent] if len(counts) >= 30 else counts
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


# ---------------------------------------------------------------------------- dengue
#
# Dengue reports are case counts at a weekly or monthly grain (docs/datasets/dengue.md).
# There is no test denominator, so tiers use completeness and recency only. Each country
# is profiled in the grain of its most recent report ("primary grain"); a country that
# moved from weekly to monthly reporting is a monthly reporter now.

DENGUE_WINDOW_WEEKS = 156   # three years: WHO's global system mostly starts in 2024
DENGUE_WINDOW_MONTHS = 36
#: A/B need cases in at least half the reported weeks: mostly-zero series (sporadic or
#: imported cases only, e.g. Canada) cannot support a meaningful forecast.
DENGUE_MAX_ZERO_SHARE = 0.5

DENGUE_TIERS = {
    "A": "Forecast-ready (weekly): >=85% weeks reported, longest gap <=8 weeks, "
         "last report <=8 weeks old, cases in >=50% of reported weeks",
    "B": "Forecast with caution (weekly): >=60% weeks reported, last report <=26 weeks old, "
         "cases in >=50% of reported weeks",
    "C": "Map and trends only: some data in the 3-year window (all monthly reporters and "
         "mostly-zero weekly series)",
    "D": "Historical only: no data in the 3-year window",
}


@dataclass
class DengueCoverage:
    reference_week: pd.Timestamp
    reference_month: pd.Timestamp | None
    provisional_weeks: pd.Series   # week_start -> reporting countries after the reference
    provisional_months: pd.Series
    profiles: pd.DataFrame         # one row per country


def dengue_reference(weekly: pd.DataFrame, monthly: pd.DataFrame, share: float = 0.8):
    wcounts = weekly.groupby("week_start")["country_code"].nunique()
    ref_w, prov_w = _reference(wcounts, share, recent=8, span=52)
    if monthly.empty:
        return ref_w, prov_w, None, pd.Series(dtype="int64")
    mcounts = monthly.groupby("month_start")["country_code"].nunique()
    ref_m, prov_m = _reference(mcounts, share, recent=2, span=12)
    return ref_w, prov_w, ref_m, prov_m


def assign_dengue_tier(grain: str, completeness: float, gap: int, since: int | None,
                       reported_in_window: int, zero_share: float | None = 0.0) -> str:
    if reported_in_window == 0:
        return "D"
    enough_cases = zero_share is not None and zero_share <= DENGUE_MAX_ZERO_SHARE
    if grain == "week" and since is not None and enough_cases:
        if completeness >= 0.85 and gap <= 8 and since <= 8:
            return "A"
        if completeness >= 0.60 and since <= 26:
            return "B"
    return "C"


def _profile_dengue(code: str, w: pd.DataFrame, m: pd.DataFrame, ref_w: pd.Timestamp,
                    ref_m: pd.Timestamp | None) -> dict:
    w = w[w["week_start"] <= ref_w]
    m = m[m["month_start"] <= ref_m] if ref_m is not None else m.iloc[0:0]
    last_w_end = w["week_start"].max() + pd.Timedelta(days=6) if len(w) else None
    last_m_end = m["month_start"].max() + pd.offsets.MonthEnd(0) if len(m) else None
    grain = "month" if last_w_end is None or (
        last_m_end is not None and last_m_end > last_w_end) else "week"

    if grain == "week":
        window = pd.date_range(end=ref_w, periods=DENGUE_WINDOW_WEEKS, freq="W-MON")
        series, col, last_end = w, "week_start", last_w_end
    else:
        window = pd.date_range(end=ref_m, periods=DENGUE_WINDOW_MONTHS, freq="MS")
        series, col, last_end = m, "month_start", last_m_end
    flags = pd.Series(window.isin(series[col]), index=window)
    in_win = series[series[col].isin(window)]
    since = None if last_end is None else max(0, int((ref_w - last_end).days // 7))
    any_rows = pd.concat([w, m])
    row = {
        "country_code": code,
        "country_name": next(iter(any_rows["country_name"].dropna()), code),
        "who_region": next(iter(any_rows["who_region"].dropna()), None),
        "grain": grain,
        "has_weekly": bool(len(w)),
        "has_monthly": bool(len(m)),
        "first_period": series[col].min(),
        "last_period": series[col].max(),
        "periods_reported_all_time": len(series),
        "window_periods_reported": int(flags.sum()),
        "window_completeness": round(float(flags.mean()), 3),
        "window_longest_gap": longest_run(flags, False),
        "weeks_since_last_report": since,
        "median_cases": in_win["cases"].median() if len(in_win) else None,
        "share_zero_case_periods": round(float((in_win["cases"] == 0).mean()), 3)
        if len(in_win) else None,
        "cases_in_window": float(in_win["cases"].sum()),
    }
    row["tier"] = assign_dengue_tier(grain, row["window_completeness"],
                                     row["window_longest_gap"], since,
                                     row["window_periods_reported"],
                                     row["share_zero_case_periods"])
    return row


def analyse_dengue(weekly: pd.DataFrame, monthly: pd.DataFrame) -> DengueCoverage:
    ref_w, prov_w, ref_m, prov_m = dengue_reference(weekly, monthly)
    codes = sorted(set(weekly["country_code"]) | set(monthly["country_code"]))
    wg = dict(tuple(weekly.groupby("country_code")))
    mg = dict(tuple(monthly.groupby("country_code")))
    profiles = pd.DataFrame(
        _profile_dengue(c, wg.get(c, weekly.iloc[0:0]), mg.get(c, monthly.iloc[0:0]),
                        ref_w, ref_m)
        for c in codes
    )
    return DengueCoverage(ref_w, ref_m, prov_w, prov_m, profiles)
