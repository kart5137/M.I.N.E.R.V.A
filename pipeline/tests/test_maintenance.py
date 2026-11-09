"""Pruning of old forecast runs (M8) and database-URL normalisation."""

from __future__ import annotations

import pytest
from sqlalchemy import text

from ei_db.session import normalize_url
from ei_pipeline.maintenance import prune_runs

# Four runs, oldest first; run "r2" (not the newest) is the active one.
RUNS = [("r1", False), ("r2", True), ("r3", False), ("r4", False)]


def _seed(db) -> None:
    with db.begin() as c:
        c.execute(text("""
            INSERT INTO diseases (id, key, name, native_granularity, primary_metric,
                                  metric_label)
              VALUES (1, 'influenza', 'Influenza', 'weekly', 'positivity', 'Positivity')"""))
        c.execute(text("INSERT INTO countries (iso3, name) VALUES ('AAA', 'Alpha')"))
        for i, (run, active) in enumerate(RUNS, start=1):
            c.execute(text("""
                INSERT INTO model_versions (id, disease_id, run_key, model_type, kind, target,
                  horizon_weeks, train_end, trained_at, is_active)
                VALUES (:i, 1, :r, 'xgboost', 'ml', 'positivity', 1, '2025-01-06',
                        now() - make_interval(days => :age), :a)"""),
                {"i": i, "r": run, "a": active, "age": 10 - i})
            c.execute(text("""
                INSERT INTO model_evaluations (model_version_id, iso3, metric, value, n_obs,
                  n_origins, eval_start, eval_end)
                VALUES (:i, NULL, 'mase', 0.5, 10, 5, '2024-01-01', '2025-01-06'),
                       (:i, 'AAA', 'mase', 0.4, 10, 5, '2024-01-01', '2025-01-06')"""),
                {"i": i})
            c.execute(text("""
                INSERT INTO forecasts (id, model_version_id, disease_id, iso3, origin_week,
                  target_week, horizon_weeks, target, point)
                VALUES (:i, :i, 1, 'AAA', '2025-01-06', '2025-01-13', 1, 'positivity', 0.1)"""),
                {"i": i})
            c.execute(text("""
                INSERT INTO forecast_explanations (forecast_id, feature, shap_value, rank)
                VALUES (:i, 'lag1', 0.01, 1)"""), {"i": i})


def _detail(db) -> dict[str, tuple[int, int, int]]:
    """run → (pooled evaluations, per-country evaluations, explanations)."""
    with db.connect() as c:
        rows = c.execute(text("""
            SELECT v.run_key,
              (SELECT count(*) FROM model_evaluations e
                WHERE e.model_version_id = v.id AND e.iso3 IS NULL),
              (SELECT count(*) FROM model_evaluations e
                WHERE e.model_version_id = v.id AND e.iso3 IS NOT NULL),
              (SELECT count(*) FROM forecast_explanations x JOIN forecasts f
                ON f.id = x.forecast_id WHERE f.model_version_id = v.id)
            FROM model_versions v ORDER BY v.run_key""")).all()
    return {r[0]: tuple(r[1:]) for r in rows}


def test_prune_keeps_latest_and_active_runs(db):
    _seed(db)
    out = prune_runs(db, keep=2)
    # Kept in full: the active run (r2) and the newest other run (r4).
    assert out == {"older_runs": 2, "evaluations_deleted": 2, "explanations_deleted": 2}
    assert _detail(db) == {"r1": (1, 0, 0), "r2": (1, 1, 1), "r3": (1, 0, 0),
                           "r4": (1, 1, 1)}
    # Pooled metrics and forecasts stay, so old model pages still open; idempotent.
    assert prune_runs(db, keep=2)["evaluations_deleted"] == 0
    with pytest.raises(ValueError):
        prune_runs(db, keep=0)


def test_prune_with_nothing_to_do(db):
    _seed(db)
    assert prune_runs(db, keep=10)["older_runs"] == 0


@pytest.mark.parametrize(("url", "expected"), [
    ("postgres://u:p@h/db", "postgresql+psycopg://u:p@h/db"),
    ("postgresql://u:p@h/db?sslmode=require", "postgresql+psycopg://u:p@h/db?sslmode=require"),
    ("postgresql+psycopg://u:p@h/db", "postgresql+psycopg://u:p@h/db"),
])
def test_normalize_url(url, expected):
    assert normalize_url(url) == expected
