"""Inputs for detection: weekly rows for every country with data, country metadata,
season assignment."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd
from sqlalchemy import Engine, text

from ei_pipeline.detection import config as cfg


@dataclass
class DetectionData:
    weekly: pd.DataFrame       # iso3, week_start, tests, positives, is_provisional, p, …
    countries: pd.DataFrame    # iso3, name, flu_season, lon, lat, has_geom
    disease_id: int
    reference_week: date
    latest_week: date


def season_start_year(week_start: pd.Series, season_type: pd.Series) -> pd.Series:
    """Season of each week: NH runs ISO week 40 → week 39 (start year = ISO year of
    week 40); SH and YR follow the ISO year."""
    iso = week_start.dt.isocalendar()
    nh = (season_type == "NH") & (iso["week"] < cfg.NH_START_WEEK)
    return (iso["year"] - nh.astype(int)).astype(int)


def season_first_week(year: int, season_type: str) -> date:
    week = cfg.NH_START_WEEK if season_type == "NH" else 1
    return date.fromisocalendar(year, week, 1)


def season_label(year: int, season_type: str) -> str:
    return f"{year}/{(year + 1) % 100:02d}" if season_type == "NH" else str(year)


def covid_disrupted(first: date, last: date) -> bool:
    return first <= cfg.COVID_END and last >= cfg.COVID_START


def load_detection_data(engine: Engine, disease_key: str = "influenza") -> DetectionData:
    with engine.connect() as c:
        disease_id, reference, latest = c.execute(text("""
            SELECT d.id,
              (SELECT max(week_start) FROM surveillance_weekly
                WHERE disease_id = d.id AND NOT is_provisional),
              (SELECT max(week_start) FROM surveillance_weekly WHERE disease_id = d.id)
            FROM diseases d WHERE d.key = :k
        """), {"k": disease_key}).one()
        if reference is None:
            raise RuntimeError("No surveillance data; run `ei ingest all` first.")
        countries = pd.read_sql(text("""
            SELECT iso3, name, flu_season, ST_X(centroid) AS lon, ST_Y(centroid) AS lat,
                   geom IS NOT NULL AS has_geom
            FROM countries ORDER BY iso3
        """), c)
        weekly = pd.read_sql(text("""
            SELECT iso3, week_start, specimens_tested AS tests, positives, is_provisional
            FROM surveillance_weekly
            WHERE disease_id = :d AND week_start >= :start
            ORDER BY iso3, week_start
        """), c, params={"d": disease_id, "start": cfg.HISTORY_START})
    weekly["week_start"] = pd.to_datetime(weekly["week_start"])
    ok = (weekly["tests"] >= cfg.MIN_TESTS) & weekly["positives"].notna() & (
        weekly["positives"] <= weekly["tests"])
    weekly["p"] = (weekly["positives"] / weekly["tests"]).where(ok)
    weekly["covid"] = weekly["week_start"].between(pd.Timestamp(cfg.COVID_START),
                                                   pd.Timestamp(cfg.COVID_END))
    weekly["is_provisional"] = weekly["is_provisional"].fillna(False).astype(bool)
    return DetectionData(weekly=weekly, countries=countries, disease_id=disease_id,
                         reference_week=reference, latest_week=latest)


def as_dates(s: pd.Series) -> np.ndarray:
    return s.dt.date.to_numpy()
