"""WHO Global Health Observatory (GHO) OData API: one JSON document per indicator.

`https://ghoapi.azureedge.net/api/<INDICATOR>` returns every row of an indicator as
`{"value": [...]}`; each row has SpatialDimType (COUNTRY, REGION, GLOBAL…), SpatialDim
(ISO3, WHO region code or GLOBAL), TimeDim (year), NumericValue and, for modelled
estimates, Low/High. Verified 2026-11-11 (docs/datasets/malaria.md).
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from ei_pipeline.config import RAW_DIR
from ei_pipeline.util import download as _download

API = "https://ghoapi.azureedge.net/api"
#: GHO area types kept, and the scope they are stored under.
SCOPES = {"COUNTRY": "country", "REGION": "region", "GLOBAL": "global"}
WHO_REGIONS = {"AFR", "AMR", "EMR", "EUR", "SEAR", "WPR"}


def url(indicator: str) -> str:
    return f"{API}/{indicator}"


def raw_path(indicator: str) -> Path:
    return RAW_DIR / "gho" / f"{indicator}.json"


def download(indicator: str, dest: Path | None = None) -> Path:
    return _download(url(indicator), dest or raw_path(indicator), timeout=180)


def load(path: Path) -> pd.DataFrame:
    """Rows as (scope, area, year, value, low, high); other area types (e.g. income
    groups) and rows without a numeric value are dropped. Non-WHO region codes are
    dropped too."""
    doc = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(doc, dict) or "value" not in doc:
        raise ValueError(f"{path.name}: not a GHO OData document")
    rows = []
    for r in doc["value"]:
        scope = SCOPES.get(r.get("SpatialDimType"))
        if scope is None or r.get("NumericValue") is None or r.get("TimeDimType") != "YEAR":
            continue
        area = str(r.get("SpatialDim") or "")
        if scope == "region" and area not in WHO_REGIONS:
            continue
        rows.append({"scope": scope, "area": area, "year": int(r["TimeDim"]),
                     "value": float(r["NumericValue"]),
                     "low": None if r.get("Low") is None else float(r["Low"]),
                     "high": None if r.get("High") is None else float(r["High"])})
    df = pd.DataFrame(rows, columns=["scope", "area", "year", "value", "low", "high"])
    # Fixed dtypes: an indicator without any ranges must not give object columns.
    return df.astype({"year": "int64", "value": "float64", "low": "float64", "high": "float64"})
