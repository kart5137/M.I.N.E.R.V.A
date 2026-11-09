from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.common import ResponseMeta


class AlertItem(BaseModel):
    id: int
    iso3: str
    name: str
    who_region: str | None
    alert_type: str
    severity: str
    week_start: date
    title: str
    details: dict
    status: str
    created_at: datetime
    retracted_at: datetime | None


class AlertList(BaseModel):
    meta: ResponseMeta
    rules: dict[str, str]
    total: int
    page: int
    page_size: int
    by_type: dict[str, int]
    by_severity: dict[str, int]
    items: list[AlertItem]


class ReportSummary(BaseModel):
    id: int
    title: str
    scope: str
    iso3: str | None
    region: str | None
    period_start: date
    period_end: date
    weeks: int
    generator: str
    template_version: str
    inputs_sha256: str
    created_at: datetime
    alerts: int


class ReportList(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[ReportSummary]


class ReportDetail(ReportSummary):
    content: dict
    rendered_md: str


class GenerateRequest(BaseModel):
    scope: Literal["global", "country"] = "global"
    iso3: str | None = Field(default=None, description="Required for a country report.")
    region: str | None = Field(default=None, description="WHO region (global reports).")
    to: date | None = Field(default=None, description="Period end (default: reference week).")
    weeks: int = Field(default=4, ge=1, le=52)


class GenerateResponse(BaseModel):
    report: ReportDetail
    #: True when an identical report (same scope and inputs) already existed.
    reused: bool


class Verification(BaseModel):
    report_id: int
    stored_sha256: str
    current_sha256: str
    inputs_identical: bool
    #: Rendering the stored facts again gives the stored Markdown byte for byte.
    rendering_identical: bool
    #: Regenerating from the database now gives the stored Markdown byte for byte.
    regenerated_identical: bool
    changed_sections: list[str]


class SourceInfo(BaseModel):
    key: str
    name: str
    url: str | None
    licence: str | None
    attribution: str | None
    notes: str | None
    last_ingestion: datetime | None
    last_status: str | None
    #: Rows currently stored from this source (country-weeks, boundaries, or
    #: population + indicator values).
    stored_rows: int


class TierInfo(BaseModel):
    tier: str
    countries: int
    rule: str


class About(BaseModel):
    meta: ResponseMeta
    sources: list[SourceInfo]
    coverage_reference_week: date | None
    tiers: list[TierInfo]
    forecast_run: dict | None
    detection_run: dict | None
    limitations: list[str]
