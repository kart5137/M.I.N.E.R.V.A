from __future__ import annotations

from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.core.errors import ApiError
from app.queries import countries as q
from app.queries.common import (
    MIN_SPECIMENS_FOR_RATE,
    WEEK,
    Window,
    check_region,
    load_disease,
    make_window,
    monday,
)
from app.queries.seasons import country_seasons
from app.queries.surveillance import country_window
from app.schemas.countries import CountryList, CountryProfile, CountrySeasons, CountryTimeseries

router = APIRouter(prefix="/countries", tags=["countries"])

Disease = Annotated[str, Query(description="Disease key, e.g. `influenza`.")]
SortKey = Literal["name", "tier", "positivity", "specimens_tested", "positives",
                  "last_reported_week"]
#: Window for "recent" values in the list and profile: 4 weeks to the reference week.
RECENT_WEEKS = 4
SEASON_RULES = {
    "NH": "Northern-hemisphere season: ISO week 40 to week 39 of the next year.",
    "SH": "Southern-hemisphere season: calendar ISO year.",
    "YR": "Year-round circulation: calendar ISO year.",
}


@router.get("", response_model=CountryList,
            summary="Countries with tier and values for the recent window (sortable)")
def list_countries(
    session: Session = Depends(get_session),
    disease: Disease = "influenza",
    region: str | None = None,
    q_: Annotated[str | None, Query(alias="q", max_length=60,
                                    description="Name contains / exact ISO3")] = None,
    sort: SortKey = "name",
    order: Literal["asc", "desc"] = "asc",
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=300)] = 50,
) -> CountryList:
    ctx = load_disease(session, disease)
    w = make_window(ctx, None, RECENT_WEEKS)
    total, items = q.list_countries(session, ctx, w, check_region(region), q_, sort, order,
                                    page, page_size)
    return CountryList(meta=ctx.meta(), window=w.info(ctx), sort=sort, order=order,
                       total=total, page=page, page_size=page_size, items=items)


@router.get("/{iso3}", response_model=CountryProfile, summary="Country profile")
def country_profile(
    iso3: str,
    session: Session = Depends(get_session),
    disease: Disease = "influenza",
) -> CountryProfile:
    ctx = load_disease(session, disease)
    c = q.country_row(session, iso3)
    w = make_window(ctx, None, RECENT_WEEKS)
    recent = country_window(session, ctx, w, None, c["iso3"])
    return CountryProfile(
        meta=ctx.meta(), **c,
        population=q.population(session, c["iso3"]),
        coverage=q.coverage(session, ctx, c["iso3"]),
        surveillance=q.surveillance_summary(session, ctx, c["iso3"]),
        health=q.health(session, c["iso3"]),
        recent_window=w.info(ctx),
        recent=recent[0] if recent else None,
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


@router.get("/{iso3}/seasons", response_model=CountrySeasons,
            summary="Season-aligned weekly curves for the latest seasons")
def country_seasons_endpoint(
    iso3: str,
    session: Session = Depends(get_session),
    disease: Disease = "influenza",
    n: Annotated[int, Query(ge=1, le=15, description="Number of seasons")] = 6,
) -> CountrySeasons:
    ctx = load_disease(session, disease)
    c = q.country_row(session, iso3)
    season_type = c["flu_season"]
    if season_type is None:
        # Area without FluNet reports: no season type is known, nothing to align.
        return CountrySeasons(meta=ctx.meta(), iso3=c["iso3"], season_type=None,
                              season_rule="No FluNet season type for this area.",
                              min_specimens_for_peak=MIN_SPECIMENS_FOR_RATE, seasons=[])
    return CountrySeasons(
        meta=ctx.meta(), iso3=c["iso3"], season_type=season_type,
        season_rule=SEASON_RULES[season_type],
        min_specimens_for_peak=MIN_SPECIMENS_FOR_RATE,
        seasons=country_seasons(session, ctx, c["iso3"], season_type, n),
    )
