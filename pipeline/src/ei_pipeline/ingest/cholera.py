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
from ei_pipeline.ingest.weekly_reports import store_weekly
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
        with session_scope(engine) as s:
            areas = weekly.drop_duplicates("iso3", keep="last")
            ensured = [s.execute(text(ENSURE_COUNTRIES), {
                "iso3": r.iso3, "name": r.name, "who_region": r.who_region}).scalar()
                for r in areas.itertuples()]
            counts = store_weekly(s, weekly, disease_id=disease_id, source_id=run.source_id,
                                  run_id=run.run_id, reference=reference)
        run.loaded_rows = counts["inserted"] + counts["updated"]
        run.report.update({
            "job": "cholera_weekly", "source": {"url": cholera.WEEKLY_URL},
            "cleaning": asdict(rep), **counts,
            "unchanged": len(weekly) - counts["inserted"] - counts["updated"],
            "latest_week": latest.date().isoformat(), "reference_week": reference.isoformat(),
            "countries": int(weekly["iso3"].nunique()),
            "areas_added_without_boundary": sum(1 for x in ensured if x),
        })
        report = run.report
    report["history"] = _history(engine, disease_id, raw_dir, refresh)
    return report
