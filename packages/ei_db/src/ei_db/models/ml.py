"""Forecasting registry and outputs (M5).

A training *run* (`run_key`) fits every model type for every horizon. Each
(model type, horizon) is one `model_versions` row; per horizon exactly one version of the
latest run is active (selection rule in docs/DESIGN.md §6.2).
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Double,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    false,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ei_db.base import Base


class ModelVersion(Base):
    __tablename__ = "model_versions"
    __table_args__ = (
        UniqueConstraint("run_key", "model_type", "target", "horizon_weeks"),
        Index("ix_model_versions_active", "disease_id", "target", "horizon_weeks", "is_active"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    disease_id: Mapped[int] = mapped_column(ForeignKey("diseases.id"), nullable=False)
    run_key: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    model_type: Mapped[str] = mapped_column(String(32), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)  # "baseline" | "ml"
    target: Mapped[str] = mapped_column(String(16), nullable=False)
    horizon_weeks: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    train_start: Mapped[date | None] = mapped_column(Date)
    train_end: Mapped[date] = mapped_column(Date, nullable=False)
    features: Mapped[list | None] = mapped_column(JSONB)
    hyperparams: Mapped[dict | None] = mapped_column(JSONB)
    # Mean |SHAP| per feature over the latest forecasts (tree models only).
    global_importance: Mapped[dict | None] = mapped_column(JSONB)
    artefact_uri: Mapped[str | None] = mapped_column(Text)
    git_sha: Mapped[str | None] = mapped_column(String(40))
    trained_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false(), nullable=False
    )
    selection_note: Mapped[str | None] = mapped_column(Text)


class ModelEvaluation(Base):
    """Backtest metric for one model version: pooled (`iso3` NULL) or per country."""

    __tablename__ = "model_evaluations"
    __table_args__ = (UniqueConstraint("model_version_id", "iso3", "metric"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    model_version_id: Mapped[int] = mapped_column(
        ForeignKey("model_versions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    iso3: Mapped[str | None] = mapped_column(ForeignKey("countries.iso3"))
    metric: Mapped[str] = mapped_column(String(24), nullable=False)
    value: Mapped[float | None] = mapped_column(Double)
    n_obs: Mapped[int] = mapped_column(Integer, nullable=False)
    n_origins: Mapped[int] = mapped_column(Integer, nullable=False)
    eval_start: Mapped[date] = mapped_column(Date, nullable=False)
    eval_end: Mapped[date] = mapped_column(Date, nullable=False)


class Forecast(Base):
    __tablename__ = "forecasts"
    __table_args__ = (
        UniqueConstraint("model_version_id", "iso3", "origin_week"),
        Index("ix_forecasts_iso3_origin", "iso3", "origin_week"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    model_version_id: Mapped[int] = mapped_column(
        ForeignKey("model_versions.id", ondelete="CASCADE"), nullable=False
    )
    disease_id: Mapped[int] = mapped_column(ForeignKey("diseases.id"), nullable=False)
    iso3: Mapped[str] = mapped_column(ForeignKey("countries.iso3"), nullable=False)
    origin_week: Mapped[date] = mapped_column(Date, nullable=False)
    target_week: Mapped[date] = mapped_column(Date, nullable=False)
    horizon_weeks: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    target: Mapped[str] = mapped_column(String(16), nullable=False)
    point: Mapped[float] = mapped_column(Double, nullable=False)
    lo80: Mapped[float | None] = mapped_column(Double)
    hi80: Mapped[float | None] = mapped_column(Double)
    lo95: Mapped[float | None] = mapped_column(Double)
    hi95: Mapped[float | None] = mapped_column(Double)
    # SHAP expected value (model output scale, logit) for the explanation waterfall.
    explanation_base: Mapped[float | None] = mapped_column(Double)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ForecastExplanation(Base):
    """Top contributors to one forecast (SHAP values on the model's logit scale)."""

    __tablename__ = "forecast_explanations"

    forecast_id: Mapped[int] = mapped_column(
        ForeignKey("forecasts.id", ondelete="CASCADE"), primary_key=True
    )
    feature: Mapped[str] = mapped_column(String(64), primary_key=True)
    shap_value: Mapped[float] = mapped_column(Double, nullable=False)
    feature_value: Mapped[float | None] = mapped_column(Double)
    rank: Mapped[int] = mapped_column(SmallInteger, nullable=False)


class BacktestPrediction(Base):
    """Out-of-sample prediction at a past origin, with the value later observed."""

    __tablename__ = "backtest_predictions"
    __table_args__ = (
        UniqueConstraint("model_version_id", "iso3", "origin_week"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    model_version_id: Mapped[int] = mapped_column(
        ForeignKey("model_versions.id", ondelete="CASCADE"), nullable=False
    )
    iso3: Mapped[str] = mapped_column(ForeignKey("countries.iso3"), nullable=False)
    origin_week: Mapped[date] = mapped_column(Date, nullable=False)
    target_week: Mapped[date] = mapped_column(Date, nullable=False)
    point: Mapped[float] = mapped_column(Double, nullable=False)
    lo80: Mapped[float | None] = mapped_column(Double)
    hi80: Mapped[float | None] = mapped_column(Double)
    lo95: Mapped[float | None] = mapped_column(Double)
    hi95: Mapped[float | None] = mapped_column(Double)
    actual: Mapped[float] = mapped_column(Double, nullable=False)
