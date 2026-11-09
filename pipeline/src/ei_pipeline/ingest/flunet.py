"""Load WHO FluNet into `surveillance_weekly` with revision history, provisional flags
and coverage tiers."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
from sqlalchemy import Engine, select, text
from sqlalchemy.orm import Session

from ei_db.models import Disease
from ei_pipeline.db import session_scope, track_run
from ei_pipeline.quality.coverage import analyse
from ei_pipeline.quality.validation import validate_weekly
from ei_pipeline.sources import flunet
from ei_pipeline.util import sha256_file

log = logging.getLogger(__name__)

DISEASE_KEY = "influenza"
VALUE_COLS = ("specimens_tested", "positives", "positivity", "breakdown")
STAGE_COLS = ("iso3", "week_start", "iso_year", "iso_week", "specimens_tested", "positives",
              "positivity", "breakdown")

STAGE_DDL = """
CREATE TEMP TABLE flu_stage (
    iso3 char(3), week_start date, iso_year smallint, iso_week smallint,
    specimens_tested float8, positives float8, positivity float8, breakdown jsonb,
    PRIMARY KEY (iso3, week_start)
) ON COMMIT DROP
"""

_DIFF = (
    "(t.specimens_tested, t.positives, t.positivity, t.breakdown) IS DISTINCT FROM "
    "(s.specimens_tested, s.positives, s.positivity, s.breakdown)"
)

RECORD_REVISIONS = f"""
INSERT INTO surveillance_revisions (surveillance_id, previous_values, ingestion_run_id)
SELECT t.id,
       jsonb_build_object('specimens_tested', t.specimens_tested, 'positives', t.positives,
                          'positivity', t.positivity, 'breakdown', t.breakdown,
                          'ingestion_run_id', t.ingestion_run_id),
       :run_id
