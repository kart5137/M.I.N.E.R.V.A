from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    CHAR,
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
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ei_db.base import Base


class SurveillanceWeekly(Base):
    """One row per disease, country and ISO week.

    Influenza rows carry lab results (specimens_tested, positives, positivity) and leave
    `cases` NULL; case-based diseases fill `cases`.
    """

    __tablename__ = "surveillance_weekly"
    __table_args__ = (
        UniqueConstraint("disease_id", "iso3", "week_start"),
        Index("ix_surveillance_weekly_disease_week", "disease_id", "week_start"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    disease_id: Mapped[int] = mapped_column(ForeignKey("diseases.id"), nullable=False)
    iso3: Mapped[str] = mapped_column(ForeignKey("countries.iso3"), nullable=False)
    week_start: Mapped[date] = mapped_column(Date, nullable=False)
    iso_year: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    iso_week: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    specimens_tested: Mapped[float | None] = mapped_column(Double)
    positives: Mapped[float | None] = mapped_column(Double)
    cases: Mapped[float | None] = mapped_column(Double)
    positivity: Mapped[float | None] = mapped_column(Double)
    breakdown: Mapped[dict | None] = mapped_column(JSONB)
    is_provisional: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    source_id: Mapped[int] = mapped_column(ForeignKey("data_sources.id"), nullable=False)
    ingestion_run_id: Mapped[int] = mapped_column(ForeignKey("ingestion_runs.id"), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class SurveillanceRevision(Base):
    """Append-only history: previous values when a source revises a past week."""

    __tablename__ = "surveillance_revisions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    surveillance_id: Mapped[int] = mapped_column(
        ForeignKey("surveillance_weekly.id", ondelete="CASCADE"), nullable=False, index=True
    )
    previous_values: Mapped[dict] = mapped_column(JSONB, nullable=False)
    revised_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    ingestion_run_id: Mapped[int] = mapped_column(ForeignKey("ingestion_runs.id"), nullable=False)


class PopulationAnnual(Base):
    __tablename__ = "population_annual"

    iso3: Mapped[str] = mapped_column(ForeignKey("countries.iso3"), primary_key=True)
    year: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    population: Mapped[int] = mapped_column(BigInteger, nullable=False)
    source_id: Mapped[int] = mapped_column(ForeignKey("data_sources.id"), nullable=False)


class HealthIndicator(Base):
    __tablename__ = "health_indicators"

    iso3: Mapped[str] = mapped_column(ForeignKey("countries.iso3"), primary_key=True)
    indicator_code: Mapped[str] = mapped_column(String(64), primary_key=True)
    year: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    value: Mapped[float] = mapped_column(Double, nullable=False)
    unit: Mapped[str | None] = mapped_column(String(64))
    source_id: Mapped[int] = mapped_column(ForeignKey("data_sources.id"), nullable=False)


class CoverageProfile(Base):
    """Profiler output; decides which countries are eligible for forecasting."""

    __tablename__ = "coverage_profiles"

    disease_id: Mapped[int] = mapped_column(ForeignKey("diseases.id"), primary_key=True)
    iso3: Mapped[str] = mapped_column(ForeignKey("countries.iso3"), primary_key=True)
    reference_week: Mapped[date] = mapped_column(Date, primary_key=True)
    tier: Mapped[str] = mapped_column(CHAR(1), nullable=False)
    completeness: Mapped[float] = mapped_column(Double, nullable=False)
    longest_gap: Mapped[int] = mapped_column(Integer, nullable=False)
    median_tests: Mapped[float | None] = mapped_column(Double)
    weeks_since_last: Mapped[int | None] = mapped_column(Integer)
