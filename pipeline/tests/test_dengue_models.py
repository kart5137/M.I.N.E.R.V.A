"""Dengue forecasting and detection (D4): incidence panel, weather features, the
change-from-this-week target, the weather comparison, dengue detection rules, and an
end-to-end run that leaves influenza's outputs alone."""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest
from sqlalchemy import text

from ei_pipeline.detection import config as dcfg
from ei_pipeline.detection.anomalies import seasonal_ewma_anomalies
from ei_pipeline.detection.hotspots import window_values
from ei_pipeline.detection.thresholds import compute_thresholds, quality_issue
from ei_pipeline.forecasting import config as cfg
from ei_pipeline.forecasting import spec as specs
from ei_pipeline.forecasting.data import (
    WEATHER_COLUMNS,
    anomaly_name,
    build_dengue_calendar,
    weather_features,
)
from ei_pipeline.forecasting.models import fit, predict_p
from ei_pipeline.forecasting.report import weather_comparison, weather_verdict
from ei_pipeline.intelligence.alerts import dengue_growth_alerts

LATEST = date(2025, 6, 30)


# ---------- panel ----------

def test_dengue_calendar_incidence_offset_and_population_rule():
    weeks = pd.date_range("2013-01-07", LATEST, freq="7D")
    rows = pd.DataFrame({"iso3": "AAA", "week_start": weeks, "cases": 50.0,
                         "is_provisional": False})
    rows = rows[rows["week_start"] != pd.Timestamp("2019-01-07")]          # a gap
    rows.loc[rows["week_start"] == pd.Timestamp("2019-02-04"), "cases"] = np.nan
    rows.loc[rows["week_start"] == pd.Timestamp("2025-06-30"), "is_provisional"] = True
    pop = pd.DataFrame({"iso3": "AAA", "year": [2015, 2020], "population": [1e6, 2e6]})
    df = build_dengue_calendar(rows, pop, ["AAA"], LATEST).set_index("week_start")
    # Before the first population year: the earliest; afterwards the latest year ≤ week's.
    assert df.loc["2014-01-06", "population"] == 1e6
    assert df.loc["2019-03-04", "population"] == 1e6
    assert df.loc["2024-03-04", "population"] == 2e6
    assert df.loc["2016-03-07", "p"] == pytest.approx(5.0)               # 50 / 1e6 × 1e5
    assert df.loc["2016-03-07", "offset"] == pytest.approx(0.1)          # one case
    assert df.loc["2016-03-07", "y"] == pytest.approx(np.log(51 / 10))   # log(cases+1) − log(10)
    assert np.isnan(df.loc["2019-01-07", "y"]) and np.isnan(df.loc["2019-02-04", "y"])
    assert not df.loc["2025-06-30", "trainable"]
    assert df.loc["2021-01-04", "trainable"]                             # COVID weeks kept


def test_log_incidence_round_trip_and_interval_floor():
    sp = specs.dengue()
    off = np.array([0.1, 0.001])
    v = np.array([0.0, 12.5])
    assert sp.from_y(sp.to_y(v, off), off) == pytest.approx(v)
    lo, hi = sp.interval(sp.to_y(np.array([0.0, 1.0]), off), np.array([3.0, 0.5]), off)
    assert lo[0] == 0.0 and hi[0] > 0 and 0 < lo[1] < 1 < hi[1]


def test_weather_features_lag_and_anomaly_from_normal():
    weeks = pd.date_range("2013-01-07", "2025-12-29", freq="W-MON")
    woy = weeks.isocalendar().week.to_numpy().astype(float)
    temp = 25 + 3 * np.sin(2 * np.pi * woy / 52) + np.where(weeks.year >= 2024, 2.0, 0.0)
    wx = pd.DataFrame({"iso3": "AAA", "week_start": weeks, "temperature": temp,
                       "precipitation": 10.0, "humidity": 80.0})
    f = weather_features(wx).set_index("week_start")
    assert anomaly_name("precipitation_sum4_lag8") == "precipitation_anom4_lag8"
    assert set(WEATHER_COLUMNS) <= set(f.columns) and len(WEATHER_COLUMNS) == 18
    t = pd.Timestamp("2018-06-04")
    window = wx.set_index("week_start").loc[t - pd.Timedelta(weeks=7): t - pd.Timedelta(weeks=4)]
    assert f.loc[t, "temperature_mean4_lag4"] == pytest.approx(window["temperature"].mean())
    assert f.loc[t, "precipitation_sum4_lag4"] == pytest.approx(40.0)
    # 2013–2022 normal: no anomaly then, +2 °C once the shift is fully in the window.
    assert abs(f.loc[t, "temperature_anom4_lag4"]) < 0.05
    late = f.loc[pd.Timestamp("2025-06-02"), "temperature_anom4_lag4"]
    assert late == pytest.approx(2.0, abs=0.05)


