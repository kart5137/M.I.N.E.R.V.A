"""Live forecast scorecard: published forecasts scored once their target week settled.

Seeded influenza positivity (conftest): AAA 0.1·(w+1), BBB 0.1 (W3 invalid), CCC W6 has
no test count, CCC W5 has 0 tests; W7 (2024-02-19) is provisional, so the reference
week is W6 (2024-02-12).

Runs (horizon 1): S0 and S1 both start at W3; only the later S1 counts. S1 published
XGBoost (selection note) with a last-value baseline and an unselected Random Forest. S2
starts at W4 (CCC, target W5 without a valid value) and S3 at W6 (target W7, pending).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

V1 = "/api/v1"
IDS = "(501, 502, 503, 504, 505, 506, 507)"


@pytest.fixture(scope="module")
def runs(seeded_engine):
    with seeded_engine.begin() as c:
        c.execute(text("""
            INSERT INTO model_versions (id, disease_id, run_key, model_type, kind, target,
              horizon_weeks, train_end, is_active, selection_note, trained_at)
            VALUES
              (501, 1, 'S0', 'xgboost', 'ml', 'positivity', 1, '2024-01-22', false,
               'Lowest MASE.', '2024-01-23'),
              (502, 1, 'S1', 'xgboost', 'ml', 'positivity', 1, '2024-01-22', false,
               'Lowest MASE.', '2024-01-24'),
              (503, 1, 'S1', 'last_value', 'baseline', 'positivity', 1, '2024-01-22', false,
               NULL, '2024-01-24'),
              (504, 1, 'S1', 'random_forest', 'ml', 'positivity', 1, '2024-01-22', false,
               NULL, '2024-01-24'),
              (505, 1, 'S2', 'xgboost', 'ml', 'positivity', 1, '2024-01-29', false,
               'Lowest MASE.', '2024-01-30'),
              (506, 1, 'S3', 'xgboost', 'ml', 'positivity', 1, '2024-02-12', false,
               'Lowest MASE.', '2024-02-13'),
              (507, 2, 'den-S', 'xgboost', 'ml', 'incidence', 1, '2024-01-22', false,
               'Lowest MASE.', '2024-01-24');
            INSERT INTO model_evaluations (model_version_id, iso3, metric, value, n_obs,
              n_origins, eval_start, eval_end)
            VALUES (506, NULL, 'mae', 0.03, 50, 5, '2023-01-02', '2024-01-29'),
                   (506, NULL, 'coverage_80', 0.79, 50, 5, '2023-01-02', '2024-01-29');
            INSERT INTO forecasts (id, model_version_id, disease_id, iso3, origin_week,
              target_week, horizon_weeks, target, point, lo80, hi80, lo95, hi95)
            VALUES
              (601, 501, 1, 'AAA', '2024-01-22', '2024-01-29', 1, 'positivity', 0.9,
               NULL, NULL, NULL, NULL),
              (602, 502, 1, 'AAA', '2024-01-22', '2024-01-29', 1, 'positivity', 0.48,
               0.45, 0.55, 0.40, 0.60),
              (603, 502, 1, 'BBB', '2024-01-22', '2024-01-29', 1, 'positivity', 0.2,
               0.15, 0.25, 0.05, 0.30),
              (604, 503, 1, 'AAA', '2024-01-22', '2024-01-29', 1, 'positivity', 0.4,
               NULL, NULL, NULL, NULL),
              (605, 503, 1, 'BBB', '2024-01-22', '2024-01-29', 1, 'positivity', 0.1,
               NULL, NULL, NULL, NULL),
              (606, 504, 1, 'AAA', '2024-01-22', '2024-01-29', 1, 'positivity', 0.5,
               NULL, NULL, NULL, NULL),
              (607, 505, 1, 'CCC', '2024-01-29', '2024-02-05', 1, 'positivity', 0.1,
               0.05, 0.15, 0.0, 0.2),
              (608, 506, 1, 'AAA', '2024-02-12', '2024-02-19', 1, 'positivity', 0.75,
               0.7, 0.8, 0.6, 0.9),
              (609, 507, 2, 'AAA', '2024-01-22', '2024-01-29', 1, 'incidence', 450,
               400, 520, 350, 600);
        """))
    yield
    with seeded_engine.begin() as c:
        c.execute(text(f"DELETE FROM forecasts WHERE model_version_id IN {IDS}"))
        c.execute(text(f"DELETE FROM model_evaluations WHERE model_version_id IN {IDS}"))
        c.execute(text(f"DELETE FROM model_versions WHERE id IN {IDS}"))


def test_scorecard_scores_published_forecasts_against_settled_weeks(api: TestClient, runs):
    s = api.get(f"{V1}/forecasts/scorecard").json()
    assert s["target"] == "positivity" and "settled" in s["rule"]
    assert s["next_target_week"] == "2024-02-19"
    (h,) = s["horizons"]
    # AAA and BBB from S1 (S0 is superseded, Random Forest not published), CCC from S2,
    # AAA from S3.
    assert (h["published"], h["scored"], h["pending"], h["unscorable"], h["origins"]) == (
        4, 2, 1, 1, 3)
    # Errors 0.02 and 0.10; last value 0.10 and 0.00.
    assert h["mae"] == pytest.approx(0.06)
    assert h["last_value_mae"] == pytest.approx(0.05)
    assert h["skill_vs_last_value"] == pytest.approx(-0.2)
    assert (h["coverage_80"], h["coverage_95"]) == (0.5, 1.0)
    assert (h["backtest_mae"], h["backtest_coverage_80"]) == (0.03, 0.79)
    assert h["model_label"] == "XGBoost"
    assert [(o["origin_week"], o["run_key"], o["published"], o["scored"])
            for o in s["origins"]] == [("2024-01-22", "S1", 2, 2), ("2024-01-29", "S2", 1, 0),
                                       ("2024-02-12", "S3", 1, 0)]
    assert [(r["iso3"], r["actual"], r["in_80"]) for r in s["recent"]] == [
        ("BBB", pytest.approx(0.1), False), ("AAA", pytest.approx(0.5), True)]


def test_dengue_scorecard_uses_incidence(api: TestClient, runs):
    s = api.get(f"{V1}/forecasts/scorecard", params={"disease": "dengue"}).json()
    (h,) = s["horizons"]
    # AAA W4: 5 cases in a population of 1,000 = 500 per 100,000.
    assert (h["scored"], h["mae"], h["coverage_80"]) == (1, pytest.approx(50.0), 1.0)
    assert h["last_value_mae"] is None and h["skill_vs_last_value"] is None
    assert s["recent"][0]["actual"] == pytest.approx(500.0)


def test_scorecard_for_a_disease_without_data(api: TestClient):
    r = api.get(f"{V1}/forecasts/scorecard", params={"disease": "mpox"})
    assert r.status_code == 404
