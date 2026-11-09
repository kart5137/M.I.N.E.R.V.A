from __future__ import annotations

from datetime import date

from pydantic import BaseModel

from app.schemas.common import ResponseMeta, WindowInfo


class CountryListItem(BaseModel):
    iso3: str
    name: str
    who_region: str | None
    has_geometry: bool
    tier: str | None
    last_reported_week: date | None
    weeks_reported: int


class CountryList(BaseModel):
    meta: ResponseMeta
    total: int
    page: int
    page_size: int
    items: list[CountryListItem]


class Population(BaseModel):
    year: int
    value: int
    source: str


class Coverage(BaseModel):
    reference_week: date
    tier: str
    completeness: float
    longest_gap: int
    median_tests: float | None
    weeks_since_last: int | None


class SurveillanceSummary(BaseModel):
    first_week: date | None
    last_reported_week: date | None
    weeks_reported: int


class CountryProfile(BaseModel):
    meta: ResponseMeta
    iso3: str
    iso2: str | None
    name: str
    who_region: str | None
    hemisphere: str | None
    transmission_zone: str | None
    has_geometry: bool
    population: Population | None
    coverage: Coverage | None
    surveillance: SurveillanceSummary


class SeriesPoint(BaseModel):
    week_start: date
    reported: bool  # False: no row or no specimens tested (no surveillance, not zero flu)
    specimens_tested: float | None
    positives: float | None
    positivity: float | None
    is_provisional: bool


class CountryTimeseries(BaseModel):
    meta: ResponseMeta
    iso3: str
    window: WindowInfo
    points: list[SeriesPoint]
