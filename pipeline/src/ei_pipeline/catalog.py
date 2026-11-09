"""Registered data sources and diseases (reference data, seeded idempotently)."""

from __future__ import annotations

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from ei_db.models import DataSource, Disease

DATA_SOURCES = [
    {
        "key": "flunet",
        "name": "WHO FluNet (Global Influenza Surveillance and Response System)",
        "url": "https://www.who.int/tools/flunet",
        "licence": "WHO data policy — reuse with attribution",
        "attribution_text": "Influenza data: WHO FluNet, Global Influenza Surveillance and "
        "Response System (GISRS).",
        "notes": "Weekly laboratory results (specimens tested, positives), not case counts.",
    },
    {
        "key": "natural_earth",
        "name": "Natural Earth 1:50m Admin 0 – Countries (v5.1.2)",
        "url": "https://www.naturalearthdata.com/",
        "licence": "Public domain",
        "attribution_text": "Boundaries: Natural Earth.",
        "notes": "Overseas departments (e.g. French Guiana) are part of their parent "
        "country's geometry.",
    },
    {
        "key": "worldbank_wdi",
        "name": "World Bank World Development Indicators",
        "url": "https://data.worldbank.org/",
        "licence": "CC BY 4.0",
        "attribution_text": "Population: World Bank, World Development Indicators "
        "(SP.POP.TOTL), CC BY 4.0.",
        "notes": None,
    },
]

DISEASES = [
    {
        "key": "influenza",
        "name": "Influenza",
        "native_granularity": "weekly",
        "primary_metric": "positivity",
        "metric_label": "Influenza test positivity",
        "supports_forecast": True,
        "supports_anomaly": True,
        "supports_hotspots": True,
    },
]


def seed_reference(session: Session) -> dict[str, int]:
    for model, rows in ((DataSource, DATA_SOURCES), (Disease, DISEASES)):
        stmt = insert(model).values(rows)
        update = {c: stmt.excluded[c] for c in rows[0] if c != "key"}
        session.execute(stmt.on_conflict_do_update(index_elements=["key"], set_=update))
    return {"data_sources": len(DATA_SOURCES), "diseases": len(DISEASES)}
