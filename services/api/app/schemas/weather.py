from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field

from app.schemas.common import SourceRef


class WeatherPointInfo(BaseModel):
    lat: float
    lon: float
    basis: str = Field(description="`label_point` (Natural Earth label point) or `main_town` "
                                   "(areas without a boundary).")
    elevation_m: float | None


class WeatherWeek(BaseModel):
    week_start: date
    temperature: float = Field(description="Mean daily 2 m temperature, °C.")
    precipitation: float = Field(description="Total precipitation over the week, mm.")
    humidity: float = Field(description="Mean daily 2 m relative humidity, %.")
    # Mean for the same ISO week over the baseline years; null without baseline data.
    temperature_normal: float | None
    precipitation_normal: float | None
    humidity_normal: float | None


class CountryWeather(BaseModel):
    iso3: str
    point: WeatherPointInfo | None
    source: SourceRef | None
    baseline_years: tuple[int, int]
    first_week: date | None
    latest_week: date | None
    loading: bool = Field(description="History is still being loaded for this area (the "
                                      "free API is used within a daily quota).")
    weeks: list[WeatherWeek]
