"""Stored forecasting outputs (M5; dengue incidence D4). The API never trains or predicts;
it reads results. Influenza forecasts positivity (0–1); dengue forecasts weekly incidence
per 100,000."""

from __future__ import annotations

import math
import re

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.queries.common import DiseaseContext
from app.schemas.models import (
    BacktestPoint,
    Contribution,
    CountryMetric,
    ErrorPoint,
    Explanation,
    ForecastOut,
    GlobalForecastItem,
    Importance,
    Metrics,
    ModelSummary,
)
from ei_db.catalog import MODEL_LABELS, feature_label

TARGET = "positivity"
REFERENCE = "seasonal_naive"

#: Population of `iso` for the year of `week`: the latest year up to it, else the
#: earliest (as app/queries/cases.py and the pipeline).
POP_AT = """(SELECT pa.population::float8 FROM population_annual pa
   WHERE pa.iso3 = {iso} AND pa.population > 0
   ORDER BY (pa.year <= extract(year FROM {week})) DESC,
            CASE WHEN pa.year <= extract(year FROM {week}) THEN -pa.year ELSE pa.year END
   LIMIT 1)"""


def target_of(ctx: DiseaseContext) -> str:
    return "incidence" if ctx.case_based else "positivity"


def label(model_type: str) -> str:
    return MODEL_LABELS.get(model_type, model_type)


def current_run(session: Session, ctx: DiseaseContext) -> str | None:
    """The run that holds the active versions (latest run if none is active)."""
    return session.execute(text("""
        SELECT run_key FROM model_versions WHERE disease_id = :d AND target = :t
        ORDER BY is_active DESC, trained_at DESC LIMIT 1
    """), {"d": ctx.id, "t": target_of(ctx)}).scalar()


def _metrics_by_version(session: Session, version_ids: list[int], iso3: str | None = None
                        ) -> dict[int, Metrics]:
    if not version_ids:
        return {}
    rows = session.execute(text("""
        SELECT model_version_id, metric, value, n_obs, n_origins FROM model_evaluations
        WHERE model_version_id = ANY(:ids)
          AND (CASE WHEN CAST(:iso3 AS text) IS NULL THEN iso3 IS NULL ELSE iso3 = :iso3 END)
    """), {"ids": version_ids, "iso3": iso3}).all()
    out: dict[int, dict] = {}
    for vid, metric, value, n_obs, n_origins in rows:
        d = out.setdefault(vid, {"n_obs": n_obs, "n_origins": n_origins})
        d[metric] = value
    return {vid: Metrics(**d) for vid, d in out.items()}


def run_models(session: Session, run_key: str) -> list[ModelSummary]:
    rows = session.execute(text("""
        SELECT id, model_type, kind, horizon_weeks, is_active, selection_note
        FROM model_versions WHERE run_key = :r
        ORDER BY horizon_weeks, kind DESC, model_type
    """), {"r": run_key}).mappings().all()
    metrics = _metrics_by_version(session, [r["id"] for r in rows])
    return [ModelSummary(**r, label=label(r["model_type"]),
                         metrics=metrics.get(r["id"], Metrics())) for r in rows]


def run_info(session: Session, run_key: str):
    return session.execute(text("""
        SELECT max(v.trained_at) AS trained_at, max(v.train_end) AS train_end,
          (SELECT min(eval_start) FROM model_evaluations e
            JOIN model_versions v2 ON v2.id = e.model_version_id WHERE v2.run_key = :r)
            AS eval_start,
          (SELECT max(eval_end) FROM model_evaluations e
            JOIN model_versions v2 ON v2.id = e.model_version_id WHERE v2.run_key = :r)
            AS eval_end
        FROM model_versions v WHERE v.run_key = :r
    """), {"r": run_key}).mappings().one()


def version(session: Session, version_id: int, ctx: DiseaseContext | None = None):
    row = session.execute(text("SELECT * FROM model_versions WHERE id = :i"),
                          {"i": version_id}).mappings().one_or_none()
    if row is None or (ctx is not None and row["disease_id"] != ctx.id):
        raise ApiError(404, "unknown_model", f"No model version {version_id}"
                       + (f" for {ctx.name}." if ctx is not None else "."))
    return row


