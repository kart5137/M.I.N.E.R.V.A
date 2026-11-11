"""Yearly data (malaria, C1): World Malaria Report estimates and reported cases."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.common import SourceRef


class AnnualMeta(BaseModel):
    disease: str
    first_year: int
    latest_year: int = Field(description="Latest year with estimates for countries.")
    sources: list[SourceRef]
    grain: str = "year"


class MeasureValue(BaseModel):
    value: float
    #: Uncertainty range of a modelled estimate; null for reported counts and for
    #: estimates taken from routine reporting.
    low: float | None = None
    high: float | None = None


#: Measure keys: est_cases, est_deaths, est_incidence (per 1,000 at risk),
#: est_mortality (per 100,000), confirmed_cases, reported_cases (confirmed + presumed).
Values = dict[str, MeasureValue]


class AreaTotal(BaseModel):
    area: str
    values: Values
    previous: Values


class AnnualSummary(BaseModel):
    meta: AnnualMeta
    year: int
    years: list[int]
    measures: dict[str, str]
    #: WHO's global total (GLOBAL); null when not published for the year.
    world: AreaTotal | None
    regions: list[AreaTotal]
    countries_with_estimates: int
    countries_reporting: int
    notes: list[str]


class AnnualCountry(BaseModel):
    iso3: str
    name: str
    who_region: str | None
    values: Values
    previous: Values


class AnnualCountries(BaseModel):
    meta: AnnualMeta
    year: int
    region: str | None
    items: list[AnnualCountry]


class SeriesPoint(BaseModel):
    year: int
    values: Values


class AnnualSeries(BaseModel):
    meta: AnnualMeta
    area: str
    name: str
    scope: str
    points: list[SeriesPoint]
    #: A year still accumulating weekly reports (cholera: the current year); null if none.
    partial_year: int | None = None
    measures: dict[str, str] = {}
    notes: list[str] = []
