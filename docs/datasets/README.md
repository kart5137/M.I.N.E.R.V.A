# Data sources

Each source is verified before integration (existence, resolution, history, frequency,
licence, limits). Status as of 2026-11-09.

| Source | Use | Status | Doc |
|---|---|---|---|
| WHO FluNet | Influenza (MVP) | **Ingested** — `surveillance_weekly`, 146,533 country-weeks | [flunet.md](flunet.md), [profile](flunet_profile.md) |
| Natural Earth 1:50m | Country boundaries | **Ingested** — `countries`, 240 areas with geometry | [natural_earth.md](natural_earth.md) |
| World Bank WDI | Population; health-system context | **Ingested** — `population_annual` 1995–2025; `health_indicators` (5 indicators, 2010+) | [worldbank.md](worldbank.md) |
| OpenDengue | Dengue (2nd) | Partly verified — repo active, release V1.3.1; **data licence not stated in repo** | — |
| WHO COVID-19 | COVID-19 (3rd) | Partly verified — daily until 25 Aug 2023, weekly after | — |
| Open-Meteo | Weather features | Partly verified — CC BY 4.0 data, free non-commercial tier (<10k calls/day); **historical-API plan requirement unconfirmed** | — |

## Loading

```powershell
.venv\Scripts\ei ingest all            # reference → boundaries → population → health → flunet
.venv\Scripts\ei ingest flunet --refresh   # re-download and re-load one source
```

Every run is recorded in `ingestion_runs` with row counts, the raw file's SHA-256 and a
JSON quality report (cleaning actions, validation results, inserts/updates/revisions).
Re-running with unchanged source data changes nothing.

## Open questions

1. OpenDengue data licence — check the Figshare record (DOI 10.6084/m9.figshare.24259573).
2. Open-Meteo historical API — test whether it works on the free tier.
3. FluNet licence wording for public deployment.
