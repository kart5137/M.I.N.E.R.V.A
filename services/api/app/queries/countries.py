from __future__ import annotations

from datetime import date

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.queries.common import DiseaseContext, Window
from app.schemas.countries import (
    CountryListItem,
    Coverage,
    Population,
    SeriesPoint,
    SurveillanceSummary,
)

_LIST_WHERE = """
    (CAST(:region AS text) IS NULL OR c.who_region = :region)
    AND (CAST(:q AS text) IS NULL OR c.name ILIKE '%' || :q || '%' OR c.iso3 = upper(:q))
"""


def list_countries(session: Session, ctx: DiseaseContext, region: str | None, q: str | None,
                   page: int, page_size: int) -> tuple[int, list[CountryListItem]]:
    params = {"d": ctx.id, "region": region, "q": q or None,
              "limit": page_size, "offset": (page - 1) * page_size}
    total = session.execute(
        text(f"SELECT count(*) FROM countries c WHERE {_LIST_WHERE}"), params
    ).scalar_one()
    rows = session.execute(text(f"""
        WITH stats AS (
          SELECT iso3, max(week_start) AS last_reported_week, count(*) AS weeks_reported
          FROM surveillance_weekly WHERE disease_id = :d AND specimens_tested > 0
          GROUP BY iso3
        ), latest_profile AS (
          SELECT iso3, tier FROM coverage_profiles
          WHERE disease_id = :d AND reference_week =
            (SELECT max(reference_week) FROM coverage_profiles WHERE disease_id = :d)
        )
        SELECT c.iso3, c.name, c.who_region, c.geom IS NOT NULL AS has_geometry,
          lp.tier, st.last_reported_week, coalesce(st.weeks_reported, 0) AS weeks_reported
        FROM countries c
        LEFT JOIN stats st ON st.iso3 = c.iso3
        LEFT JOIN latest_profile lp ON lp.iso3 = c.iso3
        WHERE {_LIST_WHERE}
        ORDER BY c.name
        LIMIT :limit OFFSET :offset
    """), params).mappings()
    return total, [CountryListItem(**r) for r in rows]


def country_row(session: Session, iso3: str):
    row = session.execute(
        text("""SELECT iso3, iso2, name, who_region, hemisphere, transmission_zone,
                       geom IS NOT NULL AS has_geometry
                FROM countries WHERE iso3 = :iso3"""),
        {"iso3": iso3.upper()},
    ).mappings().one_or_none()
    if row is None:
        raise ApiError(404, "unknown_country", f"Unknown country code '{iso3}'.")
    return row


def population(session: Session, iso3: str) -> Population | None:
    row = session.execute(text("""
        SELECT p.year, p.population AS value, ds.name AS source
        FROM population_annual p JOIN data_sources ds ON ds.id = p.source_id
        WHERE p.iso3 = :iso3 ORDER BY p.year DESC LIMIT 1
    """), {"iso3": iso3}).mappings().one_or_none()
    return Population(**row) if row else None


def coverage(session: Session, ctx: DiseaseContext, iso3: str) -> Coverage | None:
    row = session.execute(text("""
        SELECT reference_week, tier, completeness, longest_gap, median_tests, weeks_since_last
        FROM coverage_profiles WHERE disease_id = :d AND iso3 = :iso3
        ORDER BY reference_week DESC LIMIT 1
    """), {"d": ctx.id, "iso3": iso3}).mappings().one_or_none()
    return Coverage(**row) if row else None


def surveillance_summary(session: Session, ctx: DiseaseContext, iso3: str) -> SurveillanceSummary:
    row = session.execute(text("""
        SELECT min(week_start) AS first_week,
          max(week_start) FILTER (WHERE specimens_tested > 0) AS last_reported_week,
          count(*) FILTER (WHERE specimens_tested > 0) AS weeks_reported
        FROM surveillance_weekly WHERE disease_id = :d AND iso3 = :iso3
    """), {"d": ctx.id, "iso3": iso3}).mappings().one()
    return SurveillanceSummary(**row)


def timeseries(session: Session, ctx: DiseaseContext, iso3: str, w: Window) -> list[SeriesPoint]:
    """Complete weekly calendar for the window; weeks without data are `reported=False`."""
    rows = session.execute(text("""
        WITH weeks AS (
          SELECT generate_series(CAST(:start AS date), CAST(:end AS date), interval '1 week')::date
            AS week_start
        )
        SELECT w.week_start, coalesce(s.specimens_tested > 0, false) AS reported,
          s.specimens_tested, s.positives, s.positivity,
          coalesce(s.is_provisional, w.week_start >= CAST(:prov AS date), false) AS is_provisional
        FROM weeks w
        LEFT JOIN surveillance_weekly s
          ON s.disease_id = :d AND s.iso3 = :iso3 AND s.week_start = w.week_start
        ORDER BY w.week_start
    """), {"d": ctx.id, "iso3": iso3, "start": w.start, "end": w.end,
           "prov": ctx.provisional_from}).mappings()
    return [SeriesPoint(**r) for r in rows]


def clamp_week(ctx: DiseaseContext, d: date) -> date:
    return min(max(d, ctx.first_week), ctx.latest_week)
