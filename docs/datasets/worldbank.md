# World Bank — Population, total (SP.POP.TOTL)

**Status:** verified and ingested 2026-11-09 · **Role:** denominators for per-capita rates

| | |
|---|---|
| Endpoint | `https://api.worldbank.org/v2/country/all/indicator/SP.POP.TOTL?format=json&per_page=20000&date=1995:2100` |
| Auth | None |
| Coverage | 217 economies + 49 aggregates; 1995–2025 loaded (API last updated 2026-10-08) |
| Licence | CC BY 4.0 — attribution "World Bank, World Development Indicators" |
| Loaded into | `population_annual (iso3, year, population)` |
| Job | `ei ingest population` → `pipeline/src/ei_pipeline/ingest/population.py` |

## Handling

- Only codes present in `countries` are kept; regional and income aggregates (e.g.
  `WLD`, `AFE`) are skipped and listed in the run's quality report.
- Values are upserted; a changed value overwrites the old one (no revision history —
  population is a denominator, not an observation).

## Known limitations

- **No World Bank population for ~25 areas**, including Taiwan, Vatican City, Western
  Sahara and several small territories, plus FluNet-only areas without their own
  World Bank entry (Guadeloupe, French Guiana, Martinique, Anguilla, Montserrat,
  Saint Barthélemy). Per-capita figures for these are shown as **not available**; no
  substitute source is mixed in.
- The latest year is an estimate and can be revised in later releases.
