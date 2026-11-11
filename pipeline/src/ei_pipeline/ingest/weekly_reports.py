"""Weekly case and death reports into `surveillance_weekly` (cholera C2, COVID-19 C3).

One shape for both sources: rows of iso3, week_start (ISO Monday), iso_year, iso_week,
cases, deaths. Loaded through a staging table with:

- revision history: a changed week keeps its previous values in `surveillance_revisions`;
- an upsert that touches only rows whose values changed;
- provisional flags: weeks after the reference week (the latest week minus a
  disease-specific number of weeks) are provisional, because reports arrive late.
"""

from __future__ import annotations

from datetime import date

import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session

STAGE_COLS = ("iso3", "week_start", "iso_year", "iso_week", "cases", "deaths")
STAGE_DDL = """
CREATE TEMP TABLE weekly_report_stage (
    iso3 char(3), week_start date, iso_year smallint, iso_week smallint,
    cases float8, deaths float8, PRIMARY KEY (iso3, week_start)
) ON COMMIT DROP
"""
REVISIONS = """
INSERT INTO surveillance_revisions (surveillance_id, previous_values, ingestion_run_id)
SELECT t.id, jsonb_build_object('cases', t.cases, 'deaths', t.deaths,
                                'ingestion_run_id', t.ingestion_run_id), :run_id
FROM surveillance_weekly t
JOIN weekly_report_stage s ON t.iso3 = s.iso3 AND t.week_start = s.week_start
WHERE t.disease_id = :disease_id AND (t.cases, t.deaths) IS DISTINCT FROM (s.cases, s.deaths)
"""
UPSERT = """
WITH upserted AS (
    INSERT INTO surveillance_weekly AS t (
        disease_id, iso3, week_start, iso_year, iso_week, cases, deaths, source_id,
        ingestion_run_id)
    SELECT :disease_id, iso3, week_start, iso_year, iso_week, cases, deaths, :source_id,
           :run_id
    FROM weekly_report_stage
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


def store_weekly(session: Session, weekly: pd.DataFrame, *, disease_id: int,
                 source_id: int, run_id: int, reference: date) -> dict:
    """Stage, record revisions, upsert and set provisional flags. Returns inserted,
    updated, revisions_recorded and provisional_flags_changed."""
    stage = weekly.assign(week_start=pd.to_datetime(weekly["week_start"]).dt.date)
    rows = stage[list(STAGE_COLS)].astype(object).where(stage[list(STAGE_COLS)].notna(), None)
    session.execute(text(STAGE_DDL))
    cursor = session.connection().connection.driver_connection.cursor()
    with cursor.copy(f"COPY weekly_report_stage ({', '.join(STAGE_COLS)}) FROM STDIN") as copy:
        for row in rows.itertuples(index=False):
            copy.write_row(row)
    params = {"disease_id": disease_id, "source_id": source_id, "run_id": run_id}
    revisions = session.execute(text(REVISIONS), params).rowcount
    counts = dict(session.execute(text(UPSERT), params).mappings().one())
    flags = session.execute(text(SET_PROVISIONAL),
                            {"disease_id": disease_id, "ref": reference}).rowcount
    return {**counts, "revisions_recorded": revisions, "provisional_flags_changed": flags}