# ---------- models ----------

def test_change_target_extrapolates_beyond_training_levels():
    """Trees predicting the level cannot exceed the training range; the change target
    can (dengue reaches record levels)."""
    rng = np.random.default_rng(0)
    n = 400
    lag0 = rng.uniform(0, 1, n)
    frame = pd.DataFrame({
        "origin": pd.date_range("2015-01-05", periods=n, freq="7D"),
        "y_lag0": lag0, "actual_y": lag0 + 0.5, "trainable": True,
    })
    frame["target_week"] = frame["origin"] + pd.Timedelta(weeks=1)
    sp = specs.TargetSpec(disease="dengue", target="incidence", features=("y_lag0",),
                          to_y=specs.log_incidence, from_y=specs.from_log_incidence,
                          delta_target=True)
    level = specs.TargetSpec(**{**sp.__dict__, "delta_target": False})
    new = pd.DataFrame({"y_lag0": [5.0], "offset": [1.0]})
    cutoff = frame["target_week"].max()
    m_delta, _ = fit("random_forest", frame, cutoff, cfg.FAST, sp)
    m_level, _ = fit("random_forest", frame, cutoff, cfg.FAST, level)
    y_delta = np.log(predict_p(m_delta, new, sp)[0] + 1)
    y_level = np.log(predict_p(m_level, new, level)[0] + 1)
    assert y_delta == pytest.approx(5.5, abs=0.05)
    assert y_level < 1.6


def test_weather_comparison_detects_a_real_improvement():
    rng = np.random.default_rng(1)
    rows = []
    for o in pd.date_range("2024-10-07", periods=30, freq="14D"):
        for iso3 in ("AAA", "BBB", "CCC"):
            actual = rng.uniform(1, 10)
            for model, err in (("xgboost", 2.0), ("xgboost_weather", 1.0)):
                rows.append({"model": model, "horizon": 1, "iso3": iso3, "origin": o,
                             "actual_p": actual,
                             "point": actual + err * rng.choice([-1, 1])})
    cmp_ = weather_comparison(pd.DataFrame(rows))
    r = cmp_.iloc[0]
    assert r["change"] == pytest.approx(-0.5) and r["ci_high"] < 0
    assert weather_verdict(r) == "weather helps" and r["countries_better"] == 3


# ---------- detection ----------

def _incidence_weekly(iso3="AAA", start=date(2013, 1, 7), end=date(2025, 12, 29),
                      peak_week=20, population=1e6, seed=0):
    rng = np.random.default_rng(seed)
    weeks = pd.date_range(start, end, freq="7D")
    iso_w = weeks.isocalendar().week.to_numpy().astype(float)
    dist = np.minimum(np.abs(iso_w - peak_week), 52 - np.abs(iso_w - peak_week))
    cases = np.round(20 + 400 * np.exp(-0.5 * (dist / 4) ** 2) * rng.lognormal(0, 0.1, len(weeks)))
    df = pd.DataFrame({"iso3": iso3, "week_start": weeks, "cases": cases,
                       "is_provisional": False, "covid": False})
    df["population"] = population
    df["p"] = df["cases"] / population * 1e5
    df["offset"] = 1e5 / population
    df["volume"] = df["cases"]
    return df


def test_dengue_anomaly_on_log_scale_reports_incidence():
    df = _incidence_weekly()
    surge = df["week_start"].between("2025-09-01", "2025-09-29")      # off-season, 5 weeks
    df.loc[surge, "cases"] = 300
    df["p"] = df["cases"] / df["population"] * 1e5
    flagged, _ = seasonal_ewma_anomalies("AAA", df, dcfg.DENGUE)
    weeks = {a.week_start for a in flagged}
    assert {date(2025, 9, 1) + pd.Timedelta(weeks=i).to_pytimedelta() for i in range(5)} <= weeks
    a = next(a for a in flagged if a.week_start == date(2025, 9, 1))
    assert a.observed == pytest.approx(30.0)                           # per 100,000
    # Flat off-season (20 cases): expected = upper band = 2 per 100,000.
    assert a.expected == pytest.approx(2.0) and a.upper_band == pytest.approx(2.0)
    assert a.specimens_tested is None and a.severity == "severe"


