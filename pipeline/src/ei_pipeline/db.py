"""Database helpers for pipeline jobs: sessions and ingestion-run tracking."""

from __future__ import annotations

import logging
import traceback
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from ei_db import make_engine, make_session_factory
from ei_db.models import DataSource, IngestionRun

log = logging.getLogger(__name__)


@contextmanager
def session_scope(engine: Engine | None = None) -> Iterator[Session]:
    """One transaction: commit on success, roll back on error."""
    session = make_session_factory(engine or make_engine())()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def source_id(session: Session, key: str) -> int:
    sid = session.scalar(select(DataSource.id).where(DataSource.key == key))
    if sid is None:
        raise LookupError(f"Data source {key!r} is not registered; run `ei ingest reference`.")
    return sid


@dataclass
class RunContext:
    run_id: int
    source_id: int
    report: dict[str, Any] = field(default_factory=dict)
    raw_rows: int | None = None
    loaded_rows: int | None = None
    raw_sha256: str | None = None


@contextmanager
def track_run(engine: Engine, source_key: str) -> Iterator[RunContext]:
    """Record an ingestion run. The run row is committed up front (its own transaction)
    so that failures are recorded too; the job does its data work in a separate session."""
    with session_scope(engine) as s:
        sid = source_id(s, source_key)
        run = IngestionRun(source_id=sid, status="running")
        s.add(run)
        s.flush()
        ctx = RunContext(run_id=run.id, source_id=sid)

    status = "succeeded"
    try:
        yield ctx
    except Exception as exc:
        status = "failed"
        ctx.report["error"] = {"type": type(exc).__name__, "message": str(exc),
                               "trace": traceback.format_exc(limit=5)}
        raise
    finally:
        with session_scope(engine) as s:
            run = s.get(IngestionRun, ctx.run_id)
            run.status = status
            run.finished_at = datetime.now(UTC)
            run.raw_rows = ctx.raw_rows
            run.loaded_rows = ctx.loaded_rows
            run.raw_sha256 = ctx.raw_sha256
            run.quality_report = ctx.report
        log.info("Run %s (%s) %s", ctx.run_id, source_key, status)
