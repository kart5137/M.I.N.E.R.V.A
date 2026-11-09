"""Alert rules (M7): each rule on small hand-made inputs, then upsert and retraction in
the database."""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
from sqlalchemy import text

from ei_pipeline.intelligence.alerts import (
    anomaly_alerts,
    generate_alerts,
    growth_alerts,
    hotspot_alerts,
    risk_alerts,
)

W = [date(2025, 3, 3) + timedelta(weeks=i) for i in range(10)]


def test_new_anomaly_only_at_episode_start():
    df = pd.DataFrame({
        "id": [1, 2, 3, 4], "iso3": "AAA", "name": "Alpha",
        "week_start": [W[0], W[1], W[2], W[5]], "observed": 0.3, "expected": 0.1,
        "upper_band": 0.2, "score": [2.0, 3.5, 6.0, 2.0],
        "severity": ["moderate", "high", "severe", "moderate"], "is_provisional": False,
        "specimens_tested": 100,
    })
    alerts = anomaly_alerts(df)
    assert [(a.week_start, a.severity, a.anomaly_id) for a in alerts] == [
        (W[0], "low", 1), (W[5], "low", 4)]
    assert alerts[0].title.startswith("Alpha: positivity 30.0% above the seasonal range")


def test_new_hotspot_on_entry_only():
    df = pd.DataFrame({
        "id": [1, 2, 3, 4], "iso3": "AAA", "name": "Alpha",
        "window_end": [W[0], W[1], W[2], W[3]], "value": 0.4, "z_score": 3.0,
        "p_fdr": 0.01, "classification": ["hot", "hot", "ns", "hot"],
    })
    assert [a.week_start for a in hotspot_alerts(df)] == [W[0], W[3]]


def test_risk_escalation_needs_a_rise_to_moderate_or_high():
    df = pd.DataFrame({
        "id": [1, 2, 3, 4, 5], "iso3": "AAA", "name": "Alpha",
        "assessed_week": W[:5], "target_week": W[2:7],
        "risk_level": ["low", "moderate", "moderate", "high", "low"],
        "forecast_point": 0.2, "epidemic_threshold": 0.1, "high_threshold": 0.3,
        "season": "2024/25",
    })
    out = risk_alerts(df)
    assert [(a.week_start, a.severity, a.details["previous_level"]) for a in out] == [
        (W[1], "medium", "low"), (W[3], "high", "moderate")]
    # A first assessment that is already moderate alerts too.
    first = df.iloc[[2]].assign(iso3="BBB", name="Bravo")
    assert [a.details["previous_level"] for a in risk_alerts(first)] == [None]


def _weekly(p, tests=100, weeks=None, iso3="AAA"):
    weeks = weeks or W[:len(p)]
    return pd.DataFrame({"iso3": iso3, "name": "Alpha", "week_start": weeks,
                         "tests": tests, "positives": [round(x * tests) for x in p],
                         "is_provisional": False})


def test_sustained_growth_rule():
    # Rises 3 weeks in a row by 9 pp in total: alert at the 4th value, once per run-up.
    out = growth_alerts(_weekly([0.05, 0.07, 0.10, 0.14, 0.20, 0.10]))
    assert [(a.week_start, a.severity) for a in out] == [(W[3], "low")]
    assert out[0].details["rise_pp"] == 9.0
    # Small total rise: nothing. Big rise: medium.
    assert growth_alerts(_weekly([0.05, 0.06, 0.07, 0.08])) == []
    assert growth_alerts(_weekly([0.05, 0.10, 0.15, 0.20]))[0].severity == "medium"
    # A missing week breaks the run; too few specimens never count.
    gap = [W[0], W[1], W[3], W[4]]
    assert growth_alerts(_weekly([0.05, 0.07, 0.10, 0.14], weeks=gap)) == []
    assert growth_alerts(_weekly([0.05, 0.07, 0.10, 0.14], tests=40)) == []


def test_alerts_are_upserted_and_retracted(db):
    with db.begin() as c:
        c.execute(text("""
            INSERT INTO data_sources (id, key, name) VALUES (1, 'flunet', 'FluNet');
            INSERT INTO diseases (id, key, name, native_granularity, primary_metric,
                                  metric_label)
              VALUES (1, 'influenza', 'Influenza', 'weekly', 'positivity', 'Positivity');
            INSERT INTO countries (iso3, name) VALUES ('AAA', 'Alpha');
            INSERT INTO detection_runs (id, disease_id, run_key, reference_week, latest_week)
              VALUES (1, 1, 'r1', '2025-03-24', '2025-03-24'),
                     (2, 1, 'r2', '2025-03-24', '2025-03-24'),
                     (3, 1, 'r3', '2025-03-24', '2025-03-24');
            INSERT INTO anomalies (id, run_id, disease_id, iso3, week_start, metric, method,
              observed, expected, upper_band, score, specimens_tested, severity)
            VALUES (1, 1, 1, 'AAA', '2025-03-03', 'positivity', 'seasonal_ewma', 0.3, 0.1,
                    0.2, 2.0, 100, 'moderate'),
                   (2, 1, 1, 'AAA', '2025-03-17', 'positivity', 'seasonal_ewma', 0.3, 0.1,
                    0.2, 5.5, 100, 'severe');
        """))
    def q(sql):
        with db.connect() as c:
            return c.execute(text(sql)).all()
    assert generate_alerts(db, 1, 1)["active"] == 2
    first_ids = {r[0] for r in q("SELECT id FROM alerts")}

    # Same outputs again: same rows (ids kept), nothing retracted.
    res = generate_alerts(db, 1, 2)
    assert res["retracted_now"] == 0
    assert {r[0] for r in q("SELECT id FROM alerts")} == first_ids
    assert q("SELECT DISTINCT first_run_id, last_run_id FROM alerts") == [(1, 2)]

    # A revision removes one anomaly: its alert is kept but retracted.
    with db.begin() as c:
        c.execute(text("DELETE FROM anomalies WHERE id = 2"))
    assert generate_alerts(db, 1, 3)["retracted_now"] == 1
    assert q("SELECT week_start::text, status, severity FROM alerts ORDER BY week_start") == [
        ("2025-03-03", "active", "low"), ("2025-03-17", "retracted", "high")]
