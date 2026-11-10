"""Weather (D3): Open-Meteo parsing and pacing, daily checks, ISO-week aggregation,
lagged features and the resumable database load."""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest
from sqlalchemy import text

from ei_pipeline import weather
from ei_pipeline.catalog import seed_reference
from ei_pipeline.db import session_scope
from ei_pipeline.ingest import weather as ingest
from ei_pipeline.sources import open_meteo


def payload(start: date, values: list[tuple], lat=1.5, lon=2.5) -> dict:
    days = [(start + timedelta(days=i)).isoformat() for i in range(len(values))]
    return {"latitude": lat, "longitude": lon, "elevation": 120.0, "daily": {
        "time": days,
        "temperature_2m_mean": [v[0] for v in values],
        "precipitation_sum": [v[1] for v in values],
        "relative_humidity_2m_mean": [v[2] for v in values],
    }}


def test_parse_turns_nulls_into_gaps():
    s = open_meteo.parse(payload(date(2024, 1, 1), [(20.0, 1.0, 80), (None, 2.0, None)]))
    assert (s.lat, s.lon, s.elevation_m) == (1.5, 2.5, 120.0)
    assert list(s.daily.columns) == ["date", "temperature", "precipitation", "humidity"]
    assert s.daily["temperature"].isna().tolist() == [False, True]
    assert s.daily["precipitation"].tolist() == [1.0, 2.0]


def test_parse_rejects_a_response_without_the_variables():
    with pytest.raises(ValueError, match="lacks"):
        open_meteo.parse({"error": True, "reason": "bad"})


def test_request_weight_follows_the_api_rule():
    d = date(2024, 1, 1)
    assert open_meteo.weight(d, d) == 1.0
    assert open_meteo.weight(d, d + timedelta(days=13)) == 1.0
    assert open_meteo.weight(d, d + timedelta(days=363)) == 26.0


class Clock:
    def __init__(self):
        self.t, self.slept = 0.0, []

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.slept.append(s)
        self.t += s


def test_quota_paces_minutes_and_stops_at_the_hour_or_budget():
    c = Clock()
    q = open_meteo.Quota(budget=10_000, per_minute=50, per_hour=120, clock=c, sleep=c.sleep)
    q.take(26)
    q.take(20)
    q.take(26)  # would exceed 50 in the minute: waits until the first call ages out
    assert c.slept and c.slept[0] == pytest.approx(60.5)
    c.t += 61
    q.take(26)
    c.t += 61
    with pytest.raises(open_meteo.QuotaExhausted, match="hourly"):
        q.take(26)  # 98 + 26 > 120 within the hour
    small = open_meteo.Quota(budget=30, clock=c, sleep=c.sleep)
    small.take(26)
    with pytest.raises(open_meteo.QuotaExhausted, match="budget"):
        small.take(26)
    assert small.used == 26
    timed = open_meteo.Quota(budget=1000, max_seconds=100, clock=c, sleep=c.sleep)
    timed.take(1)
    c.t += 101
    with pytest.raises(open_meteo.QuotaExhausted, match="time limit"):
        timed.take(1)


def test_chunks_are_week_aligned_and_cover_the_range():
    start, end = date(2013, 1, 7), date(2015, 3, 3)
    ch = ingest._chunks(start, end)
    assert ch[0] == (start, start + timedelta(days=363))
    assert all(a.weekday() == 0 for a, _ in ch)
    assert all((b - a).days + 1 <= open_meteo.MAX_DAYS for a, b in ch)
    assert ch[-1][1] == end
    assert all(ch[i][1] + timedelta(days=1) == ch[i + 1][0] for i in range(len(ch) - 1))


def test_check_daily_blanks_and_counts_implausible_values():
    daily = pd.DataFrame({"date": pd.date_range("2024-01-01", periods=3),
                          "temperature": [20.0, 75.0, np.nan],
                          "precipitation": [0.0, -1.0, 3.0],
                          "humidity": [50.0, 101.0, 60.0]})
    out, rep = weather.check_daily(daily)
    assert rep.days == 3
    assert rep.implausible == {"temperature": 1, "precipitation": 1, "humidity": 1}
    assert rep.missing == {"temperature": 2, "precipitation": 1, "humidity": 1}
    assert out.loc[1, ["temperature", "precipitation", "humidity"]].isna().all()


