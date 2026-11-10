"""Case-based disease (dengue) endpoints against the hand-checkable dataset in conftest.py.

Weeks W0..W7 start 2024-01-01; W7 is provisional, so the reference week is W6
(2024-02-12). A 4-week window ends at W6: W3..W6 (2024-01-22 .. 2024-02-12); the previous
window is 2023-12-25 .. 2024-01-15 (data only from W0).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

V1 = "/api/v1"
D = {"disease": "dengue"}


def test_overview_kpis_use_weekly_reports_only(api: TestClient):
    body = api.get(f"{V1}/overview", params={**D, "weeks": 4}).json()
    assert body["window"] == {"start": "2024-01-22", "end": "2024-02-12", "weeks": 4,
                              "includes_provisional": False}
    k = body["kpis"]
    assert k["detections"] is None and k["positivity"] is None
    # AAA 4+5+6+7 and BBB 4×5; CCC's monthly reports are not added to weekly totals.
    assert k["cases"]["value"] == 42 and k["cases"]["previous"] == 16  # AAA 1+2+3, BBB 2×5
    assert k["cases"]["change"] == pytest.approx(162.5)
    # Incidence pools countries with population (AAA): 22 / (1000 × 4 weeks) × 100,000.
    assert k["incidence"]["value"] == pytest.approx(550)
    assert k["incidence"]["previous"] == pytest.approx(200)  # 6 / (1000 × 3) × 100,000
    assert k["countries_reporting"]["value"] == 3  # AAA, BBB weekly + CCC monthly
    assert k["countries_reporting"]["note"] == "2 weekly, 1 monthly reporters"
    assert k["anomalies"] is None and k["hotspots"] is None

    last = body["trend"][-1]
    assert last["week_start"] == "2024-02-19" and last["is_provisional"] is True
    assert (last["cases"], last["countries_reporting"]) == (8, 1)
    assert last["incidence"] == pytest.approx(800)
    w2 = next(p for p in body["trend"] if p["week_start"] == "2024-01-15")
    assert (w2["cases"], w2["countries_reporting"]) == (3, 1)  # BBB missing, not zero


def test_movers_rank_relative_incidence_change_with_a_case_floor(api: TestClient):
    none = api.get(f"{V1}/overview", params={**D, "weeks": 4}).json()
    assert none["top_movers"] == [] and none["movers_min_cases"] == 50
    body = api.get(f"{V1}/overview", params={**D, "weeks": 4, "movers_min_cases": 5}).json()
    # BBB has no population, so no incidence: only AAA can be ranked.
    [m] = body["top_movers"]
    assert m["iso3"] == "AAA" and m["cases"] == 22
    assert m["incidence"] == pytest.approx(550) and m["previous_incidence"] == pytest.approx(200)
    assert m["change_pct"] == pytest.approx(175)
    assert m["positivity"] is None


def test_map_values_pick_one_grain_per_country(api: TestClient):
    body = api.get(f"{V1}/surveillance/global", params={**D, "weeks": 4}).json()
    by = {c["iso3"]: c for c in body["countries"]}
    aaa, bbb, ccc = by["AAA"], by["BBB"], by["CCC"]
    # AAA has weekly reports in the window: its monthly Jan row is not added.
    assert (aaa["grain"], aaa["cases"], aaa["periods_reported"]) == ("week", 22, 4)
    assert aaa["incidence"] == pytest.approx(550) and aaa["population"] == 1000
    assert (aaa["period_start"], aaa["period_end"]) == ("2024-01-22", "2024-02-18")
    assert aaa["tier"] == "A" and aaa["positivity"] is None
    assert bbb["incidence"] is None and bbb["cases"] == 20
    # CCC reports monthly: the months overlapping the window (Jan, Feb).
    assert (ccc["grain"], ccc["cases"], ccc["periods_reported"]) == ("month", 91, 2)
    assert (ccc["period_start"], ccc["period_end"]) == ("2024-01-01", "2024-02-29")
    assert ccc["weeks_reported"] == 0 and ccc["provisional_weeks"] == 1
    assert ccc["tier"] == "C"


def test_country_list_and_profile(api: TestClient):
    body = api.get(f"{V1}/countries",
                   params={**D, "sort": "incidence", "order": "desc"}).json()
    items = body["items"]
    assert [i["iso3"] for i in items] == ["AAA", "BBB", "CCC"]  # missing incidence last
    ccc = items[2]
    assert ccc["grain"] == "month" and ccc["last_reported_month"] == "2024-02-01"
    assert ccc["last_reported_week"] is None and ccc["weeks_reported"] == 0
    by_cases = api.get(f"{V1}/countries", params={**D, "sort": "cases", "order": "desc"})
    assert [i["iso3"] for i in by_cases.json()["items"]] == ["CCC", "AAA", "BBB"]

    profile = api.get(f"{V1}/countries/CCC", params=D).json()
    assert profile["coverage"]["grain"] == "month"
    assert profile["surveillance"] == {
        "first_week": None, "last_reported_week": None, "weeks_reported": 0,
        "first_month": "2024-01-01", "last_reported_month": "2024-02-01",
        "months_reported": 2}
    assert profile["recent"]["cases"] == 91
    assert profile["meta"]["sources"][0]["key"] == "who_dengue"


def test_timeseries_has_weekly_gaps_and_monthly_reports(api: TestClient):
    body = api.get(f"{V1}/countries/AAA/timeseries",
                   params={**D, "from": "2024-01-01", "to": "2024-02-19"}).json()
    pts = {p["week_start"]: p for p in body["points"]}
    assert pts["2024-01-01"]["cases"] == 1 and pts["2024-01-01"]["incidence"] == 100
    assert pts["2024-02-19"]["is_provisional"] is True
    [jan] = body["monthly"]
    # 310 cases over 31 days = 70/week; per 1,000 people = 7,000 per 100,000.
    assert jan["month_start"] == "2024-01-01" and jan["incidence"] == pytest.approx(7000)

    bbb = api.get(f"{V1}/countries/BBB/timeseries",
                  params={**D, "from": "2024-01-01", "to": "2024-02-19"}).json()
    gap = next(p for p in bbb["points"] if p["week_start"] == "2024-01-15")
    assert gap["reported"] is False and gap["cases"] is None  # a gap, not zero


def test_seasons_not_available_for_dengue(api: TestClient):
    body = api.get(f"{V1}/countries/AAA/seasons", params=D).json()
    assert body["seasons"] == [] and "not available for Dengue" in body["season_rule"]


def test_influenza_responses_unchanged_by_dengue_rows(api: TestClient):
    k = api.get(f"{V1}/overview", params={"weeks": 4}).json()["kpis"]
    assert k["cases"] is None and k["detections"]["value"] is not None
    about = api.get(f"{V1}/about").json()
    dengue = next(s for s in about["sources"] if s["key"] == "who_dengue")
    assert dengue["stored_rows"] == 8 + 6 + 3  # weekly AAA, BBB + monthly rows
