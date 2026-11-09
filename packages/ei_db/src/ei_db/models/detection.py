"""Detection outputs (M6): seasonal thresholds, risk, anomalies, hotspots.

Each `ei detect run` records a `detection_runs` row and replaces the previous outputs
for the disease (they are fully recomputable from `surveillance_weekly` and the active
forecasts). Method details: docs/DESIGN.md §6.3–6.5.
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


class DetectionRun(Base):
    __tablename__ = "detection_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    disease_id: Mapped[int] = mapped_column(ForeignKey("diseases.id"), nullable=False)
    run_key: Mapped[str] = mapped_column(String(40), nullable=False, unique=True)
    reference_week: Mapped[date] = mapped_column(Date, nullable=False)
    latest_week: Mapped[date] = mapped_column(Date, nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    git_sha: Mapped[str | None] = mapped_column(String(40))
    #: Settings used and counts produced (thresholds, anomalies, hotspots, risk).
    summary: Mapped[dict | None] = mapped_column(JSONB)


class SeasonalThreshold(Base):
    """Moving Epidemic Method thresholds for one country and season, computed from
    earlier non-COVID seasons only."""

    __tablename__ = "seasonal_thresholds"
    __table_args__ = (UniqueConstraint("disease_id", "iso3", "season_start", "method"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("detection_runs.id", ondelete="CASCADE"), nullable=False
    )
    disease_id: Mapped[int] = mapped_column(ForeignKey("diseases.id"), nullable=False)
    iso3: Mapped[str] = mapped_column(ForeignKey("countries.iso3"), nullable=False, index=True)
    season: Mapped[str] = mapped_column(String(8), nullable=False)  # "2025/26" or "2026"
    season_start: Mapped[date] = mapped_column(Date, nullable=False)
    method: Mapped[str] = mapped_column(String(16), nullable=False)  # "mem"
    # Positivity as a fraction (0–1), like surveillance_weekly.positivity.
    epidemic_threshold: Mapped[float] = mapped_column(Double, nullable=False)
    post_threshold: Mapped[float | None] = mapped_column(Double)
    medium: Mapped[float] = mapped_column(Double, nullable=False)
    high: Mapped[float] = mapped_column(Double, nullable=False)
    very_high: Mapped[float] = mapped_column(Double, nullable=False)
    n_seasons_used: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    seasons_used: Mapped[list] = mapped_column(JSONB, nullable=False)
    #: Mean epidemic length (weeks) of the seasons used, from the MEM timing step.
    mean_epidemic_weeks: Mapped[float | None] = mapped_column(Double)
    #: NULL when the levels are usable; otherwise why not (e.g. epidemic threshold above
    #: medium intensity). Unusable thresholds are kept for transparency but never used
    #: for risk.
    quality_note: Mapped[str | None] = mapped_column(Text)


class RiskAssessment(Base):
    """Risk level of a 2-week-ahead forecast against the season's MEM thresholds.
    Forecast values and the thresholds used are copied in, so the row stays meaningful
    after forecast or detection reruns. Unlike the other outputs, risk rows are kept
    across runs (one per country and assessed week): the history drives the
    risk-escalation alert (M7)."""

    __tablename__ = "risk_assessments"
    __table_args__ = (UniqueConstraint("disease_id", "iso3", "assessed_week"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("detection_runs.id", ondelete="CASCADE"), nullable=False
    )
    disease_id: Mapped[int] = mapped_column(ForeignKey("diseases.id"), nullable=False)
    iso3: Mapped[str] = mapped_column(ForeignKey("countries.iso3"), nullable=False, index=True)
    assessed_week: Mapped[date] = mapped_column(Date, nullable=False)  # forecast origin
    target_week: Mapped[date] = mapped_column(Date, nullable=False)
    risk_level: Mapped[str] = mapped_column(String(16), nullable=False)  # low|moderate|high
    rule: Mapped[str] = mapped_column(Text, nullable=False)
    forecast_point: Mapped[float] = mapped_column(Double, nullable=False)
    forecast_lo80: Mapped[float | None] = mapped_column(Double)
    forecast_hi80: Mapped[float | None] = mapped_column(Double)
    model_type: Mapped[str] = mapped_column(String(32), nullable=False)
    forecast_id: Mapped[int | None] = mapped_column(
        ForeignKey("forecasts.id", ondelete="SET NULL")
    )
    threshold_id: Mapped[int | None] = mapped_column(
        ForeignKey("seasonal_thresholds.id", ondelete="SET NULL")
    )
    season: Mapped[str | None] = mapped_column(String(8))
    epidemic_threshold: Mapped[float | None] = mapped_column(Double)
    high_threshold: Mapped[float | None] = mapped_column(Double)


class Anomaly(Base):
    """A week whose positivity is unusually high for that country and time of year.

    `method` = "seasonal_ewma" (primary: above the seasonal upper band and the EWMA
    control chart signals) or "isolation_forest" (secondary signal, never an alert)."""

    __tablename__ = "anomalies"
    __table_args__ = (
        UniqueConstraint("disease_id", "iso3", "week_start", "method"),
        Index("ix_anomalies_week", "disease_id", "week_start"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("detection_runs.id", ondelete="CASCADE"), nullable=False
    )
    disease_id: Mapped[int] = mapped_column(ForeignKey("diseases.id"), nullable=False)
    iso3: Mapped[str] = mapped_column(ForeignKey("countries.iso3"), nullable=False, index=True)
    week_start: Mapped[date] = mapped_column(Date, nullable=False)
    metric: Mapped[str] = mapped_column(String(16), nullable=False)  # "positivity"
    method: Mapped[str] = mapped_column(String(24), nullable=False)
    observed: Mapped[float] = mapped_column(Double, nullable=False)
    expected: Mapped[float | None] = mapped_column(Double)
    upper_band: Mapped[float | None] = mapped_column(Double)
    #: seasonal_ewma: standardised residual; isolation_forest: anomaly score (higher = rarer).
    score: Mapped[float] = mapped_column(Double, nullable=False)
    ewma: Mapped[float | None] = mapped_column(Double)
    ewma_limit: Mapped[float | None] = mapped_column(Double)
    specimens_tested: Mapped[int | None] = mapped_column(Integer)
    severity: Mapped[str | None] = mapped_column(String(16))  # moderate|high|severe
    is_provisional: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false(), nullable=False
    )
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class HotspotResult(Base):
    """Local spatial statistic for one country over a window of weeks."""

    __tablename__ = "hotspot_results"
    __table_args__ = (
        UniqueConstraint("disease_id", "iso3", "window_end", "window_weeks", "statistic"),
        Index("ix_hotspot_results_window", "disease_id", "window_end", "statistic"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("detection_runs.id", ondelete="CASCADE"), nullable=False
    )
    disease_id: Mapped[int] = mapped_column(ForeignKey("diseases.id"), nullable=False)
    iso3: Mapped[str] = mapped_column(ForeignKey("countries.iso3"), nullable=False, index=True)
    window_end: Mapped[date] = mapped_column(Date, nullable=False)
    window_weeks: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    statistic: Mapped[str] = mapped_column(String(16), nullable=False)  # gi_star|local_moran
    #: Pooled positivity of the country over the window (the input value).
    value: Mapped[float] = mapped_column(Double, nullable=False)
    stat_value: Mapped[float] = mapped_column(Double, nullable=False)
    z_score: Mapped[float] = mapped_column(Double, nullable=False)
    p_value: Mapped[float] = mapped_column(Double, nullable=False)  # permutation pseudo-p
    p_fdr: Mapped[float] = mapped_column(Double, nullable=False)    # Benjamini–Hochberg
    #: gi_star: hot|cold|ns · local_moran: HH|LL|HL|LH|ns
    classification: Mapped[str] = mapped_column(String(8), nullable=False)
    n_neighbours: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    #: "queen" or "knn" — how this country's neighbours were found.
    neighbour_source: Mapped[str] = mapped_column(String(8), nullable=False)
    weights_spec: Mapped[str] = mapped_column(Text, nullable=False)
