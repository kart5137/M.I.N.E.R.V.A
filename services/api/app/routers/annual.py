"""Yearly diseases (malaria, C1): summary, per-country values and series."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.queries import annual as q
from app.queries.common import WHO_REGIONS, check_region
from app.queries.countries import country_row
from app.schemas.annual import (
    AnnualCountries,
    AnnualCountry,
    AnnualSeries,
    AnnualSummary,
    AreaTotal,
    SeriesPoint,
)

router = APIRouter(tags=["annual"])

Disease = Annotated[str, Query(description="A yearly disease, e.g. `malaria`.")]
Year = Annotated[int | None, Query(description="Default: the latest year with estimates.")]
Region = Annotated[str | None, Query(description="WHO region code, e.g. `AFR`.")]


@router.get("/annual/summary", response_model=AnnualSummary,
            summary="Global and regional totals for one year, with the previous year")
def summary(session: Session = Depends(get_session), disease: Disease = "malaria",
            year: Year = None) -> AnnualSummary:
    ctx = q.load_annual(session, disease)
    y = q.check_year(ctx, year)
    glob = q.area_values(session, ctx, "global", (y, y - 1))
    regs = q.area_values(session, ctx, "region", (y, y - 1))
    regions = sorted({a for a, _ in regs})
    with_est, reporting = q.counts(session, ctx, y)
    return AnnualSummary(
        meta=ctx.meta(), year=y, years=list(range(ctx.first_year, ctx.latest_year + 1)),
        measures=ctx.measures,
        world=(AreaTotal(area="GLOBAL", values=glob[("GLOBAL", y)],
                           previous=glob.get(("GLOBAL", y - 1), {}))
                 if ("GLOBAL", y) in glob else None),
        regions=[AreaTotal(area=r, values=regs.get((r, y), {}), previous=regs.get((r, y - 1), {}))
                 for r in regions if (r, y) in regs],
        countries_with_estimates=with_est, countries_reporting=reporting, notes=ctx.notes)


@router.get("/annual/countries", response_model=AnnualCountries,
            summary="Every country's values for one year (and the previous year)")
def countries(session: Session = Depends(get_session), disease: Disease = "malaria",
              year: Year = None, region: Region = None) -> AnnualCountries:
    ctx = q.load_annual(session, disease)
    y = q.check_year(ctx, year)
    region = check_region(region)
    items = [AnnualCountry(iso3=r["iso3"], name=r["name"], who_region=r["who_region"],
                           values=cur, previous=prev)
             for r, cur, prev in q.countries(session, ctx, y, region)]
    return AnnualCountries(meta=ctx.meta(), year=y, region=region, items=items)


@router.get("/annual/series", response_model=AnnualSeries,
            summary="Yearly series for the world (GLOBAL), a WHO region or a country")
def series(area: Annotated[str, Query(description="GLOBAL, a WHO region code or an ISO3")],
           session: Session = Depends(get_session), disease: Disease = "malaria"
           ) -> AnnualSeries:
    ctx = q.load_annual(session, disease)
    code = area.strip().upper()
    if code != "GLOBAL" and code not in WHO_REGIONS:
        code = country_row(session, code)["iso3"]  # 404 for an unknown country
    scope, name, pts = q.series(session, ctx, code)
    partial = ctx.latest_year if ctx.weekly else None
    return AnnualSeries(meta=ctx.meta(), area=code, name=name, scope=scope,
                        points=[SeriesPoint(year=y, values=v) for y, v in pts],
                        partial_year=partial, notes=ctx.notes, measures=ctx.measures)
