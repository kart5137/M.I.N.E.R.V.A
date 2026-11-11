from __future__ import annotations

from datetime import date

from pydantic import BaseModel

from app.schemas.common import ResponseMeta


class TrendBucket(BaseModel):
    period_start: date
    label: str
    weeks: int  # weeks with any row in the bucket
    countries_reporting: int
    specimens_tested: float | None
    positives: float | None
    positivity: float | None
    # Influenza A share among typed positives (rows reporting both A and B).
    share_a: float | None
    inf_a: float | None
    inf_b: float | None
    # Change vs the previous bucket of this series.
    positivity_change_pp: float | None
    positives_change_pct: float | None
    partial: bool  # bucket extends past the reference week (incomplete or provisional)
    # Case-based diseases (dengue, cholera, COVID-19); null for influenza.
    cases: float | None = None
    deaths: float | None = None
    #: Cases per 100,000 per week over the reported country-weeks (weekly reports only).
    incidence: float | None = None
    cases_change_pct: float | None = None


class TrendSeries(BaseModel):
    key: str
    label: str
    kind: str  # "country" | "region" | "world"
    buckets: list[TrendBucket]


class Trends(BaseModel):
    meta: ResponseMeta
    granularity: str
    start: date
    end: date
    series: list[TrendSeries]


class HeatmapCell(BaseModel):
    iso_year: int
    iso_week: int
    positivity: float | None
    specimens_tested: float | None
    is_provisional: bool
    # Case-based diseases: cases and cases per 100,000 that week; null for influenza.
    cases: float | None = None
    incidence: float | None = None


class Heatmap(BaseModel):
    meta: ResponseMeta
    key: str
    label: str
    years: list[int]
    min_specimens: int
    cells: list[HeatmapCell]
