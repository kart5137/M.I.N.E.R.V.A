"""WHO Global Dengue Surveillance: download, load and clean into weekly and monthly rows.

Countries report dengue *cases* under their own case definitions (suspected, probable or
confirmed), at one of three grains: CDC/PAHO epidemiological weeks (Sunday start), ISO
weeks (Monday start) or calendar months. See docs/datasets/dengue.md for the source and
docs/datasets/dengue_profile.md for the measured quality issues these rules handle.

Rules (each counted in the CleaningReport):
* A missing START_DATE is rebuilt from YEAR and DATE_NUM for its grain.
* Epi-weeks are mapped to the ISO week that contains them (start + 1 day), so dengue
  and influenza share Monday weeks. Monthly rows stay monthly: never split into weeks.
* A row without a case value is not a report and is dropped (most are empty future
  placeholders). Negative *case* values are left for validation to exclude; negative
  confirmed/severe/death values are cleared individually.
* If the same country has an epi-week and an ISO week for the same Monday, the ISO week
  (the country's own grain choice for that period) is kept.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from ei_pipeline.config import RAW_DIR
from ei_pipeline.util import download_checked

log = logging.getLogger(__name__)

DENGUE_URL = "https://xmart-api-public.who.int/ARBOV/V_DENGUE_GLOBAL_VALIDATED_PUBLIC?$format=csv"
#: Same CDN behaviour as FluNet (both are WHO xMart exports): try identity first.
DOWNLOAD_VARIANTS: tuple[dict[str, str], ...] = (
    {"Accept-Encoding": "identity"},
    {"Accept-Encoding": "identity", "Cache-Control": "no-cache"},
    {"Accept-Encoding": "gzip, deflate"},
)
RAW_PATH = RAW_DIR / "dengue" / "V_DENGUE_GLOBAL_VALIDATED_PUBLIC.csv"

WEEKLY_TYPES = ("epiweek", "isoweek")
MONTHLY_TYPE = "month"
EXTRA_COUNTS = ("confirmed", "severe", "deaths")
SEROTYPES = ("SERO_1", "SERO_2", "SERO_3", "SERO_4")

_RENAME = {
    "ISO3": "country_code",
    "COUNTRY": "country_name",
    "WHO_REGION": "who_region",
    "YEAR": "year",
    "DATE_NUM": "period_num",
    "START_DATE": "start",
    "DATE_TYPE": "date_type",
    "CASES": "cases",
    "CONFIRMED_CASES": "confirmed",
    "SEVERE_CASES": "severe",
    "DEATHS": "deaths",
}


@dataclass
class CleaningReport:
    """Counts of every cleaning action, so the profile can document them."""

    raw_rows: int = 0
    exact_duplicates_dropped: int = 0
    unknown_date_type_dropped: int = 0
    start_date_rebuilt: int = 0
    start_date_unrecoverable: int = 0
    period_label_mismatch: int = 0
    no_case_value_dropped: int = 0
    no_case_value_future_placeholders: int = 0
    negative_extra_values_cleared: dict[str, int] = field(default_factory=dict)
    epiweeks_mapped_to_iso: int = 0
    overlapping_epi_iso_weeks_dropped: int = 0
    weekly_rows: int = 0
    monthly_rows: int = 0
    notes: list[str] = field(default_factory=list)


@dataclass
class Cleaned:
    weekly: pd.DataFrame   # one row per (country_code, week_start), Monday weeks
    monthly: pd.DataFrame  # one row per (country_code, month_start)
    report: CleaningReport


def download(dest: Path = RAW_PATH) -> Path:
    """Download the full WHO dengue table as CSV (~3 MB) and keep it only if complete."""
    return download_checked(DENGUE_URL, dest, DOWNLOAD_VARIANTS, label="WHO dengue")


def load_raw(path: Path = RAW_PATH) -> pd.DataFrame:
    return pd.read_csv(path, low_memory=False, encoding="utf-8")


def epiweek_start(year: int, week: int) -> date:
    """Sunday starting CDC/PAHO epidemiological week `week` of `year`. Week 1 is the
    Sunday-to-Saturday week containing 4 January (at least four days in the year)."""
    jan4 = date(year, 1, 4)
    first = jan4 - timedelta(days=(jan4.weekday() + 1) % 7)
    return first + timedelta(weeks=week - 1)


def _period_start(date_type: str, year: int, num: int) -> date | None:
    try:
        if date_type == MONTHLY_TYPE:
            return date(year, num, 1)
        if date_type == "isoweek":
            return date.fromisocalendar(year, num, 1)
        if date_type == "epiweek":
            return epiweek_start(year, num)
    except ValueError:
        return None
    return None


def _breakdown(df: pd.DataFrame) -> pd.Series:
    """JSON with confirmed/severe/deaths and the serotypes reported as circulating."""
    sero = df[list(SEROTYPES)].apply(
        lambda s: s.astype(str).str.upper().map({"TRUE": True, "FALSE": False})
    )

    def one(i: int) -> str | None:
        d: dict = {k: float(df[k].iat[i]) for k in EXTRA_COUNTS if pd.notna(df[k].iat[i])}
        flags = sero.iloc[i]
        if flags.notna().any():
            d["serotypes"] = [n + 1 for n, f in enumerate(flags) if f is True]
        return json.dumps(d, sort_keys=True) if d else None

    return pd.Series([one(i) for i in range(len(df))], index=df.index, dtype=object)


def clean(raw: pd.DataFrame, today: date | None = None) -> Cleaned:
    today_ts = pd.Timestamp(today or date.today())
    report = CleaningReport(raw_rows=len(raw))

    df = raw.drop_duplicates()
    report.exact_duplicates_dropped = len(raw) - len(df)
    df = df.rename(columns=_RENAME)

    known = df["date_type"].isin((*WEEKLY_TYPES, MONTHLY_TYPE))
    report.unknown_date_type_dropped = int((~known).sum())
    df = df[known].copy()

    for col in ("cases", *EXTRA_COUNTS):
        df[col] = pd.to_numeric(df[col], errors="coerce").astype("float64")
    df["year"] = pd.to_numeric(df["year"], errors="coerce").astype("Int64")
    df["period_num"] = pd.to_numeric(df["period_num"], errors="coerce").astype("Int64")

    # Start date: as published, else rebuilt from the period label.
    df["start"] = pd.to_datetime(df["start"], errors="coerce")
    labelled = [
        _period_start(t, int(y), int(n)) if pd.notna(y) and pd.notna(n) else None
        for t, y, n in zip(df["date_type"], df["year"], df["period_num"], strict=True)
    ]
    from_label = pd.to_datetime(pd.Series(labelled, index=df.index, dtype=object))
    missing = df["start"].isna()
    report.start_date_rebuilt = int((missing & from_label.notna()).sum())
    report.period_label_mismatch = int(
        (df["start"].notna() & from_label.notna() & (df["start"] != from_label)).sum()
    )
    df["start"] = df["start"].fillna(from_label)
    report.start_date_unrecoverable = int(df["start"].isna().sum())
    df = df[df["start"].notna()]
    if report.period_label_mismatch:
        report.notes.append("START_DATE disagrees with YEAR/DATE_NUM for some rows; "
                            "START_DATE is used.")

    # A row without a case value is not a report.
    no_value = df["cases"].isna()
    report.no_case_value_dropped = int(no_value.sum())
    report.no_case_value_future_placeholders = int((no_value & (df["start"] > today_ts)).sum())
    df = df[~no_value].copy()

    for col in EXTRA_COUNTS:
        neg = df[col] < 0
        report.negative_extra_values_cleared[col] = int(neg.sum())
        df.loc[neg, col] = float("nan")

    df["breakdown"] = _breakdown(df)

    # ---- weekly
    wk = df[df["date_type"].isin(WEEKLY_TYPES)].copy()
    epi = wk["date_type"] == "epiweek"
    report.epiweeks_mapped_to_iso = int(epi.sum())
    wk["week_start"] = wk["start"] + pd.to_timedelta(epi.astype(int), unit="D")
    iso = wk["week_start"].dt.isocalendar()
    wk["iso_year"] = iso["year"].astype("int64")
    wk["iso_week"] = iso["week"].astype("int64")
    # Prefer the ISO-week row when a country has both grains for the same Monday.
    wk = wk.sort_values(["country_code", "week_start", "date_type"],
                        ascending=[True, True, False])  # "isoweek" sorts before "epiweek"
    dup = (wk.duplicated(["country_code", "week_start"], keep="first")
           & (wk["date_type"] == "epiweek"))
    report.overlapping_epi_iso_weeks_dropped = int(dup.sum())
    wk = wk[~dup]
    wk["reported"] = True
    weekly = wk[["country_code", "country_name", "who_region", "week_start", "iso_year",
                 "iso_week", "date_type", "cases", *EXTRA_COUNTS, "breakdown", "reported"]]

    # ---- monthly
    mo = df[df["date_type"] == MONTHLY_TYPE].copy()
    mo["month_start"] = mo["start"]
    mo["reported"] = True
    monthly = mo[["country_code", "country_name", "who_region", "month_start", "cases",
                  *EXTRA_COUNTS, "breakdown", "reported"]]

    report.weekly_rows, report.monthly_rows = len(weekly), len(monthly)
    return Cleaned(
        weekly.sort_values(["country_code", "week_start"]).reset_index(drop=True),
        monthly.sort_values(["country_code", "month_start"]).reset_index(drop=True),
        report,
    )


def soft_checks(df: pd.DataFrame) -> dict[str, pd.Series]:
    """Plausibility warnings (counted, not excluded). Case definitions differ between
    countries, so e.g. confirmed > reported cases can be legitimate bookkeeping."""
    return {
        "confirmed_exceed_cases": df["confirmed"] > df["cases"],
        "deaths_exceed_cases": df["deaths"] > df["cases"],
        "zero_case_periods": df["cases"] == 0,
    }
