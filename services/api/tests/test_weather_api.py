"""Weather endpoint (D3) against the hand-checkable rows in conftest.py."""

from __future__ import annotations

from fastapi.testclient import TestClient

V1 = "/api/v1"


def test_latest_weeks_with_normals(api: TestClient):
    body = api.get(f"{V1}/countries/aaa/weather", params={"weeks": 2}).json()
    assert body["iso3"] == "AAA"
    assert body["point"] == {"lat": 0.5, "lon": 0.5, "basis": "label_point", "elevation_m": 12}
    assert body["source"]["key"] == "open_meteo_era5"
    assert body["baseline_years"] == [2013, 2022]
    assert (body["first_week"], body["latest_week"]) == ("2013-01-07", "2024-01-08")
    assert body["loading"] is False
    # Two weeks to the latest: 2024-01-01 has no row, 2024-01-08 does.
    assert body["weeks"] == [{
        "week_start": "2024-01-08", "temperature": 15.0, "precipitation": 7.0,
        "humidity": 75.0, "temperature_normal": 12.0, "precipitation_normal": 10.0,
        "humidity_normal": 75.0,
    }]


def test_week_53_shares_the_week_52_normal(api: TestClient):
    body = api.get(f"{V1}/countries/AAA/weather",
                   params={"from": "2015-12-23", "to": "2021-01-01"}).json()
    # `from` is moved to its Monday (2015-12-21).
    assert [w["week_start"] for w in body["weeks"]] == ["2015-12-21", "2020-12-28"]
    assert {w["temperature_normal"] for w in body["weeks"]} == {25.0}
    assert {w["precipitation_normal"] for w in body["weeks"]} == {20.0}


def test_area_without_weather_and_errors(api: TestClient):
    body = api.get(f"{V1}/countries/BBB/weather").json()
    assert body["point"] is None and body["weeks"] == [] and body["latest_week"] is None
    assert body["loading"] is True  # no weather stored yet
    assert api.get(f"{V1}/countries/XXX/weather").status_code == 404
    bad = api.get(f"{V1}/countries/AAA/weather", params={"from": "2020-01-01", "to": "2019-01-01"})
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "invalid_range"
    assert api.get(f"{V1}/countries/AAA/weather", params={"weeks": 0}).status_code == 422
