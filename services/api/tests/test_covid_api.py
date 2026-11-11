"""COVID-19 (C3): weekly cases with deaths but no case fatality rate, and yearly totals
summed from the weekly reports (there is no separate yearly source).

COVID-19 (id 7): AAA weeks of 2021 (W52) and 2024 (W1–W3), BBB W1 of 2024.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

V1 = "/api/v1"
COV = {"disease": "covid19"}


@pytest.fixture(scope="module")
def covid(seeded_engine):
    with seeded_engine.begin() as c:
        c.execute(text("""
            INSERT INTO data_sources (id, key, name, attribution_text) VALUES
              (13, 'who_covid_dashboard', 'WHO COVID-19 dashboard', 'COVID-19 data: WHO.');
            INSERT INTO diseases (id, key, name, native_granularity, primary_metric,
                                  metric_label)
              VALUES (7, 'covid19', 'COVID-19', 'weekly+annual', 'cases', 'Reported cases');
            INSERT INTO ingestion_runs (id, source_id, status) VALUES (13, 13, 'success');
            INSERT INTO surveillance_weekly (disease_id, iso3, week_start, iso_year, iso_week,
              cases, deaths, is_provisional, source_id, ingestion_run_id) VALUES
              (7, 'AAA', '2021-12-27', 2021, 52, 1000, 10, false, 13, 13),
              (7, 'AAA', '2024-01-01', 2024, 1, 100, 2, false, 13, 13),
              (7, 'AAA', '2024-01-08', 2024, 2, 80, 1, false, 13, 13),
              (7, 'AAA', '2024-01-15', 2024, 3, 60, NULL, true, 13, 13),
              (7, 'BBB', '2024-01-01', 2024, 1, 40, 0, false, 13, 13);
        """))
    yield
    with seeded_engine.begin() as c:
        c.execute(text("DELETE FROM surveillance_weekly WHERE disease_id = 7; "
                       "DELETE FROM ingestion_runs WHERE id = 13; "
                       "DELETE FROM diseases WHERE id = 7; "
                       "DELETE FROM data_sources WHERE id = 13"))


def test_weekly_values_have_deaths_but_no_case_fatality(api: TestClient, covid):
    g = api.get(f"{V1}/surveillance/global", params={**COV, "to": "2024-01-15",
                                                      "weeks": 3}).json()
    by = {c["iso3"]: c for c in g["countries"]}
    assert (by["AAA"]["cases"], by["AAA"]["deaths"]) == (240, 3)
    assert by["AAA"]["cfr"] is None and by["BBB"]["cfr"] is None   # never for COVID-19
    assert g["meta"]["reference_week"] == "2024-01-08"


def test_yearly_totals_are_sums_of_weeks(api: TestClient, covid):
    s = api.get(f"{V1}/annual/series", params={**COV, "area": "AAA"}).json()
    years = {p["year"]: p["values"] for p in s["points"]}
    assert set(years) == {2021, 2024}
    assert years[2021]["reported_cases"]["value"] == 1000
    assert (years[2024]["reported_cases"]["value"], years[2024]["reported_deaths"]["value"]) \
        == (240, 3)
    assert (s["meta"]["first_year"], s["meta"]["latest_year"], s["partial_year"]) \
        == (2021, 2024, 2024)
    assert set(s["measures"]) == {"reported_cases", "reported_deaths"}
    assert any("2023" in n for n in s["notes"])


def test_summary_serves_the_about_page(api: TestClient, covid):
    r = api.get(f"{V1}/annual/summary", params=COV)
    assert r.status_code == 200
    d = r.json()
    assert d["years"] == [2021, 2022, 2023, 2024]
    assert [s["key"] for s in d["meta"]["sources"]] == ["who_covid_dashboard"]



def test_analytics_trends_carry_cases_deaths_and_incidence(api: TestClient, covid):
    t = api.get(f"{V1}/analytics/trends", params={
        **COV, "series": "AAA", "granularity": "year", "from": "2021-01-04",
        "to": "2024-01-15"}).json()
    by = {b["label"]: b for b in t["series"][0]["buckets"]}
    assert (by["2021"]["cases"], by["2021"]["deaths"]) == (1000, 10)
    assert (by["2024"]["cases"], by["2024"]["deaths"]) == (240, 3)
    assert by["2024"]["positivity"] is None and by["2024"]["incidence"] is not None
    assert by["2024"]["cases_change_pct"] == pytest.approx(-76)
