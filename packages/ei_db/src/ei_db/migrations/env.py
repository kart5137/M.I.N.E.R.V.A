from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from geoalchemy2 import alembic_helpers
from sqlalchemy import pool

import ei_db.models  # noqa: F401  (registers all tables on Base.metadata)
from ei_db import Base, get_database_url, make_engine

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# PostGIS creates its own tables/schemas; never let autogenerate drop them.
POSTGIS_TABLES = {"spatial_ref_sys", "topology", "layer"}


def include_object(obj, name, type_, reflected, compare_to):
    if type_ == "table" and name in POSTGIS_TABLES:
        return False
    # Only compare what our models define. Extensions add their own tables (newer
    # postgis images install the tiger geocoder: tabblock20, zip_lookup, ...), and
    # autogenerate must never propose dropping them. Dropping one of our own tables
    # therefore needs a hand-written op.drop_table().
    if type_ == "table" and reflected and compare_to is None:
        return False
    table = getattr(obj, "table", None)
    if reflected and table is not None and table.name not in target_metadata.tables:
        return False
    return alembic_helpers.include_object(obj, name, type_, reflected, compare_to)


COMMON = dict(
    target_metadata=target_metadata,
    include_object=include_object,
    process_revision_directives=alembic_helpers.writer,
    render_item=alembic_helpers.render_item,
    compare_type=True,
)


def run_migrations_offline() -> None:
    context.configure(url=get_database_url(), literal_binds=True, **COMMON)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = make_engine(poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, **COMMON)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
