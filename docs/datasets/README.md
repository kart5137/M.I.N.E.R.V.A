# Data sources

Each source is verified before integration (existence, resolution, history, frequency,
licence, limits). Status as of 2026-11-10.

| Source | Use | Status | Doc |
|---|---|---|---|
| WHO FluNet | Influenza (MVP) | **Ingested** — `surveillance_weekly`, 146,533 country-weeks | [flunet.md](flunet.md), [profile](flunet_profile.md) |
| Natural Earth 1:50m | Country boundaries | **Ingested** — `countries`, 240 areas with geometry | [natural_earth.md](natural_earth.md) |
| World Bank WDI | Population; health-system context | **Ingested** — `population_annual` 1995–2025; `health_indicators` (5 indicators, 2010+) | [worldbank.md](worldbank.md) |
| WHO Global Dengue Surveillance | Dengue (P1) | **Ingested** — `surveillance_weekly` 32,754 country-weeks + `surveillance_monthly` 2,949 country-months, 199 areas | [dengue.md](dengue.md), [profile](dengue_profile.md) |
| OpenDengue | Dengue history (not used) | Verified — V1.3.1, CC BY 4.0 per LSHTM; historical only (weekly series end Dec 2024), not mixed with WHO data | — |
| WHO COVID-19 | COVID-19 (3rd) | Partly verified — daily until 25 Aug 2023, weekly after | — |
| Open-Meteo (ERA5) | Weather for dengue areas (D3) | **Ingested** — `weather_weekly` from 2013, loaded in daily batches within the free quota; NASA POWER evaluated and rejected | [weather.md](weather.md) |

## Loading

```powershell
.venv\Scripts\ei ingest all            # reference → boundaries → population → health → flunet → dengue → weather
.venv\Scripts\ei ingest flunet --refresh   # re-download and re-load one source
.venv\Scripts\ei ingest weather --budget 2000   # continue the weather history (resumable)
```

Every run is recorded in `ingestion_runs` with row counts, the raw file's SHA-256 and a
JSON quality report (cleaning actions, validation results, inserts/updates/revisions).
Re-running with unchanged source data changes nothing.

## Open questions

1. FluNet and WHO dengue licence wording for public deployment.
