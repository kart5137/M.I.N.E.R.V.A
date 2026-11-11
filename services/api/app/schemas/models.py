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
    feature_value: float | None  # as the model saw it (model scale for level features)
    #: Dengue level features (this week, means, peak, last year) converted back to
    #: incidence per 100,000; null otherwise.
    natural_value: float | None = None
    rank: int


class Explanation(BaseModel):
    forecast_id: int
    model_type: str
    horizon_weeks: int
    #: "positivity" (model scale: logit) or "incidence" (model scale: log(incidence + one
    #: case per 100,000); the tree models learn the change from the origin week, so the
    #: base value includes the origin week's level).
    target: str = "positivity"
    base_value: float | None  # model scale
    prediction_logit: float   # the forecast on the model scale (logit for positivity)
    point: float
    other_features: float  # sum of contributions not in the top-k (model scale)
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


class GlobalForecastItem(BaseModel):
    iso3: str
    name: str
    who_region: str | None
    origin_week: date
    target_week: date
    #: Observed value in the origin week (what the forecast starts from): positivity
    #: (0–1) or incidence per 100,000.
    origin_value: float | None
    point: float
    lo80: float | None
    hi80: float | None
    #: Positivity: point − origin_value, in percentage points.
    change_pp: float | None
    #: Incidence: relative change from the origin week, in percent.
    change_pct: float | None = None


class GlobalForecasts(BaseModel):
    meta: ResponseMeta
    run_key: str | None
    horizon_weeks: int
    model_type: str | None
    model_label: str | None
    items: list[GlobalForecastItem]


class HorizonScore(BaseModel):
    """Live accuracy of the published forecasts at one horizon (all origins pooled)."""
    horizon_weeks: int
    model_label: str
    #: Published forecasts; scored = target week settled with a valid observation;
    #: pending = target week not settled yet; unscorable = settled but no valid value.
    published: int
    scored: int
    pending: int
    unscorable: int
    origins: int
    mae: float | None
    last_value_mae: float | None
    skill_vs_last_value: float | None
    coverage_80: float | None
    coverage_95: float | None
    #: The latest selected model's pooled backtest, for comparison.
    backtest_mae: float | None
    backtest_coverage_80: float | None


class OriginScore(BaseModel):
    origin_week: date
    horizon_weeks: int
    run_key: str
    model_label: str
    published: int
    scored: int
    mae: float | None
    coverage_80: float | None


class ScoredForecast(BaseModel):
    iso3: str
    name: str
    origin_week: date
    target_week: date
    horizon_weeks: int
    model_label: str
    point: float
    lo80: float | None
    hi80: float | None
    actual: float
    last_value: float | None
    abs_error: float
    in_80: bool | None


class Scorecard(BaseModel):
    meta: ResponseMeta
    target: str
    rule: str
    #: The earliest target week still waiting to settle (scores arrive after it does).
    next_target_week: date | None
    horizons: list[HorizonScore]
    origins: list[OriginScore]
    recent: list[ScoredForecast]
