from __future__ import annotations

import os

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

DEFAULT_URL = "postgresql+psycopg://ei:ei@localhost:5432/epidemic_intelligence"


def normalize_url(url: str) -> str:
    """Use the psycopg 3 driver for plain Postgres URLs.

    Hosted databases (Neon, Supabase, Render) hand out `postgres://` or `postgresql://`
    URLs, which SQLAlchemy would map to psycopg2 (not installed)."""
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


def get_database_url() -> str:
    return normalize_url(os.environ.get("DATABASE_URL") or DEFAULT_URL)


def make_engine(url: str | None = None, **kwargs) -> Engine:
    kwargs.setdefault("pool_pre_ping", True)
    return create_engine(normalize_url(url) if url else get_database_url(), **kwargs)


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)
