from __future__ import annotations

from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.core.config import get_settings
from ei_db import make_engine, make_session_factory


@lru_cache
def get_engine() -> Engine:
    # Short connect timeout so a missing database fails fast with a clear 503.
    return make_engine(get_settings().database_url, connect_args={"connect_timeout": 3})


def get_session() -> Iterator[Session]:
    session = make_session_factory(get_engine())()
    try:
        yield session
    finally:
        session.close()
