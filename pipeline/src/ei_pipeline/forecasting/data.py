"""Load the modelling panel: eligible countries × a complete weekly calendar."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd
from sqlalchemy import Engine, text

from ei_pipeline.detection.weights import Neighbours, load_geography, neighbours
from ei_pipeline.forecasting import config as cfg

#: Same k as the hotspot weights.
KNN_K = 4


@dataclass
class Panel:
    weekly: pd.DataFrame       # one row per (iso3, week_start), complete calendar
    countries: pd.DataFrame    # iso3, name, flu_season, transmission_zone, lat, tier
    disease_id: int
    reference_week: date
    latest_week: date
    #: Spatial neighbours among the modelled countries (None in unit tests without
    #: geometry).
    neighbours: Neighbours | None = None


def logit(p):
    return np.log(p / (1 - p))


def expit(x):
    return 1 / (1 + np.exp(-x))


def load_panel(engine: Engine, disease_key: str = "influenza") -> Panel:
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
            SELECT c.iso3, c.name, c.flu_season, c.transmission_zone,
                   ST_Y(c.centroid) AS lat, cp.tier
            FROM coverage_profiles cp JOIN countries c ON c.iso3 = cp.iso3
            WHERE cp.disease_id = :d AND cp.tier = ANY(:tiers)
              AND cp.reference_week = (SELECT max(reference_week) FROM coverage_profiles
                                       WHERE disease_id = :d)
            ORDER BY c.iso3
        """), c, params={"d": disease_id, "tiers": list(cfg.ELIGIBLE_TIERS)})
        rows = pd.read_sql(text("""
            SELECT iso3, week_start, specimens_tested AS tests, positives, is_provisional
            FROM surveillance_weekly
            WHERE disease_id = :d AND iso3 = ANY(:codes) AND week_start >= :start
        """), c, params={"d": disease_id, "codes": countries["iso3"].tolist(),
                         "start": cfg.HISTORY_START})
    nb = neighbours(load_geography(engine), countries["iso3"].tolist(), KNN_K)
    return Panel(weekly=build_calendar(rows, countries["iso3"], latest),
                 countries=countries, disease_id=disease_id,
                 reference_week=reference, latest_week=latest, neighbours=nb)


def build_calendar(rows: pd.DataFrame, codes, latest: date) -> pd.DataFrame:
    """Reindex to every Monday from HISTORY_START to `latest` for every country, and
    derive the modelling columns. Missing weeks stay missing (never zero-filled).

    - `p`: observed positivity (positives / tests) when tests ≥ MIN_TESTS, else NaN.
    - `y`: logit of smoothed positivity (positives + 0.5) / (tests + 1), same mask.
    - `trainable`: `y` is usable as a training/evaluation target (not provisional,
      not in the COVID window).
    """
    weeks = pd.date_range(cfg.HISTORY_START, latest, freq="7D")
    idx = pd.MultiIndex.from_product([sorted(codes), weeks], names=["iso3", "week_start"])
    rows = rows.assign(week_start=pd.to_datetime(rows["week_start"]))
    df = rows.set_index(["iso3", "week_start"]).reindex(idx).reset_index()

    tests, pos = df["tests"], df["positives"]
    ok = (tests >= cfg.MIN_TESTS) & pos.notna() & (pos <= tests)
    df["p"] = (pos / tests).where(ok)
    smoothed = ((pos + 0.5) / (tests + 1)).where(ok)  # in (0, 1) wherever ok
    df["y"] = logit(smoothed)
    covid = df["week_start"].between(pd.Timestamp(cfg.COVID_START), pd.Timestamp(cfg.COVID_END))
    df["is_provisional"] = df["is_provisional"].astype("boolean").fillna(False).astype(bool)
    df["trainable"] = ok & ~covid & ~df["is_provisional"]
    return df
