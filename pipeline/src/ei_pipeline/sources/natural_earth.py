"""Natural Earth 1:50m Admin-0 country boundaries (public domain).

See docs/datasets/natural_earth.md for code handling and known limitations.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from ei_pipeline.config import RAW_DIR
from ei_pipeline.util import download as _download

VERSION = "v5.1.2"
URL = (
    "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/"
    f"{VERSION}/geojson/ne_50m_admin_0_countries.geojson"
)
RAW_PATH = RAW_DIR / "natural_earth" / "ne_50m_admin_0_countries.geojson"

# Natural Earth codes that differ from the project's canonical key.
# XKX is the code used by WHO FluNet and the World Bank for Kosovo.
CODE_ALIASES = {"KOS": "XKX"}


@dataclass(frozen=True)
class Boundary:
    iso3: str          # canonical key after aliasing
    source_code: str   # code as derived from Natural Earth
    adm0_a3: str
    iso2: str | None
    name: str
    continent: str
    label_lon: float
    label_lat: float
    geometry_json: str


def download(dest: Path = RAW_PATH) -> Path:
    return _download(URL, dest)


def _code(props: dict) -> str:
    # ISO_A3 is -99 for France/Norway; ISO_A3_EH fixes those. Fall back to ADM0_A3
    # for areas without an ISO code (Kosovo, N. Cyprus, Somaliland, Siachen).
    return props["ISO_A3_EH"] if props["ISO_A3_EH"] != "-99" else props["ADM0_A3"]


def load(path: Path = RAW_PATH) -> list[Boundary]:
    features = json.loads(path.read_text(encoding="utf-8"))["features"]
    out = []
    for f in features:
        p = f["properties"]
        code = _code(p)
        iso2 = p.get("ISO_A2_EH")
        out.append(
            Boundary(
                iso3=CODE_ALIASES.get(code, code),
                source_code=code,
                adm0_a3=p["ADM0_A3"],
                iso2=iso2 if iso2 and iso2 != "-99" else None,
                name=p.get("NAME_LONG") or p["NAME"],
                continent=p["CONTINENT"],
                label_lon=float(p["LABEL_X"]),
                label_lat=float(p["LABEL_Y"]),
                geometry_json=json.dumps(f["geometry"], separators=(",", ":")),
            )
        )
    return out
