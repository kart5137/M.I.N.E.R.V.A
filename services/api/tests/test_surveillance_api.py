"""Every expected number below is computed by hand from the table in conftest.py."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

V1 = "/api/v1"


def test_meta_block_uses_reference_and_provisional_weeks(api: TestClient):
    meta = api.get(f"{V1}/surveillance/global").json()["meta"]
    assert meta["first_week"] == "2024-01-01"
    assert meta["reference_week"] == "2024-02-12"  # W6: last non-provisional week
    assert meta["provisional_from"] == "2024-02-19"
    assert meta["latest_week"] == "2024-02-19"
    assert meta["demo"] is False
    assert [s["key"] for s in meta["sources"]] == ["flunet"]


def test_global_defaults_to_reference_week(api: TestClient):
    body = api.get(f"{V1}/surveillance/global").json()
    assert body["window"] == {"start": "2024-02-12", "end": "2024-02-12", "weeks": 1,
                              "includes_provisional": False}
    by = {c["iso3"]: c for c in body["countries"]}
    assert by["AAA"]["positivity"] == pytest.approx(0.70)
    assert by["AAA"]["tier"] == "A" and by["AAA"]["has_geometry"] is True
    assert by["BBB"]["positivity"] == pytest.approx(0.10) and by["BBB"]["tier"] is None
    # Positives without a test count: detections shown, positivity unknown, not "reported".
    assert by["CCC"] == {**by["CCC"], "positives": 4, "positivity": None,
                         "specimens_tested": None, "weeks_reported": 0, "has_geometry": False}


def test_global_window_pools_positivity_and_skips_invalid_weeks(api: TestClient):
    body = api.get(f"{V1}/surveillance/global", params={"to": "2024-01-25", "weeks": 2}).json()
    assert body["window"]["start"] == "2024-01-15"  # 'to' snapped to Monday 2024-01-22
    by = {c["iso3"]: c for c in body["countries"]}
    # BBB W3 has positives > tests: counted as detections, excluded from positivity.
    assert by["BBB"]["positives"] == 65
    assert by["BBB"]["positivity"] == pytest.approx(5 / 50)
    assert by["AAA"]["positivity"] == pytest.approx((30 + 40) / 200)


def test_global_region_filter(api: TestClient):
    body = api.get(f"{V1}/surveillance/global", params={"region": "eur"}).json()
    assert body["region"] == "EUR"
    assert {c["iso3"] for c in body["countries"]} == {"AAA", "BBB"}


def test_global_flags_provisional_window(api: TestClient):
    body = api.get(f"{V1}/surveillance/global", params={"to": "2024-02-19"}).json()
    assert body["window"]["includes_provisional"] is True
    assert {c["iso3"]: c["provisional_weeks"] for c in body["countries"]} == {"AAA": 1, "BBB": 1}


def test_overview_kpis_against_previous_window(api: TestClient):
    body = api.get(f"{V1}/overview", params={"weeks": 2}).json()
    assert body["window"]["start"] == "2024-02-05"
    assert body["previous_window"] == {"start": "2024-01-22", "end": "2024-01-29", "weeks": 2,
                                       "includes_provisional": False}
    k = body["kpis"]
    # Current W5–W6: 60+70 (AAA) + 5+5 (BBB) + 4 (CCC) ; previous W3–W4: 40+50+60+5+2+2
    assert k["detections"]["value"] == 144 and k["detections"]["previous"] == 159
    assert k["detections"]["change"] == pytest.approx((144 - 159) / 159 * 100)
    # Valid rows only: current 140/300, previous (90+5+4)/(200+50+40)
    assert k["positivity"]["value"] == pytest.approx(140 / 300)
    assert k["positivity"]["previous"] == pytest.approx(99 / 290)
    assert k["positivity"]["change"] == pytest.approx((140 / 300 - 99 / 290) * 100)
    assert k["countries_reporting"]["value"] == 2 and k["countries_reporting"]["previous"] == 3
    assert k["pending"] == [] and k["anomalies"] is None  # no detection run seeded


def test_overview_trend_is_complete_and_marks_provisional(api: TestClient):
    trend = api.get(f"{V1}/overview", params={"weeks": 2}).json()["trend"]
    assert [p["week_start"] for p in trend][0] == "2024-01-01"  # clipped to first week
    assert len(trend) == 8
    last = trend[-1]
    assert last["is_provisional"] is True and last["countries_reporting"] == 2
    assert last["positivity"] == pytest.approx((80 + 5) / 150)
    assert not any(p["is_provisional"] for p in trend[:-1])


def test_overview_movers_require_minimum_specimens(api: TestClient):
    movers = api.get(f"{V1}/overview", params={"weeks": 2}).json()["top_movers"]
    assert [m["iso3"] for m in movers] == ["AAA", "BBB"]  # CCC: no valid tests
    assert movers[0]["change_pp"] == pytest.approx((130 / 200 - 90 / 200) * 100)
    strict = api.get(f"{V1}/overview",
                     params={"weeks": 2, "movers_min_specimens": 101}).json()["top_movers"]
    assert [m["iso3"] for m in strict] == ["AAA"]


def test_country_profile(api: TestClient):
    body = api.get(f"{V1}/countries/aaa").json()
    assert body["iso3"] == "AAA" and body["has_geometry"] is True
    assert body["population"] == {"year": 2023, "value": 1000, "source": "World Bank WDI"}
    assert body["coverage"]["tier"] == "A"
    assert body["surveillance"] == {"first_week": "2024-01-01",
                                    "last_reported_week": "2024-02-19", "weeks_reported": 8}
    ccc = api.get(f"{V1}/countries/CCC").json()
    assert ccc["population"] is None and ccc["coverage"] is None  # shown as "not available"


def test_timeseries_marks_gaps_instead_of_zero_filling(api: TestClient):
    body = api.get(f"{V1}/countries/CCC/timeseries",
                   params={"from": "2024-01-29", "to": "2024-02-25"}).json()
    pts = {p["week_start"]: p for p in body["points"]}
    assert list(pts) == ["2024-01-29", "2024-02-05", "2024-02-12", "2024-02-19"]
    assert pts["2024-01-29"]["reported"] is True
    assert pts["2024-02-05"]["reported"] is False  # 0 tests: no surveillance
    assert pts["2024-02-12"]["positives"] == 4 and pts["2024-02-12"]["reported"] is False
    assert pts["2024-02-19"] == {"week_start": "2024-02-19", "reported": False,
                                 "specimens_tested": None, "positives": None,
                                 "positivity": None, "is_provisional": True}


def test_country_list_search_and_pagination(api: TestClient):
    body = api.get(f"{V1}/countries", params={"page_size": 2}).json()
    assert body["total"] == 3 and [c["iso3"] for c in body["items"]] == ["AAA", "BBB"]
    page2 = api.get(f"{V1}/countries", params={"page_size": 2, "page": 2}).json()
    assert [c["iso3"] for c in page2["items"]] == ["CCC"]
    assert [c["iso3"] for c in api.get(f"{V1}/countries", params={"q": "rav"}).json()["items"]] \
        == ["BBB"]
    assert api.get(f"{V1}/countries", params={"region": "AFR"}).json()["total"] == 1


@pytest.mark.parametrize(("url", "status", "code"), [
    ("/overview?disease=measles", 404, "unknown_disease"),
    ("/overview?disease=dengue", 404, "no_data"),
    ("/overview?region=XYZ", 422, "invalid_region"),
    ("/overview?to=2023-12-01", 422, "out_of_range"),
    ("/countries/ZZZ", 404, "unknown_country"),
    ("/countries/AAA/timeseries?from=2024-02-01&to=2024-01-01", 422, "invalid_range"),
])
def test_errors(api: TestClient, url: str, status: int, code: str):
    r = api.get(V1 + url)
    assert r.status_code == status
    assert r.json()["error"]["code"] == code


def test_diseases(api: TestClient):
    assert [d["key"] for d in api.get(f"{V1}/diseases").json()] == ["dengue", "influenza"]
