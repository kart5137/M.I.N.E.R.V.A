"""Load WHO dengue surveillance into `surveillance_weekly` (weekly reporters) and
`surveillance_monthly` (monthly reporters), with revision history, provisional flags and
coverage tiers. Same approach as the FluNet job (ingest/flunet.py)."""

from __future__ import annotations

import logging
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
from sqlalchemy import Engine, select, text
from sqlalchemy.orm import Session

from ei_db.models import Disease
from ei_pipeline.db import session_scope, track_run
from ei_pipeline.quality.coverage import DengueCoverage, analyse_dengue
from ei_pipeline.quality.validation import validate_monthly, validate_weekly
from ei_pipeline.sources import dengue
from ei_pipeline.util import sha256_file

log = logging.getLogger(__name__)

DISEASE_KEY = "dengue"
SOURCE_KEY = "who_dengue"

WEEK_STAGE_COLS = ("iso3", "week_start", "iso_year", "iso_week", "cases", "breakdown")
MONTH_STAGE_COLS = ("iso3", "month_start", "cases", "breakdown")

STAGE_DDL = """
CREATE TEMP TABLE dengue_week_stage (
    iso3 char(3), week_start date, iso_year smallint, iso_week smallint,
    cases float8, breakdown jsonb, PRIMARY KEY (iso3, week_start)
) ON COMMIT DROP;
CREATE TEMP TABLE dengue_month_stage (
    iso3 char(3), month_start date, cases float8, breakdown jsonb,
    PRIMARY KEY (iso3, month_start)
) ON COMMIT DROP
"""

WEEK_REVISIONS = """
INSERT INTO surveillance_revisions (surveillance_id, previous_values, ingestion_run_id)
SELECT t.id, jsonb_build_object('cases', t.cases, 'breakdown', t.breakdown,
                                'ingestion_run_id', t.ingestion_run_id), :run_id
FROM surveillance_weekly t
JOIN dengue_week_stage s ON t.iso3 = s.iso3 AND t.week_start = s.week_start
WHERE t.disease_id = :disease_id AND (t.cases, t.breakdown) IS DISTINCT FROM (s.cases, s.breakdown)
"""

WEEK_UPSERT = """
WITH upserted AS (
    INSERT INTO surveillance_weekly AS t (
        disease_id, iso3, week_start, iso_year, iso_week, cases, breakdown,
        source_id, ingestion_run_id)
    SELECT :disease_id, iso3, week_start, iso_year, iso_week, cases, breakdown,
           :source_id, :run_id
    FROM dengue_week_stage
    ON CONFLICT (disease_id, iso3, week_start) DO UPDATE SET
        iso_year = EXCLUDED.iso_year, iso_week = EXCLUDED.iso_week,
        cases = EXCLUDED.cases, breakdown = EXCLUDED.breakdown,
        source_id = EXCLUDED.source_id, ingestion_run_id = EXCLUDED.ingestion_run_id,
        updated_at = now()
    WHERE (t.cases, t.breakdown) IS DISTINCT FROM (EXCLUDED.cases, EXCLUDED.breakdown)
    RETURNING (xmax = 0) AS inserted
)
SELECT count(*) FILTER (WHERE inserted) AS inserted,
       count(*) FILTER (WHERE NOT inserted) AS updated
FROM upserted
"""

MONTH_REVISIONS = """
INSERT INTO surveillance_monthly_revisions
    (surveillance_monthly_id, previous_values, ingestion_run_id)
SELECT t.id, jsonb_build_object('cases', t.cases, 'breakdown', t.breakdown,
                                'ingestion_run_id', t.ingestion_run_id), :run_id
FROM surveillance_monthly t
JOIN dengue_month_stage s ON t.iso3 = s.iso3 AND t.month_start = s.month_start
WHERE t.disease_id = :disease_id AND (t.cases, t.breakdown) IS DISTINCT FROM (s.cases, s.breakdown)
"""

