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
    {
        "key": "who_dengue",
        "name": "WHO Global Dengue Surveillance",
        "url": "https://xmart-api-public.who.int/ARBOV/V_DENGUE_GLOBAL_VALIDATED_PUBLIC",
        "licence": "WHO data policy — reuse with attribution",
        "attribution_text": "Dengue data: WHO Global Dengue Surveillance.",
        "notes": "Reported cases as defined by each country (suspected, probable or "
        "confirmed), weekly or monthly. Compare within a country over time, not across "
        "countries.",
    },
    {
        "key": "open_meteo_era5",
        "name": "Open-Meteo Historical Weather API (ERA5 reanalysis)",
        "url": "https://open-meteo.com/en/docs/historical-weather-api",
        "licence": "CC BY 4.0 (Open-Meteo); ERA5: Copernicus licence, attribution required. "
        "Free API for non-commercial use.",
        "attribution_text": "Weather: Open-Meteo.com (CC BY 4.0), ERA5 reanalysis — "
        "Hersbach et al. (2020), Copernicus Climate Change Service (C3S).",
        "notes": "Daily mean 2 m temperature, precipitation and mean 2 m relative humidity "
        "at one point per country (ERA5, 0.25° grid), aggregated to ISO weeks. A single "
        "point does not represent large or climatically varied countries.",
    },
    {
        "key": "who_gho_malaria",
        "name": "WHO Global Health Observatory — malaria (World Malaria Report)",
        "url": "https://www.who.int/data/gho/data/themes/malaria",
        "licence": "WHO dataset terms: CC BY 4.0 with attribution (data.who.int); older GHO "
        "metadata lists CC BY-NC-SA 3.0 IGO. Used non-commercially, unmodified, attributed.",
        "attribution_text": "Malaria data: WHO Global Health Observatory (World Malaria "
        "Report estimates and reported cases).",
        "notes": "Yearly. Estimated cases, deaths and incidence are modelled (with "
        "uncertainty ranges) and revised each year; reported cases are what national "
        "programmes reported. The two differ, often widely.",
    },
    {
        "key": "who_cholera_dashboard",
        "name": "WHO Global Cholera and AWD Dashboard — weekly cases by country",
        "url": "https://who-global-cholera-and-awd-dashboard-1-who.hub.arcgis.com/",
        "licence": "CC BY-IGO (WHO, via the Humanitarian Data Exchange) — reuse with "
        "attribution",
        "attribution_text": "Cholera data: WHO Global Cholera and AWD Dashboard "
        "(preliminary weekly reports from Member States).",
        "notes": "Weekly cholera cases and deaths reported by countries with outbreaks, "
        "since January 2023. Preliminary and subject to revision; a week without a report "
        "is unknown, not zero.",
    },
    {
        "key": "who_gho_cholera",
        "name": "WHO Global Health Observatory — cholera (yearly, to 2016)",
        "url": "https://www.who.int/data/gho/data/themes/topics/cholera",
        "licence": "WHO dataset terms: CC BY 4.0 with attribution (data.who.int); older GHO "
        "metadata lists CC BY-NC-SA 3.0 IGO. Used non-commercially, unmodified, attributed.",
        "attribution_text": "Cholera history: WHO Global Health Observatory (cases and "
        "deaths reported to WHO, 1949–2016).",
        "notes": "Yearly reported cases, deaths and case fatality rate; the series ends in "
        "2016.",
    },
    {
        "key": "who_covid_dashboard",
        "name": "WHO COVID-19 dashboard — weekly cases and deaths by country",
        "url": "https://data.who.int/dashboards/covid19/data",
        "licence": "WHO dataset terms: CC BY 4.0 with attribution (data.who.int)",
        "attribution_text": "COVID-19 data: WHO COVID-19 dashboard (cases and deaths "
        "reported to WHO by Member States).",
        "notes": "Weekly new cases and deaths reported to WHO since January 2020. Since "
        "2023 many countries test and report far less, so reported cases understate "
        "infections more than before; a week without a report is unknown, not zero.",
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
    {
        # Capabilities switch on in phase D4, once dengue forecasting/detection exist.
        "key": "dengue",
        "name": "Dengue",
        "native_granularity": "weekly+monthly",
        "primary_metric": "cases",
        "metric_label": "Reported dengue cases",
        "supports_forecast": False,
        "supports_anomaly": False,
        "supports_hotspots": False,
    },
    {
        # Yearly data: trends and maps only (no forecasting, anomalies or hotspots).
        "key": "malaria",
        "name": "Malaria",
        "native_granularity": "annual",
        "primary_metric": "annual",
        "metric_label": "Estimated malaria cases",
        "supports_forecast": False,
        "supports_anomaly": False,
        "supports_hotspots": False,
    },
    {
        # Weekly outbreak reporting since 2023 (too short and patchy for forecasting or
        # detection) plus yearly history to 2016 (C2).
        "key": "cholera",
        "name": "Cholera",
        "native_granularity": "weekly+annual",
        "primary_metric": "cases",
        "metric_label": "Reported cholera cases",
        "supports_forecast": False,
        "supports_anomaly": False,
        "supports_hotspots": False,
    },
    {
        "key": "covid19",
        "name": "COVID-19",
        # Weekly reports; the yearly views sum them (no separate yearly source).
        "native_granularity": "weekly+annual",
        "primary_metric": "cases",
        "metric_label": "Reported COVID-19 cases",
        "supports_forecast": False,
        "supports_anomaly": False,
        "supports_hotspots": False,
    },
]


def seed_reference(session: Session) -> dict[str, int]:
    for model, rows in ((DataSource, DATA_SOURCES), (Disease, DISEASES)):
        stmt = insert(model).values(rows)
        update = {c: stmt.excluded[c] for c in rows[0] if c != "key"}
        session.execute(stmt.on_conflict_do_update(index_elements=["key"], set_=update))
    return {"data_sources": len(DATA_SOURCES), "diseases": len(DISEASES)}
