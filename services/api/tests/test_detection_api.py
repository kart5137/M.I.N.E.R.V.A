"""Detection endpoints read stored results. A tiny run is inserted by hand (and removed
afterwards so the other modules see no detection run):

- thresholds: AAA (NH) 2023/24 usable; BBB (SH) 2024 with a quality note.
- risk: AAA moderate.
- anomalies (seasonal EWMA): AAA W5 moderate, W6 high; BBB W3 severe;
  BBB W1 Isolation Forest (secondary).
- hotspots: windows ending W2 and W6 for AAA and BBB; AAA is a hot spot at W6.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

V1 = "/api/v1"
W = ["2024-01-01", "2024-01-08", "2024-01-15", "2024-01-22", "2024-01-29", "2024-02-05",
     "2024-02-12", "2024-02-19"]
SUMMARY = ('{"thresholds": {"not_assessed": {"CCC": '
           '"year-round circulation: MEM assumes one epidemic per season"}}}')
TABLES = ("risk_assessments", "anomalies", "hotspot_results", "seasonal_thresholds",
          "detection_runs")


def _hs(iso3, end, stat, z, p, fdr, cls):
    return (f"(1, 1, '{iso3}', '{end}', 4, '{stat}', 0.3, 1.0, {z}, {p}, {fdr}, '{cls}', 1, "
            f"'queen', 'queen contiguity')")


@pytest.fixture(scope="module")
def detection(seeded_engine):
    hs = ",\n".join([
        _hs("AAA", W[6], "gi_star", 3.1, 0.001, 0.01, "hot"),
        _hs("AAA", W[6], "local_moran", 2.0, 0.002, 0.02, "HH"),
        _hs("BBB", W[6], "gi_star", -0.5, 0.4, 0.4, "ns"),
        _hs("BBB", W[6], "local_moran", 0.1, 0.5, 0.5, "ns"),
        _hs("AAA", W[2], "gi_star", 0.5, 0.3, 0.6, "ns"),
        _hs("AAA", W[2], "local_moran", 0.2, 0.4, 0.6, "ns"),
        _hs("BBB", W[2], "gi_star", 0.1, 0.6, 0.6, "ns"),
        _hs("BBB", W[2], "local_moran", 0.0, 0.9, 0.9, "ns"),
    ])
    with seeded_engine.begin() as c:
        c.execute(text("""
            INSERT INTO detection_runs (id, disease_id, run_key, reference_week, latest_week,
              finished_at, summary)
            VALUES (1, 1, 'D1', :ref, :latest, now(), CAST(:summary AS jsonb))
        """), {"ref": W[6], "latest": W[7], "summary": SUMMARY})
        c.execute(text(f"""
            INSERT INTO seasonal_thresholds (id, run_id, disease_id, iso3, season, season_start,
              method, epidemic_threshold, post_threshold, medium, high, very_high,
              n_seasons_used, seasons_used, mean_epidemic_weeks, quality_note)
            VALUES (1, 1, 1, 'AAA', '2023/24', '2023-10-02', 'mem', 0.10, 0.08, 0.20, 0.30,
                    0.40, 5, '["2016/17","2017/18","2018/19","2022/23","2023/24"]', 10, NULL),
                   (2, 1, 1, 'BBB', '2024', '2024-01-01', 'mem', 0.30, NULL, 0.20, 0.40,
                    0.50, 3, '["2019","2023","2022"]', 8, 'levels are not ordered');
            INSERT INTO risk_assessments (run_id, disease_id, iso3, assessed_week, target_week,
              risk_level, rule, forecast_point, forecast_lo80, forecast_hi80, model_type,
              forecast_id, threshold_id)
            VALUES (1, 1, 'AAA', '{W[6]}', '2024-02-26', 'moderate', 'rule text', 0.25, 0.2,
                    0.3, 'xgboost', NULL, 1);
            INSERT INTO anomalies (run_id, disease_id, iso3, week_start, metric, method,
              observed, expected, upper_band, score, ewma, ewma_limit, specimens_tested,
              severity, is_provisional)
            VALUES (1, 1, 'AAA', '{W[5]}', 'positivity', 'seasonal_ewma', 0.6, 0.2, 0.3, 2.0,
                    1.5, 1.26, 100, 'moderate', false),
                   (1, 1, 'AAA', '{W[6]}', 'positivity', 'seasonal_ewma', 0.7, 0.2, 0.3, 3.5,
                    2.0, 1.26, 100, 'high', false),
                   (1, 1, 'BBB', '{W[3]}', 'positivity', 'seasonal_ewma', 0.9, 0.1, 0.2, 6.0,
                    3.0, 1.26, 50, 'severe', false),
                   (1, 1, 'BBB', '{W[1]}', 'positivity', 'isolation_forest', 0.1, NULL, NULL,
                    0.7, NULL, NULL, 50, NULL, false);
            INSERT INTO hotspot_results (run_id, disease_id, iso3, window_end, window_weeks,
              statistic, value, stat_value, z_score, p_value, p_fdr, classification,
              n_neighbours, neighbour_source, weights_spec)
            VALUES {hs};
        """))
    yield "D1"
    with seeded_engine.begin() as c:
        for t in TABLES:
            c.execute(text(f"DELETE FROM {t}"))


def test_anomalies_window_and_country_summary(api: TestClient, detection):
    body = api.get(f"{V1}/anomalies", params={"weeks": 4}).json()
    assert body["window"]["start"] == W[3] and body["window"]["end"] == W[6]
    assert [(a["iso3"], a["week_start"]) for a in body["items"]] == [
        ("AAA", W[6]), ("AAA", W[5]), ("BBB", W[3])]
    by = body["by_country"]
    assert [b["iso3"] for b in by] == ["BBB", "AAA"]  # most severe first
    assert by[1]["weeks_flagged"] == 2 and by[1]["max_severity"] == "high"
    assert by[1]["latest_week"] == W[6]
    sec = api.get(f"{V1}/anomalies", params={"weeks": 8, "method": "isolation_forest"}).json()
    assert [a["iso3"] for a in sec["items"]] == ["BBB"] and sec["by_country"] == []
    one = api.get(f"{V1}/anomalies", params={"weeks": 8, "iso3": "aaa"}).json()
    assert one["iso3"] == "AAA" and len(one["items"]) == 2
    assert api.get(f"{V1}/anomalies", params={"iso3": "ZZZ"}).status_code == 404


def test_hotspots_pair_statistics_per_window(api: TestClient, detection):
    body = api.get(f"{V1}/hotspots").json()
    assert body["window"] == {"start": W[3], "end": W[6], "weeks": 4,
                              "includes_provisional": False}
    assert body["available_from"] == W[2] and body["available_to"] == W[6]
    aaa = body["items"][0]
    assert aaa["iso3"] == "AAA" and aaa["gi_star"]["classification"] == "hot"
    assert aaa["local_moran"]["classification"] == "HH"
    assert api.get(f"{V1}/hotspots", params={"to": "2024-01-17"}).json()["window"]["end"] == W[2]
    outside = api.get(f"{V1}/hotspots", params={"to": "2024-01-01"}).json()
    assert outside["window"] is None and outside["items"] == []


def test_history_counts(api: TestClient, detection):
    pts = api.get(f"{V1}/detection/history").json()["points"]
    assert [(p["week_start"], p["hot"], p["participants"], p["anomalies"]) for p in pts] == [
        (W[2], 0, 2, 0), (W[6], 1, 2, 1)]


def test_risk_and_not_assessed_reasons(api: TestClient, detection):
    body = api.get(f"{V1}/risk").json()
    assert [r["iso3"] for r in body["items"]] == ["AAA"]
    r = body["items"][0]
    assert r["risk_level"] == "moderate" and r["thresholds"]["epidemic_threshold"] == 0.10
    reasons = {n["iso3"]: n["reason"] for n in body["not_assessed"]}
    assert "year-round" in reasons["CCC"]
    assert reasons["BBB"].startswith("no forecast")
    assert api.get(f"{V1}/risk", params={"region": "AFR"}).json()["items"] == []


def test_country_detection(api: TestClient, detection):
    a = api.get(f"{V1}/countries/AAA/detection").json()
    assert a["thresholds"]["season"] == "2023/24" and a["thresholds_reason"] is None
    assert a["risk"]["risk_level"] == "moderate"
    assert len(a["anomalies"]) == 2
    assert [h["window_end"] for h in a["hotspots"]] == [W[2], W[6]]
    b = api.get(f"{V1}/countries/BBB/detection").json()
    assert b["thresholds_reason"] == "MEM levels unusable: levels are not ordered"
    assert b["risk"] is None
    c = api.get(f"{V1}/countries/CCC/detection").json()
    assert c["thresholds"] is None and "year-round" in c["thresholds_reason"]


def test_seasons_carry_thresholds(api: TestClient, detection):
    seasons = api.get(f"{V1}/countries/AAA/seasons").json()["seasons"]
    current = [s for s in seasons if s["is_current"]][0]
    assert current["label"] == "2023/24"
    assert current["thresholds"]["high"] == 0.30


def test_overview_detection_kpis(api: TestClient, detection):
    k = api.get(f"{V1}/overview", params={"weeks": 4}).json()["kpis"]
    assert k["anomalies"]["value"] == 2 and k["anomalies"]["previous"] == 0
    assert k["hotspots"]["value"] == 1 and k["hotspots"]["previous"] == 0
    assert k["above_threshold"]["value"] == 1 and k["above_threshold"]["denominator"] == 1
    assert k["pending"] == []


def test_global_forecasts_without_run(api: TestClient, detection):
    body = api.get(f"{V1}/forecasts/global", params={"horizon": 2}).json()
    assert body["items"] == [] and body["run_key"] in (None, "R1")
    assert api.get(f"{V1}/forecasts/global", params={"horizon": 3}).status_code == 422
