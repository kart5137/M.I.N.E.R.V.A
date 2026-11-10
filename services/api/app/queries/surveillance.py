"""Map layers and Overview aggregates. Aggregation rules: see app/queries/common.py."""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.queries import cases
from app.queries import detection as det
from app.queries.common import WEEK, DiseaseContext, Window
from app.schemas.surveillance import (
    CountryWindowValue,
    Kpi,
    Kpis,
    Mover,
    PendingKpi,
    TrendPoint,
)

# Indicators produced by later milestones. Listed so the UI can say when they arrive
# instead of showing a number. (All M6 indicators are now real; kept for future ones.)
PENDING_KPIS: list[PendingKpi] = []

_REGION = "(CAST(:region AS text) IS NULL OR c.who_region = :region)"

# Pooled positivity over rows with a valid weekly positivity.
_POSITIVITY = (
    "sum(s.positives) FILTER (WHERE s.positivity IS NOT NULL)"
    " / NULLIF(sum(s.specimens_tested) FILTER (WHERE s.positivity IS NOT NULL), 0)"
)

_COUNTRY_WINDOW = text(f"""
    WITH latest_profile AS (
      SELECT iso3, tier FROM coverage_profiles
      WHERE disease_id = :d AND reference_week =
        (SELECT max(reference_week) FROM coverage_profiles WHERE disease_id = :d)
    )
    SELECT c.iso3, c.name, c.who_region, c.geom IS NOT NULL AS has_geometry,
      sum(s.specimens_tested) FILTER (WHERE s.specimens_tested > 0) AS specimens_tested,
      sum(s.positives) AS positives,
      {_POSITIVITY} AS positivity,
      count(*) FILTER (WHERE s.specimens_tested > 0) AS weeks_reported,
      count(*) FILTER (WHERE s.specimens_tested > 0 AND s.is_provisional) AS provisional_weeks,
      lp.tier
    FROM surveillance_weekly s
    JOIN countries c ON c.iso3 = s.iso3
    LEFT JOIN latest_profile lp ON lp.iso3 = s.iso3
    WHERE s.disease_id = :d AND s.week_start BETWEEN :start AND :end AND {_REGION}
      AND (CAST(:iso3 AS text) IS NULL OR s.iso3 = :iso3)
    GROUP BY c.iso3, c.name, c.who_region, c.geom IS NOT NULL, lp.tier
    HAVING count(*) FILTER (WHERE s.specimens_tested > 0) > 0 OR sum(s.positives) IS NOT NULL
    ORDER BY c.iso3
""")


def country_window(session: Session, ctx: DiseaseContext, w: Window,
                   region: str | None, iso3: str | None = None) -> list[CountryWindowValue]:
    if ctx.case_based:
        return cases.country_window(session, ctx, w, region, iso3)
    rows = session.execute(
        _COUNTRY_WINDOW,
        {"d": ctx.id, "start": w.start, "end": w.end, "region": region, "iso3": iso3},
    ).mappings()
    return [CountryWindowValue(**r) for r in rows]


_TOTALS = text(f"""
    SELECT sum(s.positives) AS detections,
      {_POSITIVITY} AS positivity,
      count(DISTINCT s.iso3) FILTER (WHERE s.specimens_tested > 0) AS countries_reporting
    FROM surveillance_weekly s JOIN countries c ON c.iso3 = s.iso3
    WHERE s.disease_id = :d AND s.week_start BETWEEN :start AND :end AND {_REGION}
""")


def _totals(session: Session, ctx: DiseaseContext, w: Window, region: str | None):
    return session.execute(
        _TOTALS, {"d": ctx.id, "start": w.start, "end": w.end, "region": region}
    ).one()


def _relative(cur: float | None, prev: float | None) -> float | None:
    if cur is None or not prev:
        return None
    return (cur - prev) / prev * 100


def kpis(session: Session, ctx: DiseaseContext, w: Window, region: str | None) -> Kpis:
    if ctx.case_based:
        return cases.kpis(session, ctx, w, region)
    cur = _totals(session, ctx, w, region)
    prev = _totals(session, ctx, w.previous, region)
    pp = (None if cur.positivity is None or prev.positivity is None
          else (cur.positivity - prev.positivity) * 100)
    return Kpis(
        detections=Kpi(value=cur.detections, previous=prev.detections,
                       change=_relative(cur.detections, prev.detections), change_unit="percent"),
        positivity=Kpi(value=cur.positivity, previous=prev.positivity, change=pp,
                       change_unit="pp"),
        countries_reporting=Kpi(
            value=cur.countries_reporting, previous=prev.countries_reporting,
            change=cur.countries_reporting - prev.countries_reporting, change_unit="count",
        ),
        **detection_kpis(session, ctx, w, region),
        pending=PENDING_KPIS,
    )


