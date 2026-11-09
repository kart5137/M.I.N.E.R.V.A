from __future__ import annotations

from datetime import datetime
from typing import Any

from geoalchemy2 import Geometry
from sqlalchemy import CHAR, Boolean, DateTime, ForeignKey, Integer, String, Text, false, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ei_db.base import Base, TimestampMixin


class Country(TimestampMixin, Base):
    __tablename__ = "countries"

    iso3: Mapped[str] = mapped_column(CHAR(3), primary_key=True)
    iso2: Mapped[str | None] = mapped_column(CHAR(2))
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    who_region: Mapped[str | None] = mapped_column(String(8))
    hemisphere: Mapped[str | None] = mapped_column(String(4))
    transmission_zone: Mapped[str | None] = mapped_column(String(32))
    continent: Mapped[str | None] = mapped_column(String(32))
    # NULL for reporting areas without a boundary in the boundary dataset.
    geom: Mapped[Any | None] = mapped_column(
        Geometry("MULTIPOLYGON", srid=4326, spatial_index=True), nullable=True
    )
    centroid: Mapped[Any | None] = mapped_column(
        Geometry("POINT", srid=4326, spatial_index=False), nullable=True
    )


class DataSource(TimestampMixin, Base):
    __tablename__ = "data_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    url: Mapped[str | None] = mapped_column(Text)
    licence: Mapped[str | None] = mapped_column(String(200))
    attribution_text: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)


class CountryCodeAlias(Base):
    """Maps a source-specific code (e.g. FluNet 'X09', 'XKX') to a country."""

    __tablename__ = "country_code_aliases"

    alias: Mapped[str] = mapped_column(String(16), primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("data_sources.id"), primary_key=True)
    iso3: Mapped[str] = mapped_column(ForeignKey("countries.iso3"), nullable=False)
    note: Mapped[str | None] = mapped_column(Text)


class Disease(TimestampMixin, Base):
    __tablename__ = "diseases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    native_granularity: Mapped[str] = mapped_column(String(16), nullable=False)
    primary_metric: Mapped[str] = mapped_column(String(32), nullable=False)
    metric_label: Mapped[str] = mapped_column(String(100), nullable=False)
    supports_forecast: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false(), nullable=False
    )
    supports_anomaly: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false(), nullable=False
    )
    supports_hotspots: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false(), nullable=False
    )


class IngestionRun(Base):
    __tablename__ = "ingestion_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("data_sources.id"), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(
        String(16), default="running", server_default="running", nullable=False
    )
    raw_rows: Mapped[int | None] = mapped_column(Integer)
    loaded_rows: Mapped[int | None] = mapped_column(Integer)
    raw_sha256: Mapped[str | None] = mapped_column(CHAR(64))
    quality_report: Mapped[dict | None] = mapped_column(JSONB)
