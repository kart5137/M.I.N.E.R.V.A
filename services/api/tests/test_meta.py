from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.db import get_session
from app.main import create_app
from ei_db import make_engine, make_session_factory


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


def test_health(client: TestClient):
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_status_returns_503_when_database_unreachable():
    # Port 1 is never a Postgres server: the connection fails immediately.
    engine = make_engine(
        "postgresql+psycopg://x:x@127.0.0.1:1/none", connect_args={"connect_timeout": 1}
    )

    def broken_session():
        s = make_session_factory(engine)()
        try:
            yield s
        finally:
            s.close()

    app = create_app()
    app.dependency_overrides[get_session] = broken_session
    r = TestClient(app).get("/api/v1/meta/status")
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "database_unavailable"


def test_openapi_lists_endpoints(client: TestClient):
    paths = client.get("/api/v1/openapi.json").json()["paths"]
    assert "/api/v1/health" in paths and "/api/v1/meta/status" in paths
