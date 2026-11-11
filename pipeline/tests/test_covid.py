"""COVID-19 (C3): cleaning rules of the WHO weekly file and the weekly load with revisions
and provisional weeks."""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest
from sqlalchemy import text

from ei_pipeline.catalog import seed_reference
from ei_pipeline.db import session_scope
from ei_pipeline.ingest import covid as ingest
from ei_pipeline.sources import covid

HEADER = ["Date_reported", "Country_code", "Country", "WHO_region", "New_cases",
          "Cumulative_cases", "New_deaths", "Cumulative_deaths"]
ISO2 = {"AA": "AAA", "NA": "NAM"}

ROWS = [
    # date (Sunday), code, name, region, cases, deaths
    ("2024-01-07", "AA", "Alpha", "AFRO", 10, 1),
    ("2024-01-14", "AA", "Alpha", "AFRO", None, None),          # not reported: dropped
    ("2024-01-21", "AA", "Alpha", "AFRO", -5, 2),               # negative cases removed
    ("2024-01-07", "NA", "Namibia", "AFRO", 3, 0),              # "NA" is a code, not missing
    ("2024-01-07", "RE", "R�union", None, 7, 0),           # override + clean name
    ("2024-01-07", "XXJ", "International conveyance (Diamond Princess)", "OTHER", 700, 0),
    ("2024-01-07", "ZZ", "Nowhere", "EURO", 1, 0),              # unknown code
]


def weekly_csv(path, rows):
    pd.DataFrame([[d, c, n, r, cs, None, de, None] for d, c, n, r, cs, de in rows],
                 columns=HEADER).to_csv(path, index=False)
    return path


def test_clean_maps_codes_weeks_and_values(tmp_path):
    raw = covid.load(weekly_csv(tmp_path / "w.csv", ROWS))
    df, rep = covid.clean(raw, ISO2)
    assert (rep.rows, rep.dropped_conveyance, rep.dropped_empty) == (7, 1, 1)
    assert rep.negative_values_removed == 1 and rep.not_sunday == 0
    assert (rep.unknown_codes, rep.dropped_unknown_code) == (["ZZ"], 1)
    assert sorted(df["iso3"].unique()) == ["AAA", "NAM", "REU"]
    a = df[df["iso3"] == "AAA"].assign(w=lambda d: d["week_start"].dt.date).set_index("w")
    # A Sunday report covers the week from the Monday six days earlier.
    assert list(a.index) == [date(2024, 1, 1), date(2024, 1, 15)]
    assert a.loc[date(2024, 1, 1), "cases"] == 10
    assert pd.isna(a.loc[date(2024, 1, 15), "cases"]) and a.loc[date(2024, 1, 15), "deaths"] == 2
    assert df.loc[df["iso3"] == "REU", "name"].item() == "Réunion"
    assert set(df["who_region"].dropna()) == {"AFR"}
    assert (df["iso_year"].tolist()[0], df["iso_week"].tolist()[0]) == (2024, 1)


def test_load_rejects_unexpected_columns(tmp_path):
    p = tmp_path / "bad.csv"
    p.write_text("a,b\n1,2\n", encoding="utf-8")
    with pytest.raises(ValueError, match="missing columns"):
        covid.load(p)


def _q(db, sql):
    with db.connect() as c:
        return c.execute(text(sql)).scalar()


def test_ingest_weekly_with_revisions(db, tmp_path):
    with session_scope(db) as s:
        seed_reference(s)
        s.execute(text("INSERT INTO countries (iso3, iso2, name) VALUES ('AAA', 'AA', 'Alpha')"))
    sundays = ["2024-01-07", "2024-01-14", "2024-01-21", "2024-01-28", "2024-02-04",
               "2024-02-11"]
    rows = [(d, "AA", "Alpha", "AFRO", 10 * k, k % 2) for k, d in enumerate(sundays, 1)]
    rows.append(("2024-02-11", "GI", "Gibraltar", None, 3, 0))     # new area (override)
    rep = ingest.ingest_covid(db, path=weekly_csv(tmp_path / "w.csv", rows))
    assert (rep["inserted"], rep["updated"]) == (7, 0)
    assert rep["latest_week"] == "2024-02-05" and rep["reference_week"] == "2024-01-08"
    assert rep["first_week"] == "2024-01-01" and rep["areas_added_without_boundary"] == 1
    cov = "(SELECT id FROM diseases WHERE key = 'covid19')"
    assert _q(db, f"SELECT count(*) FROM surveillance_weekly WHERE disease_id = {cov}"
                  " AND is_provisional") == 5
    assert _q(db, "SELECT name FROM countries WHERE iso3 = 'GIB'") == "Gibraltar"

    rows[0] = ("2024-01-07", "AA", "Alpha", "AFRO", 11, 1)          # WHO revises a week
    again = ingest.ingest_covid(db, path=weekly_csv(tmp_path / "w2.csv", rows))
    assert (again["inserted"], again["updated"], again["revisions_recorded"]) == (0, 1, 1)
    assert _q(db, "SELECT (previous_values->>'cases')::float FROM surveillance_revisions") == 10


def test_ingest_needs_the_disease(db, tmp_path):
    with pytest.raises(LookupError, match="covid19"):
        ingest.ingest_covid(db, path=weekly_csv(tmp_path / "w.csv", ROWS[:1]))
