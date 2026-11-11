"""Yearly data from `surveillance_annual` (malaria, C1).

Rules: values are shown as WHO publishes them. Global and regional totals are WHO's own
rows (their uncertainty ranges cannot be summed from countries); a country's estimates
and its reported cases are kept apart, because they differ, often widely. Nothing is
filled in for a missing year or measure.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.schemas.annual import AnnualMeta, MeasureValue
from app.schemas.common import SourceRef

MEASURES = {
    "est_cases": "Estimated cases",
    "est_deaths": "Estimated deaths",
    "est_incidence": "Estimated cases per 1,000 population at risk",
    "est_mortality": "Estimated deaths per 100,000 population",
    "confirmed_cases": "Reported confirmed cases",
    "reported_cases": "Reported cases (confirmed + presumed)",
}
NOTES = [
    "Estimated cases, deaths and rates are World Malaria Report model estimates with "
    "uncertainty ranges; WHO revises the whole series each year.",
    "Reported cases are what national programmes reported; they differ from estimates, "
    "often widely, where testing and reporting are incomplete.",
    "Yearly data: no forecasts, anomaly detection or weekly alerts.",
]


@dataclass(frozen=True)
class AnnualContext:
    id: int
    key: str
    name: str
    first_year: int
    latest_year: int
    sources: tuple[SourceRef, ...]

    def meta(self) -> AnnualMeta:
        return AnnualMeta(disease=self.key, first_year=self.first_year,
                          latest_year=self.latest_year, sources=list(self.sources))


def load_annual(session: Session, key: str) -> AnnualContext:
    row = session.execute(text("""
        SELECT d.id, d.key, d.name, d.native_granularity,
          (SELECT min(year) FROM surveillance_annual WHERE disease_id = d.id
             AND scope = 'country'),
          (SELECT max(year) FROM surveillance_annual WHERE disease_id = d.id
             AND scope = 'country' AND measure = 'est_cases')
        FROM diseases d WHERE d.key = :k
    """), {"k": key}).one_or_none()
    if row is None:
        raise ApiError(404, "unknown_disease", f"Unknown disease '{key}'.")
    did, dkey, name, grain, first, latest = row
    if grain != "annual":
        raise ApiError(422, "not_available",
                       f"{name} is reported weekly; yearly views are for yearly diseases.")
    if latest is None:
        raise ApiError(404, "no_data",
                       f"No {name.lower()} data is loaded. Run `ei ingest malaria`.")
    sources = session.execute(text("""
        SELECT key, name, attribution_text FROM data_sources WHERE id IN
          (SELECT DISTINCT source_id FROM surveillance_annual WHERE disease_id = :d)
        ORDER BY key
    """), {"d": did}).all()
    return AnnualContext(id=did, key=dkey, name=name, first_year=first, latest_year=latest,
                         sources=tuple(SourceRef(key=k, name=n, attribution=a)
                                       for k, n, a in sources))


def check_year(ctx: AnnualContext, year: int | None) -> int:
    y = ctx.latest_year if year is None else year
    if not ctx.first_year <= y <= ctx.latest_year:
        raise ApiError(422, "invalid_parameter",
                       f"year must be between {ctx.first_year} and {ctx.latest_year}.")
    return y


def _values(rows) -> dict[str, MeasureValue]:
    return {r["measure"]: MeasureValue(value=r["value"], low=r["low"], high=r["high"])
            for r in rows}


def area_values(session: Session, ctx: AnnualContext, scope: str, years: tuple[int, ...]
                ) -> dict[tuple[str, int], dict[str, MeasureValue]]:
    """{(area, year): {measure: value}} for one scope and some years."""
    rows = session.execute(text("""
        SELECT area, year, measure, value, low, high FROM surveillance_annual
        WHERE disease_id = :d AND scope = :s AND year = ANY(:y)
    """), {"d": ctx.id, "s": scope, "y": list(years)}).mappings()
    out: dict[tuple[str, int], list] = defaultdict(list)
    for r in rows:
        out[(r["area"], r["year"])].append(r)
    return {k: _values(v) for k, v in out.items()}


def counts(session: Session, ctx: AnnualContext, year: int) -> tuple[int, int]:
    r = session.execute(text("""
        SELECT count(DISTINCT area) FILTER (WHERE measure = 'est_cases'),
               count(DISTINCT area) FILTER (WHERE measure = 'reported_cases')
        FROM surveillance_annual WHERE disease_id = :d AND scope = 'country' AND year = :y
    """), {"d": ctx.id, "y": year}).one()
    return r[0], r[1]


def countries(session: Session, ctx: AnnualContext, year: int, region: str | None):
    vals = area_values(session, ctx, "country", (year, year - 1))
    rows = session.execute(text("""
        SELECT DISTINCT c.iso3, c.name, c.who_region FROM surveillance_annual a
        JOIN countries c ON c.iso3 = a.iso3
        WHERE a.disease_id = :d AND a.scope = 'country' AND a.year IN (:y, :y - 1)
          AND (CAST(:region AS text) IS NULL OR c.who_region = :region)
        ORDER BY c.name
    """), {"d": ctx.id, "y": year, "region": region}).mappings().all()
    return [(r, vals.get((r["iso3"], year), {}), vals.get((r["iso3"], year - 1), {}))
            for r in rows]


def series(session: Session, ctx: AnnualContext, area: str) -> tuple[str, str, list]:
    """(scope, name, [(year, values)]) for GLOBAL, a WHO region code or a country."""
    rows = session.execute(text("""
        SELECT scope, year, measure, value, low, high FROM surveillance_annual
        WHERE disease_id = :d AND area = :a ORDER BY year
    """), {"d": ctx.id, "a": area}).mappings().all()
    scope = rows[0]["scope"] if rows else ("global" if area == "GLOBAL" else "country")
    by_year: dict[int, list] = defaultdict(list)
    for r in rows:
        by_year[r["year"]].append(r)
    if scope == "country":
        name = session.execute(text("SELECT name FROM countries WHERE iso3 = :a"),
                               {"a": area}).scalar() or area
    else:
        name = "World" if area == "GLOBAL" else area
    return scope, name, [(y, _values(v)) for y, v in sorted(by_year.items())]
