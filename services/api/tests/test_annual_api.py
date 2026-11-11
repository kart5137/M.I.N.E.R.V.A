"""Yearly disease endpoints (malaria, C1) on a hand-checkable dataset.

Malaria (id 4, yearly): AAA (EUR) and CCC (AFR) estimates for 2023 and 2024, CCC with an
uncertainty range and reported cases in 2024; WHO's GLOBAL and AFR totals with their own
ranges.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

V1 = "/api/v1"
MAL = {"disease": "malaria"}


@pytest.fixture(scope="module")
def malaria(seeded_engine):
    with seeded_engine.begin() as c:
        c.execute(text("""
            INSERT INTO data_sources (id, key, name, attribution_text)
              VALUES (9, 'who_gho_malaria', 'WHO GHO malaria', 'Malaria data: WHO GHO.');
            INSERT INTO diseases (id, key, name, native_granularity, primary_metric,
                                  metric_label)
              VALUES (4, 'malaria', 'Malaria', 'annual', 'annual', 'Estimated cases');
            INSERT INTO ingestion_runs (id, source_id, status) VALUES (9, 9, 'success');
            INSERT INTO surveillance_annual (disease_id, scope, area, iso3, year, measure,
              value, low, high, source_id, ingestion_run_id) VALUES
              (4, 'country', 'AAA', 'AAA', 2023, 'est_cases', 10, NULL, NULL, 9, 9),
              (4, 'country', 'AAA', 'AAA', 2024, 'est_cases', 0, NULL, NULL, 9, 9),
              (4, 'country', 'CCC', 'CCC', 2023, 'est_cases', 900, 700, 1200, 9, 9),
              (4, 'country', 'CCC', 'CCC', 2024, 'est_cases', 1000, 800, 1300, 9, 9),
              (4, 'country', 'CCC', 'CCC', 2024, 'est_incidence', 250, 200, 320, 9, 9),
              (4, 'country', 'CCC', 'CCC', 2024, 'reported_cases', 640, NULL, NULL, 9, 9),
              (4, 'region', 'AFR', NULL, 2024, 'est_cases', 1000, 800, 1300, 9, 9),
              (4, 'global', 'GLOBAL', NULL, 2023, 'est_cases', 910, 720, 1220, 9, 9),
              (4, 'global', 'GLOBAL', NULL, 2024, 'est_cases', 1000, 790, 1310, 9, 9);
        """))
    yield
    with seeded_engine.begin() as c:
        c.execute(text("DELETE FROM surveillance_annual WHERE disease_id = 4; "
                       "DELETE FROM ingestion_runs WHERE id = 9; "
                       "DELETE FROM diseases WHERE id = 4; DELETE FROM data_sources WHERE id = 9"))


def test_summary_uses_who_totals_and_previous_year(api: TestClient, malaria):
    s = api.get(f"{V1}/annual/summary", params=MAL).json()
    assert s["year"] == 2024 and s["years"] == [2023, 2024]
    assert s["meta"] == {"disease": "malaria", "first_year": 2023, "latest_year": 2024,
                         "grain": "year", "sources": [
                             {"key": "who_gho_malaria", "name": "WHO GHO malaria",
                              "attribution": "Malaria data: WHO GHO."}]}
    w = s["world"]
    assert w["values"]["est_cases"] == {"value": 1000, "low": 790, "high": 1310}
    assert w["previous"]["est_cases"]["value"] == 910
    assert [r["area"] for r in s["regions"]] == ["AFR"]
    assert (s["countries_with_estimates"], s["countries_reporting"]) == (2, 1)
    assert "est_incidence" in s["measures"] and len(s["notes"]) == 3
    old = api.get(f"{V1}/annual/summary", params={**MAL, "year": 2023}).json()
    assert old["world"]["previous"] == {} and old["regions"] == []


def test_countries_keep_estimates_and_reports_apart(api: TestClient, malaria):
    c = api.get(f"{V1}/annual/countries", params=MAL).json()
    by = {i["iso3"]: i for i in c["items"]}
    assert set(by) == {"AAA", "CCC"}
    assert by["CCC"]["values"]["reported_cases"] == {"value": 640, "low": None, "high": None}
    assert by["CCC"]["values"]["est_cases"]["low"] == 800
    assert by["CCC"]["previous"]["est_cases"]["value"] == 900
    assert by["AAA"]["values"]["est_cases"]["value"] == 0      # a real zero, kept
    afr = api.get(f"{V1}/annual/countries", params={**MAL, "region": "AFR"}).json()
    assert [i["iso3"] for i in afr["items"]] == ["CCC"]


def test_series_for_world_region_and_country(api: TestClient, malaria):
    w = api.get(f"{V1}/annual/series", params={**MAL, "area": "global"}).json()
    assert (w["name"], w["scope"], [p["year"] for p in w["points"]]) == (
        "World", "global", [2023, 2024])
    r = api.get(f"{V1}/annual/series", params={**MAL, "area": "AFR"}).json()
    assert r["scope"] == "region" and len(r["points"]) == 1
    c = api.get(f"{V1}/annual/series", params={**MAL, "area": "ccc"}).json()
    assert (c["name"], c["area"]) == ("Charlie", "CCC")
    assert c["points"][1]["values"]["est_incidence"]["high"] == 320
    assert api.get(f"{V1}/annual/series", params={**MAL, "area": "ZZZ"}).status_code == 404


def test_annual_errors(api: TestClient, malaria):
    bad_year = api.get(f"{V1}/annual/summary", params={**MAL, "year": 1999})
    assert bad_year.status_code == 422 and "2023" in bad_year.json()["error"]["message"]
    weekly = api.get(f"{V1}/annual/summary", params={"disease": "influenza"})
    assert weekly.status_code == 422
    assert api.get(f"{V1}/annual/summary", params={"disease": "nope"}).status_code == 404
    # Weekly views answer a yearly disease with a clear 422.
    ov = api.get(f"{V1}/overview", params=MAL)
    assert ov.status_code == 422 and "reported yearly" in ov.json()["error"]["message"]


def test_annual_disease_without_data(api: TestClient, seeded_engine):
    with seeded_engine.begin() as c:
        c.execute(text("INSERT INTO diseases (id, key, name, native_granularity,"
                       " primary_metric, metric_label) VALUES (5, 'cholera', 'Cholera',"
                       " 'annual', 'annual', 'Cases')"))
    try:
        r = api.get(f"{V1}/annual/summary", params={"disease": "cholera"})
        assert r.status_code == 404 and r.json()["error"]["code"] == "no_data"
    finally:
        with seeded_engine.begin() as c:
            c.execute(text("DELETE FROM diseases WHERE id = 5"))
