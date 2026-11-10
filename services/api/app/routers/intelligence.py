from __future__ import annotations

from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.queries import detection as det
from app.queries import models as mq
from app.queries.alerts import alert_rules, list_alerts
from app.queries.common import check_region, load_disease
from app.queries.countries import country_row
from app.reports import service
from app.reports.facts import limitations
from app.schemas.intelligence import (
    About,
    AlertList,
    GenerateRequest,
    GenerateResponse,
    ReportDetail,
    ReportList,
    SourceInfo,
    TierInfo,
    Verification,
)

router = APIRouter(tags=["intelligence"])

Disease = Annotated[str, Query(description="Disease key, e.g. `influenza`.")]

#: Mirrors pipeline/src/ei_pipeline/quality/coverage.py TIERS (5-year window).
TIER_RULES = {
    "A": "Forecast-ready: ≥ 85% of weeks reported, longest gap ≤ 8 weeks, median ≥ 30 "
         "specimens/week, last report ≤ 8 weeks old.",
    "B": "Forecast with caution: ≥ 60% of weeks reported, median ≥ 10 specimens/week, "
         "last report ≤ 26 weeks old.",
    "C": "Map and trends only: some data in the 5-year window.",
    "D": "Historical only: no data in the 5-year window.",
}
DATA_LIMITATIONS = [
    "FluNet reports what national laboratories submit: testing strategies, sentinel versus "
    "non-sentinel mix and reporting delays differ between countries and over time.",
    "Some country-weeks report implausibly high positivity (above 90%), which affects MEM "
    "intensity levels; such levels fail the quality check and are not used.",
    "Year-round (mostly tropical) countries have no MEM thresholds, so no risk level.",
    "Backtests use today's revised data, not the data as first published, so live "
    "forecast accuracy will be somewhat lower than reported.",
    "Overseas departments (GLP, GUF, MTQ) have no boundary of their own and are not "
    "mapped or used in spatial statistics.",
]
#: Mirrors pipeline/src/ei_pipeline/quality/coverage.py DENGUE_TIERS (3-year window).
DENGUE_TIER_RULES = {
    "A": "Forecast-ready (weekly): ≥ 85% of weeks reported, longest gap ≤ 8 weeks, last "
         "report ≤ 8 weeks old, cases in ≥ 50% of reported weeks.",
    "B": "Forecast with caution (weekly): ≥ 60% of weeks reported, last report ≤ 26 weeks "
         "old, cases in ≥ 50% of reported weeks.",
    "C": "Map and trends only: some data in the 3-year window (every monthly reporter and "
         "mostly-zero weekly series).",
    "D": "Historical only: no data in the 3-year window.",
}
DENGUE_DATA_LIMITATIONS = [
    "Countries report suspected, probable or confirmed cases under their own case "
    "definitions, so incidence compares within a country over time, not between countries.",
    "Recent weeks are often revised upwards as reports arrive; provisional weeks are "
    "marked and excluded from model training.",
    "Monthly reporters are shown as trends only; they are not forecast or scanned for "
    "anomalies, and their months are never split into invented weeks.",
    "Weather is ERA5 at one point per country, which does not represent large or "
    "climatically varied countries.",
    "Most countries' dengue years are too irregular for MEM thresholds, so few countries "
    "have a risk level.",
    "Backtests use today's revised data, not the data as first published, so live "
    "forecast accuracy will be somewhat lower than reported.",
]