def test_to_weeks_keeps_only_complete_monday_weeks():
    # 2024-01-01 is a Monday. Week 1 complete; week 2 misses one humidity value;
    # week 3 has only 3 days (the current, unfinished week).
    days = pd.date_range("2024-01-01", periods=17)
    daily = pd.DataFrame({"date": days, "temperature": np.arange(17, dtype=float),
                          "precipitation": 1.5, "humidity": 70.0})
    daily.loc[9, "humidity"] = np.nan
    weeks, dropped = weather.to_weeks(daily)
    assert dropped == 2
    assert weeks["week_start"].tolist() == [pd.Timestamp("2024-01-01")]
    w = weeks.iloc[0]
    assert (w.iso_year, w.iso_week) == (2024, 1)
    assert w.temperature == pytest.approx(3.0)        # mean of 0..6
    assert w.precipitation == pytest.approx(10.5)     # 7 × 1.5
    assert w.humidity == pytest.approx(70.0)


def test_to_weeks_of_nothing():
    empty = pd.DataFrame(columns=["date", *weather.VARIABLES]).astype({"date": "datetime64[ns]"})
    weeks, dropped = weather.to_weeks(empty)
    assert weeks.empty and dropped == 0


def test_lagged_features_use_past_weeks_and_respect_gaps():
    starts = pd.date_range("2024-01-01", periods=10, freq="W-MON")
    w = pd.DataFrame({"iso3": "AAA", "week_start": starts, "temperature": np.arange(10.0),
                      "precipitation": 2.0, "humidity": 60.0})
    w = w[w.week_start != starts[7]]  # one missing week
    f = weather.lagged_features(w, window=2, lags=(1,)).set_index("week_start")
    # Week 3: mean of weeks 1–2 (lag 1, window 2) = (1 + 2) / 2.
    assert f.loc[starts[3], "temperature_mean2_lag1"] == pytest.approx(1.5)
    assert f.loc[starts[3], "precipitation_sum2_lag1"] == pytest.approx(4.0)
    # Too little history, and windows touching the missing week, are gaps.
    assert np.isnan(f.loc[starts[1], "temperature_mean2_lag1"])
    assert np.isnan(f.loc[starts[8], "temperature_mean2_lag1"])
    assert np.isnan(f.loc[starts[9], "temperature_mean2_lag1"])
    assert len(f) == 10  # the calendar is complete, including the missing week
    assert weather.lagged_features(w.iloc[0:0]).empty


def _seed_areas(db):
    with session_scope(db) as s:
        seed_reference(s)
        s.execute(text("""
            INSERT INTO countries (iso3, name, centroid) VALUES
              ('AAA', 'Alpha', ST_SetSRID(ST_MakePoint(10, 5), 4326)),
              ('CCC', 'Gamma', ST_SetSRID(ST_MakePoint(20, 6), 4326)),
              ('REU', 'Réunion', NULL), ('ZZZ', 'Nowhere', NULL),
              ('BBB', 'Beta (no dengue)', ST_SetSRID(ST_MakePoint(1, 1), 4326))"""))
        s.execute(text("""
            INSERT INTO ingestion_runs (source_id, status)
            SELECT id, 'succeeded' FROM data_sources WHERE key = 'who_dengue'"""))
        s.execute(text("""
            INSERT INTO surveillance_weekly (disease_id, iso3, week_start, iso_year, iso_week,
                                             cases, source_id, ingestion_run_id)
            SELECT d.id, a.iso3, DATE '2024-01-01', 2024, 1, 5, ds.id, 1
            FROM diseases d, data_sources ds, (VALUES ('AAA'), ('CCC'), ('ZZZ')) a(iso3)
            WHERE d.key = 'dengue' AND ds.key = 'who_dengue'"""))
        s.execute(text("""
            INSERT INTO surveillance_monthly (disease_id, iso3, month_start, cases, source_id,
                                              ingestion_run_id)
            SELECT d.id, 'REU', DATE '2024-01-01', 9, ds.id, 1
            FROM diseases d, data_sources ds WHERE d.key = 'dengue' AND ds.key = 'who_dengue'"""))
        # CCC is forecast-ready (tier A), so it is loaded first.
        s.execute(text("""
            INSERT INTO coverage_profiles (disease_id, iso3, reference_week, tier, grain,
                                           completeness, longest_gap)
            SELECT d.id, x.iso3, DATE '2024-01-01', x.tier, 'week', 1, 0
            FROM diseases d, (VALUES ('AAA', 'C'), ('CCC', 'A')) x(iso3, tier)
            WHERE d.key = 'dengue'"""))


class FakeApi:
    """ERA5-like daily values that depend on the date only; records each request and
    can fail for some latitudes or run out of quota after a number of requests."""

    def __init__(self, fail=frozenset(), bump=0.0, quota_after=None):
        self.calls: list[tuple[float, float, date, date]] = []
        self.fail, self.bump, self.quota_after = fail, bump, quota_after

    def __call__(self, lat, lon, start, end, *, quota):
        if self.quota_after is not None and len(self.calls) >= self.quota_after:
            raise open_meteo.QuotaExhausted("Daily API request limit exceeded")
        self.calls.append((lat, lon, start, end))
        quota.take(open_meteo.weight(start, end))
        if lat in self.fail:
            raise ConnectionError("down")
        n = (end - start).days + 1
        vals = [(25.0 + self.bump + (start + timedelta(days=i)).weekday(), 2.0, 80.0)
                for i in range(n)]
        return open_meteo.parse(payload(start, vals, lat=lat, lon=lon))


