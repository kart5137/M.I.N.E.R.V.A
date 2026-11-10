"""Load weekly ERA5 weather for every dengue reporting area (phase D3) into
`weather_weekly`, with the point used for each area in `weather_points`.
Rules: docs/datasets/weather.md.

The free API allows ~10,000 weighted calls a day; the full history is ~360 per area. So
loading is resumable: each run continues every area from its last stored week, within a
budget, forecast-ready countries (dengue tiers A/B) first. Once an area is complete a run
only re-fetches its last REVISIT_WEEKS weeks (recent ERA5 days are preliminary)."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import date, timedelta

import pandas as pd
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from ei_pipeline import weather
from ei_pipeline.db import session_scope, track_run
from ei_pipeline.sources import open_meteo

log = logging.getLogger(__name__)

SOURCE_KEY = "open_meteo_era5"
#: First week loaded: weekly dengue starts in 2014 and features need a year of lead-in.
HISTORY_START = date(2013, 1, 7)
#: Weeks re-fetched for complete areas: ERA5's latest days are preliminary (ERA5T).
REVISIT_WEEKS = 8
#: Weighted calls one run may use (two runs a day stay under the daily limit).
DEFAULT_BUDGET = 4400.0

#: Reporting areas without a Natural Earth boundary (no label point): the main town.
MAIN_TOWNS = {
    "BES": (12.150, -68.268),   # Kralendijk, Bonaire
    "GLP": (16.241, -61.533),   # Pointe-à-Pitre
    "GUF": (4.937, -52.326),    # Cayenne
    "MDR": (32.650, -16.908),   # Funchal
    "MTQ": (14.610, -61.077),   # Fort-de-France
    "MYT": (-12.780, 45.228),   # Mamoudzou
    "REU": (-20.882, 55.451),   # Saint-Denis
    "TKL": (-9.200, -171.850),  # Nukunonu
}

# Priority 0: the latest dengue coverage profile rates the area A or B (forecast-ready).
TARGETS = """
WITH dengue AS (SELECT id FROM diseases WHERE key = 'dengue'),
areas AS (
    SELECT iso3 FROM surveillance_weekly WHERE disease_id = (SELECT id FROM dengue)
    UNION
    SELECT iso3 FROM surveillance_monthly WHERE disease_id = (SELECT id FROM dengue)),
tiers AS (
    SELECT iso3, tier FROM coverage_profiles
    WHERE disease_id = (SELECT id FROM dengue)
      AND reference_week = (SELECT max(reference_week) FROM coverage_profiles
                            WHERE disease_id = (SELECT id FROM dengue)))
SELECT c.iso3, ST_Y(c.centroid) AS lat, ST_X(c.centroid) AS lon, w.last_week,
       CASE WHEN t.tier IN ('A', 'B') THEN 0 ELSE 1 END AS priority
FROM areas a
JOIN countries c USING (iso3)
LEFT JOIN tiers t USING (iso3)
LEFT JOIN (SELECT iso3, max(week_start) AS last_week FROM weather_weekly GROUP BY iso3) w
       USING (iso3)
ORDER BY priority, c.iso3
"""

STAGE_DDL = """
CREATE TEMP TABLE weather_stage (
    iso3 char(3), week_start date, iso_year smallint, iso_week smallint,
    temperature float8, precipitation float8, humidity float8, PRIMARY KEY (iso3, week_start)
) ON COMMIT DROP
"""
STAGE_COLS = ("iso3", "week_start", "iso_year", "iso_week", *weather.VARIABLES)

UPSERT = """
WITH upserted AS (
    INSERT INTO weather_weekly AS t (iso3, week_start, iso_year, iso_week, temperature,
                                     precipitation, humidity, source_id, ingestion_run_id)
    SELECT iso3, week_start, iso_year, iso_week, temperature, precipitation, humidity,
           :source_id, :run_id
    FROM weather_stage
    ON CONFLICT (iso3, week_start) DO UPDATE SET
        temperature = EXCLUDED.temperature, precipitation = EXCLUDED.precipitation,
        humidity = EXCLUDED.humidity, source_id = EXCLUDED.source_id,
        ingestion_run_id = EXCLUDED.ingestion_run_id, updated_at = now()
    WHERE (t.temperature, t.precipitation, t.humidity)
          IS DISTINCT FROM (EXCLUDED.temperature, EXCLUDED.precipitation, EXCLUDED.humidity)
    RETURNING (xmax = 0) AS inserted
)
SELECT count(*) FILTER (WHERE inserted) AS inserted,
       count(*) FILTER (WHERE NOT inserted) AS updated
