from __future__ import annotations

from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.queries import detection as q
from app.queries.common import (
    Window,
    check_region,
    load_disease,
    make_window,
    monday,
)
from app.queries.countries import country_row
from app.schemas.detection import (
    Anomalies,
    CountryDetection,
    DetectionHistory,
    Hotspots,
    RiskList,
)

router = APIRouter(tags=["detection"])

Disease = Annotated[str, Query(description="Disease key, e.g. `influenza`.")]
To = Annotated[date | None, Query(
    description="Last week of the window (snapped to its ISO-week Monday). "
                "Default: the reference week.")]
Region = Annotated[str | None, Query(description="WHO region code, e.g. `EUR`.")]


@router.get("/anomalies", response_model=Anomalies,
            summary="Anomalous country-weeks in a window (seasonal EWMA and Isolation Forest)")
def anomalies(
    session: Session = Depends(get_session),
    disease: Disease = "influenza",
    to: To = None,
    weeks: Annotated[int, Query(ge=1, le=156)] = 4,
    region: Region = None,
    iso3: Annotated[str | None, Query(description="One country")] = None,
    method: Annotated[Literal["seasonal_ewma", "isolation_forest"] | None, Query()] = None,
) -> Anomalies:
    ctx = load_disease(session, disease)
    region = check_region(region)
    code = country_row(session, iso3)["iso3"] if iso3 else None
    w = make_window(ctx, to, weeks)
    run, _ = q.run_info(session, ctx)
    items = q.anomalies(session, ctx, w, region, code, method)
    return Anomalies(meta=ctx.meta(), run=run, window=w.info(ctx), region=region, iso3=code,
                     method_note=q.anomaly_note(ctx), items=items,
                     by_country=q.by_country(items))


@router.get("/hotspots", response_model=Hotspots,
            summary="Gi* and Local Moran's I per country for the 4-week window ending at `to`")
def hotspots(
    session: Session = Depends(get_session),
    disease: Disease = "influenza",
    to: To = None,
    region: Region = None,
) -> Hotspots:
    ctx = load_disease(session, disease)
    region = check_region(region)
    run, _ = q.run_info(session, ctx)
    first, last, weeks, spec = q.hotspot_range(session, ctx)
    base = dict(meta=ctx.meta(), run=run, region=region, available_from=first,
                available_to=last, weights_spec=spec, permutations=q.PERMUTATIONS,
                fdr_alpha=q.FDR_ALPHA)
    end = monday(to) if to else ctx.reference_week
    if first is None or not first <= end <= last:
        return Hotspots(**base, window=None, items=[])
    w = Window(end - q.WEEK * (weeks - 1), end, weeks)
    return Hotspots(**base, window=w.info(ctx), items=q.hotspots(session, ctx, end, region))


@router.get("/detection/history", response_model=DetectionHistory,
            summary="Weekly counts of hotspot and anomaly countries")
def detection_history(session: Session = Depends(get_session), disease: Disease = "influenza",
                      region: Region = None) -> DetectionHistory:
    ctx = load_disease(session, disease)
    region = check_region(region)
    return DetectionHistory(meta=ctx.meta(), region=region,
                            points=q.history(session, ctx, region))


@router.get("/risk", response_model=RiskList,
            summary="Risk level of the 2-week forecast against MEM thresholds "
                    "(influenza) or the endemic channel (dengue)")
def risk(session: Session = Depends(get_session), disease: Disease = "influenza",
         region: Region = None) -> RiskList:
    ctx = load_disease(session, disease)
    region = check_region(region)
    run, summary = q.run_info(session, ctx)
    items = q.risk(session, ctx, region)
    return RiskList(meta=ctx.meta(), run=run, region=region, rule=q.risk_rule(ctx),
                    items=items,
                    not_assessed=q.not_assessed(session, summary, region,
                                                {r.iso3 for r in items}, ctx))


@router.get("/countries/{iso3}/detection", response_model=CountryDetection,
            summary="Thresholds, risk, anomalies (latest 52 weeks) and hotspot status")
def country_detection(iso3: str, session: Session = Depends(get_session),
                      disease: Disease = "influenza") -> CountryDetection:
    ctx = load_disease(session, disease)
    c = country_row(session, iso3)
    run, summary = q.run_info(session, ctx)
    by_season = q.thresholds_by_season(session, ctx, c["iso3"])
    current = by_season[max(by_season)] if by_season else None
    reason = (summary or {}).get("thresholds", {}).get("not_assessed", {}).get(c["iso3"])
    if current is not None and reason is None and current.quality_note:
        reason = f"MEM levels unusable: {current.quality_note}"
    chan = q.channel(session, ctx, c["iso3"]) if ctx.case_based else None
    if chan is not None:
        reason = None
    if current is None and chan is None and reason is None:
        if ctx.case_based:
            reason = ("No weekly dengue reporting: detection runs on weekly data (monthly "
                      "reporters are shown as trends only).")
        else:
            reason = ("No FluNet season type for this area." if c["flu_season"] is None
                      else "Not enough past seasons.")
    risk = q.risk(session, ctx, None, c["iso3"])
    return CountryDetection(
        meta=ctx.meta(), run=run, iso3=c["iso3"], thresholds=current,
        thresholds_reason=reason, channel=chan, risk=risk[0] if risk else None,
        anomalies=q.anomalies(session, ctx, q.last_weeks(ctx, 52), None, c["iso3"], None),
        hotspots=q.country_hotspots(session, ctx, c["iso3"]),
    )

