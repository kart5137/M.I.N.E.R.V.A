from __future__ import annotations

from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.core.errors import ApiError
from app.queries import analytics as q
from app.queries.common import MIN_SPECIMENS_FOR_RATE, WEEK, load_disease, monday
from app.schemas.analytics import Heatmap, Trends

router = APIRouter(prefix="/analytics", tags=["analytics"])

Disease = Annotated[str, Query(description="Disease key, e.g. `influenza`.")]
SeriesParam = Annotated[str, Query(
    description="Comma-separated series: ISO3 codes, `region:<WHO code>`, `world`. Max 6.",
    examples=["world,region:EUR,USA"])]


@router.get("/trends", response_model=Trends,
            summary="Weekly / monthly / yearly aggregates per series, with change vs. "
                    "previous bucket: positivity and influenza A/B mix (influenza) or "
                    "cases, deaths and incidence (case-based diseases)")
def trends(
    series: SeriesParam,
    session: Session = Depends(get_session),
    disease: Disease = "influenza",
    granularity: Literal["week", "month", "year"] = "week",
    from_: Annotated[date | None, Query(alias="from")] = None,
    to: date | None = None,
) -> Trends:
    ctx = load_disease(session, disease)
    specs = q.parse_series(session, series.split(","))
    one = q.case_trend_series if ctx.case_based else q.trend_series
    end = min(monday(to), ctx.latest_week) if to else ctx.latest_week
    default_span = {"week": 103, "month": 260, "year": 520}[granularity]
    start = max(monday(from_), ctx.first_week) if from_ else max(
        ctx.first_week, end - WEEK * default_span)
    if start > end:
        raise ApiError(422, "invalid_range", "'from' must not be after 'to'.")
    if granularity == "week" and (end - start).days // 7 > 520:
        raise ApiError(422, "invalid_range", "Weekly trends are limited to 10 years.")
    return Trends(
        meta=ctx.meta(), granularity=granularity, start=start, end=end,
        series=[one(session, ctx, s, granularity, start, end) for s in specs],
    )


@router.get("/heatmap", response_model=Heatmap,
            summary="Positivity (influenza) or incidence (case-based diseases) by ISO "
                    "week x ISO year for one series")
def heatmap(
    series: Annotated[str, Query(description="One series: ISO3, `region:<code>` or `world`.")],
    session: Session = Depends(get_session),
    disease: Disease = "influenza",
    years: Annotated[int, Query(ge=1, le=32)] = 10,
) -> Heatmap:
    ctx = load_disease(session, disease)
    if "," in series:
        raise ApiError(422, "invalid_series", "The heatmap takes exactly one series.")
    spec = q.parse_series(session, [series])[0]
    last = ctx.latest_week.isocalendar()[0]
    first = max(ctx.first_week.isocalendar()[0], last - years + 1)
    return Heatmap(
        meta=ctx.meta(), key=spec.key, label=spec.label, years=list(range(first, last + 1)),
        min_specimens=MIN_SPECIMENS_FOR_RATE,
        cells=(q.case_heatmap if ctx.case_based else q.heatmap)(session, ctx, spec, first, last),
    )
