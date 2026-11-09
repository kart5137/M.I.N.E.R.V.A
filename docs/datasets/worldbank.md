# World Bank — Population and health-system context

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

## Health-system context (M4)

Loaded by `ei ingest health` → `pipeline/src/ei_pipeline/ingest/health.py` into
`health_indicators (iso3, indicator_code, year, value, unit)`, 2010 onwards. The
indicator list lives in `packages/ei_db/src/ei_db/catalog.py` (shared with the API).

| Code | Indicator | Unit | Countries with a value | Latest year |
|---|---|---|---|---|
| `SH.MED.BEDS.ZS` | Hospital beds | per 1,000 people | 177 | 2023 |
| `SH.MED.PHYS.ZS` | Physicians | per 1,000 people | 194 | 2023 |
| `SH.MED.NUMW.P3` | Nurses and midwives | per 1,000 people | 198 | 2023 |
| `SH.XPD.CHEX.GD.ZS` | Current health expenditure | % of GDP | 193 | 2024 |
| `SP.POP.65UP.TO.ZS` | Population aged 65+ | % of population | 215 | 2025 |

(Counts as loaded on 2026-11-09, API last updated 2026-10-08.)

- The Country Intelligence page shows the **latest available year** for each indicator,
  with the year. Values more than 5 years older than the reference week are marked.
- Missing indicators show **Not available**. No imputation, no substitute source.
- Health-system indicators are reported irregularly (beds and physicians often lag
  several years), so they are context, not inputs to models.
