"""Live forecast scorecard: published forecasts scored against data that arrived later.

Backtests score models on today's revised data at past origins; this scores what the
dashboard actually showed. For every forecast origin week the *published* forecasts are
those of the latest run with that origin (what stayed on the site) from the model that run
selected (`model_versions.selection_note` is set on exactly that model per horizon). A
forecast is scored once its target week is settled (not provisional, at or before the
disease's reference week) and has a valid observation: positivity from ≥ 10 specimens, or
reported cases with a population (incidence per 100,000). The same run's *last value*
forecast is the naive comparison.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.queries.common import MIN_SPECIMENS_FOR_RATE, DiseaseContext
from app.queries.models import POP_AT, label, target_of
from app.schemas.models import HorizonScore, OriginScore, ScoredForecast

RULE = (
    "Each week's published forecasts (the model the run selected, per horizon) are scored "
    "once their target week is settled: absolute error against the value reported later, "
    "and whether the 80% and 95% intervals contained it. 'Last value' is the same run's "
    "naive forecast (this week's value carried forward). Backtest figures are the selected "
    "model's pooled backtest for comparison; they use today's revised data, so live errors "
    "are expected to be somewhat larger."
)

_ROWS = """
    WITH runs AS (
      SELECT DISTINCT ON (f.origin_week) f.origin_week, v.run_key
      FROM forecasts f JOIN model_versions v ON v.id = f.model_version_id
      WHERE f.disease_id = :d AND v.target = :t
      ORDER BY f.origin_week, v.trained_at DESC
    )
    SELECT f.iso3, c.name, f.origin_week, f.target_week, f.horizon_weeks, f.point, f.lo80,
           f.hi80, f.lo95, f.hi95, v.id AS version_id, v.model_type, v.run_key,
           bl.point AS last_value, {actual} AS actual
    FROM forecasts f
    JOIN model_versions v ON v.id = f.model_version_id
    JOIN runs r ON r.run_key = v.run_key AND r.origin_week = f.origin_week
    JOIN countries c ON c.iso3 = f.iso3
    LEFT JOIN model_versions bv ON bv.run_key = v.run_key AND bv.disease_id = v.disease_id
      AND bv.horizon_weeks = v.horizon_weeks AND bv.model_type = 'last_value'
    LEFT JOIN forecasts bl ON bl.model_version_id = bv.id AND bl.iso3 = f.iso3
      AND bl.origin_week = f.origin_week
    LEFT JOIN surveillance_weekly sw ON sw.disease_id = f.disease_id AND sw.iso3 = f.iso3
      AND sw.week_start = f.target_week AND NOT sw.is_provisional
      AND sw.week_start <= :reference
    WHERE f.disease_id = :d AND v.selection_note IS NOT NULL
    ORDER BY f.origin_week, f.horizon_weeks, f.iso3
"""


def _actual_sql(ctx: DiseaseContext) -> str:
    if ctx.case_based:
        return (f"sw.cases / NULLIF({POP_AT.format(iso='f.iso3', week='f.target_week')}, 0)"
                " * 100000")
    return (f"CASE WHEN sw.specimens_tested >= {MIN_SPECIMENS_FOR_RATE} "
            "THEN sw.positivity END")


def _mean(xs: list[float]) -> float | None:
    return sum(xs) / len(xs) if xs else None


def scorecard(session: Session, ctx: DiseaseContext, recent: int = 40
              ) -> tuple[list[HorizonScore], list[OriginScore], list[ScoredForecast],
                         date | None]:
    rows = session.execute(
        text(_ROWS.format(actual=_actual_sql(ctx))),
        {"d": ctx.id, "t": target_of(ctx), "reference": ctx.reference_week},
    ).mappings().all()
    ref = ctx.reference_week
    by_h: dict[int, list] = defaultdict(list)
    by_origin: dict[tuple, list] = defaultdict(list)
    for r in rows:
        by_h[r["horizon_weeks"]].append(r)
        by_origin[(r["origin_week"], r["horizon_weeks"], r["run_key"])].append(r)

    versions = sorted({r["version_id"] for r in rows})
    backtest: dict[int, dict[str, float]] = defaultdict(dict)
    if versions:
        for vid, metric, value in session.execute(text("""
            SELECT model_version_id, metric, value FROM model_evaluations
            WHERE model_version_id = ANY(:ids) AND iso3 IS NULL
              AND metric IN ('mae', 'coverage_80')
        """), {"ids": versions}).all():
            backtest[vid][metric] = value

    def scored(rs):
        return [r for r in rs if r["actual"] is not None and r["target_week"] <= ref]

    horizons = []
    for h in sorted(by_h):
        rs = by_h[h]
        s = scored(rs)
        pending = [r for r in rs if r["target_week"] > ref]
        err = [abs(r["point"] - r["actual"]) for r in s]
        base = [abs(r["last_value"] - r["actual"]) for r in s if r["last_value"] is not None]
        latest = max(rs, key=lambda r: r["origin_week"])
        bt = backtest.get(latest["version_id"], {})
        mae, base_mae = _mean(err), _mean(base)
        horizons.append(HorizonScore(
            horizon_weeks=h, published=len(rs), scored=len(s), pending=len(pending),
            unscorable=len(rs) - len(s) - len(pending),
            origins=len({r["origin_week"] for r in rs}),
            mae=mae, last_value_mae=base_mae,
            skill_vs_last_value=(1 - mae / base_mae) if mae is not None and base_mae else None,
            coverage_80=_mean([float(r["lo80"] <= r["actual"] <= r["hi80"]) for r in s
                               if r["lo80"] is not None]),
            coverage_95=_mean([float(r["lo95"] <= r["actual"] <= r["hi95"]) for r in s
                               if r["lo95"] is not None]),
            backtest_mae=bt.get("mae"), backtest_coverage_80=bt.get("coverage_80"),
            model_label=label(latest["model_type"]),
        ))

    origins = []
    for (origin, h, run_key), rs in sorted(by_origin.items()):
        s = scored(rs)
        origins.append(OriginScore(
            origin_week=origin, horizon_weeks=h, run_key=run_key,
            model_label=label(rs[0]["model_type"]), published=len(rs), scored=len(s),
            mae=_mean([abs(r["point"] - r["actual"]) for r in s]),
            coverage_80=_mean([float(r["lo80"] <= r["actual"] <= r["hi80"]) for r in s
                               if r["lo80"] is not None])))

    done = sorted(scored(rows), key=lambda r: (r["target_week"], r["horizon_weeks"],
                                               r["iso3"]), reverse=True)[:recent]
    items = [ScoredForecast(
        iso3=r["iso3"], name=r["name"], origin_week=r["origin_week"],
        target_week=r["target_week"], horizon_weeks=r["horizon_weeks"],
        model_label=label(r["model_type"]), point=r["point"], lo80=r["lo80"], hi80=r["hi80"],
        actual=r["actual"], last_value=r["last_value"],
        abs_error=abs(r["point"] - r["actual"]),
        in_80=None if r["lo80"] is None else r["lo80"] <= r["actual"] <= r["hi80"],
    ) for r in done]
    waiting = [r["target_week"] for r in rows if r["target_week"] > ref]
    return horizons, origins, items, (min(waiting) if waiting else None)
