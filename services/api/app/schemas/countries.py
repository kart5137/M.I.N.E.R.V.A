from __future__ import annotations

from datetime import date

from pydantic import BaseModel

from app.schemas.common import ResponseMeta, WindowInfo
from app.schemas.surveillance import CountryWindowValue


class CountryListItem(BaseModel):
    iso3: str
    name: str
    who_region: str | None
    flu_season: str | None
    has_geometry: bool
    tier: str | None
    last_reported_week: date | None
    weeks_reported: int
    # Values for the recent window (see CountryList.window); null when not reported.
    positivity: float | None
    positives: float | None
    specimens_tested: float | None


class CountryList(BaseModel):
    meta: ResponseMeta
    window: WindowInfo
    sort: str
    order: str
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


class HealthValue(BaseModel):
    code: str
    label: str
    unit: str
    group: str
    value: float | None  # null: no value 2010+ in the source ("Not available")
    year: int | None
    source: str | None


class CountryProfile(BaseModel):
    meta: ResponseMeta
    iso3: str
    iso2: str | None
    name: str
    who_region: str | None
    hemisphere: str | None
    transmission_zone: str | None
    flu_season: str | None
    has_geometry: bool
    population: Population | None
    coverage: Coverage | None
    surveillance: SurveillanceSummary
    health: list[HealthValue]
    recent_window: WindowInfo
    recent: CountryWindowValue | None


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


class SeasonPoint(BaseModel):
    index: int  # week of season, from 0
    week_start: date
    iso_week: int
    reported: bool
    specimens_tested: float | None
    positives: float | None
    positivity: float | None
    is_provisional: bool


class Season(BaseModel):
    label: str
    start: date
    end: date
    is_current: bool
    covid_disrupted: bool
    weeks_reported: int
    positives: float | None
    specimens_tested: float | None
    peak_positivity: float | None
    peak_week: date | None
    points: list[SeasonPoint]


class CountrySeasons(BaseModel):
    meta: ResponseMeta
    iso3: str
    season_type: str | None
    season_rule: str
    min_specimens_for_peak: int
    seasons: list[Season]