FROM upserted
"""

UPSERT_POINT = """
INSERT INTO weather_points (iso3, lat, lon, basis, elevation_m, source_id)
VALUES (:iso3, :lat, :lon, :basis, :elevation_m, :source_id)
ON CONFLICT (iso3) DO UPDATE SET lat = EXCLUDED.lat, lon = EXCLUDED.lon,
    basis = EXCLUDED.basis, elevation_m = EXCLUDED.elevation_m,
    source_id = EXCLUDED.source_id, updated_at = now()
WHERE (weather_points.lat, weather_points.lon, weather_points.basis,
       weather_points.elevation_m, weather_points.source_id)
      IS DISTINCT FROM (EXCLUDED.lat, EXCLUDED.lon, EXCLUDED.basis, EXCLUDED.elevation_m,
                        EXCLUDED.source_id)
"""

Fetcher = Callable[..., open_meteo.PointSeries]


def monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _plan(rows, *, end: date, refresh: bool, backfill_only: bool) -> tuple[list[dict], list[str]]:
    """Point, start week and priority per area. An area is *behind* until its stored
    weeks reach the revisit window; `backfill_only` keeps just those areas."""
    revisit_from = monday(end) - timedelta(weeks=REVISIT_WEEKS)
    plan, skipped = [], []
    for r in rows:
        if r.lat is not None:
            lat, lon, basis = float(r.lat), float(r.lon), "label_point"
        elif r.iso3 in MAIN_TOWNS:
            (lat, lon), basis = MAIN_TOWNS[r.iso3], "main_town"
        else:
            skipped.append(r.iso3)
            continue
        if refresh or r.last_week is None:
            start = HISTORY_START
        else:
            start = max(HISTORY_START, min(r.last_week + timedelta(weeks=1), revisit_from))
        behind = start < revisit_from
        if backfill_only and not behind:
            continue
        plan.append({"iso3": r.iso3, "lat": lat, "lon": lon, "basis": basis,
                     "start": start, "behind": behind, "priority": r.priority})
    return plan, skipped


def _chunks(start: date, end: date) -> list[tuple[date, date]]:
    """Week-aligned requests of at most MAX_DAYS days (start is a Monday)."""
    out, s = [], start
    while s <= end:
        e = min(end, s + timedelta(days=open_meteo.MAX_DAYS - 1))
        out.append((s, e))
        s = e + timedelta(days=1)
    return out


def _store(session: Session, iso3: str, weeks: pd.DataFrame, point: dict,
           ids: dict) -> dict:
    session.execute(text(UPSERT_POINT), {**point, "iso3": iso3, "source_id": ids["source_id"]})
    stage = weeks.assign(
        iso3=iso3, week_start=pd.to_datetime(weeks["week_start"]).dt.date,
        **{v: weeks[v].astype(float).round(2) for v in weather.VARIABLES})
    session.execute(text(STAGE_DDL))
    cursor = session.connection().connection.driver_connection.cursor()
    with cursor.copy(f"COPY weather_stage ({', '.join(STAGE_COLS)}) FROM STDIN") as copy:
        for row in stage[list(STAGE_COLS)].itertuples(index=False):
            copy.write_row(row)
    return dict(session.execute(text(UPSERT), ids).mappings().one())


def ingest_weather(engine: Engine, *, refresh: bool = False, backfill_only: bool = False,
                   budget: float = DEFAULT_BUDGET, today: date | None = None,
                   fetch: Fetcher = open_meteo.fetch,
                   quota: open_meteo.Quota | None = None) -> dict:
    """Fetch, check, aggregate and upsert weather within `budget` weighted API calls.
    Stops cleanly when the budget or the API's hourly/daily limit is reached; the next
    run continues from the stored weeks."""
    end = (today or date.today()) - timedelta(days=1)
    quota = quota or open_meteo.Quota(budget)
    with track_run(engine, SOURCE_KEY) as run:
        with session_scope(engine) as s:
            plan, skipped = _plan(s.execute(text(TARGETS)).all(), end=end, refresh=refresh,
                                  backfill_only=backfill_only)
        ids = {"source_id": run.source_id, "run_id": run.run_id}
        totals = {"inserted": 0, "updated": 0, "weeks": 0, "dropped": 0}
        daily = weather.DailyReport(missing=dict.fromkeys(weather.VARIABLES, 0),
                                    implausible=dict.fromkeys(weather.VARIABLES, 0))
        failed: dict[str, str] = {}
        done: list[str] = []
        stopped = None

        for p in plan:
            frames, series = [], None
            try:
                for a, b in _chunks(p["start"], end):
                    series = fetch(p["lat"], p["lon"], a, b, quota=quota)
                    frames.append(series.daily)
            except open_meteo.QuotaExhausted as exc:
                stopped = str(exc)
            except Exception as exc:  # one area's failure must not stop the others
                log.warning("Weather fetch failed for %s: %s", p["iso3"], exc)
                failed[p["iso3"]] = f"{type(exc).__name__}: {exc}"[:300]
            if frames:  # store what arrived, even when the run stops part-way
                checked, rep = weather.check_daily(pd.concat(frames, ignore_index=True))
                daily.days += rep.days
                for k in weather.VARIABLES:
                    daily.missing[k] += rep.missing[k]
                    daily.implausible[k] += rep.implausible[k]
                weeks, dropped = weather.to_weeks(checked)
                point = {"lat": p["lat"], "lon": p["lon"], "basis": p["basis"],
                         "elevation_m": series.elevation_m}
                with session_scope(engine) as s:
                    counts = _store(s, p["iso3"], weeks, point, ids)
                totals["inserted"] += counts["inserted"]
                totals["updated"] += counts["updated"]
                totals["weeks"] += len(weeks)
                totals["dropped"] += dropped
                if not stopped and p["iso3"] not in failed:
                    done.append(p["iso3"])
            if stopped:
                break

        attempted = len(done) + len(failed)
        if attempted and not done and not stopped:
            raise RuntimeError(f"Every weather request failed, e.g. {next(iter(failed.values()))}")

        with session_scope(engine) as s:
            behind = len(_plan(s.execute(text(TARGETS)).all(), end=end, refresh=False,
                               backfill_only=True)[0])
            latest = s.execute(text("SELECT max(week_start) FROM weather_weekly")).scalar()

        run.raw_rows = daily.days
        run.loaded_rows = totals["inserted"] + totals["updated"]
        run.report.update({
            "source": {"url": open_meteo.API_URL, "model": open_meteo.MODEL},
            "areas": len(plan) + len(skipped),
            "areas_planned": len(plan),
            "areas_updated": len(done),
            "areas_still_behind": behind,
            "areas_skipped_no_point": skipped,
            "areas_failed": failed,
            "stopped_early": stopped,
            "weighted_calls": round(quota.used, 1),
            "fetch_to": end.isoformat(),
            "daily": {"days": daily.days, "missing": daily.missing,
                      "implausible": daily.implausible},
            "incomplete_weeks_dropped": totals["dropped"],
            "weeks_staged": totals["weeks"],
            "inserted": totals["inserted"],
            "updated": totals["updated"],
            "unchanged": totals["weeks"] - totals["inserted"] - totals["updated"],
            "latest_week": latest.isoformat() if latest else None,
        })
        return run.report
