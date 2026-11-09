"""Load Natural Earth country boundaries into `countries` (PostGIS)."""

from __future__ import annotations

import logging
from dataclasses import asdict
from pathlib import Path

from sqlalchemy import Engine, text

from ei_pipeline.db import session_scope, track_run
from ei_pipeline.sources import natural_earth
from ei_pipeline.util import sha256_file

log = logging.getLogger(__name__)

STAGE_DDL = """
CREATE TEMP TABLE ne_stage (
    iso3 text, source_code text, adm0_a3 text, iso2 text, name text, continent text,
    label_lon float8, label_lat float8, geometry_json text
) ON COMMIT DROP
"""

STAGE_INSERT = """
INSERT INTO ne_stage VALUES (:iso3, :source_code, :adm0_a3, :iso2, :name, :continent,
                             :label_lon, :label_lat, :geometry_json)
"""

# Several features can share a code (e.g. Australia + its external territories):
# union their geometries; take attributes and label point from the main feature
# (the one whose ADM0_A3 equals the code, else the largest).
UPSERT = """
WITH parsed AS (
    SELECT *, ST_MakeValid(ST_SetSRID(ST_GeomFromGeoJSON(geometry_json), 4326)) AS g
    FROM ne_stage
), geoms AS (
    SELECT iso3, ST_Multi(ST_CollectionExtract(ST_Union(g), 3)) AS geom
    FROM parsed GROUP BY iso3
), main AS (
    SELECT DISTINCT ON (iso3) iso3, iso2, name, continent, label_lon, label_lat
    FROM parsed
    ORDER BY iso3, (adm0_a3 = source_code) DESC, ST_Area(g) DESC
), upserted AS (
    INSERT INTO countries (iso3, iso2, name, continent, geom, centroid)
    SELECT m.iso3, m.iso2, m.name, m.continent, g.geom,
           ST_SetSRID(ST_MakePoint(m.label_lon, m.label_lat), 4326)
    FROM main m JOIN geoms g USING (iso3)
    ON CONFLICT (iso3) DO UPDATE SET
        iso2 = EXCLUDED.iso2, name = EXCLUDED.name, continent = EXCLUDED.continent,
        geom = EXCLUDED.geom, centroid = EXCLUDED.centroid, updated_at = now()
    WHERE (countries.iso2, countries.name, countries.continent)
              IS DISTINCT FROM (EXCLUDED.iso2, EXCLUDED.name, EXCLUDED.continent)
       OR countries.geom IS NULL
       OR NOT ST_Equals(countries.geom, EXCLUDED.geom)
    RETURNING (xmax = 0) AS inserted
)
SELECT count(*) FILTER (WHERE inserted) AS inserted,
       count(*) FILTER (WHERE NOT inserted) AS updated
FROM upserted
"""

STAGE_STATS = """
SELECT count(*) AS features,
       count(DISTINCT iso3) AS areas,
       count(*) FILTER (WHERE NOT ST_IsValid(ST_GeomFromGeoJSON(geometry_json))) AS invalid_fixed,
       coalesce(jsonb_object_agg(iso3, n) FILTER (WHERE n > 1), '{}'::jsonb) AS merged
FROM ne_stage
LEFT JOIN (SELECT iso3, count(*) AS n FROM ne_stage GROUP BY iso3) c USING (iso3)
"""

ALIAS_UPSERT = """
INSERT INTO country_code_aliases (alias, source_id, iso3, note)
VALUES (:alias, :source_id, :iso3, :note)
ON CONFLICT (alias, source_id) DO UPDATE SET iso3 = EXCLUDED.iso3, note = EXCLUDED.note
"""


def ingest_boundaries(engine: Engine, *, refresh: bool = False, path: Path | None = None) -> dict:
    path = path or natural_earth.RAW_PATH
    if refresh or not path.exists():
        log.info("Downloading Natural Earth %s", natural_earth.VERSION)
        natural_earth.download(path)

    with track_run(engine, "natural_earth") as run:
        boundaries = natural_earth.load(path)
        run.raw_rows = len(boundaries)
        run.raw_sha256 = sha256_file(path)

        with session_scope(engine) as s:
            s.execute(text(STAGE_DDL))
            s.execute(text(STAGE_INSERT), [asdict(b) for b in boundaries])
            stats = dict(s.execute(text(STAGE_STATS)).mappings().one())
            counts = dict(s.execute(text(UPSERT)).mappings().one())
            for alias, iso3 in natural_earth.CODE_ALIASES.items():
                s.execute(text(ALIAS_UPSERT), {
                    "alias": alias, "source_id": run.source_id, "iso3": iso3,
                    "note": "Natural Earth code mapped to the project's canonical key",
                })

        run.loaded_rows = counts["inserted"] + counts["updated"]
        run.report.update({
            "source": {"url": natural_earth.URL, "version": natural_earth.VERSION},
            "features": stats["features"],
            "areas": stats["areas"],
            "invalid_geometries_repaired": stats["invalid_fixed"],
            "features_merged_by_code": stats["merged"],
            "aliases": natural_earth.CODE_ALIASES,
            **counts,
            "unchanged": stats["areas"] - counts["inserted"] - counts["updated"],
        })
        return run.report