def _q(db, sql):
    with db.connect() as c:
        return c.execute(text(sql)).scalar()


TODAY = date(2015, 3, 5)  # Thursday: data to Wednesday 4 March 2015
WEEKS = (date(2015, 3, 2) - ingest.HISTORY_START).days // 7  # complete weeks available
CALLS = sum(open_meteo.weight(a, b)
            for a, b in ingest._chunks(ingest.HISTORY_START, TODAY - timedelta(days=1)))


def test_weather_ingest_full_then_incremental(db):
    _seed_areas(db)
    api = FakeApi()
    first = ingest.ingest_weather(db, today=TODAY, fetch=api)

    # CCC (tier A) first; then AAA and REU; ZZZ has no point; BBB has no dengue.
    assert [c[0] for c in api.calls[:2]] == [6.0, 6.0]
    assert (first["areas"], first["areas_planned"]) == (4, 3)
    assert first["areas_skipped_no_point"] == ["ZZZ"]
    assert (first["areas_updated"], first["areas_still_behind"]) == (3, 0)
    assert first["inserted"] == 3 * WEEKS
    assert first["incomplete_weeks_dropped"] == 3
    assert first["weighted_calls"] == pytest.approx(3 * CALLS, abs=0.1)
    assert first["latest_week"] == "2015-02-23"
    assert _q(db, "SELECT temperature FROM weather_weekly WHERE iso3 = 'AAA' LIMIT 1") == 28.0
    assert _q(db, "SELECT precipitation FROM weather_weekly WHERE iso3 = 'AAA' LIMIT 1") == 14.0
    assert _q(db, "SELECT basis FROM weather_points WHERE iso3 = 'REU'") == "main_town"
    assert _q(db, "SELECT basis FROM weather_points WHERE iso3 = 'AAA'") == "label_point"

    # Complete areas: only the revisit window is fetched; unchanged values stay put.
    api2 = FakeApi()
    second = ingest.ingest_weather(db, today=TODAY, fetch=api2)
    revisit = date(2015, 3, 2) - timedelta(weeks=ingest.REVISIT_WEEKS)
    assert {c[2] for c in api2.calls} == {revisit}
    assert (second["inserted"], second["updated"]) == (0, 0)
    assert ingest.ingest_weather(db, today=TODAY, fetch=FakeApi(),
                                 backfill_only=True)["areas_planned"] == 0

    # ERA5 revises its preliminary days: recent weeks are updated in place.
    third = ingest.ingest_weather(db, today=TODAY, fetch=FakeApi(bump=0.5))
    assert third["updated"] == 3 * ingest.REVISIT_WEEKS


def test_weather_ingest_resumes_after_the_quota_runs_out(db):
    _seed_areas(db)
    # One request (CCC's first 52 weeks), then the daily limit is reached.
    first = ingest.ingest_weather(db, today=TODAY, fetch=FakeApi(quota_after=1))
    assert first["stopped_early"] == "Daily API request limit exceeded"
    assert first["inserted"] == 52 and first["areas_still_behind"] == 3
    assert _q(db, "SELECT status FROM ingestion_runs ORDER BY id DESC LIMIT 1") == "succeeded"

    api = FakeApi()
    second = ingest.ingest_weather(db, today=TODAY, fetch=api, backfill_only=True)
    # CCC continues from its first missing week; the others start from scratch.
    assert api.calls[0][2] == ingest.HISTORY_START + timedelta(weeks=52)
    assert second["areas_still_behind"] == 0
    assert _q(db, "SELECT count(*) FROM weather_weekly") == 3 * WEEKS


def test_weather_ingest_survives_one_failed_area_but_not_all(db):
    _seed_areas(db)
    reu_lat = ingest.MAIN_TOWNS["REU"][0]
    rep = ingest.ingest_weather(db, today=TODAY, fetch=FakeApi(fail={reu_lat}))
    assert list(rep["areas_failed"]) == ["REU"]
    assert _q(db, "SELECT count(DISTINCT iso3) FROM weather_weekly") == 2

    with pytest.raises(RuntimeError, match="Every weather request failed"):
        ingest.ingest_weather(db, today=TODAY, refresh=True,
                              fetch=FakeApi(fail={reu_lat, 5.0, 6.0}))
    assert _q(db, "SELECT status FROM ingestion_runs ORDER BY id DESC LIMIT 1") == "failed"
