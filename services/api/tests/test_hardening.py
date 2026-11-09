"""M8 hardening: response headers, caching rules, rate-limiter memory bound, report CLI."""

from __future__ import annotations

import json
import time

from fastapi.testclient import TestClient
from sqlalchemy import text

from app import cli
from app.reports import service

V1 = "/api/v1"


def test_security_headers_on_every_response(api: TestClient):
    for r in (api.get(f"{V1}/health"), api.get(f"{V1}/no-such-route")):
        assert r.headers["x-content-type-options"] == "nosniff"
        assert r.headers["x-frame-options"] == "DENY"
        assert r.headers["referrer-policy"] == "no-referrer"


def test_cache_rules(api: TestClient):
    assert api.get(f"{V1}/countries").headers["cache-control"].startswith("public, max-age=300")
    # Status checks, reports and errors are never cached.
    assert api.get(f"{V1}/health").headers["cache-control"] == "no-store"
    assert api.get(f"{V1}/meta/status").headers["cache-control"] == "no-store"
    assert api.get(f"{V1}/reports").headers["cache-control"] == "no-store"
    assert api.get(f"{V1}/countries/ZZZ").headers["cache-control"] == "no-store"


def test_cors_allows_configured_origin_only(api: TestClient):
    ok = api.get(f"{V1}/health", headers={"Origin": "http://localhost:3000"})
    assert ok.headers["access-control-allow-origin"] == "http://localhost:3000"
    other = api.get(f"{V1}/health", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in other.headers


def test_cors_origin_regex(monkeypatch):
    from app.core.config import get_settings
    from app.main import create_app

    monkeypatch.setenv("API_CORS_ORIGIN_REGEX", r"^https://ei-[a-z0-9-]+\.vercel\.app$")
    get_settings.cache_clear()
    try:
        c = TestClient(create_app())
        ok = c.get(f"{V1}/health", headers={"Origin": "https://ei-git-main-x.vercel.app"})
        assert ok.headers["access-control-allow-origin"] == "https://ei-git-main-x.vercel.app"
        no = c.get(f"{V1}/health", headers={"Origin": "https://ei.vercel.app.evil.com"})
        assert "access-control-allow-origin" not in no.headers
    finally:
        get_settings.cache_clear()


def test_rate_limiter_forgets_idle_clients(monkeypatch):
    service._hits.clear()
    monkeypatch.setattr(service, "_MAX_CLIENTS", 3)
    for ip in ("a", "b", "c"):
        service.check_rate(ip)
    # Make a and b idle for over a minute; the next new client triggers a sweep.
    for ip in ("a", "b"):
        service._hits[ip][-1] = time.monotonic() - 120
    service.check_rate("d")
    assert set(service._hits) == {"c", "d"}
    service._hits.clear()


def test_report_cli_matches_api(api: TestClient, seeded_engine, capsys):
    try:
        assert cli.main(["report", "--weeks", "4"], engine=seeded_engine) == 0
        first = json.loads(capsys.readouterr().out)
        assert not first["reused"] and first["title"].startswith("Global influenza situation")
        # The API sees the same report and reuses it for identical inputs.
        res = api.post(f"{V1}/reports/generate", json={"weeks": 4}).json()
        assert res["reused"] and res["report"]["id"] == first["id"]
        assert res["report"]["inputs_sha256"] == first["inputs_sha256"]
        # Errors exit non-zero with the API's error code.
        assert cli.main(["report", "--scope", "country", "--iso3", "ZZZ"],
                        engine=seeded_engine) == 2
        assert capsys.readouterr().err.startswith("error: unknown_country")
    finally:
        with seeded_engine.begin() as c:
            c.execute(text("DELETE FROM report_alerts"))
            c.execute(text("DELETE FROM intelligence_reports"))


def test_missing_schema_is_a_clear_503(monkeypatch):
    """An empty database (no migrations) answers 503 schema_missing, not a bare 500."""
    from psycopg.errors import UndefinedTable
    from sqlalchemy.exc import ProgrammingError

    from app.core.db import get_session
    from app.main import create_app

    class Empty:
        def execute(self, *a, **k):
            missing = UndefinedTable('relation "diseases" does not exist')
            raise ProgrammingError("SELECT", {}, missing)

        def close(self):
            pass

    app = create_app()
    app.dependency_overrides[get_session] = lambda: Empty()
    r = TestClient(app, raise_server_exceptions=False).get(f"{V1}/countries")
    assert r.status_code == 503 and r.json()["error"]["code"] == "schema_missing"