def test_dengue_thresholds_use_calendar_years_including_covid():
    weekly = _incidence_weekly(end=date(2026, 3, 30))
    countries = pd.DataFrame({"iso3": ["AAA"], "name": ["a"], "flu_season": [None],
                              "season_type": [dcfg.DENGUE_SEASON]})
    rows, not_assessed = compute_thresholds(weekly, countries, date(2026, 3, 30),
                                            date(2026, 3, 30), dcfg.DENGUE)
    current = rows[-1]
    assert current.season == "2026" and current.season_start == date(2025, 12, 29)
    assert {"2020", "2021"} <= set(current.seasons_used)
    assert current.quality_note is None and not not_assessed
    assert 2.0 < current.epidemic_threshold < current.medium < current.high   # per 100,000
    # Incidence has no 100% ceiling; positivity does.
    assert quality_issue(10, 20, 30, 400, "incidence") is None
    assert "100%" in quality_issue(10, 20, 30, 400)


def test_dengue_hotspot_values_need_two_reported_weeks():
    a = _incidence_weekly("AAA", start=date(2025, 1, 6), end=date(2025, 2, 24))
    b = _incidence_weekly("BBB", start=date(2025, 1, 6), end=date(2025, 2, 24))
    b.loc[b["week_start"] < pd.Timestamp("2025-02-24"), "p"] = np.nan  # 1 of 4 weeks
    v = window_values(pd.concat([a, b]), date(2025, 2, 24), 4, dcfg.DENGUE)
    last4 = a[a["week_start"] >= pd.Timestamp("2025-02-03")]["p"].mean()
    assert list(v.index) == ["AAA"] and v["AAA"] == pytest.approx(last4)


def test_dengue_growth_rule_is_relative_with_minimum_cases():
    w = list(pd.date_range("2025-03-03", periods=6, freq="7D").date)

    def weekly(cases, weeks=w):
        return pd.DataFrame({"iso3": "AAA", "name": "Alpha", "week_start": weeks[:len(cases)],
                             "cases": cases, "population": 1e6, "is_provisional": False})
    out = dengue_growth_alerts(weekly([40, 50, 60, 70, 30]))
    assert [(a.week_start, a.severity) for a in out] == [(w[3], "low")]   # +75%
    assert out[0].details["rise_pct"] == 75.0
    assert dengue_growth_alerts(weekly([40, 80, 100, 120]))[0].severity == "medium"
    assert dengue_growth_alerts(weekly([40, 45, 50, 55])) == []          # +37.5%
    assert dengue_growth_alerts(weekly([5, 10, 20, 40])) == []           # < 20 cases
    gap = [w[0], w[1], w[3], w[4]]
    assert dengue_growth_alerts(weekly([40, 50, 60, 70], weeks=gap)) == []


# ---------- end to end ----------

def _seed_dengue(engine):
    """Dengue cases, population and weather for the three influenza test countries."""
    with engine.begin() as c:
        c.execute(text("""
            INSERT INTO ingestion_runs (id, source_id, status)
            SELECT 2, id, 'succeeded' FROM data_sources WHERE key = 'who_dengue';
            INSERT INTO ingestion_runs (id, source_id, status)
            SELECT 3, id, 'succeeded' FROM data_sources WHERE key = 'open_meteo_era5';
            INSERT INTO ingestion_runs (id, source_id, status)
            SELECT 4, id, 'succeeded' FROM data_sources WHERE key = 'worldbank_wdi';
        """))
        for i, code in enumerate(("AAA", "BBB", "CCC")):
            c.execute(text("""
                INSERT INTO coverage_profiles (disease_id, iso3, reference_week, tier,
                  completeness, longest_gap, grain)
                SELECT id, :c, '2025-03-31', 'A', 1, 0, 'week' FROM diseases WHERE key = 'dengue'
            """), {"c": code})
            c.execute(text("""
                INSERT INTO population_annual (iso3, year, population, source_id)
                SELECT :c, 2020, :p, id FROM data_sources WHERE key = 'worldbank_wdi'
            """), {"c": code, "p": 1_000_000 * (i + 1)})
            df = _incidence_weekly(code, end=date(2025, 3, 31), peak_week=10 + 15 * i, seed=i)
            c.execute(text("""
                INSERT INTO surveillance_weekly (disease_id, iso3, week_start, iso_year,
                  iso_week, cases, source_id, ingestion_run_id)
                SELECT d.id, :iso3, :w, :y, :k, :cases, ds.id, 2
                FROM diseases d, data_sources ds WHERE d.key = 'dengue' AND ds.key = 'who_dengue'
            """), [{"iso3": code, "w": r.week_start.date(), "y": r.week_start.isocalendar()[0],
                    "k": r.week_start.isocalendar()[1], "cases": float(r.cases)}
                   for r in df.itertuples()])
            if code == "CCC":
                continue  # one country without weather: features stay missing
            wx = [{"c": code, "w": w.date(), "y": w.isocalendar()[0], "k": w.isocalendar()[1],
                   "t": 25 + np.sin(j / 8), "p": 30.0, "h": 80.0}
                  for j, w in enumerate(df["week_start"])]
            c.execute(text("""
                INSERT INTO weather_weekly (iso3, week_start, iso_year, iso_week, temperature,
                  precipitation, humidity, source_id, ingestion_run_id)
                SELECT :c, :w, :y, :k, :t, :p, :h, id, 3 FROM data_sources
                WHERE key = 'open_meteo_era5'
            """), wx)


