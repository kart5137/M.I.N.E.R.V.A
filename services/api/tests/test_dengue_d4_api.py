"""Dengue forecasting, detection, alerts and reports (D4). A tiny dengue run is inserted
by hand on top of the conftest data (AAA: population 1,000, weekly cases w + 1; reference
week W6 = 2024-02-12 with 7 cases = 700 per 100,000):

run "den-R", horizon 1: last_value (baseline) and xgboost (active), AAA only; one dengue
anomaly, one detection run and one sustained-growth alert. Removed afterwards.
"""

from __future__ import annotations

import math

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

V1 = "/api/v1"
DENGUE = {"disease": "dengue"}
TABLES = ("report_alerts", "intelligence_reports", "alerts", "anomalies", "detection_runs",
          "forecast_explanations", "forecasts", "model_evaluations", "model_versions")


@pytest.fixture(scope="module")
def dengue_run(seeded_engine):
    with seeded_engine.begin() as c:
        c.execute(text("""
            INSERT INTO model_versions (id, disease_id, run_key, model_type, kind, target,
              horizon_weeks, train_start, train_end, features, hyperparams, global_importance,
              is_active, selection_note)
            VALUES
              (301, 2, 'den-R', 'last_value', 'baseline', 'incidence', 1, NULL,
               '2024-02-12', NULL, NULL, NULL, false, NULL),
              (302, 2, 'den-R', 'xgboost', 'ml', 'incidence', 1, '2024-01-08', '2024-02-12',
               '["y_lag0", "temperature_anom4_lag8"]', '{"max_depth": 5}',
               '{"y_lag0": 0.6, "temperature_anom4_lag8": 0.1}', true, 'Lowest MASE.');
            INSERT INTO model_evaluations (model_version_id, iso3, metric, value, n_obs,
              n_origins, eval_start, eval_end)
            VALUES (302, NULL, 'mae', 12.5, 50, 5, '2024-01-01', '2024-02-05');
            INSERT INTO forecasts (id, model_version_id, disease_id, iso3, origin_week,
              target_week, horizon_weeks, target, point, lo80, hi80, lo95, hi95,
              explanation_base)
            VALUES (401, 301, 2, 'AAA', '2024-02-12', '2024-02-19', 1, 'incidence',
                    700, 600, 800, 500, 900, NULL),
                   (402, 302, 2, 'AAA', '2024-02-12', '2024-02-19', 1, 'incidence',
                    840, 700, 1000, 600, 1200, 6.7);
            INSERT INTO forecast_explanations (forecast_id, feature, shap_value,
              feature_value, rank)
            VALUES (402, 'y_lag0', 0.12, 6.68, 1), (402, 'temperature_anom4_lag8', 0.02, 1.4, 2);
            INSERT INTO detection_runs (id, disease_id, run_key, reference_week, latest_week,
              finished_at, summary)
            VALUES (9, 2, 'den-D9', '2024-02-12', '2024-02-19', now(),
                    '{"thresholds": {"not_assessed": {"AAA": "1 usable past season (needs 3)"}}}');
            INSERT INTO anomalies (run_id, disease_id, iso3, week_start, metric, method,
              observed, expected, upper_band, score, ewma, ewma_limit, specimens_tested,
              severity)
            VALUES (9, 2, 'AAA', '2024-02-05', 'incidence', 'seasonal_ewma', 600, 200, 300,
                    3.5, 2.0, 1.26, NULL, 'high');
            INSERT INTO alerts (id, disease_id, iso3, alert_type, severity, week_start, title,
              details, status, last_run_id)
            VALUES (21, 2, 'AAA', 'sustained_growth', 'medium', '2024-02-05',
                    'Alpha: incidence up 3 weeks in a row, 300 per 100k → 600 per 100k (+100%)',
                    '{"metric": "incidence"}', 'active', 9);
        """))
    yield
    with seeded_engine.begin() as c:
        for t in TABLES:
            c.execute(text(f"DELETE FROM {t} WHERE " + (
                "forecast_id IN (401, 402)" if t == "forecast_explanations" else
                "report_id IN (SELECT id FROM intelligence_reports WHERE disease_id = 2)"
                if t == "report_alerts" else
                "model_version_id IN (301, 302)" if t == "model_evaluations" else
                "disease_id = 2")))


