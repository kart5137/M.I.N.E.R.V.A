from __future__ import annotations

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.schemas.meta import DiseaseStatus, IngestionSummary, MetaStatus
from ei_db.models import DataSource, Disease, IngestionRun, SurveillanceWeekly


def _scalar_or_none(session: Session, sql: str) -> str | None:
    try:
        with session.begin_nested():
            return session.execute(text(sql)).scalar()
    except Exception:  # table/extension missing before migrations run
        return None


def get_status(session: Session) -> MetaStatus:
    session.execute(text("SELECT 1"))  # raises OperationalError → 503 if DB is down

    postgis = _scalar_or_none(session, "SELECT postgis_lib_version()")
    revision = _scalar_or_none(session, "SELECT version_num FROM alembic_version")

    diseases: list[DiseaseStatus] = []
    ingestions: list[IngestionSummary] = []
    if revision is not None:
        sw = SurveillanceWeekly
        rows = session.execute(
            select(
                Disease.key,
                Disease.name,
                func.max(sw.week_start).filter(sw.is_provisional.is_(False)),
                func.min(sw.week_start).filter(sw.is_provisional.is_(True)),
                func.max(sw.week_start),
                func.count(sw.id),
            )
            .outerjoin(sw, sw.disease_id == Disease.id)
            .group_by(Disease.id)
            .order_by(Disease.key)
        ).all()
        diseases = [
            DiseaseStatus(key=k, name=n, reference_week=ref, provisional_from=prov,
                          latest_week=latest, country_weeks=cnt)
            for k, n, ref, prov, latest, cnt in rows
        ]

        latest_run = (
            select(IngestionRun.source_id, func.max(IngestionRun.id).label("run_id"))
            .group_by(IngestionRun.source_id)
            .subquery()
        )
        runs = session.execute(
            select(DataSource.key, IngestionRun.status, IngestionRun.finished_at,
                   IngestionRun.loaded_rows)
            .join(latest_run, latest_run.c.run_id == IngestionRun.id)
            .join(DataSource, DataSource.id == IngestionRun.source_id)
            .order_by(DataSource.key)
        ).all()
        ingestions = [
            IngestionSummary(source=s, status=st, finished_at=f, loaded_rows=r)
            for s, st, f, r in runs
        ]

    return MetaStatus(
        database="ok",
        postgis_version=postgis,
        schema_revision=revision,
        diseases=diseases,
        last_ingestions=ingestions,
    )