MONTH_UPSERT = """
WITH upserted AS (
    INSERT INTO surveillance_monthly AS t (
        disease_id, iso3, month_start, cases, breakdown, source_id, ingestion_run_id)
    SELECT :disease_id, iso3, month_start, cases, breakdown, :source_id, :run_id
    FROM dengue_month_stage
    ON CONFLICT (disease_id, iso3, month_start) DO UPDATE SET
        cases = EXCLUDED.cases, breakdown = EXCLUDED.breakdown,
        source_id = EXCLUDED.source_id, ingestion_run_id = EXCLUDED.ingestion_run_id,
        updated_at = now()
    WHERE (t.cases, t.breakdown) IS DISTINCT FROM (EXCLUDED.cases, EXCLUDED.breakdown)
    RETURNING (xmax = 0) AS inserted
)
SELECT count(*) FILTER (WHERE inserted) AS inserted,
       count(*) FILTER (WHERE NOT inserted) AS updated
FROM upserted
"""

SET_PROVISIONAL = """
UPDATE {table} SET is_provisional = ({col} > :ref)
WHERE disease_id = :disease_id AND is_provisional IS DISTINCT FROM ({col} > :ref)
"""

MISSING_FROM_SOURCE = """
SELECT count(*) FROM {table} t
WHERE t.disease_id = :disease_id
  AND NOT EXISTS (SELECT 1 FROM {stage} s WHERE s.iso3 = t.iso3 AND s.{col} = t.{col})
"""

# New areas get a row (without a boundary). Existing countries keep their metadata,
# except that a missing WHO region is filled in.
ENSURE_COUNTRIES = """
INSERT INTO countries (iso3, name, who_region)
VALUES (:iso3, :name, :who_region)
ON CONFLICT (iso3) DO UPDATE SET who_region = EXCLUDED.who_region, updated_at = now()
WHERE countries.who_region IS NULL AND EXCLUDED.who_region IS NOT NULL
RETURNING (xmax = 0) AS inserted
"""


def _areas(weekly: pd.DataFrame, monthly: pd.DataFrame) -> list[dict]:
    both = pd.concat([
        weekly[["country_code", "country_name", "who_region", "week_start"]]
        .rename(columns={"week_start": "start"}),
        monthly[["country_code", "country_name", "who_region", "month_start"]]
        .rename(columns={"month_start": "start"}),
    ])
    latest = (both.sort_values("start").groupby("country_code")[["country_name", "who_region"]]
              .agg(lambda s: next(iter(s.dropna().iloc[::-1]), None)).reset_index())
    return [{"iso3": r.country_code, "name": r.country_name or r.country_code,
             "who_region": r.who_region} for r in latest.itertuples(index=False)]


def _copy(session: Session, table: str, cols: tuple[str, ...], df: pd.DataFrame) -> None:
    rows = df[list(cols)].astype(object).where(df[list(cols)].notna(), None)
    cursor = session.connection().connection.driver_connection.cursor()
    with cursor.copy(f"COPY {table} ({', '.join(cols)}) FROM STDIN") as copy:
        for row in rows.itertuples(index=False):
            copy.write_row(row)


def _store_coverage(session: Session, disease_id: int, cov: DengueCoverage) -> None:
    ref = cov.reference_week.date()
    session.execute(
        text("DELETE FROM coverage_profiles WHERE disease_id = :d AND reference_week = :r"),
        {"d": disease_id, "r": ref},
    )
    records = [
        {"d": disease_id, "iso3": p.country_code, "r": ref, "tier": p.tier, "grain": p.grain,
         "completeness": float(p.window_completeness), "gap": int(p.window_longest_gap),
         "since": None if pd.isna(p.weeks_since_last_report) else int(p.weeks_since_last_report)}
        for p in cov.profiles.itertuples(index=False)
    ]
    session.execute(text(
        "INSERT INTO coverage_profiles (disease_id, iso3, reference_week, tier, grain,"
        " completeness, longest_gap, median_tests, weeks_since_last)"
        " VALUES (:d, :iso3, :r, :tier, :grain, :completeness, :gap, NULL, :since)"
    ), records)


