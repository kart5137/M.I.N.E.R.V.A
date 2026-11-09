from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

# Simplified for display (~1 km tolerance at the equator, 4 decimal places).
# Areas without a boundary (e.g. French Guiana, drawn as part of France) are omitted.
COUNTRIES_GEOJSON = """
SELECT json_build_object(
    'type', 'FeatureCollection',
    'features', coalesce(json_agg(json_build_object(
        'type', 'Feature',
        'id', iso3,
        'properties', json_build_object(
            'iso3', iso3, 'name', name, 'who_region', who_region,
            'label', json_build_array(round(ST_X(centroid)::numeric, 3),
                                      round(ST_Y(centroid)::numeric, 3))),
        'geometry', ST_AsGeoJSON(ST_Multi(ST_SimplifyPreserveTopology(geom, :tolerance)), 4)::json
    ) ORDER BY iso3), '[]'::json)
)::text
FROM countries
WHERE geom IS NOT NULL
"""

VERSION = """
SELECT md5(count(*)::text || coalesce(max(updated_at)::text, ''))
FROM countries WHERE geom IS NOT NULL
"""


def countries_version(session: Session) -> str:
    return session.execute(text(VERSION)).scalar_one()


def countries_geojson(session: Session, tolerance: float = 0.01) -> str:
    return session.execute(text(COUNTRIES_GEOJSON), {"tolerance": tolerance}).scalar_one()
