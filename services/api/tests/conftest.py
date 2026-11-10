"""A small, hand-checkable dataset in a separate test database.

Weeks W0..W7 start on Mondays from 2024-01-01; W7 is provisional.

| country | region | geometry | weekly rows                                              |
|---------|--------|----------|----------------------------------------------------------|
| AAA     | EUR    | yes      | tests 100, positives 10·(w+1) every week                 |
| BBB     | EUR    | yes      | tests 50, positives 5; W3 has 60 positives (> tests)     |
| CCC     | AFR    | no       | tests 20, positives 2; W5 tests 0; W6 positives 4 with no |
|         |        |          | test count; no row for W7                                |

Season types: AAA NH, BBB SH, CCC YR. AAA rows carry an A/B breakdown (A = 6·(w+1),
B = 4·(w+1)). Health: AAA hospital beds 2.5 (2020) and 3.0 (2022); nothing else.

Dengue (case-based, source `who_dengue`), same weeks, W7 provisional:

| country | population | reports                                                        |
|---------|------------|----------------------------------------------------------------|
| AAA     | 1000       | weekly cases w+1 (W0..W7); also a monthly Jan 2024 row of 310   |
|         |            | (ignored in windows that have weekly reports)                  |
| BBB     | none       | weekly cases 5, W0..W6, no row for W2                           |
| CCC     | none       | monthly only: Jan 2024 62, Feb 2024 29 (provisional)            |

`mpox` is a registered disease with no data.
"""

from __future__ import annotations

import json
import os
from datetime import date, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker

from app.core.db import get_session
from app.main import create_app
from ei_db.session import get_database_url

TEST_DB = "epidemic_intelligence_api_test"
ALEMBIC_INI = Path(__file__).resolve().parents[3] / "packages" / "ei_db" / "alembic.ini"
W = [date(2024, 1, 1) + timedelta(weeks=i) for i in range(8)]


def _rows():
    for i, wk in enumerate(W):
        prov = i == 7
        yield ("AAA", wk, 100, 10 * (i + 1), prov)
        yield ("BBB", wk, 50, 60 if i == 3 else 5, prov)
        if i == 5:
            yield ("CCC", wk, 0, None, prov)
        elif i == 6:
            yield ("CCC", wk, None, 4, prov)
        elif i < 7:
            yield ("CCC", wk, 20, 2, prov)