@router.get("/alerts", response_model=AlertList, summary="Alerts with filters and facet counts")
def alerts(
    session: Session = Depends(get_session),
    disease: Disease = "influenza",
    region: Annotated[str | None, Query()] = None,
    iso3: Annotated[str | None, Query()] = None,
    alert_type: Annotated[Literal["new_anomaly", "new_hotspot", "risk_escalation",
                                  "sustained_growth"] | None, Query(alias="type")] = None,
    severity: Annotated[Literal["low", "medium", "high"] | None, Query()] = None,
    status: Annotated[Literal["active", "retracted", "all"], Query()] = "active",
    start: Annotated[date | None, Query(alias="from")] = None,
    end: Annotated[date | None, Query(alias="to")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
) -> AlertList:
    ctx = load_disease(session, disease)
    code = country_row(session, iso3)["iso3"] if iso3 else None
    total, by_type, by_sev, items = list_alerts(
        session, ctx, region=check_region(region), iso3=code, alert_type=alert_type,
        severity=severity, status=None if status == "all" else status, start=start,
        end=end, page=page, page_size=page_size)
    return AlertList(meta=ctx.meta(), rules=alert_rules(ctx), total=total, page=page,
                     page_size=page_size, by_type=by_type, by_severity=by_sev, items=items)


@router.get("/reports", response_model=ReportList, summary="Stored reports, newest first")
def reports(
    session: Session = Depends(get_session),
    disease: Disease = "influenza",
    scope: Annotated[Literal["global", "country"] | None, Query()] = None,
    iso3: Annotated[str | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> ReportList:
    ctx = load_disease(session, disease)
    total, items = service.list_reports(session, ctx, scope, iso3, page, page_size)
    return ReportList(total=total, page=page, page_size=page_size, items=items)


@router.post("/reports/generate", response_model=GenerateResponse,
             summary="Build a template report from stored data (rate-limited)")
def generate_report(req: GenerateRequest, request: Request,
                    session: Session = Depends(get_session),
                    disease: Disease = "influenza") -> GenerateResponse:
    service.check_rate(request.client.host if request.client else "unknown")
    ctx = load_disease(session, disease)
    report, reused = service.generate(session, ctx, req)
    return GenerateResponse(report=report, reused=reused)


@router.get("/reports/{report_id}", response_model=ReportDetail, summary="One report")
def report(report_id: int, session: Session = Depends(get_session)) -> ReportDetail:
    return service.get_report(session, report_id)


@router.get("/reports/{report_id}/verify", response_model=Verification,
            summary="Regenerate from current stored data and compare with the stored report")
def verify_report(report_id: int, session: Session = Depends(get_session),
                  disease: Disease = "influenza") -> Verification:
    ctx = load_disease(session, disease)
    return service.verify(session, ctx, report_id)


@router.get("/about", response_model=About,
            summary="Sources, coverage tiers, model and detection runs, limitations")
def about(session: Session = Depends(get_session), disease: Disease = "influenza") -> About:
    ctx = load_disease(session, disease)
    sources = session.execute(text("""
        SELECT ds.key, ds.name, ds.url, ds.licence, ds.attribution_text AS attribution,
               ds.notes, ir.finished_at AS last_ingestion, ir.status AS last_status,
               CASE ds.key
                 WHEN 'natural_earth' THEN
                   (SELECT count(*) FROM countries WHERE geom IS NOT NULL)
                 ELSE (SELECT count(*) FROM surveillance_weekly s WHERE s.source_id = ds.id)
                    + (SELECT count(*) FROM surveillance_monthly m WHERE m.source_id = ds.id)
                    + (SELECT count(*) FROM population_annual p WHERE p.source_id = ds.id)
                    + (SELECT count(*) FROM health_indicators h WHERE h.source_id = ds.id)
                    + (SELECT count(*) FROM weather_weekly w WHERE w.source_id = ds.id)
               END AS stored_rows
        FROM data_sources ds
        LEFT JOIN LATERAL (
          SELECT finished_at, status, loaded_rows FROM ingestion_runs
          WHERE source_id = ds.id ORDER BY id DESC LIMIT 1) ir ON true
        ORDER BY ds.id""")).mappings()
    ref = session.execute(text("""SELECT max(reference_week) FROM coverage_profiles
                                  WHERE disease_id = :d"""), {"d": ctx.id}).scalar()
    counts = dict(session.execute(text("""
        SELECT tier, count(*) FROM coverage_profiles
        WHERE disease_id = :d AND reference_week = :r GROUP BY tier"""),
        {"d": ctx.id, "r": ref}).all()) if ref else {}

    fc = None
    run_key = mq.current_run(session, ctx)
    if run_key:
        info = mq.run_info(session, run_key)
        fc = {"run_key": run_key, **{k: info[k] for k in info.keys()},
              "models": [m.model_dump() for m in mq.run_models(session, run_key)
                         if m.is_active]}
    run, summary = det.run_info(session, ctx)
    dr = None
    if run:
        s = summary or {}
        dr = {"run_key": run.run_key, "finished_at": run.finished_at,
              "reference_week": run.reference_week, "settings": s.get("settings", {}),
              "risk": s.get("risk"), "alerts": s.get("alerts"),
              "anomalies": s.get("anomalies"), "hotspots": s.get("hotspots"),
              "thresholds_current_usable": s.get("thresholds", {})
              .get("countries_current_usable")}
    return About(
        meta=ctx.meta(), sources=[SourceInfo(**r) for r in sources],
        coverage_reference_week=ref,
        tiers=[TierInfo(tier=t, countries=counts.get(t, 0), rule=rule)
               for t, rule in (DENGUE_TIER_RULES if ctx.case_based else TIER_RULES).items()],
        forecast_run=fc, detection_run=dr,
        limitations=(DENGUE_DATA_LIMITATIONS if ctx.case_based else DATA_LIMITATIONS)
        + limitations(ctx),
    )
