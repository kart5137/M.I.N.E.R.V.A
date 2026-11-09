from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.core.errors import ApiError
from app.queries import countries as q
from app.queries.common import WEEK, Window, check_region, load_disease, monday
from app.schemas.countries import CountryList, CountryProfile, CountryTimeseries

router = APIRouter(prefix="/countries", tags=["countries"])

Disease = Annotated[str, Query(description="Disease key, e.g. `influenza`.")]


@router.get("", response_model=CountryList, summary="Countries with coverage tier")
def list_countries(
    session: Session = Depends(get_session),
    disease: Disease = "influenza",
    region: str | None = None,
    q_: Annotated[str | None, Query(alias="q", max_length=60,
                                    description="Name contains / exact ISO3")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=300)] = 50,
) -> CountryList:
    ctx = load_disease(session, disease)
    total, items = q.list_countries(session, ctx, check_region(region), q_, page, page_size)
    return CountryList(meta=ctx.meta(), total=total, page=page, page_size=page_size,
                       items=items)


@router.get("/{iso3}", response_model=CountryProfile, summary="Country profile")
def country_profile(
    iso3: str,
    session: Session = Depends(get_session),
    disease: Disease = "influenza",
) -> CountryProfile:
    ctx = load_disease(session, disease)
    c = q.country_row(session, iso3)
    return CountryProfile(
        meta=ctx.meta(), **c,
        population=q.population(session, c["iso3"]),
        coverage=q.coverage(session, ctx, c["iso3"]),
        surveillance=q.surveillance_summary(session, ctx, c["iso3"]),
    )


@router.get("/{iso3}/timeseries", response_model=CountryTimeseries,
            summary="Weekly series on a complete calendar (gaps marked, not zero-filled)")
def country_timeseries(
    iso3: str,
    session: Session = Depends(get_session),
    disease: Disease = "influenza",
    from_: Annotated[date | None, Query(alias="from")] = None,
    to: date | None = None,
) -> CountryTimeseries:
    ctx = load_disease(session, disease)
    c = q.country_row(session, iso3)
    end = q.clamp_week(ctx, monday(to)) if to else ctx.latest_week
    start = q.clamp_week(ctx, monday(from_)) if from_ else max(ctx.first_week, end - WEEK * 155)
    if start > end:
        raise ApiError(422, "invalid_range", "'from' must not be after 'to'.")
    w = Window(start, end, (end - start).days // 7 + 1)
    return CountryTimeseries(meta=ctx.meta(), iso3=c["iso3"], window=w.info(ctx),
                             points=q.timeseries(session, ctx, c["iso3"], w))
