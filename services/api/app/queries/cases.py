"""Queries for case-based diseases (dengue): reported cases and incidence.

Rules (documented in docs/datasets/dengue.md, "Dashboard values"):

- A period is **reported** when it has a case value (0 counts).
- **Per-country window value.** A country's weekly reports in the window are used when
  it has any; otherwise the calendar months overlapping the window (monthly reporters,
  or weekly reporters before/after a switch). Weekly and monthly values are never
  mixed for one country in one window, so nothing is double counted.
- **Incidence** = cases per 100,000 population per week, over the reported periods only
  (gaps are not zeros): cases / (reported days / 7) / population × 100,000. Population
  is the latest World Bank value up to the window's year.
- **Totals, trend and movers** use weekly reports only: a calendar month does not fit a
  weekly window, so adding monthly reports would over- or under-count. Monthly reporters
  appear on the map, in the country list and in "countries reporting".
- Case definitions differ by country (suspected / probable / confirmed); values compare
  within a country over time.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.queries.common import WEEK, DiseaseContext, Window
from app.schemas.countries import MonthPoint, SeriesPoint, SurveillanceSummary
from app.schemas.surveillance import CountryWindowValue, Kpi, Kpis, Mover, TrendPoint

_REGION = "(CAST(:region AS text) IS NULL OR c.who_region = :region)"
_ISO3 = "(CAST(:iso3 AS text) IS NULL OR s.iso3 = :iso3)"
_MONTH_END = "(s.month_start + interval '1 month')::date"

#: Latest population up to the window's year (falls back to the earliest when a
#: country's series starts later).
_POP = """
  pop AS (
    SELECT DISTINCT ON (iso3) iso3, population::float8 AS population
    FROM population_annual
    ORDER BY iso3, (year <= extract(year FROM CAST(:end AS date))) DESC,
             CASE WHEN year <= extract(year FROM CAST(:end AS date)) THEN -year ELSE year END
  )"""

#: Case fatality rate (deaths ÷ cases in the window) only from this many cases (cholera,
#: C2): a rate from a handful of cases is misleading.
CFR_MIN_CASES = 20

_WEEKLY = f"""
  wk AS (
    SELECT s.iso3, sum(s.cases) AS cases, count(*) AS periods, count(*) * 7 AS days,
      count(*) FILTER (WHERE s.is_provisional) AS provisional,
      min(s.week_start) AS period_start, max(s.week_start) + 6 AS period_end,
      sum(s.deaths) AS deaths
    FROM surveillance_weekly s
    WHERE s.disease_id = :d AND s.cases IS NOT NULL
      AND s.week_start BETWEEN :start AND :end AND {_ISO3}
    GROUP BY s.iso3
  )"""

_MONTHLY = f"""
  mo AS (
    SELECT s.iso3, sum(s.cases) AS cases, count(*) AS periods,
      sum({_MONTH_END} - s.month_start) AS days,
      count(*) FILTER (WHERE s.is_provisional) AS provisional,
      min(s.month_start) AS period_start, max({_MONTH_END}) - 1 AS period_end,
      NULL::float8 AS deaths
    FROM surveillance_monthly s
    WHERE s.disease_id = :d AND s.cases IS NOT NULL
      AND s.month_start <= CAST(:end AS date) + 6 AND {_MONTH_END} > :start AND {_ISO3}
      AND s.iso3 NOT IN (SELECT iso3 FROM wk)
    GROUP BY s.iso3
  )"""

_COUNTRY_WINDOW = text(f"""
    WITH {_POP}, {_WEEKLY}, {_MONTHLY},
    latest_profile AS (
      SELECT iso3, tier FROM coverage_profiles
      WHERE disease_id = :d AND reference_week =
        (SELECT max(reference_week) FROM coverage_profiles WHERE disease_id = :d)
    ),
    x AS (SELECT *, 'week' AS grain FROM wk UNION ALL SELECT *, 'month' AS grain FROM mo)
    SELECT c.iso3, c.name, c.who_region, c.geom IS NOT NULL AS has_geometry,
      NULL AS specimens_tested, NULL AS positives, NULL AS positivity,
      CASE WHEN x.grain = 'week' THEN x.periods ELSE 0 END AS weeks_reported,
      x.provisional AS provisional_weeks, lp.tier,
      x.cases, x.grain, x.periods AS periods_reported, x.period_start, x.period_end,
      p.population::bigint AS population,
      x.cases / (x.days / 7.0) / NULLIF(p.population, 0) * 100000 AS incidence,
      x.deaths,
      CASE WHEN x.cases >= :cfr_min THEN x.deaths / x.cases END AS cfr
    FROM x
    JOIN countries c ON c.iso3 = x.iso3
    LEFT JOIN pop p ON p.iso3 = x.iso3
    LEFT JOIN latest_profile lp ON lp.iso3 = x.iso3
    WHERE {_REGION}
    ORDER BY c.iso3
