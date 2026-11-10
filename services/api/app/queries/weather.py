"""Weekly weather at the country's representative point (phase D3)."""

from __future__ import annotations

from datetime import date

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.schemas.common import SourceRef
from app.schemas.weather import WeatherPointInfo, WeatherWeek

#: "Normal" = mean of the same ISO week over these years (week 53 uses week 52).
BASELINE_YEARS = (2013, 2022)


def point(session: Session, iso3: str) -> tuple[WeatherPointInfo, SourceRef] | None:
    row = session.execute(text("""
        SELECT p.lat, p.lon, p.basis, p.elevation_m,
               ds.key, ds.name, ds.attribution_text AS attribution
        FROM weather_points p JOIN data_sources ds ON ds.id = p.source_id
        WHERE p.iso3 = :iso3"""), {"iso3": iso3}).mappings().one_or_none()
    if row is None:
        return None
    return (WeatherPointInfo(lat=row["lat"], lon=row["lon"], basis=row["basis"],
                             elevation_m=row["elevation_m"]),
            SourceRef(key=row["key"], name=row["name"], attribution=row["attribution"]))


#: An area whose latest week is this far behind the newest stored week is still loading.
LOADING_LAG_WEEKS = 8


def extent(session: Session, iso3: str) -> tuple[date | None, date | None, bool]:
    """First and latest stored week, and whether the area's history is still loading
    (no point yet, or its latest week lags the newest week of any area)."""
    row = session.execute(text("""
        SELECT min(week_start) FILTER (WHERE iso3 = :iso3),
               max(week_start) FILTER (WHERE iso3 = :iso3),
               max(week_start)
        FROM weather_weekly"""), {"iso3": iso3}).one()
    first, latest, newest = row
    loading = latest is None or (newest - latest).days > 7 * LOADING_LAG_WEEKS
    return first, latest, loading


def weeks(session: Session, iso3: str, start: date, end: date) -> list[WeatherWeek]:
    rows = session.execute(text("""
        WITH normals AS (
            SELECT least(iso_week, 52) AS wk, avg(temperature) AS t, avg(precipitation) AS p,
                   avg(humidity) AS h
            FROM weather_weekly
            WHERE iso3 = :iso3 AND iso_year BETWEEN :y0 AND :y1
            GROUP BY 1
        )
        SELECT w.week_start, w.temperature, w.precipitation, w.humidity,
               n.t AS temperature_normal, n.p AS precipitation_normal,
               n.h AS humidity_normal
        FROM weather_weekly w LEFT JOIN normals n ON n.wk = least(w.iso_week, 52)
        WHERE w.iso3 = :iso3 AND w.week_start BETWEEN :start AND :end
        ORDER BY w.week_start"""),
        {"iso3": iso3, "start": start, "end": end,
         "y0": BASELINE_YEARS[0], "y1": BASELINE_YEARS[1]}).mappings().all()
    return [WeatherWeek(**{k: (round(v, 2) if isinstance(v, float) else v)
                           for k, v in r.items()}) for r in rows]
