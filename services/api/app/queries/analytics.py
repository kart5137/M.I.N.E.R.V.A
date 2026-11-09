"""Aggregated comparisons for the Analytics page. Aggregation rules: app/queries/common.py.

A *series* is one of: an ISO3 country code, `region:<WHO code>`, or `world`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.queries.common import WHO_REGIONS, DiseaseContext
from app.schemas.analytics import HeatmapCell, TrendBucket, TrendSeries

REGION_LABELS = {
    "AFR": "Africa", "AMR": "Americas", "EMR": "Eastern Mediterranean", "EUR": "Europe",
    "SEAR": "South-East Asia", "WPR": "Western Pacific",
}
MAX_SERIES = 6

# Bucket start per granularity. Weeks belong to the month/year of their Thursday (ISO).
_BUCKET = {
    "week": "s.week_start",
    "month": "CAST(date_trunc('month', s.week_start + 3) AS date)",
    "year": "make_date(s.iso_year, 1, 1)",
}


@dataclass(frozen=True)
class SeriesSpec:
    key: str
    label: str
    kind: str
    where: str
    param: str | None


def parse_series(session: Session, tokens: list[str]) -> list[SeriesSpec]:
    if not tokens:
        raise ApiError(422, "invalid_series", "Give at least one series.")
    if len(tokens) > MAX_SERIES:
        raise ApiError(422, "invalid_series", f"At most {MAX_SERIES} series.")
    out: list[SeriesSpec] = []
    for raw in tokens:
        tok = raw.strip()
        low = tok.lower()
        if low == "world":
            out.append(SeriesSpec("world", "World", "world", "TRUE", None))
        elif low.startswith("region:"):
            code = tok.split(":", 1)[1].upper()
            if code not in WHO_REGIONS:
                raise ApiError(422, "invalid_series", f"Unknown WHO region '{code}'.")
            out.append(SeriesSpec(f"region:{code}", REGION_LABELS[code], "region",
                                  "c.who_region = :p", code))
        else:
            iso3 = tok.upper()
            name = session.execute(text("SELECT name FROM countries WHERE iso3 = :i"),
                                   {"i": iso3}).scalar()
            if name is None:
                raise ApiError(422, "invalid_series", f"Unknown country code '{tok}'.")
            out.append(SeriesSpec(iso3, name, "country", "s.iso3 = :p", iso3))
    if len({s.key for s in out}) != len(out):
        raise ApiError(422, "invalid_series", "Series must not repeat.")
    return out


def _label(d: date, granularity: str) -> str:
    if granularity == "year":
        return str(d.year)
    if granularity == "month":
        return d.strftime("%Y-%m")
    y, w, _ = d.isocalendar()
    return f"{y}-W{w:02d}"


def trend_series(session: Session, ctx: DiseaseContext, spec: SeriesSpec, granularity: str,
                 start: date, end: date) -> TrendSeries:
    bucket = _BUCKET[granularity]
    has_ab = "s.breakdown ? 'inf_a' AND s.breakdown ? 'inf_b'"
    rows = session.execute(text(f"""
        SELECT {bucket} AS period_start,
          count(DISTINCT s.week_start) AS weeks,
          count(DISTINCT s.iso3) FILTER (WHERE s.specimens_tested > 0) AS countries_reporting,
          sum(s.specimens_tested) FILTER (WHERE s.specimens_tested > 0) AS specimens_tested,
          sum(s.positives) AS positives,
          sum(s.positives) FILTER (WHERE s.positivity IS NOT NULL)
            / NULLIF(sum(s.specimens_tested) FILTER (WHERE s.positivity IS NOT NULL), 0)
            AS positivity,
          sum(CAST(s.breakdown->>'inf_a' AS float8)) FILTER (WHERE {has_ab}) AS inf_a,
          sum(CAST(s.breakdown->>'inf_b' AS float8)) FILTER (WHERE {has_ab}) AS inf_b,
          max(s.week_start) AS last_week
        FROM surveillance_weekly s JOIN countries c ON c.iso3 = s.iso3
        WHERE s.disease_id = :d AND s.week_start BETWEEN :start AND :end AND {spec.where}
        GROUP BY 1 ORDER BY 1
    """), {"d": ctx.id, "start": start, "end": end, "p": spec.param}).mappings().all()

    buckets: list[TrendBucket] = []
    prev = None
    for r in rows:
        a, b = r["inf_a"], r["inf_b"]
        typed = (a or 0) + (b or 0)
        pos, rate = r["positives"], r["positivity"]
        buckets.append(TrendBucket(
            period_start=r["period_start"], label=_label(r["period_start"], granularity),
            weeks=r["weeks"], countries_reporting=r["countries_reporting"],
            specimens_tested=r["specimens_tested"], positives=pos, positivity=rate,
            inf_a=a, inf_b=b, share_a=(a / typed) if typed else None,
            positivity_change_pp=(
                (rate - prev["positivity"]) * 100
                if prev and rate is not None and prev["positivity"] is not None else None),
            positives_change_pct=(
                (pos - prev["positives"]) / prev["positives"] * 100
                if prev and pos is not None and prev["positives"] else None),
            partial=_bucket_end(r["period_start"], granularity) > ctx.reference_week,
        ))
        prev = r
    return TrendSeries(key=spec.key, label=spec.label, kind=spec.kind, buckets=buckets)


def _bucket_end(start: date, granularity: str) -> date:
    """Last Monday that can belong to the bucket."""
    if granularity == "week":
        return start
    if granularity == "month":
        nxt = date(start.year + (start.month == 12), start.month % 12 + 1, 1)
    else:
        nxt = date(start.year + 1, 1, 1)
    # Weeks are assigned by their Thursday, so the last Monday is ≤ 3 days before `nxt`.
    return date.fromordinal(nxt.toordinal() - 4)


def heatmap(session: Session, ctx: DiseaseContext, spec: SeriesSpec, first_year: int,
            last_year: int) -> list[HeatmapCell]:
    rows = session.execute(text(f"""
        SELECT s.iso_year, s.iso_week,
          sum(s.positives) FILTER (WHERE s.positivity IS NOT NULL)
            / NULLIF(sum(s.specimens_tested) FILTER (WHERE s.positivity IS NOT NULL), 0)
            AS positivity,
          sum(s.specimens_tested) FILTER (WHERE s.specimens_tested > 0) AS specimens_tested,
          min(s.week_start) AS week_start
        FROM surveillance_weekly s JOIN countries c ON c.iso3 = s.iso3
        WHERE s.disease_id = :d AND s.iso_year BETWEEN :y0 AND :y1 AND {spec.where}
        GROUP BY 1, 2 ORDER BY 1, 2
    """), {"d": ctx.id, "y0": first_year, "y1": last_year, "p": spec.param}).mappings()
    prov = ctx.provisional_from
    return [
        HeatmapCell(
            iso_year=r["iso_year"], iso_week=r["iso_week"],
            positivity=r["positivity"], specimens_tested=r["specimens_tested"],
            is_provisional=prov is not None and r["week_start"] >= prov,
        )
        for r in rows
    ]

