"""WHO dengue: cleaning rules, validation, coverage tiers and database ingestion."""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
from sqlalchemy import text

from ei_pipeline.catalog import seed_reference
from ei_pipeline.db import session_scope
from ei_pipeline.ingest.dengue import ingest_dengue
from ei_pipeline.quality.coverage import analyse_dengue, assign_dengue_tier
from ei_pipeline.quality.validation import validate_monthly, validate_weekly
from ei_pipeline.sources import dengue

TODAY = date(2026, 11, 10)


def row(iso3, date_type, year, num, start, cases, **extra):
    return {"COUNTRY": extra.pop("name", iso3), "ISO3": iso3,
            "WHO_REGION": extra.pop("region", "AMR"), "YEAR": year, "DATE_NUM": num,
            "START_DATE": start, "DATE_TYPE": date_type, "CASES": cases,
            "CONFIRMED_CASES": extra.get("confirmed"), "SEVERE_CASES": extra.get("severe"),
            "DEATHS": extra.get("deaths"), "SERO_1": extra.get("s1"), "SERO_2": extra.get("s2"),
            "SERO_3": None, "SERO_4": None, "POPULATION": None}


def test_epiweek_start_matches_cdc_calendar():
    # MMWR week 1 of 2024 began Sun 31 Dec 2023; of 2026, Sun 4 Jan 2026.
    assert dengue.epiweek_start(2024, 1) == date(2023, 12, 31)
    assert dengue.epiweek_start(2026, 1) == date(2026, 1, 4)
    assert dengue.epiweek_start(2014, 53) == date(2014, 12, 28)  # a 53-week epi year


def test_clean_maps_grains_and_counts_every_action():
    raw = pd.DataFrame([
        # Epi-week (Sunday) -> the ISO week starting the next day.
        row("BRA", "epiweek", 2026, 10, "2026-03-01", 120, confirmed=40, deaths=-3, s1="TRUE",
            s2="FALSE"),
        # ISO week with its start date missing: rebuilt from YEAR/DATE_NUM.
        row("SGP", "isoweek", 2025, 52, None, 80),
        # Same Monday reported both ways: the ISO week wins.
        row("SGP", "epiweek", 2025, 52, "2025-12-21", 999),
        # Monthly report with no start date: rebuilt; stays monthly.
        row("AUS", "month", 2009, 3, None, 277),
        # Impossible period label (2024 has 52 ISO weeks): unrecoverable, dropped.
        row("SDN", "isoweek", 2024, 53, None, 5),
        # Empty future placeholder: not a report.
        row("VCT", "epiweek", 2026, 50, "2026-12-13", None),
    ])
    c = dengue.clean(raw, today=TODAY)
    r = c.report
    assert (r.start_date_rebuilt, r.start_date_unrecoverable) == (2, 1)
    assert (r.no_case_value_dropped, r.no_case_value_future_placeholders) == (1, 1)
    assert r.overlapping_epi_iso_weeks_dropped == 1
    assert r.negative_extra_values_cleared["deaths"] == 1
    assert (r.weekly_rows, r.monthly_rows) == (2, 1)

    bra = c.weekly.set_index("country_code").loc["BRA"]
    assert bra["week_start"] == pd.Timestamp("2026-03-02")  # Monday
    assert (bra["iso_year"], bra["iso_week"]) == (2026, 10)
    assert bra["breakdown"] == '{"confirmed": 40.0, "serotypes": [1]}'  # negative deaths cleared

    sgp = c.weekly.set_index("country_code").loc["SGP"]
    assert sgp["cases"] == 80 and sgp["date_type"] == "isoweek"
    assert c.monthly["month_start"].tolist() == [pd.Timestamp("2009-03-01")]


def test_validation_excludes_negative_and_future_rows():
    raw = pd.DataFrame([
        row("DOM", "epiweek", 2023, 49, "2023-12-03", -4150),
        row("MYS", "epiweek", 2029, 23, "2029-06-03", 2732),
        row("MYS", "epiweek", 2026, 23, "2026-05-31", 900, confirmed=950),
        row("IND", "month", 2026, 9, "2026-09-01", 0),
    ])
    c = dengue.clean(raw, today=TODAY)
    weekly, rep = validate_weekly(c.weekly, today=TODAY, count_cols=("cases",),
                                  soft=dengue.soft_checks(c.weekly))
    assert rep["hard"]["negative_counts"]["rows"] == 1
    assert rep["hard"]["week_in_future"]["rows"] == 1
    assert rep["soft"]["confirmed_exceed_cases"] == 1
    assert weekly["country_code"].tolist() == ["MYS"]
    monthly, mrep = validate_monthly(c.monthly, today=TODAY, soft=dengue.soft_checks(c.monthly))
    assert len(monthly) == 1 and mrep["soft"]["zero_case_periods"] == 1


