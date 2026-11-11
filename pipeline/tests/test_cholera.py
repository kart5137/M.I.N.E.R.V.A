"""Cholera (C2): weekly cleaning rules, the weekly load with revisions and provisional
weeks, and the yearly GHO history (including counts carried only as text)."""

from __future__ import annotations

import json
from datetime import date

import pandas as pd
import pytest
from sqlalchemy import text

from ei_pipeline.catalog import seed_reference
from ei_pipeline.db import session_scope
from ei_pipeline.ingest import cholera as ingest
from ei_pipeline.sources import cholera, gho

HEADER = ["", "adm0_name", "date_wk", "cases", "deaths", "who_region", "iso_3_code"]


def weekly_csv(path, rows):
    pd.DataFrame([[i, *r] for i, r in enumerate(rows)], columns=HEADER).to_csv(path, index=False)
    return path


ROWS = [
    # name, date, cases, deaths, region, iso3
    ("ALPHA", "2024-01-01", 10, 1, "African Region", "AAA"),        # Monday
    ("ALPHA", "2024-01-07", 20, 0, "African Region", "AAA"),        # Sunday → 2024-01-08
    ("ALPHA", "2024-01-10", 5, None, "African Region", "AAA"),      # Wednesday → 2024-01-08
    ("ALPHA", "2024-01-15", None, None, "African Region", "AAA"),   # empty: dropped
    ("ALPHA", "2024-01-22", -3, 0, "African Region", "AAA"),        # negative: dropped
    ("BETA", "2024-01-29", None, 2, "Region of the Americas", "BBB"),  # deaths only
    ("BETA", "2024-02-26", 7, 0, "Mars Region", "BBB"),             # unknown region name
]


def test_clean_aligns_weeks_merges_and_drops():
    raw = pd.DataFrame([dict(zip(HEADER[1:], r, strict=True)) for r in ROWS])
    df, rep = cholera.clean(raw)
    assert (rep.rows, rep.dropped_empty, rep.dropped_negative) == (7, 1, 1)
    assert (rep.moved_from_sunday, rep.moved_other_weekday, rep.merged_duplicates) == (1, 1, 1)
    assert rep.unknown_regions == ["Mars Region"]
    a = df[df["iso3"] == "AAA"].assign(w=lambda d: d["week_start"].dt.date).set_index("w")
    assert a.loc[date(2024, 1, 8), "cases"] == 25        # Sunday and Wednesday merged
    assert a.loc[date(2024, 1, 8), "deaths"] == 0        # a missing value does not erase a 0
    b = df[df["iso3"] == "BBB"].assign(w=lambda d: d["week_start"].dt.date).set_index("w")
    assert pd.isna(b.loc[date(2024, 1, 29), "cases"]) and b.loc[date(2024, 1, 29), "deaths"] == 2
    assert set(df["who_region"].dropna()) == {"AFR", "AMR"}
    assert list(df["name"].unique()) == ["Alpha", "Beta"]
    assert (df["week_start"].dt.dayofweek == 0).all()
    assert df["iso_week"].tolist()[:2] == [1, 2]


def test_load_rejects_unexpected_columns(tmp_path):
    p = tmp_path / "bad.csv"
    p.write_text("a,b\n1,2\n", encoding="utf-8")
    with pytest.raises(ValueError, match="missing columns"):
        cholera.load(p)


def test_numeric_reads_text_only_counts():
    assert gho.numeric({"NumericValue": None, "Value": "2 937"}) == 2937
    assert gho.numeric({"NumericValue": 1.5, "Value": "x"}) == 1.5
    assert gho.numeric({"NumericValue": None, "Value": "<0.1"}) is None


def gho_file(dir_, code, rows):
    (dir_ / f"{code}.json").write_text(json.dumps({"value": [
        {"SpatialDimType": "COUNTRY", "SpatialDim": a, "TimeDimType": "YEAR", "TimeDim": y,
         "NumericValue": n, "Value": v} for a, y, n, v in rows]}), encoding="utf-8")


def _q(db, sql):
    with db.connect() as c:
        return c.execute(text(sql)).scalar()


def test_ingest_weekly_and_history(db, tmp_path):
    with session_scope(db) as s:
        seed_reference(s)
        s.execute(text("INSERT INTO countries (iso3, name) VALUES ('AAA', 'Alpha')"))
    raw_dir = tmp_path / "gho"
    raw_dir.mkdir()
    gho_file(raw_dir, "CHOLERA_0000000001", [("AAA", 2010, None, "1 200"),
                                             ("ZZZ", 2010, 5, "5")])   # unknown country
    gho_file(raw_dir, "CHOLERA_0000000002", [("AAA", 2010, 12, "12")])
    gho_file(raw_dir, "CHOLERA_0000000003", [("AAA", 2010, 1.0, "1.0")])
    rows = [("ALPHA", f"2024-{m:02d}-{d:02d}", 10 * k, k % 2, "African Region", "AAA")
            for k, (m, d) in enumerate([(1, 1), (1, 8), (1, 15), (1, 22), (1, 29), (2, 5)], 1)]
    rows.append(("BETA", "2024-02-05", 3, 0, "Region of the Americas", "BBB"))   # new area
    csv = weekly_csv(tmp_path / "week.csv", rows)

    rep = ingest.ingest_cholera(db, path=csv, raw_dir=raw_dir)
    assert (rep["inserted"], rep["updated"]) == (7, 0)
    assert rep["latest_week"] == "2024-02-05" and rep["reference_week"] == "2024-01-08"
    assert rep["areas_added_without_boundary"] == 1
    cholera_id = "(SELECT id FROM diseases WHERE key = 'cholera')"
    # The latest 4 weeks (after 2024-01-08) are provisional.
    assert _q(db, f"SELECT count(*) FROM surveillance_weekly WHERE disease_id = {cholera_id}"
                  " AND is_provisional") == 5
    assert _q(db, f"SELECT sum(deaths) FROM surveillance_weekly WHERE disease_id = {cholera_id}"
                  " AND iso3 = 'AAA'") == 3
    h = rep["history"]
    assert (h["inserted"], h["countries"], h["unknown_country_codes"]) == (3, 1, ["ZZZ"])
    assert _q(db, f"SELECT value FROM surveillance_annual WHERE disease_id = {cholera_id}"
                  " AND measure = 'reported_cases'") == 1200

    # A revised week is updated in place and its previous value kept.
    rows[0] = ("ALPHA", "2024-01-01", 11, 1, "African Region", "AAA")
    again = ingest.ingest_cholera(db, path=weekly_csv(tmp_path / "week2.csv", rows),
                                  raw_dir=raw_dir)
    assert (again["updated"], again["revisions_recorded"]) == (1, 1)
    assert _q(db, "SELECT (previous_values->>'cases')::float FROM surveillance_revisions") == 10


def test_ingest_needs_the_disease(db, tmp_path):
    csv = weekly_csv(tmp_path / "w.csv", ROWS[:1])
    with pytest.raises(LookupError, match="cholera"):
        ingest.ingest_cholera(db, path=csv, raw_dir=tmp_path)