def _q(engine, sql):
    with engine.connect() as c:
        return c.execute(text(sql)).scalar()


def test_end_to_end_dengue_run_keeps_influenza_outputs(db, tmp_path):
    from test_forecasting import _seed_db

    from ei_pipeline.forecasting.run import run_forecast

    _seed_db(db)
    _seed_dengue(db)
    run_forecast(db, fast=True, artefact_root=tmp_path / "models", card_path=None)
    flu_bt = _q(db, "SELECT count(*) FROM backtest_predictions")
    assert flu_bt > 0

    card = tmp_path / "dengue.md"
    summary = run_forecast(db, disease="dengue", fast=True, artefact_root=tmp_path / "models",
                           card_path=card)
    sp = specs.dengue()
    n_models = len(cfg.BASELINES) + len(sp.ml_models)
    assert summary["run_key"].startswith("den-") and summary["countries"] == 3
    assert _q(db, """SELECT count(*) FROM model_versions v JOIN diseases d
                     ON d.id = v.disease_id WHERE d.key = 'dengue'""") == (
        n_models * len(cfg.HORIZONS))
    assert _q(db, """SELECT count(*) FROM model_versions v JOIN diseases d ON d.id = v.disease_id
                     WHERE d.key = 'dengue' AND v.is_active""") == len(cfg.HORIZONS)
    # Influenza's active models and backtest detail are untouched by the dengue run.
    assert _q(db, """SELECT count(*) FROM model_versions v JOIN diseases d ON d.id = v.disease_id
                     WHERE d.key = 'influenza' AND v.is_active""") == len(cfg.HORIZONS)
    assert _q(db, """SELECT count(*) FROM backtest_predictions b JOIN model_versions v
                     ON v.id = b.model_version_id JOIN diseases d ON d.id = v.disease_id
                     WHERE d.key = 'influenza'""") == flu_bt
    assert _q(db, "SELECT DISTINCT target FROM forecasts WHERE disease_id = "
                  "(SELECT id FROM diseases WHERE key = 'dengue')") == "incidence"
    assert _q(db, """SELECT bool_and(0 <= lo95 AND lo95 <= lo80 AND lo80 <= point
                       AND point <= hi80 AND hi80 <= hi95) FROM forecasts f
                     JOIN diseases d ON d.id = f.disease_id WHERE d.key = 'dengue'""")
    # Weather models record their 38 features; the others 20.
    assert _q(db, """SELECT jsonb_array_length(features) FROM model_versions
                     WHERE model_type = 'xgboost_weather' LIMIT 1""") == len(sp.features) + 18
    # Change target: the explanation starts from this week's level, per forecast.
    assert _q(db, """SELECT count(DISTINCT f.explanation_base) FROM forecasts f
                     JOIN model_versions v ON v.id = f.model_version_id
                     WHERE v.model_type = 'xgboost' AND f.disease_id =
                       (SELECT id FROM diseases WHERE key = 'dengue') AND v.horizon_weeks = 1
                  """) == 3
    text_ = card.read_text(encoding="utf-8")
    assert text_.startswith("# Model card — dengue incidence forecasts")
    assert "## Does weather help?" in text_ and "2 of 3 countries at the latest origin" in text_


def test_weather_model_needs_a_clear_benefit_to_stay_active():
    from ei_pipeline.forecasting.evaluation import Selection
    from ei_pipeline.forecasting.run import require_weather_benefit

    rng = np.random.default_rng(3)
    rows = []
    for o in pd.date_range("2024-10-07", periods=30, freq="14D"):
        for iso3 in ("AAA", "BBB"):
            actual = rng.uniform(1, 10)
            for h, err_w in ((1, 1.0), (2, 2.0)):   # h1: weather halves the error; h2: equal
                for model, err in (("xgboost", 2.0), ("xgboost_weather", err_w)):
                    rows.append({"model": model, "horizon": h, "iso3": iso3, "origin": o,
                                 "actual_p": actual, "point": actual + err})
    sel = {h: Selection(h, "xgboost_weather", "Lowest MASE.") for h in (1, 2)}
    out = require_weather_benefit(sel, pd.DataFrame(rows))
    assert out[1].active == "xgboost_weather"
    assert out[2].active == "xgboost" and "without weather is used" in out[2].note
