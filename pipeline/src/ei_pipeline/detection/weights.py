"""Spatial weights between countries (DESIGN.md §6.5).

Queen contiguity from the Natural Earth 1:50m polygons in PostGIS (any shared boundary
point). Countries with no land neighbour among the participants get their k nearest
participants by great-circle distance between centroids. Used by the hotspot statistics
and by the neighbour features of the forecasting model.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sqlalchemy import Engine, text

EARTH_RADIUS_KM = 6371.0


@dataclass(frozen=True)
class Geography:
    #: iso3 → set of land neighbours (queen contiguity), for countries with geometry.
    contiguity: dict[str, frozenset[str]]
    #: iso3 → (lon, lat) of the centroid.
    centroids: dict[str, tuple[float, float]]


def load_geography(engine: Engine) -> Geography:
    with engine.connect() as c:
        pairs = c.execute(text("""
            SELECT a.iso3, b.iso3 FROM countries a
            JOIN countries b ON a.iso3 < b.iso3 AND ST_Intersects(a.geom, b.geom)
        """)).all()
        cents = c.execute(text("""
            SELECT iso3, ST_X(centroid), ST_Y(centroid) FROM countries
            WHERE geom IS NOT NULL AND centroid IS NOT NULL
        """)).all()
    nb: dict[str, set[str]] = {iso3: set() for iso3, _, _ in cents}
    for a, b in pairs:
        nb.setdefault(a, set()).add(b)
        nb.setdefault(b, set()).add(a)
    return Geography(contiguity={k: frozenset(v) for k, v in nb.items()},
                     centroids={iso3: (lon, lat) for iso3, lon, lat in cents})


def haversine_km(lon1, lat1, lon2, lat2):
    lon1, lat1, lon2, lat2 = map(np.radians, (lon1, lat1, lon2, lat2))
    a = (np.sin((lat2 - lat1) / 2) ** 2
         + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2)
    return 2 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(a))


@dataclass(frozen=True)
class Neighbours:
    codes: list[str]                 # participants, in matrix order
    lists: list[np.ndarray]          # indices of each participant's neighbours
    source: list[str]                # "queen" | "knn"


def neighbours(geo: Geography, participants: list[str], k: int) -> Neighbours:
    """Neighbour lists restricted to `participants` (which must have centroids)."""
    codes = [c for c in participants if c in geo.centroids]
    pos = {c: i for i, c in enumerate(codes)}
    lon = np.array([geo.centroids[c][0] for c in codes])
    lat = np.array([geo.centroids[c][1] for c in codes])
    lists, source = [], []
    for i, c in enumerate(codes):
        land = sorted(pos[n] for n in geo.contiguity.get(c, ()) if n in pos)
        if land:
            lists.append(np.array(land, dtype=int))
            source.append("queen")
            continue
        d = haversine_km(lon[i], lat[i], lon, lat)
        d[i] = np.inf
        lists.append(np.argsort(d)[: min(k, len(codes) - 1)].astype(int))
        source.append("knn")
    return Neighbours(codes=codes, lists=lists, source=source)


def neighbour_mean(values: pd.DataFrame, nb: Neighbours, column: str) -> pd.Series:
    """For a frame indexed by (iso3, week_start) with `column`, the mean of the column
    over each country's neighbours in the same week (NaN-aware; NaN when none valid)."""
    wide = values[column].unstack("iso3").reindex(columns=nb.codes)
    arr = wide.to_numpy()
    out = np.full_like(arr, np.nan)
    for i, idx in enumerate(nb.lists):
        sub = arr[:, idx]
        cnt = np.sum(~np.isnan(sub), axis=1)
        with np.errstate(invalid="ignore"):
            out[:, i] = np.where(cnt > 0, np.nansum(sub, axis=1) / np.maximum(cnt, 1),
                                 np.nan)
    res = pd.DataFrame(out, index=wide.index, columns=nb.codes)
    return res.stack(future_stack=True).swaplevel().sort_index()
