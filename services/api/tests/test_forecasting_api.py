"""Forecasting endpoints read stored results. A tiny run is inserted by hand:

run "R1", horizon 1: seasonal_naive (baseline) and xgboost (active, ML).
AAA has forecasts from both; the xgboost one has two SHAP contributions.
"""

from __future__ import annotations

import math

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

V1 = "/api/v1"


@pytest.fixture(scope="module")
def run(seeded_engine):
    with seeded_engine.begin() as c:
        c.execute(text("""
            INSERT INTO model_versions (id, disease_id, run_key, model_type, kind, target,
              horizon_weeks, train_start, train_end, features, hyperparams, global_importance,
              is_active, selection_note)
            VALUES
              (101, 1, 'R1', 'seasonal_naive', 'baseline', 'positivity', 1, NULL,
               '2024-02-12', NULL, NULL, NULL, false, NULL),
              (102, 1, 'R1', 'xgboost', 'ml', 'positivity', 1, '2024-01-08', '2024-02-12',
               '["y_lag0", "lat"]', '{"max_depth": 5}', '{"y_lag0": 0.6, "lat": 0.1}',
               true, 'Lowest backtest MASE.');
            INSERT INTO model_evaluations (model_version_id, iso3, metric, value, n_obs,
              n_origins, eval_start, eval_end)
            VALUES (101, NULL, 'mae', 0.08, 50, 5, '2024-01-01', '2024-02-05'),
                   (101, NULL, 'mase', 0.9, 50, 5, '2024-01-01', '2024-02-05'),
                   (102, NULL, 'mae', 0.04, 50, 5, '2024-01-01', '2024-02-05'),
                   (102, NULL, 'mase', 0.45, 50, 5, '2024-01-01', '2024-02-05'),
                   (102, 'AAA', 'mae', 0.03, 5, 5, '2024-01-01', '2024-02-05');
            INSERT INTO forecasts (id, model_version_id, disease_id, iso3, origin_week,
              target_week, horizon_weeks, target, point, lo80, hi80, lo95, hi95,
              explanation_base)
            VALUES (201, 101, 1, 'AAA', '2024-02-12', '2024-02-19', 1, 'positivity',
                    0.5, 0.4, 0.6, 0.3, 0.7, NULL),
                   (202, 102, 1, 'AAA', '2024-02-12', '2024-02-19', 1, 'positivity',
                    0.75, 0.6, 0.85, 0.5, 0.9, -1.0);
            INSERT INTO forecast_explanations (forecast_id, feature, shap_value,
              feature_value, rank)
            VALUES (202, 'y_lag0', 1.5, 0.85, 1), (202, 'lat', 0.3, 10.0, 2);
            INSERT INTO backtest_predictions (model_version_id, iso3, origin_week,
              target_week, point, lo80, hi80, lo95, hi95, actual)
            VALUES (102, 'AAA', '2024-01-29', '2024-02-05', 0.55, NULL, NULL, NULL, NULL, 0.6),
                   (102, 'AAA', '2024-01-15', '2024-01-22', 0.45, 0.4, 0.5, 0.3, 0.6, 0.4);
        """))
    return "R1"


def test_models_lists_current_run(api: TestClient, run):
    body = api.get(f"{V1}/models").json()
    assert body["run_key"] == "R1"
    assert body["eval_start"] == "2024-01-01"
    by = {m["model_type"]: m for m in body["models"]}
    assert by["xgboost"]["is_active"] and not by["seasonal_naive"]["is_active"]
    assert by["xgboost"]["metrics"]["mae"] == pytest.approx(0.04)
    assert by["xgboost"]["label"] == "XGBoost" and by["xgboost"]["kind"] == "ml"


def test_model_detail(api: TestClient, run):
    d = api.get(f"{V1}/models/102").json()
    assert d["reference"]["mase"] == pytest.approx(0.9)  # seasonal naive, same run/horizon
    assert [i["feature"] for i in d["importance"]] == ["y_lag0", "lat"]
    assert d["importance"][0]["label"] == "Positivity this week"
    assert [e["origin_week"] for e in d["error_by_origin"]] == ["2024-01-15", "2024-01-29"]
    assert d["error_by_origin"][0]["mae"] == pytest.approx(0.05)
    assert d["countries"][0]["iso3"] == "AAA" and d["countries"][0]["metrics"]["mae"] == 0.03
    assert api.get(f"{V1}/models/999").json()["error"]["code"] == "unknown_model"


def test_country_forecasts_and_reasons(api: TestClient, run):
    body = api.get(f"{V1}/forecasts", params={"iso3": "aaa"}).json()
    assert body["eligible"] and body["run_key"] == "R1"
    assert [f["model_type"] for f in body["forecasts"]] == ["xgboost", "seasonal_naive"]
    assert body["forecasts"][0]["has_explanation"] is True
    assert body["country_metrics"]["xgboost:1"]["mae"] == pytest.approx(0.03)
    # BBB has no coverage profile → explained, not an empty chart.
    bbb = api.get(f"{V1}/forecasts", params={"iso3": "BBB"}).json()
    assert not bbb["eligible"] and "coverage profile" in bbb["reason"]


def test_explanation_accounts_for_the_remainder(api: TestClient, run):
    e = api.get(f"{V1}/forecasts/202/explanation").json()
    logit = math.log(0.75 / 0.25)
    assert e["prediction_logit"] == pytest.approx(logit)
    # base + shown contributions + remainder = prediction
    assert e["other_features"] == pytest.approx(logit - (-1.0) - 1.8)
    assert [c["label"] for c in e["contributions"]] == ["Positivity this week", "Latitude"]
    base = api.get(f"{V1}/forecasts/201/explanation")
    assert base.status_code == 404 and base.json()["error"]["code"] == "no_explanation"


def test_backtest_points(api: TestClient, run):
    b = api.get(f"{V1}/backtest", params={"iso3": "AAA", "model_version_id": 102}).json()
    assert [p["origin_week"] for p in b["points"]] == ["2024-01-15", "2024-01-29"]
    assert b["points"][1]["lo80"] is None  # before conformal calibration
    gone = api.get(f"{V1}/backtest", params={"iso3": "AAA", "model_version_id": 101})
    assert gone.json()["error"]["code"] == "no_backtest"
