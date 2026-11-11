# Malaria — WHO Global Health Observatory (World Malaria Report)

Milestone C1 (2026-11-11). Yearly data: trends and maps only — no forecasts, anomaly or
hotspot detection, alerts or reports (one value a year cannot support them honestly).

## Source (verified 2026-11-11)

| | |
|---|---|
| API | `https://ghoapi.azureedge.net/api/<INDICATOR>` (WHO GHO OData; one JSON document per indicator, no key) |
| Loader | `ei ingest malaria` (`pipeline/src/ei_pipeline/ingest/malaria.py`); part of the weekly job, optional (a failure is logged and the stored years stay) |
| Licence | WHO's dataset terms (data.who.int) give CC BY 4.0 with an attribution requirement; older GHO metadata lists CC BY-NC-SA 3.0 IGO. This project is non-commercial, shows values unmodified and attributes WHO, which satisfies both. |
| Attribution | "Malaria data: WHO Global Health Observatory (World Malaria Report estimates and reported cases)." |

| Stored measure | GHO indicator | Meaning | Coverage (countries, years) |
|---|---|---|---|
| `est_cases` | MALARIA_EST_CASES | Estimated cases (modelled), with uncertainty range | 110, 2000–2024 |
| `est_deaths` | MALARIA_EST_DEATHS | Estimated deaths, with range | 110, 2000–2024 |
| `est_incidence` | MALARIA_EST_INCIDENCE | Estimated cases per 1,000 population at risk, with range | 110, 2000–2024 |
| `est_mortality` | MALARIA_EST_MORTALITY | Estimated deaths per 100,000 population, with range | 110, 2000–2024 |
| `confirmed_cases` | MALARIA_CONF_CASES | Cases confirmed by microscopy or RDT, as reported | 103, 2015–2024 |
| `reported_cases` | MALARIA_TOTAL_CASES | Reported cases, confirmed + presumed | 103, 2015–2024 |

GHO also publishes WHO-region and GLOBAL rows with their own ranges; they are stored
(`scope` = `region` / `global`) and used for totals, because uncertainty ranges cannot be
summed from countries. Reported-case totals at region/global level stop in 2021 and are
not shown.

## Storage — `surveillance_annual`

Long form: one row per disease, scope, area, year and measure (`value`, `low`, `high`).
`iso3` is set for country rows only. `low`/`high` are NULL for reported counts and for
estimates WHO takes directly from routine reporting (about 1,000 country-years: countries
with complete reporting have no modelled range).

## Checks (local load 2026-11-11: 13,579 rows, none dropped)

- value ≥ 0; where a range is given, low ≤ value ≤ high;
- year from 2000 to the current year;
- a country code must exist in `countries` (all 110 do);
- non-WHO regional groupings (e.g. World Bank income groups) are skipped on load.

WHO re-estimates the whole series with each World Malaria Report (December), so changed
values are updated in place; the run report counts `updated` rows.

## Dashboard

- **Overview (yearly):** world map of estimated cases per 1,000 at risk for the selected
  year (Year selector in the top bar), countries raised by √ estimated cases (capped at 70
  million a year); world estimates with ranges and change vs the previous year; cases by
  WHO region; world cases and deaths by year.
- **Countries:** every country's estimates (with ranges), rate, deaths, reported cases and
  change vs the previous year, sortable.
- **Country page:** estimated cases with range against reported and confirmed cases;
  incidence per 1,000 at risk; deaths.
- Weekly pages (Global Surveillance, Prediction Center, Hotspots, Reports & Alerts,
  Analytics) explain why they do not apply and offer a switch to influenza. The weekly API
  endpoints answer `422 not_available` for malaria; yearly data is under `/annual/*`.

## Limitations

- **Estimates are models.** World Malaria Report estimates combine routine reporting with
  modelled adjustments for incomplete testing and reporting; ranges are wide in
  high-burden countries (Nigeria 2024: 68.5 million, range 49.1–92.5 million).
- **Estimates vs reports.** Reported cases are often far below estimates (Nigeria 2024:
  24.0 million reported vs 68.5 million estimated). They are shown side by side and never
  mixed.
- **Revisions.** Past years change with each report; the dashboard shows the latest
  series, not a vintage.
- **Population at risk.** Incidence is per 1,000 population *at risk*, which WHO defines
  per country; rates compare risk-adjusted burden, not whole-population rates.
- **Non-endemic countries** have no estimates (shown as "no estimate"); a zero means no
  indigenous cases.
