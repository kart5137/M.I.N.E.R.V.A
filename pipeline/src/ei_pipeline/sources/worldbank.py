"""World Bank World Development Indicators (CC BY 4.0).

- Population, total (SP.POP.TOTL) → `population_annual`.
- Health-system and demographic indicators (`ei_db.catalog.HEALTH_INDICATORS`) →
  `health_indicators`.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from ei_pipeline.config import RAW_DIR
from ei_pipeline.util import download as _download

INDICATOR = "SP.POP.TOTL"
FIRST_YEAR = 1995
#: Health indicators are sparse and slow-moving; older values are not useful as context.
HEALTH_FIRST_YEAR = 2010


def url(indicator: str = INDICATOR, first_year: int = FIRST_YEAR) -> str:
    return (
        f"https://api.worldbank.org/v2/country/all/indicator/{indicator}"
        f"?format=json&per_page=20000&date={first_year}:2100"
    )


def raw_path(indicator: str = INDICATOR) -> Path:
    return RAW_DIR / "worldbank" / f"{indicator}.json"


URL = url()
RAW_PATH = raw_path()


def download(dest: Path = RAW_PATH, indicator: str = INDICATOR,
             first_year: int = FIRST_YEAR) -> Path:
    return _download(url(indicator, first_year), dest)


def load_indicator(path: Path) -> tuple[pd.DataFrame, dict]:
    """Return (iso3, year, value) rows with values, plus API metadata.

    Aggregates (regions, income groups) are included here; ingest steps keep only codes
    present in the `countries` table.
    """
    meta, rows = json.loads(path.read_text(encoding="utf-8"))
    if meta.get("pages", 1) != 1:
        raise ValueError(f"Expected a single page from the World Bank API, got {meta}")
    df = pd.DataFrame(
        [{"iso3": r["countryiso3code"], "year": int(r["date"]), "value": r["value"]}
         for r in rows if r.get("countryiso3code")],
        columns=["iso3", "year", "value"],
    )
    return df.dropna(subset=["value"]), meta


def load(path: Path = RAW_PATH) -> tuple[pd.DataFrame, dict]:
    """Population rows as (iso3, year, population)."""
    df, meta = load_indicator(path)
    df = df.rename(columns={"value": "population"}).astype({"population": "int64"})
    return df, meta
