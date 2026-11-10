from __future__ import annotations

from datetime import date

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.queries import cases
from app.queries.common import MIN_SPECIMENS_FOR_RATE, DiseaseContext, Window
from app.queries.surveillance import country_window
from app.schemas.countries import (
    CountryListItem,
    Coverage,
    HealthValue,
    Population,
    SeriesPoint,
    SurveillanceSummary,
)
from ei_db.catalog import HEALTH_INDICATORS

_LIST_WHERE = """
    (CAST(:region AS text) IS NULL OR c.who_region = :region)
    AND (CAST(:q AS text) IS NULL OR c.name ILIKE '%' || :q || '%' OR c.iso3 = upper(:q))
"""

SORT_KEYS = ("name", "tier", "positivity", "specimens_tested", "positives",
             "last_reported_week", "cases", "incidence")

_LAB_STATS = """
    SELECT iso3, max(week_start) AS last_reported_week, count(*) AS weeks_reported
    FROM surveillance_weekly WHERE disease_id = :d AND specimens_tested > 0
    GROUP BY iso3
"""


def list_countries(session: Session, ctx: DiseaseContext, w: Window, region: str | None,
                   q: str | None, sort: str, order: str, page: int,
                   page_size: int) -> tuple[int, list[CountryListItem]]:
    """All matching countries with their recent-window values; sorted in Python (≤ ~250
    rows). Missing values always sort last, whatever the order."""
    params = {"d": ctx.id, "region": region, "q": q or None}
    stats = cases.LIST_STATS if ctx.case_based else _LAB_STATS
    rows = session.execute(text(f"""
        WITH stats AS ({stats}), latest_profile AS (
          SELECT iso3, tier FROM coverage_profiles
          WHERE disease_id = :d AND reference_week =
            (SELECT max(reference_week) FROM coverage_profiles WHERE disease_id = :d)
        )
        SELECT c.iso3, c.name, c.who_region, c.flu_season, c.geom IS NOT NULL AS has_geometry,
          lp.tier, st.last_reported_week, coalesce(st.weeks_reported, 0) AS weeks_reported
        FROM countries c
        LEFT JOIN stats st ON st.iso3 = c.iso3
        LEFT JOIN latest_profile lp ON lp.iso3 = c.iso3
        WHERE {_LIST_WHERE}
    """), params).mappings().all()
    values = {v.iso3: v for v in country_window(session, ctx, w, region)}
    last_month = (dict(session.execute(cases.LAST_MONTHS, {"d": ctx.id}).all())
                  if ctx.case_based else {})

    items = []
    for r in rows:
        v = values.get(r["iso3"])
        items.append(CountryListItem(
            **r,
            positivity=v.positivity if v else None,
            positives=v.positives if v else None,
            specimens_tested=v.specimens_tested if v else None,
            cases=v.cases if v else None,
            incidence=v.incidence if v else None,
            grain=v.grain if v else None,
            last_reported_month=last_month.get(r["iso3"]),
        ))

    def key(item: CountryListItem):
        # A rate from fewer than MIN_SPECIMENS_FOR_RATE specimens is not ranked.
        if sort == "positivity" and (item.specimens_tested or 0) < MIN_SPECIMENS_FOR_RATE:
            return None
        return getattr(item, sort)

    present = [i for i in items if key(i) is not None]
    missing = [i for i in items if key(i) is None]
    # Two stable sorts: ties keep alphabetical order in both directions.
    present.sort(key=lambda i: i.name)
    present.sort(key=key, reverse=order == "desc")
    missing.sort(key=lambda i: i.name)
    ordered = present + missing
    start = (page - 1) * page_size
    return len(ordered), ordered[start:start + page_size]


def health(session: Session, iso3: str) -> list[HealthValue]:
    """Latest value per catalogue indicator; indicators without data are listed as null."""
    rows = session.execute(text("""
        SELECT DISTINCT ON (h.indicator_code) h.indicator_code, h.value, h.year,
          ds.name AS source
        FROM health_indicators h JOIN data_sources ds ON ds.id = h.source_id
        WHERE h.iso3 = :iso3
        ORDER BY h.indicator_code, h.year DESC
    """), {"iso3": iso3}).mappings()
    latest = {r["indicator_code"]: r for r in rows}
    out = []
    for spec in HEALTH_INDICATORS:
        r = latest.get(spec.code)
        out.append(HealthValue(
            code=spec.code, label=spec.label, unit=spec.unit, group=spec.group,
            value=r["value"] if r else None, year=r["year"] if r else None,
            source=r["source"] if r else None,
        ))
    return out


def country_row(session: Session, iso3: str):
    row = session.execute(
        text("""SELECT iso3, iso2, name, who_region, hemisphere, transmission_zone,
                       flu_season, geom IS NOT NULL AS has_geometry
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
        SELECT reference_week, tier, completeness, longest_gap, median_tests, weeks_since_last,
          grain
        FROM coverage_profiles WHERE disease_id = :d AND iso3 = :iso3
        ORDER BY reference_week DESC LIMIT 1
    """), {"d": ctx.id, "iso3": iso3}).mappings().one_or_none()
    return Coverage(**row) if row else None


def surveillance_summary(session: Session, ctx: DiseaseContext, iso3: str) -> SurveillanceSummary:
    if ctx.case_based:
        return cases.surveillance_summary(session, ctx, iso3)
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