def test_dengue_tiers():
    assert assign_dengue_tier("week", 0.9, 4, 2, 140) == "A"
    assert assign_dengue_tier("week", 0.9, 12, 2, 140) == "B"   # long gap
    assert assign_dengue_tier("week", 0.7, 4, 30, 100) == "C"   # stale
    assert assign_dengue_tier("month", 1.0, 0, 0, 36) == "C"    # monthly: never forecast
    assert assign_dengue_tier("week", 0.0, 156, None, 0) == "D"
    # Complete and current, but zero cases in most weeks: not forecastable.
    assert assign_dengue_tier("week", 1.0, 0, 0, 156, zero_share=0.9) == "C"


def _weekly_raw(codes, weeks, end=date(2026, 9, 28), drop_last=()):
    rows = []
    for code in codes:
        for k in range(weeks):
            d = end - timedelta(weeks=weeks - 1 - k)
            if code in drop_last and k >= weeks - 2:
                continue
            iy, iw, _ = d.isocalendar()
            rows.append(row(code, "isoweek", iy, iw, d.isoformat(), 10 + k % 5))
    return rows


def test_primary_grain_follows_the_latest_report():
    raw = pd.DataFrame([
        *_weekly_raw(["BRA", "COL"], 160),
        # BGD: weekly until 2023, monthly since -> profiled as a monthly reporter.
        *[row("BGD", "isoweek", 2023, w, date.fromisocalendar(2023, w, 1).isoformat(), 50)
          for w in range(1, 53)],
        *[row("BGD", "month", 2026, m, date(2026, m, 1).isoformat(), 900) for m in range(1, 10)],
    ])
    c = dengue.clean(raw, today=TODAY)
    cov = analyse_dengue(c.weekly, c.monthly)
    p = cov.profiles.set_index("country_code")
    assert p.loc["BRA", "grain"] == "week" and p.loc["BRA", "tier"] == "A"
    assert p.loc["BGD", "grain"] == "month" and p.loc["BGD", "tier"] == "C"
    assert cov.reference_month == pd.Timestamp("2026-09-01")


def _q(engine, sql):
    with engine.connect() as c:
        return c.execute(text(sql)).scalar()


def test_dengue_ingest_is_idempotent_and_records_revisions(db, tmp_path):
    with session_scope(db) as s:
        seed_reference(s)
    rows = _weekly_raw(["BRA", "COL", "PER"], 30, drop_last=("COL", "PER"))
    rows += [row("IND", "month", 2026, m, date(2026, m, 1).isoformat(), 100 * m,
                 name="India", region="SEAR") for m in range(1, 10)]
    raw = pd.DataFrame(rows)
    path = tmp_path / "dengue.csv"
    raw.to_csv(path, index=False)

    first = ingest_dengue(db, path=path, today=TODAY)
    assert first["by_grain"]["weekly"]["inserted"] == 30 + 28 + 28
    assert first["by_grain"]["monthly"]["inserted"] == 9
    assert first["areas_added_without_boundary"] == 4
    assert _q(db, "SELECT count(*) FROM surveillance_weekly WHERE is_provisional") == 2
    assert _q(db, "SELECT count(*) FROM surveillance_weekly WHERE positivity IS NOT NULL") == 0
    assert _q(db, "SELECT grain FROM coverage_profiles WHERE iso3 = 'IND'") == "month"

    second = ingest_dengue(db, path=path, today=TODAY)
    assert (second["inserted"], second["updated"], second["revisions_recorded"]) == (0, 0, 0)

    # WHO revises one weekly and one monthly value.
    raw.loc[(raw.ISO3 == "BRA") & (raw.DATE_NUM == raw.DATE_NUM.iloc[5]), "CASES"] = 777
    raw.loc[(raw.ISO3 == "IND") & (raw.DATE_NUM == 3), "CASES"] = 333
    raw.to_csv(path, index=False)
    third = ingest_dengue(db, path=path, today=TODAY)
    assert (third["updated"], third["revisions_recorded"]) == (2, 2)
    assert _q(db, "SELECT previous_values->>'cases' FROM surveillance_monthly_revisions") == "300"