FROM surveillance_weekly t
JOIN flu_stage s ON t.iso3 = s.iso3 AND t.week_start = s.week_start
WHERE t.disease_id = :disease_id AND {_DIFF}
"""

UPSERT = """
WITH upserted AS (
    INSERT INTO surveillance_weekly AS t (
        disease_id, iso3, week_start, iso_year, iso_week, specimens_tested, positives,
        positivity, breakdown, source_id, ingestion_run_id)
    SELECT :disease_id, iso3, week_start, iso_year, iso_week, specimens_tested, positives,
           positivity, breakdown, :source_id, :run_id
    FROM flu_stage
    ON CONFLICT (disease_id, iso3, week_start) DO UPDATE SET
        iso_year = EXCLUDED.iso_year, iso_week = EXCLUDED.iso_week,
        specimens_tested = EXCLUDED.specimens_tested, positives = EXCLUDED.positives,
        positivity = EXCLUDED.positivity, breakdown = EXCLUDED.breakdown,
        source_id = EXCLUDED.source_id, ingestion_run_id = EXCLUDED.ingestion_run_id,
        updated_at = now()
    WHERE (t.specimens_tested, t.positives, t.positivity, t.breakdown)
          IS DISTINCT FROM
          (EXCLUDED.specimens_tested, EXCLUDED.positives, EXCLUDED.positivity, EXCLUDED.breakdown)
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

MISSING_FROM_SOURCE = """
SELECT count(*) FROM surveillance_weekly t
WHERE t.disease_id = :disease_id
  AND NOT EXISTS (SELECT 1 FROM flu_stage s WHERE s.iso3 = t.iso3 AND s.week_start = t.week_start)
"""

ENSURE_COUNTRIES = """
WITH upserted AS (
    INSERT INTO countries (iso3, name, who_region, hemisphere, transmission_zone, flu_season)
    VALUES (:iso3, :name, :who_region, :hemisphere, :transmission_zone, :flu_season)
    ON CONFLICT (iso3) DO UPDATE SET
        who_region = EXCLUDED.who_region, hemisphere = EXCLUDED.hemisphere,
        transmission_zone = EXCLUDED.transmission_zone, flu_season = EXCLUDED.flu_season,
        updated_at = now()
    WHERE (countries.who_region, countries.hemisphere, countries.transmission_zone,
           countries.flu_season)
          IS DISTINCT FROM
          (EXCLUDED.who_region, EXCLUDED.hemisphere, EXCLUDED.transmission_zone,
           EXCLUDED.flu_season)
    RETURNING (xmax = 0) AS inserted
)
SELECT count(*) FILTER (WHERE inserted) FROM upserted
"""

ALIAS_UPSERT = """
INSERT INTO country_code_aliases (alias, source_id, iso3, note)
VALUES (:alias, :source_id, 'GBR', :note)
ON CONFLICT (alias, source_id) DO UPDATE SET iso3 = EXCLUDED.iso3, note = EXCLUDED.note
"""


def _area_metadata(weekly: pd.DataFrame) -> list[dict]:
    """Latest non-null name/region/hemisphere/zone/season type per area."""
    cols = ["country_name", "who_region", "hemisphere", "transmission_zone", "flu_season"]
    latest = (
        weekly.sort_values("week_start")
        .groupby("country_code")[cols]
        .agg(lambda s: next(iter(s.dropna().iloc[::-1]), None))
        .reset_index()
    )
    return [
        {"iso3": r.country_code, "name": r.country_name or r.country_code,
         "who_region": r.who_region, "hemisphere": r.hemisphere,
         "transmission_zone": r.transmission_zone, "flu_season": r.flu_season}
        for r in latest.itertuples(index=False)
    ]


def _breakdown(df: pd.DataFrame) -> pd.Series:
    def one(a, b):
        d = {k: float(v) for k, v in (("inf_a", a), ("inf_b", b)) if pd.notna(v)}
        return json.dumps(d, sort_keys=True) if d else None
    pairs = zip(df["inf_a"], df["inf_b"], strict=True)
    return pd.Series([one(a, b) for a, b in pairs], index=df.index)


def _stage(session: Session, df: pd.DataFrame) -> None:
    session.execute(text(STAGE_DDL))
    rows = df.astype(object).where(df.notna(), None)
    cursor = session.connection().connection.driver_connection.cursor()
    with cursor.copy(f"COPY flu_stage ({', '.join(STAGE_COLS)}) FROM STDIN") as copy:
        for row in rows.itertuples(index=False):
            copy.write_row(row)


def _store_coverage(session: Session, disease_id: int, profiles: pd.DataFrame,
                    ref: pd.Timestamp) -> None:
    session.execute(
        text("DELETE FROM coverage_profiles WHERE disease_id = :d AND reference_week = :r"),
        {"d": disease_id, "r": ref.date()},
    )
    records = [
        {"d": disease_id, "iso3": p.country_code, "r": ref.date(), "tier": p.tier,
         "completeness": float(p.window_completeness), "gap": int(p.window_longest_gap),
         "med": None if pd.isna(p.median_tests_per_week) else float(p.median_tests_per_week),
         "since": None if pd.isna(p.weeks_since_last_report) else int(p.weeks_since_last_report)}
        for p in profiles.itertuples(index=False)
    ]
    session.execute(text(
        "INSERT INTO coverage_profiles (disease_id, iso3, reference_week, tier, completeness,"
        " longest_gap, median_tests, weeks_since_last)"
        " VALUES (:d, :iso3, :r, :tier, :completeness, :gap, :med, :since)"
    ), records)


def ingest_flunet(engine: Engine, *, refresh: bool = False, path: Path | None = None,
                  today=None) -> dict:
    path = path or flunet.RAW_PATH
    if refresh or not path.exists():
        log.info("Downloading WHO FluNet")
        flunet.download(path)

    with track_run(engine, "flunet") as run:
        raw = flunet.load_raw(path)
        run.raw_rows = len(raw)
        run.raw_sha256 = sha256_file(path)

        weekly, cleaning = flunet.clean(raw)
        weekly, validation = validate_weekly(weekly, today=today)
        coverage = analyse(weekly)
        ref = coverage.reference_week

        stage = weekly.rename(columns={"country_code": "iso3"}).assign(
            week_start=lambda d: d["week_start"].dt.date,
            breakdown=_breakdown(weekly),
        )[list(STAGE_COLS)]

        with session_scope(engine) as s:
            disease_id = s.scalar(select(Disease.id).where(Disease.key == DISEASE_KEY))
            if disease_id is None:
                raise LookupError("Disease 'influenza' missing; run `ei ingest reference`.")
            params = {"disease_id": disease_id, "source_id": run.source_id, "run_id": run.run_id}

            new_areas = sum(
                s.execute(text(ENSURE_COUNTRIES), m).scalar() for m in _area_metadata(weekly)
            )
            # Aliases only when GBR exists (a FluNet extract without UK rows has no GBR).
            has_gbr = (weekly["country_code"] == "GBR").any()
            for code, nation in flunet.UK_NATION_CODES.items() if has_gbr else ():
                s.execute(text(ALIAS_UPSERT), {
                    "alias": code, "source_id": run.source_id,
                    "note": f"United Kingdom, {nation}: summed into GBR"})

            _stage(s, stage)
            revisions = s.execute(text(RECORD_REVISIONS), params).rowcount
            counts = dict(s.execute(text(UPSERT), params).mappings().one())
            provisional_changed = s.execute(
                text(SET_PROVISIONAL), {"disease_id": disease_id, "ref": ref.date()}
            ).rowcount
            missing = s.execute(text(MISSING_FROM_SOURCE), {"disease_id": disease_id}).scalar()
            _store_coverage(s, disease_id, coverage.profiles, ref)

        run.loaded_rows = counts["inserted"] + counts["updated"]
        run.report.update({
            "source": {
                "url": flunet.FLUNET_URL,
                "file_modified": datetime.fromtimestamp(path.stat().st_mtime, UTC).isoformat(),
            },
            "cleaning": asdict(cleaning),
            "validation": validation,
            "reference_week": ref.date().isoformat(),
            "provisional_weeks": {d.date().isoformat(): int(n)
                                  for d, n in coverage.provisional.items()},
            "rows_staged": len(stage),
            **counts,
            "unchanged": len(stage) - counts["inserted"] - counts["updated"],
            "revisions_recorded": revisions,
            "provisional_flags_changed": provisional_changed,
            "rows_missing_from_source": missing,
            "areas_added_without_boundary": new_areas,
            "coverage_tiers": coverage.profiles["tier"].value_counts().sort_index().to_dict(),
        })
        return run.report
