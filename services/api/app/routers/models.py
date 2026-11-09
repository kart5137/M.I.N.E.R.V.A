from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.core.errors import ApiError
from app.queries import models as q
from app.queries.common import load_disease
from app.queries.countries import country_row
from app.schemas.models import (
    CountryBacktest,
    CountryForecasts,
    Explanation,
    ModelDetail,
    ModelRun,
)

router = APIRouter(tags=["forecasting"])

Disease = Annotated[str, Query(description="Disease key, e.g. `influenza`.")]


@router.get("/models", response_model=ModelRun,
            summary="Model versions of the current run with pooled backtest metrics")
def models(session: Session = Depends(get_session), disease: Disease = "influenza") -> ModelRun:
    ctx = load_disease(session, disease)
    run_key = q.current_run(session, ctx)
    if run_key is None:
        return ModelRun(meta=ctx.meta(), run_key=None, target=q.TARGET, trained_at=None,
                        train_end=None, eval_start=None, eval_end=None, models=[])
    info = q.run_info(session, run_key)
    return ModelRun(meta=ctx.meta(), run_key=run_key, target=q.TARGET, **info,
                    models=q.run_models(session, run_key))


@router.get("/models/{version_id}", response_model=ModelDetail,
            summary="One model version: backtest metrics, per-country errors, importance")
def model_detail(version_id: int, session: Session = Depends(get_session),
                 disease: Disease = "influenza") -> ModelDetail:
    ctx = load_disease(session, disease)
    v = q.version(session, version_id)
    return ModelDetail(
        meta=ctx.meta(), id=v["id"], run_key=v["run_key"], model_type=v["model_type"],
        label=q.label(v["model_type"]), kind=v["kind"], target=v["target"],
        horizon_weeks=v["horizon_weeks"], is_active=v["is_active"],
        selection_note=v["selection_note"], train_start=v["train_start"],
        train_end=v["train_end"], trained_at=v["trained_at"], features=v["features"],
        hyperparams=v["hyperparams"], git_sha=v["git_sha"], artefact_uri=v["artefact_uri"],
        **q.model_detail_parts(session, v),
    )


@router.get("/forecasts", response_model=CountryForecasts,
            summary="Stored forecasts for one country from the current run (all models)")
def forecasts(iso3: str, session: Session = Depends(get_session),
              disease: Disease = "influenza") -> CountryForecasts:
    ctx = load_disease(session, disease)
    c = country_row(session, iso3)
    run_key = q.current_run(session, ctx)
    if run_key is None:
        return CountryForecasts(meta=ctx.meta(), iso3=c["iso3"], run_key=None, eligible=False,
                                reason="No forecasting run yet (`ei forecast run`).",
                                forecasts=[], country_metrics={})
    fc, metrics = q.country_forecasts(session, ctx, run_key, c["iso3"])
    return CountryForecasts(
        meta=ctx.meta(), iso3=c["iso3"], run_key=run_key, eligible=bool(fc),
        reason=None if fc else q.no_forecast_reason(session, ctx, c["iso3"]),
        forecasts=fc, country_metrics=metrics,
    )


@router.get("/forecasts/{forecast_id}/explanation", response_model=Explanation,
            summary="SHAP contributors for one forecast (tree models only)")
def forecast_explanation(forecast_id: int, session: Session = Depends(get_session)
                         ) -> Explanation:
    return q.explanation(session, forecast_id)


@router.get("/backtest", response_model=CountryBacktest,
            summary="Out-of-sample backtest predictions vs. actuals for one country")
def backtest(iso3: str, model_version_id: int, session: Session = Depends(get_session),
             disease: Disease = "influenza") -> CountryBacktest:
    ctx = load_disease(session, disease)
    c = country_row(session, iso3)
    v = q.version(session, model_version_id)
    latest = session.execute(text("SELECT count(*) FROM backtest_predictions "
                                  "WHERE model_version_id = :v"), {"v": v["id"]}).scalar()
    if not latest:
        raise ApiError(404, "no_backtest",
                       "Backtest detail is kept only for the current run.")
    return CountryBacktest(meta=ctx.meta(), iso3=c["iso3"], model_version_id=v["id"],
                           model_type=v["model_type"], horizon_weeks=v["horizon_weeks"],
                           points=q.backtest_points(session, v["id"], c["iso3"]))
