"""Alerts and reports (M7).

Alerts are derived deterministically from stored detection outputs by rules
(pipeline/src/ei_pipeline/intelligence/alerts.py). They are keyed by
(disease, country, type, week) and upserted on every detection run, so links from reports
survive reruns; an alert that a rerun no longer produces (e.g. after a data revision) is
marked `retracted`, never deleted.

Reports are deterministic templates over stored facts (services/api/app/reports). Each
stores its facts (`content`), the rendered Markdown and the SHA-256 of the canonical
facts, so it can be regenerated and checked for identity.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ei_db.base import Base


class Alert(Base):
    __tablename__ = "alerts"
    __table_args__ = (
        UniqueConstraint("disease_id", "iso3", "alert_type", "week_start"),
        Index("ix_alerts_week", "disease_id", "week_start"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    disease_id: Mapped[int] = mapped_column(ForeignKey("diseases.id"), nullable=False)
    iso3: Mapped[str] = mapped_column(ForeignKey("countries.iso3"), nullable=False, index=True)
    #: new_anomaly | new_hotspot | risk_escalation | sustained_growth
    alert_type: Mapped[str] = mapped_column(String(32), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)  # low|medium|high
    week_start: Mapped[date] = mapped_column(Date, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    #: Facts behind the alert (values, thresholds, rule) as of the last run producing it.
    details: Mapped[dict] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="active")
    anomaly_id: Mapped[int | None] = mapped_column(
        ForeignKey("anomalies.id", ondelete="SET NULL"))
    hotspot_id: Mapped[int | None] = mapped_column(
        ForeignKey("hotspot_results.id", ondelete="SET NULL"))
    risk_id: Mapped[int | None] = mapped_column(
        ForeignKey("risk_assessments.id", ondelete="SET NULL"))
    first_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("detection_runs.id", ondelete="SET NULL"))
    last_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("detection_runs.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False)
    retracted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class IntelligenceReport(Base):
    __tablename__ = "intelligence_reports"
    __table_args__ = (Index("ix_reports_inputs", "inputs_sha256"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    disease_id: Mapped[int] = mapped_column(ForeignKey("diseases.id"), nullable=False)
    scope: Mapped[str] = mapped_column(String(16), nullable=False)  # global | country
    iso3: Mapped[str | None] = mapped_column(ForeignKey("countries.iso3"), index=True)
    region: Mapped[str | None] = mapped_column(String(8))
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    weeks: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[dict] = mapped_column(JSONB, nullable=False)
    rendered_md: Mapped[str] = mapped_column(Text, nullable=False)
    generator: Mapped[str] = mapped_column(String(16), nullable=False)  # template
    template_version: Mapped[str] = mapped_column(String(16), nullable=False)
    inputs_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False)


class ReportAlert(Base):
    __tablename__ = "report_alerts"

    report_id: Mapped[int] = mapped_column(
        ForeignKey("intelligence_reports.id", ondelete="CASCADE"), primary_key=True)
    alert_id: Mapped[int] = mapped_column(
        ForeignKey("alerts.id", ondelete="CASCADE"), primary_key=True)
