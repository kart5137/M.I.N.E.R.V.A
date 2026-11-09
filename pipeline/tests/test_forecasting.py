"""Forecasting: leakage, baselines, conformal maths, selection, and one end-to-end run."""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest
from sqlalchemy import text

from ei_pipeline.forecasting import config as cfg
from ei_pipeline.forecasting.backtest import conformal_quantiles, origins
from ei_pipeline.forecasting.data import Panel, build_calendar
from ei_pipeline.forecasting.evaluation import select
from ei_pipeline.forecasting.features import FEATURES, build_frames
from ei_pipeline.forecasting.models import P_CLIP, interval, training_rows

LATEST = date(2025, 6, 30)


def _rows(codes=("AAA", "BBB", "CCC"), latest=LATEST, seed=0):
    """Seasonal positivity with noise; ~1,000 specimens a week."""
    rng = np.random.default_rng(seed)
    weeks = pd.date_range(cfg.HISTORY_START, latest, freq="7D")
    out = []
    for i, code in enumerate(codes):
        phase = i * 0.7
        p = 0.08 + 0.07 * np.sin(2 * np.pi * np.arange(len(weeks)) / 52.18 + phase)
        p = np.clip(p + rng.normal(0, 0.01, len(weeks)), 0.0, 0.9)
        tests = rng.integers(800, 1200, len(weeks)).astype(float)
        out.append(pd.DataFrame({"iso3": code, "week_start": weeks, "tests": tests,
                                 "positives": np.round(p * tests), "is_provisional": False}))
    return pd.concat(out, ignore_index=True)


def _panel(rows=None, latest=LATEST):
    rows = _rows() if rows is None else rows
    codes = sorted(rows["iso3"].unique())
    n = len(codes)
    countries = pd.DataFrame({"iso3": codes, "name": codes, "flu_season": ["NH", "SH", "YR"][:n],
                              "transmission_zone": "Z1", "lat": [50.0, -30.0, 5.0][:n],
                              "tier": "A"})
    return Panel(weekly=build_calendar(rows, codes, latest), countries=countries, disease_id=1,
                 reference_week=latest, latest_week=latest)


# ---------- data ----------

def test_calendar_masks_low_testing_covid_and_gaps():
    rows = _rows(codes=("AAA",))
    rows = rows[rows["week_start"] != pd.Timestamp("2019-01-07")]          # a gap
    rows.loc[rows["week_start"] == pd.Timestamp("2019-02-04"), "tests"] = 5  # too few tests
    df = build_calendar(rows, ["AAA"], LATEST).set_index("week_start")
    assert np.isnan(df.loc["2019-01-07", "y"])          # gap stays missing
    assert np.isnan(df.loc["2019-02-04", "p"])          # < MIN_TESTS
    assert not df.loc["2021-01-04", "trainable"]         # COVID window
    assert df.loc["2019-03-04", "trainable"]


# ---------- features ----------

def test_features_do_not_use_future_data():
    origin = pd.Timestamp("2024-11-04")
    before = build_frames(_panel(), cfg.HORIZONS)
    rows = _rows()
    future = rows["week_start"] > origin
    rows.loc[future, "positives"] = rows.loc[future, "tests"] * 0.85     # change the future
    after = build_frames(_panel(rows), cfg.HORIZONS)
    for h in cfg.HORIZONS:
        a = before[h].set_index(["iso3", "origin"]).loc[(slice(None), origin), FEATURES]
        b = after[h].set_index(["iso3", "origin"]).loc[(slice(None), origin), FEATURES]
        pd.testing.assert_frame_equal(a, b)
        # ...while the target did change
        ta = before[h].set_index(["iso3", "origin"]).loc[(slice(None), origin), "actual_p"]
        tb = after[h].set_index(["iso3", "origin"]).loc[(slice(None), origin), "actual_p"]
        assert (tb > ta).all()


