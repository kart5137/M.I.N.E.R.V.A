from __future__ import annotations

from datetime import date

from pydantic import BaseModel

from app.schemas.common import ResponseMeta, WindowInfo


class DiseaseOut(BaseModel):
    key: str
    name: str
    primary_metric: str
    metric_label: str
    supports_forecast: bool
    supports_anomaly: bool
    supports_hotspots: bool


class CountryWindowValue(BaseModel):
    iso3: str
    name: str
    who_region: str | None
    has_geometry: bool
    specimens_tested: float | None
    positives: float | None
    positivity: float | None
    weeks_reported: int
    provisional_weeks: int
    tier: str | None


class GlobalSurveillance(BaseModel):
    meta: ResponseMeta
    window: WindowInfo
    region: str | None
    countries: list[CountryWindowValue]


class Kpi(BaseModel):
    value: float | None
    previous: float | None
    change: float | None
    change_unit: str  # "percent" (relative) or "pp" (percentage points)


class PendingKpi(BaseModel):
    key: str
    label: str
    available_in: str


class Kpis(BaseModel):
    detections: Kpi
    positivity: Kpi
    countries_reporting: Kpi
    pending: list[PendingKpi]


class TrendPoint(BaseModel):
    week_start: date
    specimens_tested: float | None
    positives: float | None
    positivity: float | None
    countries_reporting: int
    is_provisional: bool


class Mover(BaseModel):
    iso3: str
    name: str
    positivity: float
    previous_positivity: float
    change_pp: float
    specimens_tested: float


class Overview(BaseModel):
    meta: ResponseMeta
    window: WindowInfo
    previous_window: WindowInfo
    region: str | None
    kpis: Kpis
    trend: list[TrendPoint]
    top_movers: list[Mover]
    movers_min_specimens: int
