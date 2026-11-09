from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from test_meta_db import _database_ready

pytestmark = pytest.mark.skipif(not _database_ready(), reason="no migrated database reachable")


def test_countries_geojson_with_etag():
    client = TestClient(create_app())
    r = client.get("/api/v1/geo/countries", headers={"Accept-Encoding": "gzip"})
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/geo+json"
    body = r.json()
    assert body["type"] == "FeatureCollection"
    for f in body["features"][:5]:
        assert f["id"] == f["properties"]["iso3"]
        assert f["geometry"]["type"] == "MultiPolygon"
        assert len(f["properties"]["label"]) == 2

    again = client.get("/api/v1/geo/countries", headers={"If-None-Match": r.headers["etag"]})
    assert again.status_code == 304