def test_baselines_and_target_alignment():
    panel = _panel()
    w = panel.weekly.set_index(["iso3", "week_start"])["p"]
    o = pd.Timestamp("2024-11-04")
    for h in cfg.HORIZONS:
        r = build_frames(panel, [h])[h].set_index(["iso3", "origin"]).loc[("AAA", o)]
        assert r["bl_last_value"] == pytest.approx(w[("AAA", o)])
        assert r["bl_seasonal_naive"] == pytest.approx(w[("AAA", o + pd.Timedelta(weeks=h - 52))])
        assert r["actual_p"] == pytest.approx(w[("AAA", o + pd.Timedelta(weeks=h))])
        assert r["target_week"] == o + pd.Timedelta(weeks=h)


def test_training_rows_end_at_cutoff():
    frame = build_frames(_panel(), [4])[4]
    cutoff = pd.Timestamp("2024-12-02")
    rows = training_rows(frame, cutoff)
    assert rows["target_week"].max() <= cutoff
    assert rows["origin"].max() <= cutoff - pd.Timedelta(weeks=4)
    assert rows["target_week"].min() >= pd.Timestamp(cfg.TRAIN_START)


def test_origins():
    os_ = origins(date(2025, 1, 6), horizon=2)
    assert os_[0] == pd.Timestamp(cfg.BACKTEST_START)
    assert os_[-1] <= pd.Timestamp("2024-12-23")
    assert all((b - a).days == 7 * cfg.ORIGIN_STEP for a, b in zip(os_, os_[1:], strict=False))


# ---------- intervals and selection ----------

def test_conformal_quantile_is_finite_sample_corrected():
    q = conformal_quantiles(np.arange(1, 10, dtype=float))  # n = 9
    assert q[0.80] == 8.0   # ceil(10 · 0.8) = 8th smallest
    assert q[0.95] == 9.0


def test_interval_reaches_zero_when_bound_hits_clip():
    lo, hi = interval(np.array([-5.0, 0.0]), np.array([10.0, 0.1]))
    assert lo[0] == 0.0 and 0 < lo[1] < 0.5 < hi[1] < 1
    assert hi[0] < 1 and P_CLIP[0] > 0


def _evals(rows):
    return pd.DataFrame([{"model": m, "horizon": h, "iso3": None, "metric": k, "value": v}
                         for m, h, mase, skill, mae in rows
                         for k, v in (("mase", mase), ("skill_vs_snaive", skill), ("mae", mae))])


def test_selection_keeps_seasonal_naive_unless_beaten():
    sel = select(_evals([("seasonal_naive", 1, 0.9, 0.0, 0.09), ("xgboost", 1, 0.95, -0.05, 0.095),
                         ("seasonal_naive", 2, 0.9, 0.0, 0.09), ("xgboost", 2, 0.5, 0.4, 0.05),
                         ("last_value", 2, 0.6, 0.3, 0.06)]))
    assert sel[1].active == "seasonal_naive" and "stays active" in sel[1].note
    assert sel[2].active == "xgboost" and "last value" in sel[2].note


# ---------- end to end ----------

def _seed_db(engine):
    from ei_pipeline.catalog import seed_reference
    from ei_pipeline.db import session_scope

    with session_scope(engine) as s:
        seed_reference(s)
    rows = _rows(latest=date(2025, 3, 31))
    with engine.begin() as c:
        c.execute(text("INSERT INTO ingestion_runs (id, source_id, status) "
                       "SELECT 1, id, 'succeeded' FROM data_sources WHERE key = 'flunet'"))
        for code, season, lat in (("AAA", "NH", 50), ("BBB", "SH", -30), ("CCC", "YR", 5)):
            c.execute(text("""
                INSERT INTO countries (iso3, name, flu_season, transmission_zone, centroid)
                VALUES (:c, :n, :s, 'Z1', ST_SetSRID(ST_MakePoint(0, :lat), 4326))
            """), {"c": code, "n": code, "s": season, "lat": lat})
            c.execute(text("""
                INSERT INTO coverage_profiles (disease_id, iso3, reference_week, tier,
                  completeness, longest_gap)
                SELECT id, :c, '2025-03-31', 'A', 1, 0 FROM diseases WHERE key = 'influenza'
            """), {"c": code})
        recs = rows.assign(
            week_start=rows["week_start"].dt.date,
            iso_year=rows["week_start"].dt.isocalendar().year.astype(int),
            iso_week=rows["week_start"].dt.isocalendar().week.astype(int),
            positivity=rows["positives"] / rows["tests"],
        ).to_dict("records")
        c.execute(text("""
            INSERT INTO surveillance_weekly (disease_id, iso3, week_start, iso_year, iso_week,
              specimens_tested, positives, positivity, source_id, ingestion_run_id)
            SELECT d.id, :iso3, :week_start, :iso_year, :iso_week, :tests, :positives,
                   :positivity, ds.id, 1
            FROM diseases d, data_sources ds WHERE d.key = 'influenza' AND ds.key = 'flunet'
        """), recs)