""")


def country_window(session: Session, ctx: DiseaseContext, w: Window, region: str | None,
                   iso3: str | None = None) -> list[CountryWindowValue]:
    rows = session.execute(_COUNTRY_WINDOW, {
        "d": ctx.id, "start": w.start, "end": w.end, "region": region, "iso3": iso3,
        "cfr_min": CFR_MIN_CASES,
    }).mappings()
    return [CountryWindowValue(**r) for r in rows]


# ------------------------------------------------------------------------- overview

_TOTALS = text(f"""
    WITH {_POP},
    per AS (
      SELECT s.iso3, sum(s.cases) AS cases, count(*) AS weeks
      FROM surveillance_weekly s JOIN countries c ON c.iso3 = s.iso3
      WHERE s.disease_id = :d AND s.cases IS NOT NULL
        AND s.week_start BETWEEN :start AND :end AND {_REGION}
      GROUP BY s.iso3
    ),
    monthly_only AS (
      SELECT DISTINCT s.iso3
      FROM surveillance_monthly s JOIN countries c ON c.iso3 = s.iso3
      WHERE s.disease_id = :d AND s.cases IS NOT NULL
        AND s.month_start <= CAST(:end AS date) + 6 AND {_MONTH_END} > :start AND {_REGION}
        AND s.iso3 NOT IN (SELECT iso3 FROM per)
    )
    SELECT sum(per.cases) AS cases,
      sum(per.cases) FILTER (WHERE p.population > 0)
        / NULLIF(sum(p.population * per.weeks) FILTER (WHERE p.population > 0), 0)
        * 100000 AS incidence,
      count(per.iso3) AS weekly_countries,
      (SELECT count(*) FROM monthly_only) AS monthly_countries
    FROM per LEFT JOIN pop p ON p.iso3 = per.iso3
