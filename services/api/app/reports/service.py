"""Generate, store, list and verify template reports."""

from __future__ import annotations

import json
import threading
import time
from collections import deque

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.queries.common import DiseaseContext
from app.reports.facts import TEMPLATE_VERSION, gather, sha256, title_of
from app.reports.render import render_markdown
from app.schemas.intelligence import (
    GenerateRequest,
    ReportDetail,
    ReportSummary,
    Verification,
)

#: POST /reports/generate: at most this many new reports per client per minute.
RATE_LIMIT = 10
_hits: dict[str, deque] = {}
_lock = threading.Lock()


def check_rate(client: str) -> None:
    now = time.monotonic()
    with _lock:
        q = _hits.setdefault(client, deque())
        while q and now - q[0] > 60:
            q.popleft()
        if len(q) >= RATE_LIMIT:
            raise ApiError(429, "rate_limited",
                           f"At most {RATE_LIMIT} reports per minute; try again shortly.")
        q.append(now)


_SUMMARY_COLS = """r.id, r.title, r.scope, r.iso3, r.region, r.period_start, r.period_end,
    r.weeks, r.generator, r.template_version, r.inputs_sha256, r.created_at,
    (SELECT count(*) FROM report_alerts ra WHERE ra.report_id = r.id) AS alerts"""


def get_report(session: Session, report_id: int) -> ReportDetail:
    r = session.execute(text(f"""
        SELECT {_SUMMARY_COLS}, r.content, r.rendered_md FROM intelligence_reports r
        WHERE r.id = :id"""), {"id": report_id}).mappings().one_or_none()
    if r is None:
        raise ApiError(404, "unknown_report", f"No report with id {report_id}.")
    return ReportDetail(**r)


def list_reports(session: Session, ctx: DiseaseContext, scope: str | None, iso3: str | None,
                 page: int, page_size: int) -> tuple[int, list[ReportSummary]]:
    p = {"d": ctx.id, "scope": scope, "iso3": iso3.upper() if iso3 else None}
    where = """r.disease_id = :d AND (CAST(:scope AS text) IS NULL OR r.scope = :scope)
               AND (CAST(:iso3 AS text) IS NULL OR r.iso3 = :iso3)"""
    total = session.execute(text(f"SELECT count(*) FROM intelligence_reports r WHERE {where}"),
                            p).scalar_one()
    rows = session.execute(text(f"""
        SELECT {_SUMMARY_COLS} FROM intelligence_reports r WHERE {where}
        ORDER BY r.created_at DESC, r.id DESC LIMIT :limit OFFSET :offset"""),
        {**p, "limit": page_size, "offset": (page - 1) * page_size}).mappings()
    return total, [ReportSummary(**r) for r in rows]


def _params(req: GenerateRequest) -> dict:
    return {"scope": req.scope, "iso3": req.iso3, "region": req.region, "to": req.to,
            "weeks": req.weeks}


def generate(session: Session, ctx: DiseaseContext, req: GenerateRequest
             ) -> tuple[ReportDetail, bool]:
    content = gather(session, ctx, **_params(req))
    digest = sha256(content)
    existing = session.execute(text("""
        SELECT id FROM intelligence_reports
        WHERE disease_id = :d AND inputs_sha256 = :h AND template_version = :v
        ORDER BY id LIMIT 1"""),
        {"d": ctx.id, "h": digest, "v": TEMPLATE_VERSION}).scalar()
    if existing is not None:
        return get_report(session, existing), True

    p = content["period"]
    rid = session.execute(text("""
        INSERT INTO intelligence_reports (disease_id, scope, iso3, region, period_start,
          period_end, weeks, title, content, rendered_md, generator, template_version,
          inputs_sha256)
        VALUES (:d, :scope, :iso3, :region, :start, :end, :weeks, :title,
                CAST(:content AS jsonb), :md, 'template', :v, :h)
        RETURNING id"""), {
        "d": ctx.id, "scope": content["scope"], "iso3": content["iso3"],
        "region": content["who_region"] if content["scope"] == "global" else None,
        "start": p["start"], "end": p["end"], "weeks": p["weeks"],
        "title": title_of(content), "content": json.dumps(content, ensure_ascii=False),
        "md": render_markdown(content), "v": TEMPLATE_VERSION, "h": digest,
    }).scalar_one()
    ids = [a["id"] for a in content["alerts"]]
    if ids:
        session.execute(text("""
            INSERT INTO report_alerts (report_id, alert_id)
            SELECT :r, unnest(CAST(:ids AS bigint[]))"""), {"r": rid, "ids": ids})
    session.commit()
    return get_report(session, rid), False


def verify(session: Session, ctx: DiseaseContext, report_id: int) -> Verification:
    r = get_report(session, report_id)
    stored = r.content
    again = gather(session, ctx, scope=r.scope, iso3=r.iso3, region=r.region,
                   to=r.period_end, weeks=r.weeks)
    current = sha256(again)
    changed = sorted(k for k in set(stored) | set(again) if stored.get(k) != again.get(k))
    return Verification(
        report_id=r.id, stored_sha256=r.inputs_sha256, current_sha256=current,
        inputs_identical=current == r.inputs_sha256,
        rendering_identical=render_markdown(stored) == r.rendered_md,
        regenerated_identical=render_markdown(again) == r.rendered_md,
        changed_sections=changed,
    )