def _q(engine, sql):
    with engine.connect() as c:
        return c.execute(text(sql)).scalar()


def test_end_to_end_run_writes_registry_and_forecasts(db, tmp_path):
    from ei_pipeline.forecasting.run import run_forecast

    _seed_db(db)
    summary = run_forecast(db, fast=True, artefact_root=tmp_path / "models",
                           card_path=tmp_path / "card.md")
    n_models = len(cfg.BASELINES) + len(cfg.ML_MODELS)
    assert _q(db, "SELECT count(*) FROM model_versions") == n_models * len(cfg.HORIZONS)
    assert _q(db, "SELECT count(*) FROM model_versions WHERE is_active") == len(cfg.HORIZONS)
    # Every backtest prediction targets origin + horizon and was made after training data.
    assert _q(db, """
        SELECT count(*) FROM backtest_predictions b JOIN model_versions v
          ON v.id = b.model_version_id
        WHERE b.target_week <> b.origin_week + 7 * v.horizon_weeks""") == 0
    # Forecasts: 3 countries × every model × every horizon, from the reference week.
    assert summary["forecasts"] == 3 * n_models * len(cfg.HORIZONS)
    assert _q(db, "SELECT count(DISTINCT origin_week) FROM forecasts") == 1
    assert _q(db, "SELECT bool_and(lo95 <= lo80 AND lo80 <= point AND point <= hi80 "
                  "AND hi80 <= hi95) FROM forecasts")
    # ML forecasts carry top-k explanations; baselines carry none.
    assert _q(db, """SELECT count(*) FROM forecast_explanations e JOIN forecasts f
                     ON f.id = e.forecast_id JOIN model_versions v ON v.id = f.model_version_id
                     WHERE v.kind = 'baseline'""") == 0
    assert _q(db, "SELECT max(rank) FROM forecast_explanations") == cfg.TOP_K_EXPLANATIONS
    assert (tmp_path / "card.md").read_text(encoding="utf-8").startswith("# Model card")
    assert any((tmp_path / "models").rglob("xgboost_h1.json"))

    # A second run deactivates the first.
    run_forecast(db, fast=True, artefact_root=tmp_path / "models", card_path=None)
    assert _q(db, "SELECT count(*) FROM model_versions WHERE is_active") == len(cfg.HORIZONS)
    assert _q(db, "SELECT count(DISTINCT run_key) FROM model_versions") == 2


def test_group_quantiles_per_testing_volume_with_fallback():
    from ei_pipeline.forecasting.backtest import group_quantiles, volume_group

    assert list(volume_group([10, 50, 199, 200, 5000, np.nan])) == [0, 1, 1, 2, 3, 0]
    n = cfg.CONFORMAL_MIN_GROUP
    scores = pd.DataFrame({
        "score": np.r_[np.full(n, 4.0), np.full(n, 0.5), [9.0]],
        "volume_group": np.r_[np.zeros(n, int), np.full(n, 3), [2]],
    })
    q = group_quantiles(scores)
    assert q[0][0.8] == 4.0          # noisy low-volume group keeps its own, wide quantile
    assert q[3][0.8] == 0.5          # high-volume group is not widened by it
    assert q[2] == q[1]              # too few scores (1 and 0): both fall back to pooled
