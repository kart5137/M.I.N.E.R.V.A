"""Alerts, reports and About (M7). Seeds three alerts and one anomaly; removes them (and
any reports) afterwards.

Done-when check for M7: a report regenerates identically from stored inputs."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.reports import service

V1 = "/api/v1"
W = ["2024-01-01", "2024-01-08", "2024-01-15", "2024-01-22", "2024-01-29", "2024-02-05",
     "2024-02-12", "2024-02-19"]
TABLES = ("report_alerts", "intelligence_reports", "alerts", "anomalies", "detection_runs")


@pytest.fixture(scope="module")
def seeded(seeded_engine):
    with seeded_engine.begin() as c:
        c.execute(text(f"""
            INSERT INTO detection_runs (id, disease_id, run_key, reference_week, latest_week,
              finished_at, summary)
            VALUES (7, 1, 'D7', '{W[6]}', '{W[7]}', now(), '{{}}');
            INSERT INTO anomalies (run_id, disease_id, iso3, week_start, metric, method,
              observed, expected, upper_band, score, ewma, ewma_limit, specimens_tested,
              severity)
            VALUES (7, 1, 'AAA', '{W[5]}', 'positivity', 'seasonal_ewma', 0.6, 0.2, 0.3, 3.5,
                    2.0, 1.26, 100, 'high');
            INSERT INTO alerts (id, disease_id, iso3, alert_type, severity, week_start, title,
              details, status, last_run_id)
            VALUES
              (1, 1, 'AAA', 'new_anomaly', 'medium', '{W[5]}',
               'Alpha: positivity 60.0% above the seasonal range', '{{"observed": 0.6}}',
               'active', 7),
              (2, 1, 'BBB', 'sustained_growth', 'low', '{W[3]}',
               'Bravo: positivity up 3 weeks in a row', '{{}}', 'active', 7),
              (3, 1, 'AAA', 'new_hotspot', 'medium', '{W[2]}', 'Alpha: new Gi* hot spot',
               '{{}}', 'retracted', 7);
        """))
    yield
    with seeded_engine.begin() as c:
        for t in TABLES:
            c.execute(text(f"DELETE FROM {t}"))


def test_alerts_filters_and_facets(api: TestClient, seeded):
    body = api.get(f"{V1}/alerts").json()
    assert [a["id"] for a in body["items"]] == [1, 2]  # active only, latest week first
    assert body["by_type"] == {"new_anomaly": 1, "sustained_growth": 1}
    assert body["by_severity"] == {"medium": 1, "low": 1}
    assert body["rules"]["sustained_growth"].startswith("Positivity up in 3")
    typed = api.get(f"{V1}/alerts", params={"type": "new_anomaly"}).json()
    assert typed["total"] == 1 and typed["by_type"]["sustained_growth"] == 1  # facet kept
    assert api.get(f"{V1}/alerts", params={"status": "all"}).json()["total"] == 3
    assert api.get(f"{V1}/alerts", params={"iso3": "bbb"}).json()["items"][0]["id"] == 2
    assert api.get(f"{V1}/alerts", params={"region": "AFR"}).json()["total"] == 0
    assert api.get(f"{V1}/alerts", params={"type": "nope"}).status_code == 422


def test_report_regenerates_identically(api: TestClient, seeded):
    res = api.post(f"{V1}/reports/generate", json={"scope": "global", "weeks": 4}).json()
    r = res["report"]
    assert not res["reused"]
    assert r["title"] == "Global influenza situation — 4 weeks to 12 Feb 2024"
    assert (r["period_start"], r["period_end"]) == (W[3], W[6])
    # Active alerts in the period are linked; the retracted one and earlier ones are not.
    assert r["alerts"] == 2
    assert [a["id"] for a in r["content"]["alerts"]] == [1, 2]
    assert "Lab-confirmed detections: **303**" in r["rendered_md"]

    v = api.get(f"{V1}/reports/{r['id']}/verify").json()
    assert v["inputs_identical"] and v["rendering_identical"] and v["regenerated_identical"]
    assert v["changed_sections"] == [] and v["current_sha256"] == r["inputs_sha256"]

    again = api.post(f"{V1}/reports/generate", json={"scope": "global", "weeks": 4}).json()
    assert again["reused"] and again["report"]["id"] == r["id"]
    assert api.get(f"{V1}/reports").json()["total"] == 1


def test_verify_detects_changed_inputs(api: TestClient, seeded, seeded_engine):
    r = api.post(f"{V1}/reports/generate", json={"scope": "global", "weeks": 2}).json()["report"]
    with seeded_engine.begin() as c:
        c.execute(text(f"""
            INSERT INTO anomalies (id, run_id, disease_id, iso3, week_start, metric, method,
              observed, score, severity)
            VALUES (9999, 7, 1, 'BBB', '{W[6]}', 'positivity', 'seasonal_ewma', 0.5, 2.0,
                    'moderate')"""))
    try:
        v = api.get(f"{V1}/reports/{r['id']}/verify").json()
        assert not v["inputs_identical"] and not v["regenerated_identical"]
        assert v["rendering_identical"]  # the stored facts still render to the stored text
        assert "anomalies" in v["changed_sections"]
    finally:
        with seeded_engine.begin() as c:
            c.execute(text("DELETE FROM anomalies WHERE id = 9999"))
    assert api.get(f"{V1}/reports/{r['id']}/verify").json()["inputs_identical"]


def test_country_report_and_errors(api: TestClient, seeded):
    r = api.post(f"{V1}/reports/generate",
                 json={"scope": "country", "iso3": "aaa", "weeks": 4}).json()["report"]
    assert r["iso3"] == "AAA" and r["title"].startswith("Alpha influenza situation")
    assert "## Outlook" in r["rendered_md"] and "| 5 Feb 2024 | 60.0% |" in r["rendered_md"]
    assert api.get(f"{V1}/reports/{r['id']}").json()["content"]["iso3"] == "AAA"
    bad = api.post(f"{V1}/reports/generate", json={"scope": "country", "weeks": 4})
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "invalid_parameter"
    assert api.post(f"{V1}/reports/generate",
                    json={"scope": "country", "iso3": "ZZZ"}).status_code == 404
    assert api.get(f"{V1}/reports/99999").json()["error"]["code"] == "unknown_report"


def test_generate_is_rate_limited(api: TestClient, seeded, monkeypatch):
    monkeypatch.setattr(service, "RATE_LIMIT", 2)
    service._hits.clear()
    codes = [api.post(f"{V1}/reports/generate", json={"weeks": 4}).status_code
             for _ in range(3)]
    assert codes == [200, 200, 429]
    service._hits.clear()


def test_about(api: TestClient, seeded):
    d = api.get(f"{V1}/about").json()
    flunet = next(s for s in d["sources"] if s["key"] == "flunet")
    assert flunet["stored_rows"] == 23 and flunet["attribution"].startswith("Influenza data")
    assert {t["tier"]: t["countries"] for t in d["tiers"]} == {"A": 1, "B": 0, "C": 0, "D": 0}
    assert d["detection_run"]["run_key"] == "D7"
    assert any("not incidence" in x for x in d["limitations"])