""")


def _totals(session: Session, ctx: DiseaseContext, w: Window, region: str | None):
    return session.execute(_TOTALS, {"d": ctx.id, "start": w.start, "end": w.end,
                                     "region": region}).one()


def _relative(cur: float | None, prev: float | None) -> float | None:
    if cur is None or not prev:
        return None
    return (cur - prev) / prev * 100


def kpis(session: Session, ctx: DiseaseContext, w: Window, region: str | None) -> Kpis:
    cur = _totals(session, ctx, w, region)
    prev = _totals(session, ctx, w.previous, region)
    reporting = cur.weekly_countries + cur.monthly_countries
    reporting_prev = prev.weekly_countries + prev.monthly_countries
    return Kpis(
        detections=None,
        positivity=None,
        cases=Kpi(value=cur.cases, previous=prev.cases,
                  change=_relative(cur.cases, prev.cases), change_unit="percent",
                  denominator=cur.weekly_countries,
                  note="Reported cases in weekly-reporting countries (monthly reports do "
                       "not fit a weekly window)"),
        incidence=Kpi(value=cur.incidence, previous=prev.incidence,
                      change=_relative(cur.incidence, prev.incidence), change_unit="percent",
                      denominator=cur.weekly_countries,
                      note="Cases per 100,000 per week, pooled over weekly-reporting "
                           "countries with population data"),
        countries_reporting=Kpi(value=reporting, previous=reporting_prev,
                                change=reporting - reporting_prev, change_unit="count",
                                note=f"{cur.weekly_countries} weekly, "
                                     f"{cur.monthly_countries} monthly reporters"),
        anomalies=None, hotspots=None, above_threshold=None, pending=[],
    )


_TREND = text(f"""
    WITH {_POP},
    weeks AS (
      SELECT generate_series(CAST(:start AS date), CAST(:end AS date), interval '1 week')::date
        AS week_start
    ), agg AS (
      SELECT s.week_start, sum(s.cases) AS cases, count(*) AS countries_reporting,
        sum(s.cases) FILTER (WHERE p.population > 0)
          / NULLIF(sum(p.population) FILTER (WHERE p.population > 0), 0) * 100000
          AS incidence
      FROM surveillance_weekly s
      JOIN countries c ON c.iso3 = s.iso3
      LEFT JOIN pop p ON p.iso3 = s.iso3
      WHERE s.disease_id = :d AND s.cases IS NOT NULL
        AND s.week_start BETWEEN :start AND :end AND {_REGION}
      GROUP BY s.week_start
    )
    SELECT w.week_start, NULL AS specimens_tested, NULL AS positives, NULL AS positivity,
      a.cases, a.incidence, coalesce(a.countries_reporting, 0) AS countries_reporting
    FROM weeks w LEFT JOIN agg a USING (week_start)
    ORDER BY w.week_start
""")


def trend(session: Session, ctx: DiseaseContext, w: Window, region: str | None,
          weeks: int) -> list[TrendPoint]:
    """Weekly series of weekly-reporting countries up to the latest week."""
    start = max(ctx.first_week, min(ctx.latest_week - WEEK * (weeks - 1), w.previous.start))
    rows = session.execute(_TREND, {"d": ctx.id, "start": start, "end": ctx.latest_week,
                                    "region": region}).mappings()
    prov = ctx.provisional_from
    return [TrendPoint(**r, is_provisional=prov is not None and r["week_start"] >= prov)
            for r in rows]


_MOVERS = text(f"""
    WITH {_POP},
    per AS (
      SELECT s.iso3, s.week_start BETWEEN :start AND :end AS current,
        sum(s.cases) AS cases, count(*) AS weeks
      FROM surveillance_weekly s JOIN countries c ON c.iso3 = s.iso3
      WHERE s.disease_id = :d AND s.cases IS NOT NULL
        AND s.week_start BETWEEN :pstart AND :end AND {_REGION}
      GROUP BY s.iso3, 2
    ), rated AS (
      SELECT per.*, per.cases / per.weeks / p.population * 100000 AS incidence
      FROM per JOIN pop p ON p.iso3 = per.iso3 WHERE p.population > 0
    )
    SELECT c.iso3, c.name, cur.incidence, prev.incidence AS previous_incidence,
      (cur.incidence - prev.incidence) / prev.incidence * 100 AS change_pct,
      cur.cases
    FROM rated cur
    JOIN rated prev ON prev.iso3 = cur.iso3 AND NOT prev.current
    JOIN countries c ON c.iso3 = cur.iso3
    WHERE cur.current AND cur.cases >= :min_cases AND prev.cases >= :min_cases
    -- Symmetric in rises and falls: a doubling ranks like a halving.
    ORDER BY abs(ln(cur.incidence / prev.incidence)) DESC, c.iso3
    LIMIT :limit
""")


def top_movers(session: Session, ctx: DiseaseContext, w: Window, region: str | None,
               min_cases: int, limit: int = 8) -> list[Mover]:
    rows = session.execute(_MOVERS, {
        "d": ctx.id, "start": w.start, "end": w.end, "pstart": w.previous.start,
        "region": region, "min_cases": min_cases, "limit": limit,
    }).mappings()
    return [Mover(**r) for r in rows]


# ------------------------------------------------------------------------ countries

LIST_STATS = """
    SELECT iso3, max(week_start) AS last_reported_week, count(*) AS weeks_reported
    FROM surveillance_weekly WHERE disease_id = :d AND cases IS NOT NULL
    GROUP BY iso3
