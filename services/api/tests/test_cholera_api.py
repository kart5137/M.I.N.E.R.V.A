"""Cholera (C2): weekly cases with deaths and case fatality, yearly history with weekly
sums from 2023 on, and the gated features.

Cholera (id 6): AAA (population 1,000) weeks W0–W3 of 2024 with 10, 10, 10, 5 cases and
1, 0, 1, 0 deaths; BBB W0 with 5 cases and 1 death (too few cases for a fatality rate).
Yearly GHO history for AAA in 2016.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

V1 = "/api/v1"
CHO = {"disease": "cholera"}


@pytest.fixture(scope="module")
def cholera(seeded_engine):
    with seeded_engine.begin() as c:
        c.execute(text("""
            INSERT INTO data_sources (id, key, name, attribution_text) VALUES
              (11, 'who_cholera_dashboard', 'WHO cholera dashboard', 'Cholera data: WHO.'),
              (12, 'who_gho_cholera', 'WHO GHO cholera', 'Cholera history: WHO GHO.');
            INSERT INTO diseases (id, key, name, native_granularity, primary_metric,
                                  metric_label)
              VALUES (6, 'cholera', 'Cholera', 'weekly+annual', 'cases', 'Reported cases');
            INSERT INTO ingestion_runs (id, source_id, status) VALUES (11, 11, 'success'),
                                                                    (12, 12, 'success');
            INSERT INTO surveillance_weekly (disease_id, iso3, week_start, iso_year, iso_week,
              cases, deaths, is_provisional, source_id, ingestion_run_id) VALUES
              (6, 'AAA', '2024-01-01', 2024, 1, 10, 1, false, 11, 11),
              (6, 'AAA', '2024-01-08', 2024, 2, 10, 0, false, 11, 11),
              (6, 'AAA', '2024-01-15', 2024, 3, 10, 1, false, 11, 11),
              (6, 'AAA', '2024-01-22', 2024, 4, 5, 0, true, 11, 11),
              (6, 'BBB', '2024-01-01', 2024, 1, 5, 1, false, 11, 11);
            INSERT INTO surveillance_annual (disease_id, scope, area, iso3, year, measure,
              value, source_id, ingestion_run_id) VALUES
              (6, 'country', 'AAA', 'AAA', 2016, 'reported_cases', 400, 12, 12),
              (6, 'country', 'AAA', 'AAA', 2016, 'reported_deaths', 8, 12, 12),
              (6, 'country', 'AAA', 'AAA', 2016, 'cfr', 2.0, 12, 12);
        """))
    yield
    with seeded_engine.begin() as c:
        c.execute(text("DELETE FROM surveillance_annual WHERE disease_id = 6; "
                       "DELETE FROM surveillance_weekly WHERE disease_id = 6; "
                       "DELETE FROM ingestion_runs WHERE id IN (11, 12); "
                       "DELETE FROM diseases WHERE id = 6; "
                       "DELETE FROM data_sources WHERE id IN (11, 12)"))


def test_weekly_values_carry_deaths_and_case_fatality(api: TestClient, cholera):
    g = api.get(f"{V1}/surveillance/global", params={**CHO, "to": "2024-01-22",
                                                      "weeks": 4}).json()
    by = {c["iso3"]: c for c in g["countries"]}
    assert (by["AAA"]["cases"], by["AAA"]["deaths"]) == (35, 2)
    assert by["AAA"]["cfr"] == pytest.approx(2 / 35)
    assert by["BBB"]["deaths"] == 1 and by["BBB"]["cfr"] is None     # 5 cases < 20
    # The latest week is provisional, so the reference week is the one before.
    assert g["meta"]["reference_week"] == "2024-01-15"
    ts = api.get(f"{V1}/countries/AAA/timeseries",
                 params={**CHO, "from": "2024-01-01", "to": "2024-01-22"}).json()
    assert [p["deaths"] for p in ts["points"]] == [1, 0, 1, 0]


def test_dengue_and_influenza_values_have_no_deaths(api: TestClient, cholera):
    flu = api.get(f"{V1}/surveillance/global").json()["countries"]
    assert all(c["deaths"] is None and c["cfr"] is None for c in flu)


def test_yearly_history_with_weekly_sums_and_partial_year(api: TestClient, cholera):
    s = api.get(f"{V1}/annual/series", params={**CHO, "area": "AAA"}).json()
    years = {p["year"]: p["values"] for p in s["points"]}
    assert set(years) == {2016, 2024}
    assert years[2016]["cfr"]["value"] == 2.0
    assert years[2024]["reported_cases"]["value"] == 35
    assert years[2024]["reported_deaths"]["value"] == 2
    assert s["partial_year"] == 2024 and s["meta"]["latest_year"] == 2024
    assert set(s["measures"]) == {"reported_cases", "reported_deaths", "cfr"}
    assert any("2017–2022" in n for n in s["notes"])
    src = {x["key"] for x in s["meta"]["sources"]}
    assert src == {"who_cholera_dashboard", "who_gho_cholera"}
    summary = api.get(f"{V1}/annual/summary", params=CHO).json()
    assert summary["world"] is None and summary["year"] == 2024


def test_weekly_only_disease_has_no_yearly_view(api: TestClient):
    # Dengue reports weekly (no yearly rows): the yearly endpoints answer 422.
    assert api.get(f"{V1}/annual/series", params={"disease": "dengue", "area": "AAA"}
                   ).status_code == 422
