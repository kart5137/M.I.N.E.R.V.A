from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.queries.common import check_region, load_disease, make_window
from app.queries.surveillance import country_window, kpis, top_movers, trend
from app.schemas.surveillance import GlobalSurveillance, Overview

router = APIRouter(tags=["surveillance"])

Disease = Annotated[str, Query(description="Disease key, e.g. `influenza`.")]
To = Annotated[date | None, Query(
    description="Last week of the window (any date; snapped to its ISO-week Monday). "
                "Default: the reference week.")]
Weeks = Annotated[int, Query(ge=1, le=52, description="Window length in weeks.")]
Region = Annotated[str | None, Query(description="WHO region code, e.g. `EUR`.")]


@router.get("/surveillance/global", response_model=GlobalSurveillance,
            summary="Per-country values for one window (map layers)")
def global_surveillance(
    session: Session = Depends(get_session),
    disease: Disease = "influenza",
    to: To = None,
    weeks: Weeks = 1,
    region: Region = None,
) -> GlobalSurveillance:
    ctx = load_disease(session, disease)
    region = check_region(region)
    w = make_window(ctx, to, weeks)
    return GlobalSurveillance(
        meta=ctx.meta(), window=w.info(ctx), region=region,
        countries=country_window(session, ctx, w, region),
    )


@router.get("/overview", response_model=Overview,
            summary="KPIs vs. the previous window, weekly trend and top movers")
def overview(
    session: Session = Depends(get_session),
    disease: Disease = "influenza",
    to: To = None,
    weeks: Weeks = 4,
    region: Region = None,
    trend_weeks: Annotated[int, Query(ge=13, le=520)] = 156,
    movers_min_specimens: Annotated[int, Query(ge=1)] = 50,
    movers_min_cases: Annotated[int, Query(
        ge=1, description="Case-based diseases: minimum cases in both windows")] = 50,
) -> Overview:
    ctx = load_disease(session, disease)
    region = check_region(region)
    w = make_window(ctx, to, weeks)
    return Overview(
        meta=ctx.meta(), window=w.info(ctx), previous_window=w.previous.info(ctx),
        region=region,
        kpis=kpis(session, ctx, w, region),
        trend=trend(session, ctx, w, region, trend_weeks),
        top_movers=top_movers(session, ctx, w, region, movers_min_specimens,
                              min_cases=movers_min_cases),
        movers_min_specimens=movers_min_specimens,
        movers_min_cases=movers_min_cases if ctx.case_based else None,
    )