def model_detail_parts(session: Session, v) -> dict:
    ref_id = session.execute(text("""
        SELECT id FROM model_versions WHERE run_key = :r AND horizon_weeks = :h
          AND model_type = :m
    """), {"r": v["run_key"], "h": v["horizon_weeks"], "m": REFERENCE}).scalar()
    pooled = _metrics_by_version(session, [v["id"], ref_id] if ref_id else [v["id"]])
    # JSONB does not keep key order: sort by importance here.
    importance = [Importance(feature=f, label=feature_label(f, v["target"]), value=val)
                  for f, val in sorted((v["global_importance"] or {}).items(),
                                       key=lambda kv: -kv[1])]
    errors = [ErrorPoint(**r) for r in session.execute(text("""
        SELECT origin_week, avg(abs(point - actual)) AS mae, count(*) AS n
        FROM backtest_predictions WHERE model_version_id = :i
        GROUP BY origin_week ORDER BY origin_week
    """), {"i": v["id"]}).mappings()]
    country_rows = session.execute(text("""
        SELECT e.iso3, c.name, e.metric, e.value, e.n_obs, e.n_origins
        FROM model_evaluations e JOIN countries c ON c.iso3 = e.iso3
        WHERE e.model_version_id = :i
    """), {"i": v["id"]}).all()
    by_country: dict[str, dict] = {}
    names: dict[str, str] = {}
    for iso3, name, metric, value, n_obs, n_origins in country_rows:
        names[iso3] = name
        d = by_country.setdefault(iso3, {"n_obs": n_obs, "n_origins": n_origins})
        d[metric] = value
    countries = sorted(
        (CountryMetric(iso3=k, name=names[k], metrics=Metrics(**d)) for k, d in by_country.items()),
        key=lambda c: (c.metrics.mase is None, c.metrics.mase or 0),
    )
    return {
        "metrics": pooled.get(v["id"], Metrics()),
        "reference": pooled.get(ref_id, Metrics()) if ref_id else Metrics(),
        "importance": importance, "error_by_origin": errors, "countries": countries,
    }


def country_forecasts(session: Session, ctx: DiseaseContext, run_key: str, iso3: str
                      ) -> tuple[list[ForecastOut], dict[str, Metrics]]:
    rows = session.execute(text("""
        SELECT f.id, f.model_version_id, v.model_type, v.is_active, f.horizon_weeks,
          f.origin_week, f.target_week, f.point, f.lo80, f.hi80, f.lo95, f.hi95,
          EXISTS (SELECT 1 FROM forecast_explanations e WHERE e.forecast_id = f.id)
            AS has_explanation
        FROM forecasts f JOIN model_versions v ON v.id = f.model_version_id
        WHERE v.run_key = :r AND f.iso3 = :iso3 AND f.disease_id = :d
        ORDER BY f.horizon_weeks, v.is_active DESC, v.model_type
    """), {"r": run_key, "iso3": iso3, "d": ctx.id}).mappings().all()
    forecasts = [ForecastOut(**r, label=label(r["model_type"])) for r in rows]
    versions = session.execute(text(
        "SELECT id, model_type, horizon_weeks FROM model_versions WHERE run_key = :r"),
        {"r": run_key}).all()
    per = _metrics_by_version(session, [v[0] for v in versions], iso3)
    metrics = {f"{m}:{h}": per[vid] for vid, m, h in versions if vid in per}
    return forecasts, metrics


def no_forecast_reason(session: Session, ctx: DiseaseContext, iso3: str) -> str:
    row = session.execute(text("""
        SELECT tier, grain FROM coverage_profiles WHERE disease_id = :d AND iso3 = :i
        ORDER BY reference_week DESC LIMIT 1
    """), {"d": ctx.id, "i": iso3}).one_or_none()
    source = "WHO dengue" if ctx.case_based else "FluNet"
    if row is None:
        return f"No {source} coverage profile for this area, so it is not forecast."
    tier, grain = row
    if ctx.case_based and grain == "month":
        return ("Reports dengue monthly: forecasts are weekly and months are not split into "
                "invented weeks.")
    if tier not in ("A", "B"):
        return (f"Coverage tier {tier}: forecasts are made only for tiers A and B "
                "(regular, recent reporting).")
    if ctx.case_based:
        has_pop = session.execute(text(
            "SELECT EXISTS (SELECT 1 FROM population_annual WHERE iso3 = :i)"),
            {"i": iso3}).scalar()
        if not has_pop:
            return "No World Bank population for this area, so incidence cannot be computed."
        return ("No reported cases in the reference week, so no forecast was made from it.")
    return ("No valid positivity in the reference week (fewer than 10 specimens or no "
            "report), so no forecast was made from it.")


