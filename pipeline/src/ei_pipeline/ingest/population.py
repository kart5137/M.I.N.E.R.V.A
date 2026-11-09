"""Load World Bank population into `population_annual`."""

from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy import Engine, select, text

from ei_db.models import Country
from ei_pipeline.db import session_scope, track_run
from ei_pipeline.sources import worldbank
from ei_pipeline.util import sha256_file

log = logging.getLogger(__name__)

UPSERT = """
WITH upserted AS (
    INSERT INTO population_annual (iso3, year, population, source_id)
    SELECT iso3, year, population, :source_id FROM pop_stage
    ON CONFLICT (iso3, year) DO UPDATE
        SET population = EXCLUDED.population, source_id = EXCLUDED.source_id
        WHERE population_annual.population IS DISTINCT FROM EXCLUDED.population
    RETURNING (xmax = 0) AS inserted
)
SELECT count(*) FILTER (WHERE inserted) AS inserted,
       count(*) FILTER (WHERE NOT inserted) AS updated
FROM upserted
"""


def ingest_population(engine: Engine, *, refresh: bool = False, path: Path | None = None) -> dict:
    path = path or worldbank.RAW_PATH
    if refresh or not path.exists():
        log.info("Downloading World Bank %s", worldbank.INDICATOR)
        worldbank.download(path)

    with track_run(engine, "worldbank_wdi") as run:
        df, meta = worldbank.load(path)
        run.raw_rows = len(df)
        run.raw_sha256 = sha256_file(path)

        with session_scope(engine) as s:
            known = set(s.scalars(select(Country.iso3)))
            if not known:
                raise RuntimeError("`countries` is empty; run `ei ingest boundaries` first.")
            keep = df[df["iso3"].isin(known)]
            s.execute(text(
                "CREATE TEMP TABLE pop_stage (iso3 char(3), year smallint, population bigint)"
                " ON COMMIT DROP"
            ))
            s.execute(
                text("INSERT INTO pop_stage VALUES (:iso3, :year, :population)"),
                keep.to_dict("records"),
            )
            counts = dict(s.execute(text(UPSERT), {"source_id": run.source_id}).mappings().one())

        run.loaded_rows = counts["inserted"] + counts["updated"]
        run.report.update({
            "source": {"url": worldbank.URL, "indicator": worldbank.INDICATOR,
                       "api_last_updated": meta.get("lastupdated")},
            "rows_with_values": len(df),
            "rows_kept": len(keep),
            "codes_skipped_not_in_countries": sorted(set(df["iso3"]) - known),
            "countries_without_population": sorted(known - set(keep["iso3"])),
            "latest_year": int(keep["year"].max()) if len(keep) else None,
            **counts,
            "unchanged": len(keep) - counts["inserted"] - counts["updated"],
        })
        return run.report
