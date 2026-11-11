"""Load cholera (C2): weekly cases and deaths since 2023 (WHO Global Cholera and AWD
Dashboard) into `surveillance_weekly`, and yearly history 1949–2016 (WHO GHO) into
`surveillance_annual`.

- Weekly rows are upserted with revision history (`surveillance_revisions`), like dengue.
  The latest PROVISIONAL_WEEKS weeks of the file are provisional: outbreak reports keep
  arriving late.
- Yearly history: GHO CHOLERA_0000000001/2/3 → `reported_cases`, `reported_deaths`,
  `cfr` (percent). Years from 2023 are not stored again: the API sums the weekly rows.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import asdict
from datetime import timedelta
from pathlib import Path

import pandas as pd
from sqlalchemy import Engine, select, text

from ei_db.models import Country, Disease
from ei_pipeline.db import session_scope, track_run
from ei_pipeline.ingest.dengue import ENSURE_COUNTRIES
from ei_pipeline.ingest.malaria import UPSERT as ANNUAL_UPSERT
from ei_pipeline.sources import cholera, gho
from ei_pipeline.util import sha256_file

log = logging.getLogger(__name__)

DISEASE_KEY = "cholera"
SOURCE_KEY = "who_cholera_dashboard"
HISTORY_SOURCE_KEY = "who_gho_cholera"
PROVISIONAL_WEEKS = 4
HISTORY = {
    "reported_cases": "CHOLERA_0000000001",
    "reported_deaths": "CHOLERA_0000000002",
    "cfr": "CHOLERA_0000000003",
}

STAGE_DDL = """
CREATE TEMP TABLE cholera_week_stage (
    iso3 char(3), week_start date, iso_year smallint, iso_week smallint,
    cases float8, deaths float8, PRIMARY KEY (iso3, week_start)
) ON COMMIT DROP
"""
REVISIONS = """
INSERT INTO surveillance_revisions (surveillance_id, previous_values, ingestion_run_id)
SELECT t.id, jsonb_build_object('cases', t.cases, 'deaths', t.deaths,
                                'ingestion_run_id', t.ingestion_run_id), :run_id
FROM surveillance_weekly t
JOIN cholera_week_stage s ON t.iso3 = s.iso3 AND t.week_start = s.week_start
WHERE t.disease_id = :disease_id AND (t.cases, t.deaths) IS DISTINCT FROM (s.cases, s.deaths)
"""
UPSERT = """
WITH upserted AS (
    INSERT INTO surveillance_weekly AS t (
        disease_id, iso3, week_start, iso_year, iso_week, cases, deaths, source_id,
        ingestion_run_id)
    SELECT :disease_id, iso3, week_start, iso_year, iso_week, cases, deaths, :source_id,
           :run_id
    FROM cholera_week_stage
    ON CONFLICT (disease_id, iso3, week_start) DO UPDATE SET
        cases = EXCLUDED.cases, deaths = EXCLUDED.deaths, source_id = EXCLUDED.source_id,
        ingestion_run_id = EXCLUDED.ingestion_run_id, updated_at = now()
    WHERE (t.cases, t.deaths) IS DISTINCT FROM (EXCLUDED.cases, EXCLUDED.deaths)
    RETURNING (xmax = 0) AS inserted
)
SELECT count(*) FILTER (WHERE inserted) AS inserted,
       count(*) FILTER (WHERE NOT inserted) AS updated
