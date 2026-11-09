from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_session
from app.queries.meta import get_status
from app.schemas.meta import Health, MetaStatus

router = APIRouter(tags=["meta"])


@router.get("/health", response_model=Health, summary="Liveness check (no database)")
def health() -> Health:
    return Health(status="ok", version=get_settings().version)


@router.get("/meta/status", response_model=MetaStatus, summary="Data and schema status")
def meta_status(session: Session = Depends(get_session)) -> MetaStatus:
    return get_status(session)
