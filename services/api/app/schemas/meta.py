from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel


class Health(BaseModel):
    status: str
    version: str


class IngestionSummary(BaseModel):
    source: str
    status: str
    finished_at: datetime | None
    loaded_rows: int | None


class DiseaseStatus(BaseModel):
    key: str
    name: str
    reference_week: date | None
    provisional_from: date | None
    latest_week: date | None
    country_weeks: int


class MetaStatus(BaseModel):
    database: str
    postgis_version: str | None
    schema_revision: str | None
    diseases: list[DiseaseStatus]
    last_ingestions: list[IngestionSummary]
    demo: bool = False
