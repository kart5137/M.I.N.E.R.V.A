"""Malaria (C1): GHO parsing, checks and the yearly load into surveillance_annual."""

from __future__ import annotations

import json
from datetime import date

import pytest
from sqlalchemy import text

from ei_pipeline.catalog import seed_reference
from ei_pipeline.db import session_scope
from ei_pipeline.ingest import malaria as ingest
from ei_pipeline.sources import gho

TODAY = date(2026, 11, 11)


def row(area, year, value, low=None, high=None, kind="COUNTRY"):
    return {"SpatialDimType": kind, "SpatialDim": area, "TimeDimType": "YEAR",
            "TimeDim": year, "NumericValue": value, "Low": low, "High": high}


def write(dir_, code, rows):
    (dir_ / f"{code}.json").write_text(json.dumps({"value": rows}), encoding="utf-8")


def raw(tmp_path, cases_aaa=1000.0):
    d = tmp_path / "gho"
    d.mkdir(exist_ok=True)
    write(d, "MALARIA_EST_CASES", [
        row("AAA", 2023, cases_aaa, 800, 1300), row("AAA", 2024, 1200, 900, 1500),
        row("BBB", 2024, 50),                                       # no range (routine data)
        row("AFR", 2024, 5000, 4000, 6000, "REGION"),
        row("GLOBAL", 2024, 9000, 8000, 11000, "GLOBAL"),
        row("WB_LI", 2024, 1, kind="WORLDBANKINCOMEGROUP"),         # not kept
        row("XXX", 2024, 3, kind="REGION"),                         # not a WHO region
        row("AAA", 2022, None),                                     # no value
        row("CCC", 2024, -1),                                       # negative
        row("CCC", 2023, 10, 20, 30),                               # value below its range
        row("CCC", 1990, 10),                                       # before 2000
        row("ZZZ", 2024, 10),                                       # unknown country
    ])
    for code in ("MALARIA_EST_DEATHS", "MALARIA_EST_INCIDENCE", "MALARIA_EST_MORTALITY"):
        write(d, code, [row("AAA", 2024, 2.5, 1.0, 4.0)])
    write(d, "MALARIA_CONF_CASES", [row("AAA", 2024, 700)])
    write(d, "MALARIA_TOTAL_CASES", [row("AAA", 2024, 760)])
    return d


def test_gho_load_keeps_countries_who_regions_and_global(tmp_path):
    d = raw(tmp_path)
    df = gho.load(d / "MALARIA_EST_CASES.json")
    assert set(df["scope"]) == {"country", "region", "global"}
    assert "WB_LI" not in set(df["area"]) and "XXX" not in set(df["area"])
    assert df["value"].notna().all() and len(df) == 9
    bad = tmp_path / "bad.json"
    bad.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="not a GHO OData document"):
        gho.load(bad)


def _q(db, sql, **p):
    with db.connect() as c:
        return c.execute(text(sql), p).scalar()


@pytest.fixture
def countries(db):
    with session_scope(db) as s:
        seed_reference(s)
        s.execute(text("INSERT INTO countries (iso3, name) VALUES ('AAA', 'Alpha'),"
                       " ('BBB', 'Beta'), ('CCC', 'Gamma')"))
    return db


def test_ingest_checks_and_loads_then_updates_revised_values(countries, tmp_path):
    db = countries
    rep = ingest.ingest_malaria(db, raw_dir=raw(tmp_path), today=TODAY)
    assert rep["rows_dropped"] == {"negative": 1, "outside_range": 1, "year_out_of_range": 1,
                                   "unknown_country": 1}
    # est_cases: AAA×2, BBB, AFR, GLOBAL; four one-row measures; two reported measures.
    assert rep["inserted"] == 5 + 3 + 2 and rep["updated"] == 0
    assert rep["measures"]["est_cases"]["countries"] == 2
    assert rep["measures"]["est_cases"]["with_range"] == 2
    assert _q(db, "SELECT count(*) FROM surveillance_annual WHERE iso3 IS NULL") == 2
    assert _q(db, "SELECT low FROM surveillance_annual WHERE area = 'BBB'") is None
    assert _q(db, "SELECT high FROM surveillance_annual WHERE area = 'GLOBAL'") == 11000
    assert _q(db, "SELECT d.key FROM surveillance_annual a JOIN diseases d "
                  "ON d.id = a.disease_id LIMIT 1") == "malaria"

    # WHO re-estimates past years: a changed value is updated in place.
    again = ingest.ingest_malaria(db, raw_dir=raw(tmp_path, cases_aaa=1100.0), today=TODAY)
    assert (again["inserted"], again["updated"], again["unchanged"]) == (0, 1, 9)
    assert _q(db, "SELECT value FROM surveillance_annual WHERE area = 'AAA' AND year = 2023"
                  " AND measure = 'est_cases'") == 1100


def test_ingest_needs_countries(db, tmp_path):
    with session_scope(db) as s:
        seed_reference(s)
    with pytest.raises(RuntimeError, match="countries"):
        ingest.ingest_malaria(db, raw_dir=raw(tmp_path), today=TODAY)
