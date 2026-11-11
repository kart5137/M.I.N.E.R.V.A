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
    false,
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
    is_provisional: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false(), nullable=False
    )
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


class SurveillanceMonthly(Base):
    """One row per disease, country and calendar month, for sources that report monthly
    (e.g. many WHO dengue reporters). Kept monthly: never split into invented weeks."""

    __tablename__ = "surveillance_monthly"
    __table_args__ = (
        UniqueConstraint("disease_id", "iso3", "month_start"),
        Index("ix_surveillance_monthly_disease_month", "disease_id", "month_start"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    disease_id: Mapped[int] = mapped_column(ForeignKey("diseases.id"), nullable=False)
    iso3: Mapped[str] = mapped_column(ForeignKey("countries.iso3"), nullable=False)
    month_start: Mapped[date] = mapped_column(Date, nullable=False)
    cases: Mapped[float | None] = mapped_column(Double)
    breakdown: Mapped[dict | None] = mapped_column(JSONB)
    is_provisional: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false(), nullable=False
    )
    source_id: Mapped[int] = mapped_column(ForeignKey("data_sources.id"), nullable=False)
    ingestion_run_id: Mapped[int] = mapped_column(ForeignKey("ingestion_runs.id"), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class SurveillanceMonthlyRevision(Base):
    """Append-only history of revised monthly values."""

    __tablename__ = "surveillance_monthly_revisions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    surveillance_monthly_id: Mapped[int] = mapped_column(
        # Explicit name: the convention-generated one exceeds PostgreSQL's 63 characters.
        ForeignKey("surveillance_monthly.id", ondelete="CASCADE",
                   name="fk_surveillance_monthly_revisions_monthly"),
        nullable=False, index=True,
    )
    previous_values: Mapped[dict] = mapped_column(JSONB, nullable=False)
    revised_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    ingestion_run_id: Mapped[int] = mapped_column(ForeignKey("ingestion_runs.id"), nullable=False)


class SurveillanceAnnual(Base):
    """Yearly values for diseases reported annually (malaria, C1), in long form: one row
    per disease, area, year and measure. `scope` is "country" (area = ISO3, also in
    `iso3`), "region" (WHO region code) or "global" (area "GLOBAL"): WHO publishes regional
    and global totals with their own uncertainty ranges, which cannot be summed from
    countries. `low`/`high` bound modelled estimates; NULL for reported counts and for
    estimates that are taken from routine reporting."""

    __tablename__ = "surveillance_annual"
    __table_args__ = (
        UniqueConstraint("disease_id", "scope", "area", "year", "measure"),
        Index("ix_surveillance_annual_disease_year", "disease_id", "year"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    disease_id: Mapped[int] = mapped_column(ForeignKey("diseases.id"), nullable=False)
    scope: Mapped[str] = mapped_column(String(8), nullable=False)
    area: Mapped[str] = mapped_column(String(8), nullable=False)
    iso3: Mapped[str | None] = mapped_column(ForeignKey("countries.iso3"), index=True)
    year: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    measure: Mapped[str] = mapped_column(String(32), nullable=False)
    value: Mapped[float] = mapped_column(Double, nullable=False)
    low: Mapped[float | None] = mapped_column(Double)
    high: Mapped[float | None] = mapped_column(Double)
    source_id: Mapped[int] = mapped_column(ForeignKey("data_sources.id"), nullable=False)
    ingestion_run_id: Mapped[int] = mapped_column(ForeignKey("ingestion_runs.id"), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


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
    # Reporting grain the profile is measured in: "week" or "month". `completeness` and
    # `longest_gap` are in that unit; `weeks_since_last` is always in weeks.
    grain: Mapped[str] = mapped_column(String(8), server_default="week", nullable=False)
    completeness: Mapped[float] = mapped_column(Double, nullable=False)
    longest_gap: Mapped[int] = mapped_column(Integer, nullable=False)
    median_tests: Mapped[float | None] = mapped_column(Double)
    weeks_since_last: Mapped[int | None] = mapped_column(Integer)
