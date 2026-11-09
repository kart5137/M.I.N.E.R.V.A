"""A small, hand-checkable dataset in a separate test database.

Weeks W0..W7 start on Mondays from 2024-01-01; W7 is provisional.

| country | region | geometry | weekly rows                                              |
|---------|--------|----------|----------------------------------------------------------|
| AAA     | EUR    | yes      | tests 100, positives 10·(w+1) every week                 |
| BBB     | EUR    | yes      | tests 50, positives 5; W3 has 60 positives (> tests)     |
| CCC     | AFR    | no       | tests 20, positives 2; W5 tests 0; W6 positives 4 with no |
|         |        |          | test count; no row for W7                                |
"""

from __future__ import annotations

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
                 (2, 'worldbank_wdi', 'World Bank WDI', NULL);
        INSERT INTO diseases (id, key, name, native_granularity, primary_metric, metric_label)
          VALUES (1, 'influenza', 'Influenza', 'weekly', 'positivity', 'Test positivity'),
                 (2, 'dengue', 'Dengue', 'weekly', 'cases', 'Cases');
        INSERT INTO ingestion_runs (id, source_id, status) VALUES (1, 1, 'success');
        INSERT INTO countries (iso3, iso2, name, who_region, geom) VALUES
          ('AAA', 'AA', 'Alpha', 'EUR',
           ST_Multi(ST_GeomFromText('POLYGON((0 0,1 0,1 1,0 1,0 0))', 4326))),
          ('BBB', 'BB', 'Bravo', 'EUR',
           ST_Multi(ST_GeomFromText('POLYGON((1 0,2 0,2 1,1 1,1 0))', 4326))),
          ('CCC', NULL, 'Charlie', 'AFR', NULL);
        INSERT INTO population_annual (iso3, year, population, source_id)
          VALUES ('AAA', 2022, 900, 2), ('AAA', 2023, 1000, 2);
        INSERT INTO coverage_profiles
          (disease_id, iso3, reference_week, tier, completeness, longest_gap)
          VALUES (1, 'AAA', '2024-02-12', 'A', 1.0, 0);
    """))
    for iso3, wk, tests, pos, prov in _rows():
        valid = tests is not None and tests > 0 and pos is not None and pos <= tests
        y, n, _ = wk.isocalendar()
        conn.execute(text("""
            INSERT INTO surveillance_weekly (disease_id, iso3, week_start, iso_year, iso_week,
              specimens_tested, positives, positivity, is_provisional, source_id,
              ingestion_run_id)
            VALUES (1, :iso3, :wk, :y, :n, :tests, :pos, :positivity, :prov, 1, 1)
        """), {"iso3": iso3, "wk": wk, "y": y, "n": n, "tests": tests, "pos": pos,
               "positivity": pos / tests if valid else None, "prov": prov})


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