def ingest_dengue(engine: Engine, *, refresh: bool = False, path: Path | None = None,
                  today=None) -> dict:
    path = path or dengue.RAW_PATH
    if refresh or not path.exists():
        log.info("Downloading WHO dengue surveillance")
        dengue.download(path)

    with track_run(engine, SOURCE_KEY) as run:
        raw = dengue.load_raw(path)
        run.raw_rows = len(raw)
        run.raw_sha256 = sha256_file(path)

        cleaned = dengue.clean(raw, today=today)
        weekly, v_week = validate_weekly(cleaned.weekly, today=today, count_cols=("cases",),
                                         soft=dengue.soft_checks(cleaned.weekly))
        monthly, v_month = validate_monthly(cleaned.monthly, today=today,
                                            soft=dengue.soft_checks(cleaned.monthly))
        cov = analyse_dengue(weekly, monthly)

        wstage = weekly.rename(columns={"country_code": "iso3"}).assign(
            week_start=lambda d: d["week_start"].dt.date)
        mstage = monthly.rename(columns={"country_code": "iso3"}).assign(
            month_start=lambda d: d["month_start"].dt.date)

        with session_scope(engine) as s:
            disease_id = s.scalar(select(Disease.id).where(Disease.key == DISEASE_KEY))
            if disease_id is None:
                raise LookupError("Disease 'dengue' missing; run `ei ingest reference`.")
            params = {"disease_id": disease_id, "source_id": run.source_id, "run_id": run.run_id}

            ensured = [s.execute(text(ENSURE_COUNTRIES), a).scalar()
                       for a in _areas(weekly, monthly)]
            s.execute(text(STAGE_DDL))
            _copy(s, "dengue_week_stage", WEEK_STAGE_COLS, wstage)
            _copy(s, "dengue_month_stage", MONTH_STAGE_COLS, mstage)

            week_rev = s.execute(text(WEEK_REVISIONS), params).rowcount
            week_counts = dict(s.execute(text(WEEK_UPSERT), params).mappings().one())
            month_rev = s.execute(text(MONTH_REVISIONS), params).rowcount
            month_counts = dict(s.execute(text(MONTH_UPSERT), params).mappings().one())

            prov = {"weekly": s.execute(
                text(SET_PROVISIONAL.format(table="surveillance_weekly", col="week_start")),
                {"disease_id": disease_id, "ref": cov.reference_week.date()}).rowcount}
            if cov.reference_month is not None:
                prov["monthly"] = s.execute(
                    text(SET_PROVISIONAL.format(table="surveillance_monthly", col="month_start")),
                    {"disease_id": disease_id, "ref": cov.reference_month.date()}).rowcount
            missing = {
                "weekly": s.execute(text(MISSING_FROM_SOURCE.format(
                    table="surveillance_weekly", stage="dengue_week_stage", col="week_start")),
                    {"disease_id": disease_id}).scalar(),
                "monthly": s.execute(text(MISSING_FROM_SOURCE.format(
                    table="surveillance_monthly", stage="dengue_month_stage", col="month_start")),
                    {"disease_id": disease_id}).scalar(),
            }
            _store_coverage(s, disease_id, cov)

        inserted = week_counts["inserted"] + month_counts["inserted"]
        updated = week_counts["updated"] + month_counts["updated"]
        staged = len(wstage) + len(mstage)
        run.loaded_rows = inserted + updated
        tiers = cov.profiles.groupby(["grain", "tier"]).size()
        run.report.update({
            "source": {
                "url": dengue.DENGUE_URL,
                "file_modified": datetime.fromtimestamp(path.stat().st_mtime, UTC).isoformat(),
            },
            "cleaning": asdict(cleaned.report),
            "validation": {"weekly": v_week, "monthly": v_month,
                           "rows_excluded": v_week["rows_excluded"] + v_month["rows_excluded"]},
            "reference_week": cov.reference_week.date().isoformat(),
            "reference_month": cov.reference_month.date().isoformat()
            if cov.reference_month is not None else None,
            "provisional_weeks": {d.date().isoformat(): int(n)
                                  for d, n in cov.provisional_weeks.items()},
            "provisional_months": {d.date().isoformat(): int(n)
                                   for d, n in cov.provisional_months.items()},
            "rows_staged": {"weekly": len(wstage), "monthly": len(mstage)},
            "inserted": inserted,
            "updated": updated,
            "unchanged": staged - inserted - updated,
            "by_grain": {"weekly": week_counts, "monthly": month_counts},
            "revisions_recorded": week_rev + month_rev,
            "provisional_flags_changed": prov,
            "rows_missing_from_source": missing,
            "areas_added_without_boundary": sum(1 for x in ensured if x),
            "who_region_filled": sum(1 for x in ensured if x is False),
            "coverage_tiers": cov.profiles["tier"].value_counts().sort_index().to_dict(),
            "coverage_tiers_by_grain": {f"{g}:{t}": int(n) for (g, t), n in tiers.items()},
        })
        return run.report
