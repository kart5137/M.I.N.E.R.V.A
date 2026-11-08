"""Profile WHO FluNet coverage per country and decide which countries can be forecast.

Usage (from the repo root):
    .venv/Scripts/python pipeline/scripts/profile_flunet.py [--download]

Outputs:
    data/profiles/flunet_country_profile.csv   one row per country
    docs/datasets/flunet_profile.md            generated report
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipeline" / "src"))

from ei_pipeline.sources import flunet  # noqa: E402

RAW_PATH = ROOT / "data" / "raw" / "flunet" / "VIW_FNT.csv"
PROFILE_CSV = ROOT / "data" / "profiles" / "flunet_country_profile.csv"
REPORT_MD = ROOT / "docs" / "datasets" / "flunet_profile.md"

WINDOW_WEEKS = 260  # five years of history ending at the latest week in the data
LOW_TEST_THRESHOLD = 10

# Tier rules. They are deliberately simple and are documented in the report.
TIERS = {
    "A": "Forecast-ready: >=85% weeks reported, longest gap <=8 weeks, median >=30 tests/week, last report <=8 weeks old",
    "B": "Forecast with caution: >=60% weeks reported, median >=10 tests/week, last report <=26 weeks old",
    "C": "Map and trends only: some data in the 5-year window",
    "D": "Historical only: no data in the 5-year window",
}


def reference_week(weekly: pd.DataFrame, share: float = 0.8) -> tuple[pd.Timestamp, pd.Series]:
    """Last week whose reporting count reaches `share` of the typical weekly count.

    Countries report with a delay, so the newest weeks look artificially empty. Weeks
    after the reference week are treated as provisional and excluded from the window.
    """
    counts = weekly[weekly["reported"]].groupby("week_start")["country_code"].nunique()
    typical = counts.iloc[-60:-8].median()
    complete = counts[counts >= share * typical]
    ref = complete.index.max()
    return ref, counts[counts.index > ref]


def longest_run(flags: pd.Series, value: bool) -> int:
    best = cur = 0
    for f in flags:
        cur = cur + 1 if f == value else 0
        best = max(best, cur)
    return best


def profile_country(g: pd.DataFrame, window: pd.DatetimeIndex, latest: pd.Timestamp) -> dict:
    rep = g[g["reported"]]
    in_win = rep[rep["week_start"].isin(window)]
    flags = pd.Series(window.isin(in_win["week_start"]), index=window)

    row = {
        "country_code": g["country_code"].iat[0],
        "country_name": g["country_name"].dropna().iat[0] if g["country_name"].notna().any() else "",
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
        "avg_weeks_per_year": round(flags.sum() / (WINDOW_WEEKS / 52), 1),
    }
    row["weeks_since_last_report"] = (
        int((latest - row["last_week"]).days // 7) if pd.notna(row["last_week"]) else None
    )
    row["tier"] = assign_tier(row)
    return row


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


def md_table(df: pd.DataFrame) -> str:
    cols = list(df.columns)
    lines = ["| " + " | ".join(map(str, cols)) + " |", "|" + "---|" * len(cols)]
    for r in df.itertuples(index=False):
        lines.append("| " + " | ".join("" if pd.isna(v) else str(v) for v in r) + " |")
    return "\n".join(lines)


def build_report(weekly: pd.DataFrame, prof: pd.DataFrame, rep: flunet.CleaningReport,
                 window: pd.DatetimeIndex, latest: pd.Timestamp,
                 provisional: pd.Series) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    tier_counts = prof["tier"].value_counts().reindex(list(TIERS), fill_value=0)

    by_region = (
        prof.pivot_table(index="who_region", columns="tier", values="country_code",
                         aggfunc="count", fill_value=0)
        .reindex(columns=list(TIERS), fill_value=0)
        .assign(Total=lambda d: d.sum(axis=1))
        .reset_index()
        .rename(columns={"who_region": "WHO region"})
    )

    per_year = (
        weekly[weekly["reported"]].groupby("iso_year")
        .agg(countries=("country_code", "nunique"),
             specimens=("specimens_tested", "sum"),
             positives=("positives", "sum"))
        .reset_index()
    )
    per_year["positivity"] = (per_year["positives"] / per_year["specimens"]).round(3)
    int_cols = ["iso_year", "countries", "specimens", "positives"]
    per_year[int_cols] = per_year[int_cols].astype("int64")

    show = ["country_code", "country_name", "who_region", "window_completeness",
            "window_longest_gap", "median_tests_per_week", "weeks_since_last_report"]

    def tier_table(t: str) -> str:
        sub = prof[prof["tier"] == t].sort_values(["who_region", "country_name"])[show]
        return md_table(sub) if len(sub) else "_None._"

    near_miss = prof[(prof["tier"] == "B")].sort_values("window_completeness", ascending=False)

    return f"""# FluNet coverage profile (generated)

