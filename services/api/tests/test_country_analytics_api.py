"""M4 endpoints. Expected numbers are computed by hand from the table in conftest.py.

Reference week is W6 (2024-02-12); the "recent" window is W3–W6.
"""

from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.queries import countries as country_queries
from app.queries.seasons import season_bounds, season_of

V1 = "/api/v1"


# ---------- seasons (pure functions) ----------

def test_season_of_northern_hemisphere():
    assert season_of(date(2024, 1, 1), "NH") == (2023, "2023/24", date(2023, 10, 2))
    assert season_of(date(2023, 10, 2), "NH")[1] == "2023/24"  # ISO week 40
    assert season_of(date(2023, 9, 25), "NH")[1] == "2022/23"  # ISO week 39


def test_season_of_calendar_types():
    assert season_of(date(2024, 1, 1), "SH") == (2024, "2024", date(2024, 1, 1))
    assert season_of(date(2021, 1, 1), "YR")[1] == "2020"  # ISO week 53 of 2020


def test_season_bounds_follow_iso_years():
    start, end = season_bounds(2020, "NH")  # ISO 2020 has 53 weeks
    assert (start, end) == (date(2020, 9, 28), date(2021, 9, 27))
    assert (end - start).days // 7 + 1 == 53


# ---------- profile ----------

def test_profile_health_lists_every_indicator_with_latest_value(api: TestClient):
    body = api.get(f"{V1}/countries/AAA").json()
    assert body["flu_season"] == "NH"
    health = {h["code"]: h for h in body["health"]}
    assert len(health) == 5
    assert health["SH.MED.BEDS.ZS"] == {
        "code": "SH.MED.BEDS.ZS", "label": "Hospital beds", "unit": "per 1,000 people",
        "group": "health_system", "value": 3.0, "year": 2022, "source": "World Bank WDI"}
    assert health["SH.MED.PHYS.ZS"]["value"] is None  # shown as "Not available"


def test_profile_recent_window(api: TestClient):
    body = api.get(f"{V1}/countries/AAA").json()
    assert body["recent_window"]["start"] == "2024-01-22"
    assert body["recent"]["positives"] == 40 + 50 + 60 + 70
    assert body["recent"]["positivity"] == pytest.approx(220 / 400)


# ---------- seasons endpoint ----------

def test_nh_season_aligned_from_week_40(api: TestClient):
    body = api.get(f"{V1}/countries/AAA/seasons").json()
    assert body["season_type"] == "NH"
    (s,) = body["seasons"]
    assert (s["label"], s["start"], s["is_current"], s["covid_disrupted"]) == \
        ("2023/24", "2023-10-02", True, False)
    # 2023-10-02 .. latest week 2024-02-19 on a complete calendar
    assert len(s["points"]) == 21
    assert s["points"][0]["reported"] is False and s["points"][13]["week_start"] == "2024-01-01"
    assert s["weeks_reported"] == 8
    # Peak excludes the provisional W7 (80%): settled peak is W6, 70%.
    assert (s["peak_positivity"], s["peak_week"]) == (pytest.approx(0.7), "2024-02-12")


def test_calendar_season_and_peak_minimum(api: TestClient):
    (s,) = api.get(f"{V1}/countries/CCC/seasons").json()["seasons"]
    assert s["label"] == "2024" and len(s["points"]) == 8
    assert s["peak_positivity"] == pytest.approx(0.1)  # 20 specimens ≥ minimum of 10


# ---------- list ----------

def test_list_sorted_by_positivity_with_ties_by_name(api: TestClient):
    body = api.get(f"{V1}/countries", params={"sort": "positivity", "order": "desc"}).json()
    # AAA 220/400; BBB (5+5+5)/150 = 0.1; CCC 4/40 = 0.1 → tie broken by name
    assert [i["iso3"] for i in body["items"]] == ["AAA", "BBB", "CCC"]
    assert body["window"]["end"] == "2024-02-12"


