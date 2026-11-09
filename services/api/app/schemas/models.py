from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel

from app.schemas.common import ResponseMeta


class Metrics(BaseModel):
    mae: float | None = None
    rmse: float | None = None
    mase: float | None = None
    skill_vs_snaive: float | None = None
    coverage_80: float | None = None
    coverage_95: float | None = None
    n_obs: int | None = None
    n_origins: int | None = None


class ModelSummary(BaseModel):
    id: int
    model_type: str
    label: str
    kind: str
    horizon_weeks: int
    is_active: bool
    selection_note: str | None
    metrics: Metrics  # pooled backtest


class ModelRun(BaseModel):
    meta: ResponseMeta
    run_key: str | None
    target: str
    trained_at: datetime | None
    train_end: date | None
    eval_start: date | None
    eval_end: date | None
    models: list[ModelSummary]


class CountryMetric(BaseModel):
    iso3: str
    name: str
    metrics: Metrics


class Importance(BaseModel):
    feature: str
    label: str
    value: float


class ErrorPoint(BaseModel):
    origin_week: date
    mae: float
    n: int


class ModelDetail(BaseModel):
    meta: ResponseMeta
    id: int
    run_key: str
    model_type: str
    label: str
    kind: str
    target: str
    horizon_weeks: int
    is_active: bool
    selection_note: str | None
    train_start: date | None
    train_end: date
    trained_at: datetime
    features: list[str] | None
    hyperparams: dict | None
    git_sha: str | None
    artefact_uri: str | None
    metrics: Metrics
    reference: Metrics  # seasonal-naive, same run and horizon
    importance: list[Importance]
    error_by_origin: list[ErrorPoint]
    countries: list[CountryMetric]


class ForecastOut(BaseModel):
    id: int
    model_version_id: int
    model_type: str
    label: str
    is_active: bool
    horizon_weeks: int
    origin_week: date
    target_week: date
    point: float
    lo80: float | None
    hi80: float | None
    lo95: float | None
    hi95: float | None
    has_explanation: bool


class CountryForecasts(BaseModel):
    meta: ResponseMeta
    iso3: str
    run_key: str | None
    eligible: bool
    reason: str | None  # why there is no forecast, when there is none
    forecasts: list[ForecastOut]
    country_metrics: dict[str, Metrics]  # key: "<model_type>:<horizon>"


class Contribution(BaseModel):
    feature: str
    label: str
    shap_value: float
    feature_value: float | None
    rank: int


class Explanation(BaseModel):
    forecast_id: int
    model_type: str
    horizon_weeks: int
    base_value: float | None  # logit scale
    prediction_logit: float
    point: float
    other_features: float  # sum of contributions not in the top-k (logit)
    contributions: list[Contribution]


class BacktestPoint(BaseModel):
    origin_week: date
    target_week: date
    point: float
    lo80: float | None
    hi80: float | None
    lo95: float | None
    hi95: float | None
    actual: float


class CountryBacktest(BaseModel):
    meta: ResponseMeta
    iso3: str
    model_version_id: int
    model_type: str
    horizon_weeks: int
    points: list[BacktestPoint]