> Generated by `pipeline/scripts/profile_flunet.py` on {now}. Do not edit by hand;
> re-run the script. Source description and caveats: [flunet.md](flunet.md).

## Snapshot

- Raw rows: **{rep.raw_rows:,}** → cleaned country-weeks: **{rep.country_weeks:,}**
- Countries/areas (after merging UK nations into GBR): **{prof['country_code'].nunique()}**
- Years covered: **{int(weekly['iso_year'].min())}–{int(weekly['iso_year'].max())}**
- Reference week (last week with near-complete reporting): **{latest.date()}**
- Provisional weeks after it (still being reported, excluded from the window):
  {", ".join(f"{d.date()} ({n} countries)" for d, n in provisional.items()) or "none"}
- Profiling window: **{window[0].date()} → {window[-1].date()}** ({WINDOW_WEEKS} ISO weeks)
- A "reported week" means specimens tested > 0.

## Forecast-readiness tiers

| Tier | Countries | Rule |
|---|---|---|
""" + "\n".join(f"| {t} | {tier_counts[t]} | {TIERS[t]} |" for t in TIERS) + f"""

### By WHO region

{md_table(by_region)}

## Cleaning actions

| Action | Rows |
|---|---|
| Exact duplicate rows dropped | {rep.exact_duplicates_dropped:,} |
| `NOTDEFINED` rows dropped where sentinel/non-sentinel rows exist for the same week | {rep.notdefined_rows_dropped:,} |
| Positives filled from INF_A + INF_B (INF_ALL missing) | {rep.positives_from_a_plus_b:,} |
| Specimens tested filled from positives + negatives | {rep.tests_from_pos_plus_neg:,} |
| UK nation rows (X09–X12) aggregated into GBR | {rep.uk_nation_rows_aggregated:,} |
| Country-weeks with positives > specimens tested (positivity left empty) | {rep.positives_exceed_tests:,} |

## Reporting over time

{md_table(per_year)}

## Tier A — forecast-ready

{tier_table("A")}

## Tier B — forecast with caution

{tier_table("B")}

## Tier C — map and trends only

{tier_table("C")}

## Tier D — historical only

{tier_table("D")}
"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--download", action="store_true", help="re-download the FluNet CSV first")
    args = ap.parse_args()

    if args.download or not RAW_PATH.exists():
        print(f"Downloading FluNet → {RAW_PATH}")
        flunet.download(RAW_PATH)

    weekly, rep = flunet.clean(flunet.load_raw(RAW_PATH))

    latest, provisional = reference_week(weekly)
    window = pd.date_range(end=latest, periods=WINDOW_WEEKS, freq="W-MON")

    prof = pd.DataFrame(
        profile_country(g, window, latest) for _, g in weekly.groupby("country_code")
    )

    PROFILE_CSV.parent.mkdir(parents=True, exist_ok=True)
    prof.to_csv(PROFILE_CSV, index=False)
    REPORT_MD.parent.mkdir(parents=True, exist_ok=True)
    REPORT_MD.write_text(build_report(weekly, prof, rep, window, latest, provisional),
                         encoding="utf-8")

    print(prof["tier"].value_counts().sort_index().to_string())
    print(f"Wrote {PROFILE_CSV.relative_to(ROOT)} and {REPORT_MD.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