"""

LAST_MONTHS = text("""
    SELECT iso3, max(month_start) FROM surveillance_monthly
    WHERE disease_id = :d AND cases IS NOT NULL GROUP BY iso3
""")


def surveillance_summary(session: Session, ctx: DiseaseContext, iso3: str
                         ) -> SurveillanceSummary:
    row = session.execute(text("""
        SELECT
          (SELECT min(week_start) FROM surveillance_weekly
            WHERE disease_id = :d AND iso3 = :iso3 AND cases IS NOT NULL) AS first_week,
          (SELECT max(week_start) FROM surveillance_weekly
            WHERE disease_id = :d AND iso3 = :iso3 AND cases IS NOT NULL) AS last_reported_week,
          (SELECT count(*) FROM surveillance_weekly
            WHERE disease_id = :d AND iso3 = :iso3 AND cases IS NOT NULL) AS weeks_reported,
          (SELECT min(month_start) FROM surveillance_monthly
            WHERE disease_id = :d AND iso3 = :iso3 AND cases IS NOT NULL) AS first_month,
          (SELECT max(month_start) FROM surveillance_monthly
            WHERE disease_id = :d AND iso3 = :iso3 AND cases IS NOT NULL) AS last_reported_month,
          (SELECT count(*) FROM surveillance_monthly
            WHERE disease_id = :d AND iso3 = :iso3 AND cases IS NOT NULL) AS months_reported
    """), {"d": ctx.id, "iso3": iso3}).mappings().one()
    return SurveillanceSummary(**row)


_POP_AT = """
    LEFT JOIN LATERAL (
      SELECT population::float8 AS population FROM population_annual pa
      WHERE pa.iso3 = :iso3
      ORDER BY (pa.year <= extract(year FROM {date})) DESC,
               CASE WHEN pa.year <= extract(year FROM {date}) THEN -pa.year ELSE pa.year END
      LIMIT 1
    ) p ON true
"""


def timeseries(session: Session, ctx: DiseaseContext, iso3: str, w: Window
               ) -> tuple[list[SeriesPoint], list[MonthPoint]]:
    """Complete weekly calendar (gaps marked, not zero-filled) plus the monthly reports
    overlapping the window."""
    weekly = session.execute(text(f"""
        WITH weeks AS (
          SELECT generate_series(CAST(:start AS date), CAST(:end AS date), interval '1 week')::date
            AS week_start
        )
        SELECT w.week_start, s.cases IS NOT NULL AS reported,
          NULL AS specimens_tested, NULL AS positives, NULL AS positivity,
          s.cases, s.cases / NULLIF(p.population, 0) * 100000 AS incidence, s.deaths,
          coalesce(s.is_provisional, w.week_start >= CAST(:prov AS date), false) AS is_provisional
        FROM weeks w
        LEFT JOIN surveillance_weekly s
          ON s.disease_id = :d AND s.iso3 = :iso3 AND s.week_start = w.week_start
        {_POP_AT.format(date="w.week_start")}
        ORDER BY w.week_start
    """), {"d": ctx.id, "iso3": iso3, "start": w.start, "end": w.end,
           "prov": ctx.provisional_from}).mappings()
    monthly = session.execute(text(f"""
        SELECT s.month_start, s.cases, s.is_provisional,
          s.cases / ((({_MONTH_END} - s.month_start)) / 7.0) / NULLIF(p.population, 0)
            * 100000 AS incidence
        FROM surveillance_monthly s
        {_POP_AT.format(date="s.month_start")}
        WHERE s.disease_id = :d AND s.iso3 = :iso3
          AND s.month_start <= CAST(:end AS date) + 6 AND {_MONTH_END} > :start
        ORDER BY s.month_start
    """), {"d": ctx.id, "iso3": iso3, "start": w.start, "end": w.end}).mappings()
    return [SeriesPoint(**r) for r in weekly], [MonthPoint(**r) for r in monthly]