def _seed(conn) -> None:
    conn.execute(text("""
        INSERT INTO data_sources (id, key, name, attribution_text)
          VALUES (1, 'flunet', 'WHO FluNet', 'Influenza data: WHO FluNet.'),
                 (2, 'worldbank_wdi', 'World Bank WDI', NULL),
                 (3, 'who_dengue', 'WHO dengue', 'Dengue data: WHO.');
        INSERT INTO diseases (id, key, name, native_granularity, primary_metric, metric_label)
          VALUES (1, 'influenza', 'Influenza', 'weekly', 'positivity', 'Test positivity'),
                 (2, 'dengue', 'Dengue', 'weekly+monthly', 'cases', 'Cases'),
                 (3, 'mpox', 'Mpox', 'weekly', 'cases', 'Cases');
        INSERT INTO ingestion_runs (id, source_id, status)
          VALUES (1, 1, 'success'), (2, 3, 'success');
        INSERT INTO countries (iso3, iso2, name, who_region, flu_season, geom) VALUES
          ('AAA', 'AA', 'Alpha', 'EUR', 'NH',
           ST_Multi(ST_GeomFromText('POLYGON((0 0,1 0,1 1,0 1,0 0))', 4326))),
          ('BBB', 'BB', 'Bravo', 'EUR', 'SH',
           ST_Multi(ST_GeomFromText('POLYGON((1 0,2 0,2 1,1 1,1 0))', 4326))),
          ('CCC', NULL, 'Charlie', 'AFR', 'YR', NULL);
        INSERT INTO health_indicators (iso3, indicator_code, year, value, unit, source_id)
          VALUES ('AAA', 'SH.MED.BEDS.ZS', 2020, 2.5, 'per 1,000 people', 2),
                 ('AAA', 'SH.MED.BEDS.ZS', 2022, 3.0, 'per 1,000 people', 2);
        INSERT INTO population_annual (iso3, year, population, source_id)
          VALUES ('AAA', 2022, 900, 2), ('AAA', 2023, 1000, 2);
        INSERT INTO coverage_profiles
          (disease_id, iso3, reference_week, tier, completeness, longest_gap)
          VALUES (1, 'AAA', '2024-02-12', 'A', 1.0, 0);
        INSERT INTO coverage_profiles
          (disease_id, iso3, reference_week, tier, grain, completeness, longest_gap)
          VALUES (2, 'AAA', '2024-02-12', 'A', 'week', 1.0, 0),
                 (2, 'CCC', '2024-02-12', 'C', 'month', 1.0, 0);
        INSERT INTO surveillance_monthly
          (disease_id, iso3, month_start, cases, is_provisional, source_id, ingestion_run_id)
          VALUES (2, 'AAA', '2024-01-01', 310, false, 3, 2),
                 (2, 'CCC', '2024-01-01', 62, false, 3, 2),
                 (2, 'CCC', '2024-02-01', 29, true, 3, 2);
    """))
    for i, wk in enumerate(W):
        y, n, _ = wk.isocalendar()
        dengue = [("AAA", i + 1)] + ([("BBB", 5)] if i not in (2, 7) else [])
        for iso3, cases in dengue:
            conn.execute(text("""
                INSERT INTO surveillance_weekly (disease_id, iso3, week_start, iso_year,
                  iso_week, cases, is_provisional, source_id, ingestion_run_id)
                VALUES (2, :iso3, :wk, :y, :n, :cases, :prov, 3, 2)
            """), {"iso3": iso3, "wk": wk, "y": y, "n": n, "cases": cases, "prov": i == 7})
    for iso3, wk, tests, pos, prov in _rows():
        valid = tests is not None and tests > 0 and pos is not None and pos <= tests
        y, n, _ = wk.isocalendar()
        k = W.index(wk) + 1
        breakdown = json.dumps({"inf_a": 6.0 * k, "inf_b": 4.0 * k}) if iso3 == "AAA" else None
        conn.execute(text("""
            INSERT INTO surveillance_weekly (disease_id, iso3, week_start, iso_year, iso_week,
              specimens_tested, positives, positivity, breakdown, is_provisional, source_id,
              ingestion_run_id)
            VALUES (1, :iso3, :wk, :y, :n, :tests, :pos, :positivity, CAST(:bd AS jsonb),
                    :prov, 1, 1)
        """), {"iso3": iso3, "wk": wk, "y": y, "n": n, "tests": tests, "pos": pos,
               "positivity": pos / tests if valid else None, "bd": breakdown,
               "prov": prov})


@pytest.fixture(scope="session")
def seeded_engine():
    base = make_url(get_database_url())
    admin = create_engine(base.set(database="postgres"), isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as c:
            c.execute(text(f'DROP DATABASE IF EXISTS "{TEST_DB}" WITH (FORCE)'))
            c.execute(text(f'CREATE DATABASE "{TEST_DB}"'))
    except OperationalError:
        pytest.skip("PostgreSQL not reachable")
    finally:
        admin.dispose()

    url = base.set(database=TEST_DB).render_as_string(hide_password=False)
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = url
    try:
        from alembic import command
        from alembic.config import Config

        command.upgrade(Config(str(ALEMBIC_INI)), "head")
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous

    engine = create_engine(url)
    with engine.begin() as conn:
        _seed(conn)
    yield engine
    engine.dispose()


@pytest.fixture(scope="session")
def api(seeded_engine) -> TestClient:
    factory = sessionmaker(bind=seeded_engine)

    def session():
        s = factory()
        try:
            yield s
        finally:
            s.close()

    app = create_app()
    app.dependency_overrides[get_session] = session
    return TestClient(app)
