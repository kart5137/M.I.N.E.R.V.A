"""WHO FluNet: download, load and clean into one row per country per ISO week.

FluNet reports laboratory results (specimens tested, positives by subtype), not case
counts. See docs/datasets/flunet.md for the source description and the cleaning rules
implemented here.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from ei_pipeline.config import RAW_DIR
from ei_pipeline.util import MalformedExport, download_checked
from ei_pipeline.util import check_csv_structure as check_structure

__all__ = ["MalformedExport", "check_structure", "clean", "download", "load_raw"]

log = logging.getLogger(__name__)

FLUNET_URL = "https://xmart-api-public.who.int/FLUMART/VIW_FNT?$format=csv"
#: Request variants tried in order. WHO serves the export through a CDN that caches each
#: Accept-Encoding variant separately; in Nov 2026 the default `gzip, deflate` variant was
#: a stale, truncated copy while `identity` was current. Each download is checked and the
#: next variant is tried if the file is malformed.
DOWNLOAD_VARIANTS: tuple[dict[str, str], ...] = (
    {"Accept-Encoding": "identity"},
    {"Accept-Encoding": "identity", "Cache-Control": "no-cache"},
    {"Accept-Encoding": "gzip, deflate"},
)
RAW_PATH = RAW_DIR / "flunet" / "VIW_FNT.csv"

# FluNet reports the UK as four nations under non-ISO pseudo-codes.
UK_NATION_CODES = {"X09": "England", "X10": "Wales", "X11": "Northern Ireland", "X12": "Scotland"}

KEY = ["country_code", "iso_year", "iso_week"]
SURVEILLANCE_SOURCES = ("SENTINEL", "NONSENTINEL")

_RENAME = {
    "COUNTRY_CODE": "country_code",
    "COUNTRY_AREA_TERRITORY": "country_name",
    "WHOREGION": "who_region",
    "HEMISPHERE": "hemisphere",
    "FLUSEASON": "flu_season",
    "ITZ": "transmission_zone",
    "ISO_YEAR": "iso_year",
    "ISO_WEEK": "iso_week",
    "ISO_WEEKSTARTDATE": "week_start",
    "ORIGIN_SOURCE": "origin_source",
    "SPEC_PROCESSED_NB": "specimens_tested",
    "INF_ALL": "inf_all",
    "INF_A": "inf_a",
    "INF_B": "inf_b",
    "INF_NEGATIVE": "negatives",
}
_COUNTS = ["specimens_tested", "positives", "inf_a", "inf_b"]


@dataclass
class CleaningReport:
    """Counts of every cleaning action, so the profile can document them."""

    raw_rows: int = 0
    exact_duplicates_dropped: int = 0
    notdefined_rows_dropped: int = 0
    positives_from_a_plus_b: int = 0
    tests_from_pos_plus_neg: int = 0
    positives_exceed_tests: int = 0
    uk_nation_rows_aggregated: int = 0
    country_weeks: int = 0
    notes: list[str] = field(default_factory=list)


def download(dest: Path = RAW_PATH) -> Path:
    """Download the full FluNet table as CSV (~30 MB) and keep it only if it is complete.

    Tries each request variant in turn; the previous file at `dest` is replaced only by
    a well-formed download. Raises MalformedExport when no variant gives one."""
    return download_checked(FLUNET_URL, dest, DOWNLOAD_VARIANTS, label="FluNet")


def load_raw(path: Path = RAW_PATH) -> pd.DataFrame:
    return pd.read_csv(path, low_memory=False)


def clean(raw: pd.DataFrame) -> tuple[pd.DataFrame, CleaningReport]:
    """Return one row per (country_code, iso_year, iso_week) plus a cleaning report."""
    report = CleaningReport(raw_rows=len(raw))

    df = raw.drop_duplicates()
    report.exact_duplicates_dropped = len(raw) - len(df)

    df = df[list(_RENAME)].rename(columns=_RENAME)
    df["week_start"] = pd.to_datetime(df["week_start"])
    # Explicit numeric types: an all-empty column would otherwise be read as object.
    for col in ("specimens_tested", "inf_all", "inf_a", "inf_b", "negatives"):
        df[col] = pd.to_numeric(df[col], errors="coerce").astype("float64")
    df[["iso_year", "iso_week"]] = df[["iso_year", "iso_week"]].astype("int64")

    # Positives: INF_ALL when present, else INF_A + INF_B (identical wherever all exist).
    a_plus_b = df[["inf_a", "inf_b"]].sum(axis=1, min_count=1)
    filled = df["inf_all"].isna() & a_plus_b.notna()
    report.positives_from_a_plus_b = int(filled.sum())
    df["positives"] = df["inf_all"].fillna(a_plus_b)

    # Specimens tested: SPEC_PROCESSED_NB, else positives + negatives when both known.
    pos_plus_neg = df["positives"] + df["negatives"]
    filled = df["specimens_tested"].isna() & pos_plus_neg.notna()
    report.tests_from_pos_plus_neg = int(filled.sum())
    df["specimens_tested"] = df["specimens_tested"].fillna(pos_plus_neg)

    # Source overlap: NOTDEFINED rows can repeat SENTINEL/NONSENTINEL figures for the
    # same week. If a week has any surveillance-typed rows, drop its NOTDEFINED rows.
    has_typed = df["origin_source"].isin(SURVEILLANCE_SOURCES).groupby(
        [df[k] for k in KEY]
    ).transform("any")
    drop = has_typed & (df["origin_source"] == "NOTDEFINED")
    report.notdefined_rows_dropped = int(drop.sum())
    df = df[~drop]

    weekly = (
        df.groupby(KEY, as_index=False)
        .agg(
            country_name=("country_name", "first"),
            who_region=("who_region", "first"),
            hemisphere=("hemisphere", "first"),
            flu_season=("flu_season", "first"),
            transmission_zone=("transmission_zone", "first"),
            week_start=("week_start", "first"),
            **{c: (c, lambda s: s.sum(min_count=1)) for c in _COUNTS},
        )
    )

    weekly, report.uk_nation_rows_aggregated = _aggregate_uk(weekly)

    bad = weekly["positives"] > weekly["specimens_tested"]
    report.positives_exceed_tests = int(bad.sum())
    if report.positives_exceed_tests:
        report.notes.append(
            "Weeks with positives > specimens tested are kept but get no positivity value."
        )

    tested = weekly["specimens_tested"] > 0
    weekly["positivity"] = (weekly["positives"] / weekly["specimens_tested"]).where(
        tested & ~bad
    )
    weekly["reported"] = tested

    report.country_weeks = len(weekly)
    return weekly.sort_values(KEY).reset_index(drop=True), report


def _aggregate_uk(weekly: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Sum the four UK nations into GBR for weeks where GBR itself is absent."""
    nations = weekly[weekly["country_code"].isin(UK_NATION_CODES)]
    if nations.empty:
        return weekly, 0
    rest = weekly[~weekly["country_code"].isin(UK_NATION_CODES)]
    gbr_weeks = set(map(tuple, rest.loc[rest["country_code"] == "GBR", KEY[1:]].values))

    uk = (
        nations.groupby(["iso_year", "iso_week"], as_index=False)
        .agg(
            who_region=("who_region", "first"),
            hemisphere=("hemisphere", "first"),
            flu_season=("flu_season", "first"),
            transmission_zone=("transmission_zone", "first"),
            week_start=("week_start", "first"),
            **{c: (c, lambda s: s.sum(min_count=1)) for c in _COUNTS},
        )
        .assign(country_code="GBR", country_name="United Kingdom")
    )
    uk = uk[[(y, w) not in gbr_weeks for y, w in zip(uk["iso_year"], uk["iso_week"], strict=False)]]
    return pd.concat([rest, uk], ignore_index=True), len(nations)
