"""Weather at one representative point per country (post-MVP phase D3).

Weekly aggregates only: daily values are aggregated on ingestion and not stored."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import CHAR, Date, DateTime, Double, ForeignKey, Integer, SmallInteger, String, func
from sqlalchemy.orm import Mapped, mapped_column

from ei_db.base import Base


class WeatherPoint(Base):
    """The point whose weather stands for the country, and why it was chosen."""

    __tablename__ = "weather_points"

    iso3: Mapped[str] = mapped_column(ForeignKey("countries.iso3"), primary_key=True)
    lat: Mapped[float] = mapped_column(Double, nullable=False)
    lon: Mapped[float] = mapped_column(Double, nullable=False)
    #: "label_point" (Natural Earth label point) or "main_town" (areas without a boundary).
    basis: Mapped[str] = mapped_column(String(16), nullable=False)
    #: Elevation of the source grid cell (m), as reported by the source.
    elevation_m: Mapped[float | None] = mapped_column(Double)
    source_id: Mapped[int] = mapped_column(ForeignKey("data_sources.id"), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class WeatherWeekly(Base):
    """One complete ISO week (Monday–Sunday, all 7 days present) per country."""

    __tablename__ = "weather_weekly"

    iso3: Mapped[str] = mapped_column(CHAR(3), ForeignKey("countries.iso3"), primary_key=True)
    week_start: Mapped[date] = mapped_column(Date, primary_key=True)
    iso_year: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    iso_week: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    #: Mean of daily mean 2 m temperature (°C).
    temperature: Mapped[float] = mapped_column(Double, nullable=False)
    #: Total precipitation over the week (mm).
    precipitation: Mapped[float] = mapped_column(Double, nullable=False)
    #: Mean of daily mean 2 m relative humidity (%).
    humidity: Mapped[float] = mapped_column(Double, nullable=False)
    source_id: Mapped[int] = mapped_column(ForeignKey("data_sources.id"), nullable=False)
    ingestion_run_id: Mapped[int] = mapped_column(Integer, ForeignKey("ingestion_runs.id"),
                                                  nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
