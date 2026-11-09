"""Storage housekeeping for the weekly job (M8).

Each forecast run stores ~50k per-country evaluation rows and ~5k SHAP contributions
(~10 MB). Kept forever they would fill a free-tier database within a year. `prune_runs`
keeps everything for the latest `keep` runs (and always for the active run); older runs
keep their model versions, pooled metrics (`iso3 IS NULL`) and forecasts, so their model
pages still open, but lose the per-country metric breakdown and SHAP detail.
"""

from __future__ import annotations

from sqlalchemy import Engine, text

DEFAULT_KEEP = 8


def prune_runs(engine: Engine, keep: int = DEFAULT_KEEP) -> dict:
    if keep < 1:
        raise ValueError("keep must be at least 1")
    with engine.begin() as c:
        old = c.execute(text("""
            WITH runs AS (
              SELECT run_key, max(trained_at) AS trained_at, bool_or(is_active) AS active
              FROM model_versions GROUP BY run_key)
            SELECT run_key FROM runs WHERE NOT active
            ORDER BY trained_at DESC OFFSET :keep"""), {"keep": max(keep - 1, 0)}).scalars().all()
        if not old:
            return {"older_runs": 0, "evaluations_deleted": 0, "explanations_deleted": 0}
        p = {"runs": list(old)}
        ev = c.execute(text("""
            DELETE FROM model_evaluations e USING model_versions v
            WHERE v.id = e.model_version_id AND v.run_key = ANY(:runs)
              AND e.iso3 IS NOT NULL"""), p).rowcount
        ex = c.execute(text("""
            DELETE FROM forecast_explanations x USING forecasts f, model_versions v
            WHERE f.id = x.forecast_id AND v.id = f.model_version_id
              AND v.run_key = ANY(:runs)"""), p).rowcount
    return {"older_runs": len(old), "evaluations_deleted": ev, "explanations_deleted": ex}
