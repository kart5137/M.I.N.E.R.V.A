"""Integration tests against a real PostGIS database (skipped when none is reachable).

Run `docker compose -f infra/docker-compose.yml up -d` and `alembic upgrade head` first.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app.core.db import get_engine
from app.main import create_app


def _database_ready() -> bool:
    try:
        with get_engine().connect() as conn:
            return conn.execute(text("SELECT to_regclass('alembic_version')")).scalar() is not None
    except OperationalError:
        return False


pytestmark = pytest.mark.skipif(not _database_ready(), reason="no migrated database reachable")


def test_status_reports_postgis_and_schema():
    body = TestClient(create_app()).get("/api/v1/meta/status").json()
    assert body["database"] == "ok"
    assert body["postgis_version"].startswith("3.")
    assert body["schema_revision"]
    assert body["demo"] is False


def test_status_lists_no_fabricated_diseases_before_ingestion():
    with get_engine().connect() as conn:
        n = conn.execute(text("SELECT count(*) FROM diseases")).scalar()
    body = TestClient(create_app()).get("/api/v1/meta/status").json()
    assert len(body["diseases"]) == n
