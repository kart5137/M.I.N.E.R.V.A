"""Load WHO malaria indicators (GHO) into `surveillance_annual` (C1).

Measures (stored name ← GHO indicator):

- `est_cases`, `est_deaths` ← MALARIA_EST_CASES, MALARIA_EST_DEATHS: World Malaria Report
  modelled estimates, 2000–, with uncertainty ranges (Low/High) where modelled.
- `est_incidence` ← MALARIA_EST_INCIDENCE: estimated cases per 1,000 population at risk.
- `est_mortality` ← MALARIA_EST_MORTALITY: estimated deaths per 100,000 population.
- `confirmed_cases`, `reported_cases` ← MALARIA_CONF_CASES, MALARIA_TOTAL_CASES: what
  national programmes reported (confirmed; confirmed + presumed), 2015–.

Checks (rows failing them are dropped and counted in the run report): value ≥ 0; where a
range is given, low ≤ value ≤ high; year from 2000 to this year; a country row's code is
in `countries`. WHO re-estimates the whole series each year, so changed values are
updated in place (counted as `updated`).
"""

from __future__ import annotations

import hashlib
import logging
from datetime import date
from pathlib import Path

import pandas as pd
from sqlalchemy import Engine, select, text

from ei_db.models import Country
from ei_pipeline.db import session_scope, track_run
from ei_pipeline.sources import gho
from ei_pipeline.util import sha256_file

log = logging.getLogger(__name__)

SOURCE_KEY = "who_gho_malaria"
DISEASE_KEY = "malaria"
MEASURES = {
    "est_cases": "MALARIA_EST_CASES",
    "est_deaths": "MALARIA_EST_DEATHS",
    "est_incidence": "MALARIA_EST_INCIDENCE",
    "est_mortality": "MALARIA_EST_MORTALITY",
    "confirmed_cases": "MALARIA_CONF_CASES",
    "reported_cases": "MALARIA_TOTAL_CASES",
}
FIRST_YEAR = 2000

UPSERT = """
WITH upserted AS (
    INSERT INTO surveillance_annual (disease_id, scope, area, iso3, year, measure, value,
                                     low, high, source_id, ingestion_run_id)
    SELECT :disease_id, scope, area, iso3, year, measure, value, low, high, :source_id,
           :run_id
    FROM sa_stage
    ON CONFLICT (disease_id, scope, area, year, measure) DO UPDATE
        SET value = EXCLUDED.value, low = EXCLUDED.low, high = EXCLUDED.high,
            source_id = EXCLUDED.source_id, ingestion_run_id = EXCLUDED.ingestion_run_id,
            updated_at = now()
        WHERE (surveillance_annual.value, surveillance_annual.low, surveillance_annual.high)
              IS DISTINCT FROM (EXCLUDED.value, EXCLUDED.low, EXCLUDED.high)
    RETURNING (xmax = 0) AS inserted
)
SELECT count(*) FILTER (WHERE inserted) AS inserted,
       count(*) FILTER (WHERE NOT inserted) AS updated
FROM upserted
"""


def check(df: pd.DataFrame, known: set[str], this_year: int) -> tuple[pd.DataFrame, dict]:
    """Drop rows that fail the checks; return the kept rows and the drop counts."""
    reasons = {
        "negative": df["value"] < 0,
        "outside_range": (df["low"].notna() & (df["low"] > df["value"] + 1e-9))
        | (df["high"].notna() & (df["high"] < df["value"] - 1e-9)),
        "year_out_of_range": ~df["year"].between(FIRST_YEAR, this_year),
        "unknown_country": (df["scope"] == "country") & ~df["area"].isin(known),
    }
    bad = pd.Series(False, index=df.index)
    dropped = {}
    for name, mask in reasons.items():
        dropped[name] = int((mask & ~bad).sum())
        bad |= mask
    return df[~bad].copy(), dropped


def ingest_malaria(engine: Engine, *, refresh: bool = False, raw_dir: Path | None = None,
                   today: date | None = None) -> dict:
    paths = {}
    for measure, code in MEASURES.items():
        path = (raw_dir / f"{code}.json") if raw_dir else gho.raw_path(code)
        if refresh or not path.exists():
            log.info("Downloading WHO GHO %s", code)
            gho.download(code, path)
        paths[measure] = path

    with track_run(engine, SOURCE_KEY) as run:
        frames, per_measure = [], {}
        for measure, code in MEASURES.items():
            df = gho.load(paths[measure]).assign(measure=measure)
            frames.append(df)
            per_measure[measure] = {"indicator": code, "rows": len(df),
                                    "sha256": sha256_file(paths[measure])}
        df = pd.concat(frames, ignore_index=True)
        run.raw_rows = len(df)
        joined = "".join(v["sha256"] for v in per_measure.values())
        run.raw_sha256 = hashlib.sha256(joined.encode()).hexdigest()

        with session_scope(engine) as s:
            known = set(s.scalars(select(Country.iso3)))
            if not known:
                raise RuntimeError("`countries` is empty; run `ei ingest boundaries` first.")
            disease_id = s.execute(text("SELECT id FROM diseases WHERE key = :k"),
                                   {"k": DISEASE_KEY}).scalar_one()
            keep, dropped = check(df, known, (today or date.today()).year)
            keep["iso3"] = keep["area"].where(keep["scope"] == "country")
            s.execute(text(
                "CREATE TEMP TABLE sa_stage (scope varchar(8), area varchar(8), iso3 char(3),"
                " year smallint, measure varchar(32), value float8, low float8, high float8)"
                " ON COMMIT DROP"))
            records = keep[["scope", "area", "iso3", "year", "measure", "value", "low",
                            "high"]].astype(object).where(keep.notna(), None).to_dict("records")
            if records:
                s.execute(text("INSERT INTO sa_stage VALUES (:scope, :area, :iso3, :year,"
                               " :measure, :value, :low, :high)"), records)
            counts = dict(s.execute(text(UPSERT), {"disease_id": disease_id,
                                                   "source_id": run.source_id,
                                                   "run_id": run.run_id}).mappings().one())

        for measure in MEASURES:
            sub = keep[(keep["measure"] == measure) & (keep["scope"] == "country")]
            per_measure[measure].update({
                "countries": int(sub["area"].nunique()),
                "first_year": int(sub["year"].min()) if len(sub) else None,
                "latest_year": int(sub["year"].max()) if len(sub) else None,
                "with_range": int(sub["low"].notna().sum()),
            })
        run.loaded_rows = counts["inserted"] + counts["updated"]
        run.report.update({
            "job": "malaria",
            "measures": per_measure,
            "rows_kept": len(keep),
            "rows_dropped": dropped,
            **counts,
            "unchanged": len(keep) - counts["inserted"] - counts["updated"],
        })
        return run.report