def test_list_does_not_rank_rates_from_few_specimens(api: TestClient, monkeypatch):
    monkeypatch.setattr(country_queries, "MIN_SPECIMENS_FOR_RATE", 300)
    body = api.get(f"{V1}/countries", params={"sort": "positivity", "order": "desc"}).json()
    # Only AAA (400 specimens) is ranked; the rest follow alphabetically.
    assert [i["iso3"] for i in body["items"]] == ["AAA", "BBB", "CCC"]
    asc = api.get(f"{V1}/countries", params={"sort": "positivity", "order": "asc"}).json()
    assert [i["iso3"] for i in asc["items"]] == ["AAA", "BBB", "CCC"]


def test_list_sort_by_specimens(api: TestClient):
    body = api.get(f"{V1}/countries", params={"sort": "specimens_tested"}).json()
    assert [i["iso3"] for i in body["items"]] == ["CCC", "BBB", "AAA"]  # 40, 200, 400


# ---------- analytics ----------

def test_monthly_trends_per_series(api: TestClient):
    body = api.get(f"{V1}/analytics/trends", params={
        "series": "AAA,region:EUR,world", "granularity": "month"}).json()
    assert body["start"] == "2024-01-01" and body["end"] == "2024-02-19"
    aaa, eur, world = body["series"]
    assert [b["label"] for b in aaa["buckets"]] == ["2024-01", "2024-02"]
    jan, feb = aaa["buckets"]
    assert (jan["positives"], jan["positivity"]) == (100, pytest.approx(0.25))
    assert feb["positivity"] == pytest.approx(0.65)
    assert feb["positivity_change_pp"] == pytest.approx(40)
    assert feb["positives_change_pct"] == pytest.approx(160)
    assert jan["share_a"] == pytest.approx(0.6) and jan["inf_a"] == 60
    assert (jan["partial"], feb["partial"]) == (False, True)
    assert eur["label"] == "Europe" and eur["kind"] == "region"
    assert eur["buckets"][0]["positivity"] == pytest.approx(115 / 550)
    assert eur["buckets"][0]["share_a"] == pytest.approx(0.6)  # only AAA rows are typed
    assert world["buckets"][0]["positivity"] == pytest.approx(123 / 630)
    assert world["buckets"][0]["countries_reporting"] == 3


def test_yearly_trend_is_partial(api: TestClient):
    body = api.get(f"{V1}/analytics/trends",
                   params={"series": "world", "granularity": "year"}).json()
    (b,) = body["series"][0]["buckets"]
    assert (b["label"], b["weeks"], b["partial"]) == ("2024", 8, True)


def test_heatmap(api: TestClient):
    body = api.get(f"{V1}/analytics/heatmap", params={"series": "AAA"}).json()
    assert body["years"] == [2024] and body["label"] == "Alpha"
    cells = {c["iso_week"]: c for c in body["cells"]}
    assert cells[1]["positivity"] == pytest.approx(0.1)
    assert cells[8]["is_provisional"] is True and cells[7]["is_provisional"] is False


@pytest.mark.parametrize(("url", "code"), [
    ("/analytics/trends?series=ZZZ", "invalid_series"),
    ("/analytics/trends?series=region:XYZ", "invalid_series"),
    ("/analytics/trends?series=AAA,AAA", "invalid_series"),
    ("/analytics/trends?series=AAA,BBB,CCC,world,region:EUR,region:AFR,region:AMR",
     "invalid_series"),
    ("/analytics/heatmap?series=AAA,BBB", "invalid_series"),
    ("/analytics/trends?series=AAA&granularity=day", "invalid_parameter"),
    ("/countries?sort=bogus", "invalid_parameter"),
])
def test_errors(api: TestClient, url: str, code: str):
    r = api.get(V1 + url)
    assert r.status_code == 422
    assert r.json()["error"]["code"] == code
