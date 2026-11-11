"""Load COVID-19 (C3): weekly new cases and deaths since January 2020 from the WHO
COVID-19 dashboard into `surveillance_weekly`, with revision history (WHO revises past
weeks as countries resubmit) and provisional flags on the latest PROVISIONAL_WEEKS weeks
(late reports). Yearly totals are sums of these weeks, computed by the API.
"""

from __future__ import annotations

import logging
from dataclasses import asdict
from datetime import timedelta
from pathlib import Path

from sqlalchemy import Engine, select, text

from ei_db.models import Disease
from ei_pipeline.db import session_scope, track_run
from ei_pipeline.ingest.dengue import ENSURE_COUNTRIES
from ei_pipeline.ingest.weekly_reports import store_weekly
from ei_pipeline.sources import covid
from ei_pipeline.util import sha256_file

log = logging.getLogger(__name__)

DISEASE_KEY = "covid19"
SOURCE_KEY = "who_covid_dashboard"
PROVISIONAL_WEEKS = 4


def ingest_covid(engine: Engine, *, refresh: bool = False, path: Path | None = None) -> dict:
    path = path or covid.RAW_PATH
    if refresh or not path.exists():
        log.info("Downloading WHO COVID-19 weekly data")
        covid.download(path)

    with session_scope(engine) as s:
        disease_id = s.scalar(select(Disease.id).where(Disease.key == DISEASE_KEY))
        iso2 = dict(s.execute(text(
            "SELECT iso2, iso3 FROM countries WHERE iso2 IS NOT NULL")).all())
    if disease_id is None:
        raise LookupError("Disease 'covid19' missing; run `ei ingest reference`.")

    with track_run(engine, SOURCE_KEY) as run:
        raw = covid.load(path)
        run.raw_rows = len(raw)
        run.raw_sha256 = sha256_file(path)
        weekly, rep = covid.clean(raw, iso2)
        if weekly.empty:
            raise ValueError("WHO COVID-19 file has no usable rows")
        latest = weekly["week_start"].max()
        reference = (latest - timedelta(weeks=PROVISIONAL_WEEKS)).date()
        with session_scope(engine) as s:
            areas = weekly.drop_duplicates("iso3", keep="last")
            ensured = [s.execute(text(ENSURE_COUNTRIES), {
                "iso3": r.iso3, "name": r.name, "who_region": r.who_region}).scalar()
                for r in areas.itertuples()]
            counts = store_weekly(s, weekly, disease_id=disease_id, source_id=run.source_id,
                                  run_id=run.run_id, reference=reference)
        run.loaded_rows = counts["inserted"] + counts["updated"]
        recent = weekly[weekly["week_start"] > latest - timedelta(weeks=PROVISIONAL_WEEKS + 4)]
        run.report.update({
            "job": "covid_weekly", "source": {"url": covid.WEEKLY_URL},
            "cleaning": asdict(rep), **counts,
            "unchanged": len(weekly) - counts["inserted"] - counts["updated"],
            "first_week": weekly["week_start"].min().date().isoformat(),
            "latest_week": latest.date().isoformat(), "reference_week": reference.isoformat(),
            "countries": int(weekly["iso3"].nunique()),
            "countries_reporting_recently": int(recent["iso3"].nunique()),
            "areas_added_without_boundary": sum(1 for x in ensured if x),
        })
        return run.report
