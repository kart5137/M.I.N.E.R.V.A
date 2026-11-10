"""Load the modelling panel: eligible countries × a complete weekly calendar.

Influenza (M5): positivity from FluNet. Dengue (D4): weekly incidence per 100,000 from
WHO dengue cases and World Bank population, joined with lagged ERA5 weather features."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd
from sqlalchemy import Engine, text

from ei_pipeline import weather
from ei_pipeline.detection.weights import Neighbours, load_geography, neighbours
from ei_pipeline.forecasting import config as cfg
from ei_pipeline.forecasting import dengue_config as dcfg
from ei_pipeline.forecasting.spec import expit, log_incidence, logit  # noqa: F401

#: Same k as the hotspot weights.
KNN_K = 4


@dataclass
class Panel:
    #: One row per (iso3, week_start) on a complete calendar. `p` is the target on its
    #: natural scale (positivity 0–1, or dengue incidence per 100,000), `y` on the model
    #: scale, `volume` the weekly specimens (influenza) or cases (dengue).
    weekly: pd.DataFrame
    countries: pd.DataFrame    # iso3, name, flu_season, transmission_zone, lat, tier
    disease_id: int
    reference_week: date
    latest_week: date
    #: Spatial neighbours among the modelled countries (None in unit tests without
    #: geometry).
    neighbours: Neighbours | None = None


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
    df["volume"] = df["tests"]
    return df


# ---------- dengue (D4) ----------

def load_dengue_panel(engine: Engine) -> Panel:
    """Weekly dengue reporters in coverage tiers A/B that have a population."""
    with engine.connect() as c:
        disease_id, reference, latest = c.execute(text("""
            SELECT d.id,
              (SELECT max(week_start) FROM surveillance_weekly
                WHERE disease_id = d.id AND NOT is_provisional),
              (SELECT max(week_start) FROM surveillance_weekly WHERE disease_id = d.id)
            FROM diseases d WHERE d.key = 'dengue'
        """)).one()
        if reference is None:
            raise RuntimeError("No dengue data; run `ei ingest dengue` first.")
        countries = pd.read_sql(text("""
            SELECT c.iso3, c.name, c.flu_season, c.transmission_zone,
                   ST_Y(c.centroid) AS lat, cp.tier
            FROM coverage_profiles cp JOIN countries c ON c.iso3 = cp.iso3
            WHERE cp.disease_id = :d AND cp.tier = ANY(:tiers) AND cp.grain = 'week'
              AND cp.reference_week = (SELECT max(reference_week) FROM coverage_profiles
                                       WHERE disease_id = :d)
              AND EXISTS (SELECT 1 FROM population_annual pa WHERE pa.iso3 = c.iso3)
            ORDER BY c.iso3
        """), c, params={"d": disease_id, "tiers": list(dcfg.ELIGIBLE_TIERS)})
        codes = countries["iso3"].tolist()
        rows = pd.read_sql(text("""
            SELECT iso3, week_start, cases, is_provisional FROM surveillance_weekly
            WHERE disease_id = :d AND iso3 = ANY(:codes) AND week_start >= :start
        """), c, params={"d": disease_id, "codes": codes, "start": cfg.HISTORY_START})
        population = pd.read_sql(text("""
            SELECT iso3, year, population::float8 AS population FROM population_annual
            WHERE iso3 = ANY(:codes) AND population > 0
        """), c, params={"codes": codes})
        wx = pd.read_sql(text("""
            SELECT iso3, week_start, temperature, precipitation, humidity
            FROM weather_weekly WHERE iso3 = ANY(:codes)
        """), c, params={"codes": codes})
    weekly = build_dengue_calendar(rows, population, codes, latest)
    weekly = attach_weather(weekly, weather_features(wx))
    nb = neighbours(load_geography(engine), codes, KNN_K)
    return Panel(weekly=weekly, countries=countries, disease_id=disease_id,
                 reference_week=reference, latest_week=latest, neighbours=nb)


def population_by_week(population: pd.DataFrame, iso3: pd.Series,
                       week_start: pd.Series) -> np.ndarray:
    """Population of the latest year up to the week's year; the earliest year before
    the first one available (the API's rule, app/queries/cases.py)."""
    year = week_start.dt.year.to_numpy()
    out = np.full(len(iso3), np.nan)
    codes = iso3.to_numpy()
    for code, g in population.sort_values("year").groupby("iso3"):
        mask = codes == code
        years, pops = g["year"].to_numpy(), g["population"].to_numpy()
        idx = np.searchsorted(years, year[mask], side="right") - 1
        out[mask] = pops[np.clip(idx, 0, None)]
    return out


def build_dengue_calendar(rows: pd.DataFrame, population: pd.DataFrame, codes,
                          latest: date) -> pd.DataFrame:
    """Every Monday from HISTORY_START to `latest` per country. Missing weeks stay
    missing (never zero-filled).

    - `p`: incidence = cases / population × 100,000 (cases ≥ 0, population known).
    - `offset`: one case per 100,000 population (100,000 ÷ population).
    - `y`: log(incidence + offset), i.e. log(cases + 1) − log(population / 100,000).
    - `trainable`: `y` usable as a target (not provisional). COVID-19 weeks are kept:
      dengue transmission and reporting continued, unlike influenza circulation.
    """
    weeks = pd.date_range(cfg.HISTORY_START, latest, freq="7D")
    idx = pd.MultiIndex.from_product([sorted(codes), weeks], names=["iso3", "week_start"])
    rows = rows.assign(week_start=pd.to_datetime(rows["week_start"]))
    df = rows.set_index(["iso3", "week_start"]).reindex(idx).reset_index()
    df["population"] = population_by_week(population, df["iso3"], df["week_start"])
    ok = df["cases"].notna() & (df["cases"] >= 0) & (df["population"] > 0)
    df["p"] = (df["cases"] / df["population"] * 1e5).where(ok)
    df["offset"] = 1e5 / df["population"]
    df["y"] = pd.Series(log_incidence(df["p"], df["offset"]), index=df.index).where(ok)
    df["is_provisional"] = df["is_provisional"].astype("boolean").fillna(False).astype(bool)
    df["trainable"] = ok & ~df["is_provisional"]
    df["volume"] = df["cases"]
    return df


def anomaly_name(col: str) -> str:
    """`temperature_mean4_lag8` → `temperature_anom4_lag8`."""
    var, rest = col.split("_", 1)
    return f"{var}_anom{rest.removeprefix('mean').removeprefix('sum')}"


def _weather_columns() -> list[str]:
    w, out = dcfg.WEATHER_WINDOW, []
    for lag in dcfg.WEATHER_LAGS:
        out += [f"temperature_mean{w}_lag{lag}", f"precipitation_sum{w}_lag{lag}",
                f"humidity_mean{w}_lag{lag}"]
    return out + [anomaly_name(c) for c in out]


#: Weather feature columns: 9 lagged values, then their 9 anomalies.
WEATHER_COLUMNS = _weather_columns()


def weather_features(wx: pd.DataFrame) -> pd.DataFrame:
    """Lagged 4-week weather windows (weather.lagged_features) and their anomalies: the
    value minus the country's mean for the same ISO week over NORMAL_YEARS (week 53 uses
    week 52). Weather is exogenous, so the normal period may overlap training targets."""
    if wx.empty:
        return pd.DataFrame(columns=["iso3", "week_start", *WEATHER_COLUMNS])
    wx = wx.assign(week_start=pd.to_datetime(wx["week_start"]))
    f = weather.lagged_features(wx, window=dcfg.WEATHER_WINDOW, lags=dcfg.WEATHER_LAGS)
    values = WEATHER_COLUMNS[:len(WEATHER_COLUMNS) // 2]
    week = f["week_start"].dt.isocalendar().week.clip(upper=52).astype(int).rename("woy")
    in_normal = f["week_start"].dt.year.between(*dcfg.NORMAL_YEARS)
    normals = f[in_normal].groupby([f["iso3"], week])[values].mean()
    keyed = pd.MultiIndex.from_arrays([f["iso3"], week])
    for col in values:
        f[anomaly_name(col)] = f[col].to_numpy() - normals[col].reindex(keyed).to_numpy()
    return f


def attach_weather(weekly: pd.DataFrame, features: pd.DataFrame) -> pd.DataFrame:
    """Left-join weather features on (iso3, week_start); missing weather stays NaN."""
    features = features.assign(week_start=pd.to_datetime(features["week_start"]))
    return weekly.merge(features[["iso3", "week_start", *WEATHER_COLUMNS]],
                        on=["iso3", "week_start"], how="left")