def test_dengue_models_and_forecasts(api: TestClient, dengue_run):
    body = api.get(f"{V1}/models", params=DENGUE).json()
    assert body["run_key"] == "den-R" and body["target"] == "incidence"
    d = api.get(f"{V1}/models/302", params=DENGUE).json()
    assert [i["label"] for i in d["importance"]] == ["Incidence this week",
                                                     "Temperature anomaly, 8 weeks earlier"]
    # A dengue model is not served as an influenza one.
    assert api.get(f"{V1}/models/302").json()["error"]["code"] == "unknown_model"

    fc = api.get(f"{V1}/forecasts", params={**DENGUE, "iso3": "AAA"}).json()
    assert fc["eligible"] and [f["model_type"] for f in fc["forecasts"]] == ["xgboost",
                                                                            "last_value"]
    reasons = {iso: api.get(f"{V1}/forecasts", params={**DENGUE, "iso3": iso}).json()["reason"]
               for iso in ("BBB", "CCC")}
    assert reasons["BBB"].startswith("No WHO dengue coverage profile")
    assert reasons["CCC"].startswith("Reports dengue monthly")


def test_dengue_global_forecasts_use_relative_change(api: TestClient, dengue_run):
    g = api.get(f"{V1}/forecasts/global", params={**DENGUE, "horizon": 1}).json()
    item = g["items"][0]
    assert g["model_type"] == "xgboost" and item["iso3"] == "AAA"
    assert item["origin_value"] == pytest.approx(700.0)        # 7 cases / 1,000 × 100,000
    assert item["change_pct"] == pytest.approx(20.0) and item["change_pp"] is None


def test_dengue_explanation_on_log_incidence_scale(api: TestClient, dengue_run):
    e = api.get(f"{V1}/forecasts/402/explanation").json()
    pred = math.log(840 + 100)                                  # offset: one case per 100k
    assert e["target"] == "incidence"
    assert e["prediction_logit"] == pytest.approx(pred)
    assert e["other_features"] == pytest.approx(pred - 6.7 - 0.14)
    assert e["contributions"][0]["label"] == "Incidence this week"


def test_dengue_detection_and_alerts(api: TestClient, dengue_run):
    a = api.get(f"{V1}/anomalies", params={**DENGUE, "to": "2024-02-12"}).json()
    assert "incidence" in a["method_note"] and a["items"][0]["observed"] == 600
    assert a["items"][0]["specimens_tested"] is None
    r = api.get(f"{V1}/risk", params=DENGUE).json()
    assert "incidence" in r["rule"] and r["items"] == []
    # Weekly dengue reporters only (CCC reports monthly).
    assert {n["iso3"]: n["reason"] for n in r["not_assessed"]} == {
        "AAA": "1 usable past season (needs 3)",
        "BBB": "no forecast this week (forecasts need a weekly Tier A/B series with "
               "population and cases in the reference week)"}
    det = api.get(f"{V1}/countries/CCC/detection", params=DENGUE).json()
    assert det["thresholds_reason"].startswith("No weekly dengue reporting")
    al = api.get(f"{V1}/alerts", params=DENGUE).json()
    assert [x["id"] for x in al["items"]] == [21]
    assert al["rules"]["sustained_growth"].startswith("Incidence up in 3 consecutive weeks")
    k = api.get(f"{V1}/overview", params={**DENGUE, "to": "2024-02-12"}).json()["kpis"]
    assert k["anomalies"]["value"] == 1 and k["positivity"] is None


def test_dengue_reports_render_cases_and_incidence(api: TestClient, dengue_run):
    g = api.post(f"{V1}/reports/generate", params=DENGUE, json={"scope": "global"}).json()
    md = g["report"]["rendered_md"]
    assert md.startswith("# Global dengue situation")
    assert "Reported dengue cases (weekly reporters)" in md and "Positivity" not in md
    assert g["report"]["content"]["metric"] == "incidence"
    c = api.post(f"{V1}/reports/generate", params=DENGUE,
                 json={"scope": "country", "iso3": "AAA"}).json()["report"]
    assert "| Week | Reported cases | Incidence per 100,000 |" in c["rendered_md"]
    assert "| 19 Feb 2024 | +1 wk | XGBoost | 840 | 700–1,000 |" in c["rendered_md"]
    assert "incidence up 3 weeks in a row" in c["rendered_md"]
    v = api.get(f"{V1}/reports/{c['id']}/verify", params=DENGUE).json()
    assert v["inputs_identical"] and v["regenerated_identical"]
    m = api.post(f"{V1}/reports/generate", params=DENGUE,
                 json={"scope": "country", "iso3": "CCC"}).json()["report"]["rendered_md"]
    assert "Reported monthly" in m and "| Jan 2024 | 62 |" in m


def test_dengue_about_and_analytics_scope(api: TestClient, dengue_run):
    about = api.get(f"{V1}/about", params=DENGUE).json()
    assert about["tiers"][0]["rule"].startswith("Forecast-ready (weekly)")
    assert any("case definition" in t for t in about["limitations"])
    r = api.get(f"{V1}/analytics/trends", params={**DENGUE, "series": "global"})
    assert r.status_code == 422 and "influenza only" in r.json()["error"]["message"]