FROM upserted
"""
SET_PROVISIONAL = """
UPDATE surveillance_weekly SET is_provisional = (week_start > :ref)
WHERE disease_id = :disease_id AND is_provisional IS DISTINCT FROM (week_start > :ref)
"""


def _history(engine: Engine, disease_id: int, raw_dir: Path | None, refresh: bool) -> dict:
    paths = {}
    for measure, code in HISTORY.items():
        path = (raw_dir / f"{code}.json") if raw_dir else gho.raw_path(code)
        if refresh or not path.exists():
            log.info("Downloading WHO GHO %s", code)
            gho.download(code, path)
        paths[measure] = path
    with track_run(engine, HISTORY_SOURCE_KEY) as run:
        frames = [gho.load(p).assign(measure=m) for m, p in paths.items()]
        df = pd.concat(frames, ignore_index=True)
        df = df[(df["scope"] == "country") & (df["value"] >= 0)]
        run.raw_rows = len(df)
        run.raw_sha256 = hashlib.sha256(
            "".join(sha256_file(p) for p in paths.values()).encode()).hexdigest()
        with session_scope(engine) as s:
            known = set(s.scalars(select(Country.iso3)))
            unknown = sorted(set(df["area"]) - known)
            df = df[df["area"].isin(known)].assign(iso3=lambda d: d["area"])
            s.execute(text(
                "CREATE TEMP TABLE sa_stage (scope varchar(8), area varchar(8), iso3 char(3),"
                " year smallint, measure varchar(32), value float8, low float8, high float8)"
                " ON COMMIT DROP"))
            records = df[["scope", "area", "iso3", "year", "measure", "value", "low", "high"]] \
                .astype(object).where(df.notna(), None).to_dict("records")
            if records:
                s.execute(text("INSERT INTO sa_stage VALUES (:scope, :area, :iso3, :year,"
                               " :measure, :value, :low, :high)"), records)
            counts = dict(s.execute(text(ANNUAL_UPSERT), {
                "disease_id": disease_id, "source_id": run.source_id,
                "run_id": run.run_id}).mappings().one())
        run.loaded_rows = counts["inserted"] + counts["updated"]
        run.report.update({
            "job": "cholera_history", **counts,
            "unchanged": len(df) - counts["inserted"] - counts["updated"],
            "countries": int(df["area"].nunique()),
            "years": [int(df["year"].min()), int(df["year"].max())] if len(df) else None,
            "unknown_country_codes": unknown,
        })
        return run.report


def ingest_cholera(engine: Engine, *, refresh: bool = False, path: Path | None = None,
                   raw_dir: Path | None = None) -> dict:
    path = path or cholera.RAW_PATH
    if refresh or not path.exists():
        log.info("Downloading WHO cholera weekly data")
        cholera.download(path)

    with session_scope(engine) as s:
        disease_id = s.scalar(select(Disease.id).where(Disease.key == DISEASE_KEY))
    if disease_id is None:
        raise LookupError("Disease 'cholera' missing; run `ei ingest reference`.")

    with track_run(engine, SOURCE_KEY) as run:
        raw = cholera.load(path)
        run.raw_rows = len(raw)
        run.raw_sha256 = sha256_file(path)
        weekly, rep = cholera.clean(raw)
        latest = weekly["week_start"].max()
        reference = (latest - timedelta(weeks=PROVISIONAL_WEEKS)).date()
        stage = weekly.assign(week_start=weekly["week_start"].dt.date)
        with session_scope(engine) as s:
            params = {"disease_id": disease_id, "source_id": run.source_id, "run_id": run.run_id}
            areas = stage.drop_duplicates("iso3", keep="last")
            ensured = [s.execute(text(ENSURE_COUNTRIES), {
                "iso3": r.iso3, "name": r.name, "who_region": r.who_region}).scalar()
                for r in areas.itertuples()]
            s.execute(text(STAGE_DDL))
            cols = ["iso3", "week_start", "iso_year", "iso_week", "cases", "deaths"]
            s.execute(text("INSERT INTO cholera_week_stage VALUES (:iso3, :week_start,"
                           " :iso_year, :iso_week, :cases, :deaths)"),
                      stage[cols].astype(object).where(stage[cols].notna(), None)
                      .to_dict("records"))
            revisions = s.execute(text(REVISIONS), params).rowcount
            counts = dict(s.execute(text(UPSERT), params).mappings().one())
            flags = s.execute(text(SET_PROVISIONAL),
                              {"disease_id": disease_id, "ref": reference}).rowcount
        run.loaded_rows = counts["inserted"] + counts["updated"]
        run.report.update({
            "job": "cholera_weekly", "source": {"url": cholera.WEEKLY_URL},
            "cleaning": asdict(rep), **counts,
            "unchanged": len(stage) - counts["inserted"] - counts["updated"],
            "revisions_recorded": revisions, "provisional_flags_changed": flags,
            "latest_week": latest.date().isoformat(), "reference_week": reference.isoformat(),
            "countries": int(stage["iso3"].nunique()),
            "areas_added_without_boundary": sum(1 for x in ensured if x),
        })
        report = run.report
    report["history"] = _history(engine, disease_id, raw_dir, refresh)
    return report