def explanation(session: Session, forecast_id: int) -> Explanation:
    f = session.execute(text(f"""
        SELECT f.id, f.point, f.explanation_base, f.horizon_weeks, f.target, v.model_type,
               {POP_AT.format(iso="f.iso3", week="f.origin_week")} AS population
        FROM forecasts f JOIN model_versions v ON v.id = f.model_version_id
        WHERE f.id = :i
    """), {"i": forecast_id}).mappings().one_or_none()
    if f is None:
        raise ApiError(404, "unknown_forecast", f"No forecast {forecast_id}.")
    contribs = session.execute(text("""
        SELECT feature, shap_value, feature_value, rank FROM forecast_explanations
        WHERE forecast_id = :i ORDER BY rank
    """), {"i": forecast_id}).mappings().all()
    if not contribs:
        raise ApiError(404, "no_explanation",
                       f"{label(f['model_type'])} is a baseline; it has no feature explanation.")
    offset = None
    if f["target"] == "incidence":
        # log(incidence + one case per 100,000), as the pipeline (forecasting/spec.py).
        offset = 1e5 / f["population"] if f["population"] else 1.0
        pred_y = math.log(max(f["point"], 0.0) + offset)
    else:
        p = min(max(f["point"], 1e-6), 1 - 1e-6)
        pred_y = math.log(p / (1 - p))
    top = sum(c["shap_value"] for c in contribs)
    base = f["explanation_base"]
    return Explanation(
        forecast_id=f["id"], model_type=f["model_type"], horizon_weeks=f["horizon_weeks"],
        target=f["target"], base_value=base, prediction_logit=pred_y, point=f["point"],
        other_features=(pred_y - base - top) if base is not None else 0.0,
        contributions=[Contribution(**c, label=feature_label(c["feature"], f["target"]),
                                    natural_value=_natural(c["feature"], c["feature_value"],
                                                           offset))
                       for c in contribs],
    )


#: Dengue features on the model scale that describe the country's own incidence level.
_LEVEL = re.compile(r"^y_(lag\d|mean\d|last_year|peak52)$")


def _natural(feature: str, value: float | None, offset: float | None) -> float | None:
    if offset is None or value is None or not _LEVEL.match(feature):
        return None
    return max(math.exp(value) - offset, 0.0)


def backtest_points(session: Session, version_id: int, iso3: str) -> list[BacktestPoint]:
    rows = session.execute(text("""
        SELECT origin_week, target_week, point, lo80, hi80, lo95, hi95, actual
        FROM backtest_predictions WHERE model_version_id = :v AND iso3 = :i
        ORDER BY origin_week
    """), {"v": version_id, "i": iso3}).mappings()
    return [BacktestPoint(**r) for r in rows]


def global_forecasts(session: Session, ctx: DiseaseContext, run_key: str, horizon: int,
                     region: str | None) -> tuple[str | None, list[GlobalForecastItem]]:
    """Latest-origin forecasts of the active model at one horizon, every country."""
    origin = (f"sw.cases / NULLIF({POP_AT.format(iso='f.iso3', week='f.origin_week')}, 0)"
              " * 100000" if ctx.case_based else "sw.positivity")
    rows = session.execute(text(f"""
        SELECT f.iso3, c.name, c.who_region, f.origin_week, f.target_week, f.point, f.lo80,
               f.hi80, mv.model_type, {origin} AS origin_value
        FROM forecasts f
        JOIN model_versions mv ON mv.id = f.model_version_id
        JOIN countries c ON c.iso3 = f.iso3
        LEFT JOIN surveillance_weekly sw ON sw.disease_id = f.disease_id
          AND sw.iso3 = f.iso3 AND sw.week_start = f.origin_week
        WHERE mv.run_key = :run AND mv.is_active AND mv.horizon_weeks = :h
          AND (CAST(:region AS text) IS NULL OR c.who_region = :region)
        ORDER BY f.iso3
    """), {"run": run_key, "h": horizon, "region": region}).mappings().all()
    model = rows[0]["model_type"] if rows else None
    def changes(r) -> dict:
        o = r["origin_value"]
        if o is None:
            return {"change_pp": None, "change_pct": None}
        if ctx.case_based:
            return {"change_pp": None,
                    "change_pct": (r["point"] - o) / o * 100 if o > 0 else None}
        return {"change_pp": (r["point"] - o) * 100, "change_pct": None}

    return model, [GlobalForecastItem(
        **{k: r[k] for k in GlobalForecastItem.model_fields if k in r}, **changes(r),
    ) for r in rows]
