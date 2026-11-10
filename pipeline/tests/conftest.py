from __future__ import annotations

import os
from datetime import date, timedelta

import pandas as pd
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError

from ei_db.session import get_database_url
from ei_pipeline.config import ROOT

TEST_DB = "minerva_test"


def make_raw(weeks: int = 40, start: date = date(2024, 1, 1),
             countries=("ARG", "BRA", "CHL"), drop_last: int = 2) -> pd.DataFrame:
    """Synthetic FluNet-shaped raw table. Most countries miss the last `drop_last` weeks
    (reporting delay); the first country reports every week."""
    rows = []
    for ci, code in enumerate(countries):
        for w in range(weeks):
            if ci > 0 and w >= weeks - drop_last:
                continue
            d = start + timedelta(weeks=w)
            iy, iw, _ = d.isocalendar()
            tested = 100 + w
            pos_a, pos_b = (w % 7) + ci, (w % 3)
            rows.append({
                "WHOREGION": "AMR", "FLUSEASON": "SH", "HEMISPHERE": "SH",
                "ITZ": "FLU_TEMP_SAMR", "COUNTRY_CODE": code, "COUNTRY_AREA_TERRITORY": code,
                "ISO_WEEKSTARTDATE": d.isoformat(), "ISO_YEAR": iy, "ISO_WEEK": iw,
                "ORIGIN_SOURCE": "SENTINEL", "SPEC_PROCESSED_NB": tested,
                "INF_ALL": pos_a + pos_b, "INF_A": pos_a, "INF_B": pos_b,
                "INF_NEGATIVE": tested - pos_a - pos_b,
            })
    return pd.DataFrame(rows)


@pytest.fixture(scope="session")
def test_engine():
    """A migrated, empty test database; skipped when Postgres is unreachable."""
    base = make_url(get_database_url())
    admin = create_engine(base.set(database="postgres"), isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as c:
            if not c.execute(text("SELECT 1 FROM pg_database WHERE datname = :n"),
                             {"n": TEST_DB}).scalar():
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

        command.upgrade(Config(str(ROOT / "packages" / "ei_db" / "alembic.ini")), "head")
        engine = create_engine(url)
        yield engine
        engine.dispose()
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous


@pytest.fixture
def db(test_engine):
    """Empty all data tables before each test."""
    with test_engine.begin() as c:
        tables = c.execute(text(
            "SELECT string_agg(quote_ident(tablename), ', ') FROM pg_tables "
            "WHERE schemaname = 'public' "
            "AND tablename NOT IN ('alembic_version', 'spatial_ref_sys')"
        )).scalar()
        c.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    return test_engine
