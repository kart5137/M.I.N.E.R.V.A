"""Gather the facts of a template report from stored data (DESIGN.md §6.6).

Everything a report says comes from here, in a canonical form: JSON types only, floats
rounded to 6 decimals, lists in a fixed order, no timestamps. The SHA-256 of the
canonical JSON identifies the inputs; gathering again from unchanged data gives the same
facts, hash and Markdown.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date

from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.queries import detection as det
from app.queries import models as mq
from app.queries.alerts import alerts_in_period
from app.queries.common import DiseaseContext, Window, check_region, make_window
from app.queries.countries import country_row, timeseries
from app.queries.surveillance import country_window, kpis, top_movers, trend

TEMPLATE_VERSION = "1"
# Fixed English month names (strftime would depend on the process locale).
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
MOVERS_MIN_SPECIMENS = 50

LIMITATIONS = [
    "Test positivity reflects who is tested and how; it is not incidence. Detections "
    "depend on testing volume and are not case counts.",
    "Recent weeks are provisional: countries are still reporting and values will change.",
    "Forecasts are statistical projections with 80% intervals from backtested models; "
    "they are not public-health guidance.",
    "Risk levels use Moving Epidemic Method thresholds, available only for temperate "
    "(NH/SH) countries with at least 3 usable past seasons.",
    "Hotspots compare a country with its neighbours over 4 weeks; few pass the false "
    "discovery rate correction, and countries without data do not take part.",
]


def canonical(obj):
    """JSON-ready copy with floats rounded and dates as ISO strings."""
    if isinstance(obj, float):
        return round(obj, 6)
    if isinstance(obj, date):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {str(k): canonical(v) for k, v in obj.items()}
    if isinstance(obj, list | tuple):
        return [canonical(v) for v in obj]
    if hasattr(obj, "model_dump"):
        return canonical(obj.model_dump(mode="python"))
    return obj


def sha256(content: dict) -> str:
    blob = json.dumps(content, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _weekly(points, w: Window) -> list[dict]:
    start = w.previous.start
    return [{"week_start": p.week_start, "positivity": p.positivity,
             "positives": p.positives, "specimens_tested": p.specimens_tested,
             "provisional": p.is_provisional}
            for p in points if start <= p.week_start <= w.end]


def gather(session: Session, ctx: DiseaseContext, *, scope: str, iso3: str | None,
           region: str | None, to: date | None, weeks: int) -> dict:
    w = make_window(ctx, to, weeks)
    region = check_region(region)
    country = None
    if scope == "country":
        if not iso3:
            raise ApiError(422, "invalid_parameter", "A country report needs `iso3`.")
        country = country_row(session, iso3)
        iso3, region = country["iso3"], None
    else:
        iso3 = None

    det_run, _ = det.run_info(session, ctx)
    fc_run = mq.current_run(session, ctx)
    content: dict = {
        "template_version": TEMPLATE_VERSION,
        "disease": {"key": ctx.key, "name": ctx.name},
        "scope": scope,
        "iso3": iso3,
        "country_name": country["name"] if country else None,
        "who_region": country["who_region"] if country else region,
        "period": {"start": w.start, "end": w.end, "weeks": w.weeks,
                   "previous_start": w.previous.start, "previous_end": w.previous.end,
                   "includes_provisional": w.info(ctx).includes_provisional},
        "data": {"reference_week": ctx.reference_week, "latest_week": ctx.latest_week,
                 "provisional_from": ctx.provisional_from,
                 "sources": [{"name": s.name, "attribution": s.attribution}
                             for s in ctx.sources]},
        "runs": {"forecast": fc_run, "detection": det_run.run_key if det_run else None},
        "limitations": LIMITATIONS,
    }

    if scope == "global":
        k = kpis(session, ctx, w, region)
        content["summary"] = {
            "detections": k.detections.value, "detections_previous": k.detections.previous,
            "positivity": k.positivity.value, "positivity_previous": k.positivity.previous,
            "countries_reporting": k.countries_reporting.value,
            "countries_reporting_previous": k.countries_reporting.previous,
            "countries_with_anomaly": k.anomalies.value if k.anomalies else None,
            "countries_in_hotspot": k.hotspots.value if k.hotspots else None,
            "above_threshold": k.above_threshold.value if k.above_threshold else None,
            "risk_assessed": k.above_threshold.denominator if k.above_threshold else None,
        }
        content["weekly"] = _weekly(trend(session, ctx, w, region, 13), w)
        content["top_movers"] = [m.model_dump() for m in
                                 top_movers(session, ctx, w, region, MOVERS_MIN_SPECIMENS)]
        content["movers_min_specimens"] = MOVERS_MIN_SPECIMENS
    else:
        cur = country_window(session, ctx, w, None, iso3)
        prev = country_window(session, ctx, w.previous, None, iso3)
        c, p = (cur[0] if cur else None), (prev[0] if prev else None)
        content["summary"] = {
            "positivity": c.positivity if c else None,
            "positivity_previous": p.positivity if p else None,
            "detections": c.positives if c else None,
            "detections_previous": p.positives if p else None,
            "specimens_tested": c.specimens_tested if c else None,
            "weeks_reported": c.weeks_reported if c else 0,
            "tier": c.tier if c else None,
        }
        series = timeseries(session, ctx, iso3, Window(w.previous.start, w.end, 2 * weeks))
        content["weekly"] = [{"week_start": s.week_start, "positivity": s.positivity,
                              "positives": s.positives,
                              "specimens_tested": s.specimens_tested,
                              "provisional": s.is_provisional} for s in series]
        levels = det.thresholds_by_season(session, ctx, iso3)
        current = levels[max(levels)] if levels else None
        content["thresholds"] = current.model_dump() if current else None
        if fc_run:
            fc, _ = mq.country_forecasts(session, ctx, fc_run, iso3)
            content["forecasts"] = [
                {"horizon_weeks": f.horizon_weeks, "target_week": f.target_week,
                 "origin_week": f.origin_week, "model": f.label, "point": f.point,
                 "lo80": f.lo80, "hi80": f.hi80}
                for f in sorted((f for f in fc if f.is_active), key=lambda f: f.horizon_weeks)]
        else:
            content["forecasts"] = []

    anomalies = det.anomalies(session, ctx, w, region, iso3, "seasonal_ewma")
    content["anomalies"] = {
        "countries": [a.model_dump() for a in det.by_country(anomalies)],
        "weeks": [{"iso3": a.iso3, "name": a.name, "week_start": a.week_start,
                   "observed": a.observed, "expected": a.expected,
                   "upper_band": a.upper_band, "severity": a.severity}
                  for a in anomalies],
    }
    first, last, _, _ = det.hotspot_range(session, ctx)
    hs = (det.hotspots(session, ctx, w.end, region)
          if first and first <= w.end <= last else [])
    if iso3:
        hs = [h for h in hs if h.iso3 == iso3]
    content["hotspots"] = {
        "window_end": w.end if hs or iso3 is None else None,
        "participants": len(hs),
        "significant": [{"iso3": h.iso3, "name": h.name, "value": h.value,
                         "gi_star": h.gi_star.classification, "z": h.gi_star.z_score,
                         "p_fdr": h.gi_star.p_fdr,
                         "local_moran": h.local_moran.classification}
                        for h in sorted(hs, key=lambda h: (-h.gi_star.z_score, h.iso3))
                        if iso3 or h.gi_star.classification != "ns"
                        or h.local_moran.classification != "ns"],
    }
    content["risk"] = [{"iso3": r.iso3, "name": r.name, "risk_level": r.risk_level,
                        "target_week": r.target_week, "forecast_point": r.forecast_point,
                        "forecast_lo80": r.forecast_lo80, "forecast_hi80": r.forecast_hi80,
                        "epidemic_threshold": r.thresholds.epidemic_threshold,
                        "high_threshold": r.thresholds.high}
                       for r in det.risk(session, ctx, region, iso3)]
    content["alerts"] = alerts_in_period(session, ctx, w.start, w.end, region, iso3)
    return canonical(content)


def title_of(content: dict) -> str:
    d = date.fromisoformat(content["period"]["end"])
    end = f"{d.day} {MONTHS[d.month - 1]} {d.year}"
    weeks = content["period"]["weeks"]
    where = (content["country_name"] if content["scope"] == "country"
             else (f"WHO {content['who_region']} region" if content["who_region"] else "Global"))
    return f"{where} influenza situation — {weeks} weeks to {end}"
