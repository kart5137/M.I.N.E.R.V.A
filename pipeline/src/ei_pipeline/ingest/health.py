"""Load World Bank health-system context indicators into `health_indicators`.

Values are context for the Country Intelligence page only; they are never imputed. A
country without a value for an indicator shows "Not available".
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

import pandas as pd
from sqlalchemy import Engine, select, text

from ei_db.catalog import HEALTH_INDICATORS
from ei_db.models import Country
from ei_pipeline.db import session_scope, track_run
from ei_pipeline.sources import worldbank
from ei_pipeline.util import sha256_file

log = logging.getLogger(__name__)

UPSERT = """
WITH upserted AS (
    INSERT INTO health_indicators (iso3, indicator_code, year, value, unit, source_id)
    SELECT iso3, indicator_code, year, value, unit, :source_id FROM hi_stage
    ON CONFLICT (iso3, indicator_code, year) DO UPDATE
        SET value = EXCLUDED.value, unit = EXCLUDED.unit, source_id = EXCLUDED.source_id
        WHERE (health_indicators.value, health_indicators.unit)
              IS DISTINCT FROM (EXCLUDED.value, EXCLUDED.unit)
    RETURNING (xmax = 0) AS inserted
)
SELECT count(*) FILTER (WHERE inserted) AS inserted,
       count(*) FILTER (WHERE NOT inserted) AS updated
FROM upserted
"""


def ingest_health(engine: Engine, *, refresh: bool = False, raw_dir: Path | None = None) -> dict:
    paths = {}
    for spec in HEALTH_INDICATORS:
        path = (raw_dir / f"{spec.code}.json") if raw_dir else worldbank.raw_path(spec.code)
        if refresh or not path.exists():
            log.info("Downloading World Bank %s", spec.code)
            worldbank.download(path, spec.code, worldbank.HEALTH_FIRST_YEAR)
        paths[spec.code] = path

    with track_run(engine, "worldbank_wdi") as run:
        frames, per_indicator = [], {}
        for spec in HEALTH_INDICATORS:
            df, meta = worldbank.load_indicator(paths[spec.code])
            df = df[df["year"] >= worldbank.HEALTH_FIRST_YEAR]
            frames.append(df.assign(indicator_code=spec.code, unit=spec.unit))
            per_indicator[spec.code] = {"api_last_updated": meta.get("lastupdated"),
                                        "rows_with_values": len(df),
                                        "sha256": sha256_file(paths[spec.code])}
        df = pd.concat(frames, ignore_index=True)
        run.raw_rows = len(df)
        # One fingerprint for the set of raw files (each file's hash is in the report).
        joined = "".join(v["sha256"] for v in per_indicator.values())
        run.raw_sha256 = hashlib.sha256(joined.encode()).hexdigest()

        with session_scope(engine) as s:
            known = set(s.scalars(select(Country.iso3)))
            if not known:
                raise RuntimeError("`countries` is empty; run `ei ingest boundaries` first.")
            keep = df[df["iso3"].isin(known)]
            s.execute(text(
                "CREATE TEMP TABLE hi_stage (iso3 char(3), indicator_code varchar(64),"
                " year smallint, value float8, unit varchar(64)) ON COMMIT DROP"
            ))
            s.execute(
                text("INSERT INTO hi_stage VALUES (:iso3, :indicator_code, :year, :value, :unit)"),
                keep[["iso3", "indicator_code", "year", "value", "unit"]].to_dict("records"),
            )
            counts = dict(s.execute(text(UPSERT), {"source_id": run.source_id}).mappings().one())

        for spec in HEALTH_INDICATORS:
            sub = keep[keep["indicator_code"] == spec.code]
            per_indicator[spec.code].update({
                "countries_with_value": int(sub["iso3"].nunique()),
                "latest_year": int(sub["year"].max()) if len(sub) else None,
            })
        run.loaded_rows = counts["inserted"] + counts["updated"]
        run.report.update({
            "job": "health_indicators",
            "indicators": per_indicator,
            "rows_kept": len(keep),
            **counts,
            "unchanged": len(keep) - counts["inserted"] - counts["updated"],
        })
        return run.report
