"""WHO COVID-19 dashboard: weekly new cases and deaths by country since January 2020 (C3).

WHO publishes the dashboard data as public CSV files (data.who.int, "WHO COVID-19
dashboard"). The weekly file has one row per country and week: Date_reported,
Country_code (ISO 3166-1 alpha-2), Country, WHO_region, New_cases, Cumulative_cases,
New_deaths, Cumulative_deaths. Verified 2026-11-11 (docs/datasets/covid19.md): 85,200
rows, 240 areas, 2020-01-05 to 2026-10-18.

Cleaning (counted in the run report):

- Dates: every Date_reported is a Sunday and the value is the total reported to WHO from
  the Monday six days earlier to that Sunday (checked against WHO's daily file), so the
  row belongs to the ISO week starting that Monday.
- Country codes are ISO2. They map to ISO3 through the countries table, plus WHO codes
  for territories our reference data lists without ISO2 (OVERRIDES). Rows for
  "international conveyances" (cruise ships, WHO_region OTHER) are dropped: they are not
  countries.
- An empty value is "not reported" (unknown, not zero). Rows with neither cases nor
  deaths are dropped. Negative values (WHO's downward corrections, a few dozen) are
  removed from that week, leaving it unknown, because a week cannot have negative cases.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from ei_pipeline.config import RAW_DIR
from ei_pipeline.util import download as _download

WEEKLY_URL = "https://srhdpeuwpubsa.blob.core.windows.net/whdh/COVID/WHO-COVID-19-global-data.csv"
RAW_PATH = RAW_DIR / "covid" / "WHO-COVID-19-global-data.csv"
REQUIRED = ("Date_reported", "Country_code", "Country", "WHO_region", "New_cases",
            "New_deaths")
WHO_REGIONS = {"AFRO": "AFR", "AMRO": "AMR", "EMRO": "EMR", "EURO": "EUR",
               "SEARO": "SEAR", "WPRO": "WPR"}
#: WHO codes for areas whose reference row has no ISO2 (or a different one).
OVERRIDES = {"BQ": "BES", "GF": "GUF", "GI": "GIB", "GP": "GLP", "MQ": "MTQ",
             "RE": "REU", "TK": "TKL", "YT": "MYT"}
#: Names used when an area is new to the countries table (WHO's file garbles "Réunion").
NAMES = {"REU": "Réunion"}
#: "International conveyance (…)" and "International commercial vessel".
CONVEYANCE_REGION = "OTHER"


@dataclass
class CleanReport:
    rows: int = 0
    not_sunday: int = 0
    dropped_conveyance: int = 0
    dropped_empty: int = 0
    negative_values_removed: int = 0
    unknown_codes: list[str] = field(default_factory=list)
    dropped_unknown_code: int = 0


def download(dest: Path = RAW_PATH) -> Path:
    return _download(WEEKLY_URL, dest, timeout=180)


def load(path: Path = RAW_PATH) -> pd.DataFrame:
    # keep_default_na=False: "NA" is Namibia's code, not a missing value.
    df = pd.read_csv(path, keep_default_na=False, na_values=[""], dtype={"Country_code": str})
    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        raise ValueError(f"{path.name}: missing columns {missing}")
    return df


def clean(raw: pd.DataFrame, iso2_to_iso3: dict[str, str]) -> tuple[pd.DataFrame, CleanReport]:
    """Rows as iso3, name, who_region, week_start (ISO Monday), iso_year, iso_week, cases,
    deaths. `iso2_to_iso3` comes from the countries table."""
    rep = CleanReport(rows=len(raw))
    df = raw.copy()
    df["code"] = df["Country_code"].astype(str).str.strip().str.upper()
    df["date"] = pd.to_datetime(df["Date_reported"], errors="coerce")
    df["cases"] = pd.to_numeric(df["New_cases"], errors="coerce")
    df["deaths"] = pd.to_numeric(df["New_deaths"], errors="coerce")

    conveyance = df["WHO_region"].astype(str).str.upper() == CONVEYANCE_REGION
    rep.dropped_conveyance = int(conveyance.sum())
    df = df[~conveyance]

    for col in ("cases", "deaths"):
        neg = df[col] < 0
        rep.negative_values_removed += int(neg.sum())
        df.loc[neg, col] = float("nan")
    empty = df["date"].isna() | (df["cases"].isna() & df["deaths"].isna())
    rep.dropped_empty = int(empty.sum())
    df = df[~empty].copy()

    mapping = {**iso2_to_iso3, **OVERRIDES}
    df["iso3"] = df["code"].map(mapping)
    unknown = df["iso3"].isna()
    rep.unknown_codes = sorted(set(df.loc[unknown, "code"]))
    rep.dropped_unknown_code = int(unknown.sum())
    df = df[~unknown].copy()

    dow = df["date"].dt.dayofweek
    rep.not_sunday = int((dow != 6).sum())
    # The week ending on (or containing) the report date: its Monday.
    df["week_start"] = df["date"] - pd.to_timedelta(dow, unit="D")
    df["who_region"] = df["WHO_region"].astype(str).str.upper().map(WHO_REGIONS)
    df["name"] = df["iso3"].map(NAMES).fillna(df["Country"].astype(str))

    keys = ["iso3", "week_start"]
    out = (df.groupby(keys, as_index=False)
           .agg(cases=("cases", lambda s: s.sum(min_count=1)),
                deaths=("deaths", lambda s: s.sum(min_count=1)),
                name=("name", "last"), who_region=("who_region", "last")))
    iso = out["week_start"].dt.isocalendar()
    out["iso_year"] = iso["year"].astype(int)
    out["iso_week"] = iso["week"].astype(int)
    return out.sort_values(keys, ignore_index=True), rep
