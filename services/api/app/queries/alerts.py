"""Alerts written by `ei detect run` (pipeline/src/ei_pipeline/intelligence/alerts.py)."""

from __future__ import annotations

from datetime import date

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.queries.common import DiseaseContext
from app.schemas.intelligence import AlertItem

#: Mirrors pipeline/src/ei_pipeline/intelligence/alerts.py RULES.
ALERT_RULES = {
    "new_anomaly": "First week of a seasonal-EWMA anomaly episode (none the week before).",
    "new_hotspot": "Enters a Gi* hot spot (FDR < 0.05) in the 4-week window ending this "
                   "week; not one the week before.",
    "risk_escalation": "2-week forecast at moderate or high risk, first assessment or up "
                       "from the previous one.",
    "sustained_growth": "Positivity up in 3 consecutive weeks by ≥ 5 pp in total "
                        "(≥ 50 specimens each week).",
}
#: Mirrors the dengue rules in the pipeline (D4): incidence instead of positivity, and a
#: relative growth rule.
DENGUE_ALERT_RULES = {
    "new_anomaly": ALERT_RULES["new_anomaly"],
    "new_hotspot": ALERT_RULES["new_hotspot"],
    "risk_escalation": ALERT_RULES["risk_escalation"],
    "sustained_growth": "Incidence up in 3 consecutive weeks by ≥ 50% in total (≥ 20 "
                        "reported cases each week).",
}


def alert_rules(ctx: DiseaseContext) -> dict[str, str]:
    return DENGUE_ALERT_RULES if ctx.case_based else ALERT_RULES


SEVERITY_ORDER = "CASE a.severity WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END"

_FILTER = """
    a.disease_id = :d
    AND (CAST(:region AS text) IS NULL OR c.who_region = :region)
    AND (CAST(:iso3 AS text) IS NULL OR a.iso3 = :iso3)
    AND (CAST(:status AS text) IS NULL OR a.status = :status)
    AND (CAST(:start AS date) IS NULL OR a.week_start >= :start)
    AND (CAST(:end AS date) IS NULL OR a.week_start <= :end)
"""
_TYPED = """
    AND (CAST(:atype AS text) IS NULL OR a.alert_type = :atype)
    AND (CAST(:severity AS text) IS NULL OR a.severity = :severity)
"""
_COLS = """a.id, a.iso3, c.name, c.who_region, a.alert_type, a.severity, a.week_start,
    a.title, a.details, a.status, a.created_at, a.retracted_at"""


def list_alerts(session: Session, ctx: DiseaseContext, *, region: str | None,
                iso3: str | None, alert_type: str | None, severity: str | None,
                status: str | None, start: date | None, end: date | None,
                page: int, page_size: int) -> tuple[int, dict, dict, list[AlertItem]]:
    p = {"d": ctx.id, "region": region, "iso3": iso3, "status": status, "start": start,
         "end": end, "atype": alert_type, "severity": severity}
    base = "FROM alerts a JOIN countries c ON c.iso3 = a.iso3 WHERE " + _FILTER
    # Facet counts ignore their own filter so the UI can show what each choice gives.
    by_type = dict(session.execute(text(
        f"SELECT a.alert_type, count(*) {base} "
        "AND (CAST(:severity AS text) IS NULL OR a.severity = :severity) GROUP BY 1"),
        p).all())
    by_sev = dict(session.execute(text(
        f"SELECT a.severity, count(*) {base} "
        "AND (CAST(:atype AS text) IS NULL OR a.alert_type = :atype) GROUP BY 1"), p).all())
    total = session.execute(text(f"SELECT count(*) {base} {_TYPED}"), p).scalar_one()
    rows = session.execute(text(
        f"SELECT {_COLS} {base} {_TYPED} "
        f"ORDER BY a.week_start DESC, {SEVERITY_ORDER}, a.iso3, a.alert_type "
        "LIMIT :limit OFFSET :offset"),
        {**p, "limit": page_size, "offset": (page - 1) * page_size}).mappings()
    return total, by_type, by_sev, [AlertItem(**r) for r in rows]


def alerts_in_period(session: Session, ctx: DiseaseContext, start: date, end: date,
                     region: str | None, iso3: str | None) -> list[dict]:
    """Active alerts in a period, ordered deterministically (for reports)."""
    rows = session.execute(text(f"""
        SELECT a.id, a.iso3, c.name, a.alert_type, a.severity, a.week_start, a.title
        FROM alerts a JOIN countries c ON c.iso3 = a.iso3
        WHERE a.disease_id = :d AND a.status = 'active'
          AND a.week_start BETWEEN :start AND :end
          AND (CAST(:region AS text) IS NULL OR c.who_region = :region)
          AND (CAST(:iso3 AS text) IS NULL OR a.iso3 = :iso3)
        ORDER BY a.week_start DESC, {SEVERITY_ORDER}, a.iso3, a.alert_type
    """), {"d": ctx.id, "start": start, "end": end, "region": region, "iso3": iso3})
    return [dict(r._mapping) for r in rows]
