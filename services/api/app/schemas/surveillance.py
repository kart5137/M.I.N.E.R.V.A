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
    #: Laboratory diseases (influenza); null for case-based diseases.
    specimens_tested: float | None
    positives: float | None
    positivity: float | None
    weeks_reported: int
    provisional_weeks: int
    tier: str | None
    #: Case-based diseases (dengue); null for influenza. `grain` says whether the value
    #: comes from weekly reports in the window or, for countries without weekly reports
    #: there, from the calendar months overlapping it (`period_start`–`period_end`).
    cases: float | None = None
    incidence: float | None = None  # cases per 100,000 per week
    population: int | None = None
    grain: str | None = None
    periods_reported: int | None = None
    period_start: date | None = None
    period_end: date | None = None


class GlobalSurveillance(BaseModel):
    meta: ResponseMeta
    window: WindowInfo
    region: str | None
    countries: list[CountryWindowValue]


class Kpi(BaseModel):
    value: float | None
    previous: float | None
    change: float | None
    change_unit: str  # "percent" (relative), "pp" (percentage points) or "count"
    #: Countries the count is out of (detection KPIs), and how it is defined.
    denominator: int | None = None
    note: str | None = None


class PendingKpi(BaseModel):
    key: str
    label: str
    available_in: str


class Kpis(BaseModel):
    #: Influenza only (null for case-based diseases).
    detections: Kpi | None
    positivity: Kpi | None
    countries_reporting: Kpi
    #: Case-based diseases only: reported cases and cases per 100,000 per week.
    cases: Kpi | None = None
    incidence: Kpi | None = None
    #: M6 detection KPIs (null when `ei detect run` has not produced outputs yet).
    anomalies: Kpi | None
    hotspots: Kpi | None
    above_threshold: Kpi | None
    pending: list[PendingKpi]


class TrendPoint(BaseModel):
    week_start: date
    specimens_tested: float | None
    positives: float | None
    positivity: float | None
    countries_reporting: int
    is_provisional: bool
    cases: float | None = None
    incidence: float | None = None


class Mover(BaseModel):
    """Influenza: change in positivity (pp). Case-based: relative change in incidence."""

    iso3: str
    name: str
    positivity: float | None = None
    previous_positivity: float | None = None
    change_pp: float | None = None
    specimens_tested: float | None = None
    incidence: float | None = None
    previous_incidence: float | None = None
    change_pct: float | None = None
    cases: float | None = None


class Overview(BaseModel):
    meta: ResponseMeta
    window: WindowInfo
    previous_window: WindowInfo
    region: str | None
    kpis: Kpis
    trend: list[TrendPoint]
    top_movers: list[Mover]
    movers_min_specimens: int
    #: Case-based diseases: movers need at least this many cases in both windows.
    movers_min_cases: int | None = None