def detection_kpis(session: Session, ctx: DiseaseContext, w: Window, region: str | None
                   ) -> dict[str, Kpi | None]:
    if det.run_info(session, ctx)[0] is None:
        return {"anomalies": None, "hotspots": None, "above_threshold": None}
    a_cur = det.anomaly_country_count(session, ctx, w, region)
    a_prev = det.anomaly_country_count(session, ctx, w.previous, region)
    h_cur = det.hotspot_country_count(session, ctx, w.end, region)
    h_prev = det.hotspot_country_count(session, ctx, w.previous.end, region)
    above, assessed = det.above_threshold_count(session, ctx, region)
    return {
        "anomalies": Kpi(value=a_cur, previous=a_prev, change=a_cur - a_prev,
                         change_unit="count",
                         note="Countries with a seasonal-EWMA anomaly in the window"),
        "hotspots": None if h_cur is None else Kpi(
            value=h_cur, previous=h_prev,
            change=None if h_prev is None else h_cur - h_prev, change_unit="count",
            note="Countries in a Gi* hot spot (FDR < 0.05), 4 weeks to the window end"),
        "above_threshold": Kpi(
            value=above, previous=None, change=None, change_unit="count",
            denominator=assessed,
            note="Latest 2-week forecast at or above the MEM epidemic threshold "
                 "(countries with usable thresholds)"),
    }


_TREND = text(f"""
    WITH weeks AS (
      SELECT generate_series(CAST(:start AS date), CAST(:end AS date), interval '1 week')::date
        AS week_start
    ), agg AS (
      SELECT s.week_start,
        sum(s.specimens_tested) FILTER (WHERE s.specimens_tested > 0) AS specimens_tested,
        sum(s.positives) AS positives,
        {_POSITIVITY} AS positivity,
        count(*) FILTER (WHERE s.specimens_tested > 0) AS countries_reporting
      FROM surveillance_weekly s JOIN countries c ON c.iso3 = s.iso3
      WHERE s.disease_id = :d AND s.week_start BETWEEN :start AND :end AND {_REGION}
      GROUP BY s.week_start
    )
    SELECT w.week_start, a.specimens_tested, a.positives, a.positivity,
      coalesce(a.countries_reporting, 0) AS countries_reporting
    FROM weeks w LEFT JOIN agg a USING (week_start)
    ORDER BY w.week_start
""")


def trend(session: Session, ctx: DiseaseContext, w: Window, region: str | None,
          weeks: int) -> list[TrendPoint]:
    """Weekly pooled series up to the latest week, long enough to include both windows."""
    if ctx.case_based:
        return cases.trend(session, ctx, w, region, weeks)
    start = max(ctx.first_week, min(ctx.latest_week - WEEK * (weeks - 1), w.previous.start))
    rows = session.execute(
        _TREND, {"d": ctx.id, "start": start, "end": ctx.latest_week, "region": region}
    ).mappings()
    prov = ctx.provisional_from
    return [
        TrendPoint(**r, is_provisional=prov is not None and r["week_start"] >= prov)
        for r in rows
    ]


_MOVERS = text(f"""
    WITH per AS (
      SELECT s.iso3, s.week_start BETWEEN :start AND :end AS current,
        {_POSITIVITY} AS positivity,
        sum(s.specimens_tested) FILTER (WHERE s.positivity IS NOT NULL) AS tests
      FROM surveillance_weekly s JOIN countries c ON c.iso3 = s.iso3
      WHERE s.disease_id = :d AND s.week_start BETWEEN :pstart AND :end AND {_REGION}
      GROUP BY s.iso3, 2
    )
    SELECT c.iso3, c.name, cur.positivity, prev.positivity AS previous_positivity,
      (cur.positivity - prev.positivity) * 100 AS change_pp, cur.tests AS specimens_tested
    FROM per cur
    JOIN per prev ON prev.iso3 = cur.iso3 AND NOT prev.current
    JOIN countries c ON c.iso3 = cur.iso3
    WHERE cur.current AND cur.tests >= :min_tests AND prev.tests >= :min_tests
    ORDER BY abs(cur.positivity - prev.positivity) DESC, c.iso3
    LIMIT :limit
""")


def top_movers(session: Session, ctx: DiseaseContext, w: Window, region: str | None,
               min_tests: int, limit: int = 8, min_cases: int = 50) -> list[Mover]:
    if ctx.case_based:
        return cases.top_movers(session, ctx, w, region, min_cases, limit)
    rows = session.execute(_MOVERS, {
        "d": ctx.id, "start": w.start, "end": w.end, "pstart": w.previous.start,
        "region": region, "min_tests": min_tests, "limit": limit,
    }).mappings()
    return [Mover(**r) for r in rows]
