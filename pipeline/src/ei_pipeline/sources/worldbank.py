"""World Bank World Development Indicators: total population (SP.POP.TOTL), CC BY 4.0."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from ei_pipeline.config import RAW_DIR
from ei_pipeline.util import download as _download

INDICATOR = "SP.POP.TOTL"
FIRST_YEAR = 1995
URL = (
    f"https://api.worldbank.org/v2/country/all/indicator/{INDICATOR}"
    f"?format=json&per_page=20000&date={FIRST_YEAR}:2100"
)
RAW_PATH = RAW_DIR / "worldbank" / f"{INDICATOR}.json"


def download(dest: Path = RAW_PATH) -> Path:
    return _download(URL, dest)


def load(path: Path = RAW_PATH) -> tuple[pd.DataFrame, dict]:
    """Return (iso3, year, population) rows with values, plus API metadata.

    Aggregates (regions, income groups) are included here; the ingest step keeps only
    codes present in the `countries` table.
    """
    meta, rows = json.loads(path.read_text(encoding="utf-8"))
    if meta.get("pages", 1) != 1:
        raise ValueError(f"Expected a single page from the World Bank API, got {meta}")
    df = pd.DataFrame(
        {
            "iso3": r["countryiso3code"],
            "year": int(r["date"]),
            "population": r["value"],
        }
        for r in rows
        if r.get("countryiso3code")
    )
    return df.dropna(subset=["population"]).astype({"population": "int64"}), meta
