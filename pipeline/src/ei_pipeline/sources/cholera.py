"""WHO Global Cholera and AWD Dashboard: weekly cholera cases and deaths by country (C2).

The dashboard publishes a public CSV (`cholera_adm0_week`, ArcGIS item below; also on the
Humanitarian Data Exchange under CC BY-IGO) with one row per country and reporting week
since 2023-01-02: adm0_name, date_wk, cases, deaths, who_region, iso_3_code, …
Verified 2026-11-11 (docs/datasets/cholera.md): 5,339 rows, 43 countries.

Cleaning (counted in the run report):

- Dates: 98% are Mondays. Sundays (69 rows) start an epidemiological week that runs
  Sunday–Saturday and overlaps the following ISO week, so they move forward one day (as
  for dengue); any other weekday is assigned to the ISO week that contains it.
- A country-week that then appears twice is summed (WHO sometimes splits a week).
- Rows with neither cases nor deaths are dropped; a row with deaths but no case count
  keeps cases empty (not zero). Negative values are dropped (the source removes them).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from ei_pipeline.config import RAW_DIR
from ei_pipeline.util import download as _download

ITEM = "6d435a537d534bac95b072fd6d999355"
WEEKLY_URL = f"https://www.arcgis.com/sharing/rest/content/items/{ITEM}/data"
RAW_PATH = RAW_DIR / "cholera" / "cholera_adm0_week.csv"
REQUIRED = ("adm0_name", "date_wk", "cases", "deaths", "who_region", "iso_3_code")
WHO_REGIONS = {
    "African Region": "AFR", "Region of the Americas": "AMR",
    "Eastern Mediterranean Region": "EMR", "European Region": "EUR",
    "South-East Asia Region": "SEAR", "Western Pacific Region": "WPR",
}


@dataclass
class CleanReport:
    rows: int = 0
    moved_from_sunday: int = 0
    moved_other_weekday: int = 0
    merged_duplicates: int = 0
    dropped_empty: int = 0
    dropped_negative: int = 0
    unknown_regions: list[str] = field(default_factory=list)


def download(dest: Path = RAW_PATH) -> Path:
    return _download(WEEKLY_URL, dest, timeout=180)


def load(path: Path = RAW_PATH) -> pd.DataFrame:
    df = pd.read_csv(path)
    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        raise ValueError(f"{path.name}: missing columns {missing}")
    return df


def clean(raw: pd.DataFrame) -> tuple[pd.DataFrame, CleanReport]:
    """Rows as iso3, name, who_region, week_start (ISO Monday), cases, deaths."""
    rep = CleanReport(rows=len(raw))
    df = raw.rename(columns={"iso_3_code": "iso3", "adm0_name": "name"}).copy()
    df["iso3"] = df["iso3"].astype(str).str.strip().str.upper()
    df["date"] = pd.to_datetime(df["date_wk"], errors="coerce")
    df["cases"] = pd.to_numeric(df["cases"], errors="coerce")
    df["deaths"] = pd.to_numeric(df["deaths"], errors="coerce")

    empty = df["date"].isna() | (df["cases"].isna() & df["deaths"].isna())
    rep.dropped_empty = int(empty.sum())
    negative = ~empty & ((df["cases"] < 0) | (df["deaths"] < 0))
    rep.dropped_negative = int(negative.sum())
    df = df[~empty & ~negative].copy()

    dow = df["date"].dt.dayofweek
    rep.moved_from_sunday = int((dow == 6).sum())
    rep.moved_other_weekday = int(((dow != 0) & (dow != 6)).sum())
    sunday = df["date"] + pd.Timedelta(days=1)
    other = df["date"] - pd.to_timedelta(dow, unit="D")
    df["week_start"] = sunday.where(dow == 6, other)

    region = df["who_region"].map(WHO_REGIONS)
    rep.unknown_regions = sorted(set(df.loc[region.isna(), "who_region"].dropna().astype(str)))
    df["who_region"] = region
    name = df["name"].astype(str).str.title()

    keys = ["iso3", "week_start"]
    rep.merged_duplicates = int(df.duplicated(keys).sum())
    out = (df.assign(name=name)
           .groupby(keys, as_index=False)
           .agg(cases=("cases", lambda s: s.sum(min_count=1)),
                deaths=("deaths", lambda s: s.sum(min_count=1)),
                name=("name", "last"), who_region=("who_region", "last")))
    iso = out["week_start"].dt.isocalendar()
    out["iso_year"] = iso["year"].astype(int)
    out["iso_week"] = iso["week"].astype(int)
    return out.sort_values(keys, ignore_index=True), rep
