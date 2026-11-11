# COVID-19 — WHO COVID-19 dashboard (weekly cases and deaths)

Milestone C3. Weekly new cases and deaths reported to WHO by country, January 2020 to
the latest week, shown as maps, trends, country pages and yearly totals. No forecasting,
outbreak detection or alerts (see Limitations).

## Source (verified 2026-11-11)

- **File:** `WHO-COVID-19-global-data.csv`, the weekly table behind the WHO COVID-19
  dashboard (<https://data.who.int/dashboards/covid19/data>), downloaded from
  `https://srhdpeuwpubsa.blob.core.windows.net/whdh/COVID/WHO-COVID-19-global-data.csv`.
- **Columns:** Date_reported, Country_code (ISO 3166-1 alpha-2), Country, WHO_region,
  New_cases, Cumulative_cases, New_deaths, Cumulative_deaths.
- **Size on 2026-11-11:** 85,200 rows, 240 areas, 2020-01-05 to 2026-10-18 (about 4 MB).
- **Licence:** WHO dataset terms on data.who.int (CC BY 4.0, with attribution).
- **Cross-check:** the loaded weeks sum to 779.6 million cases and 7.12 million deaths,
  matching WHO's published cumulative totals (about 778 million and 7.1 million).

Other files on the same site (daily data; hospital and ICU admissions) are not loaded.
WHO's FluNet views carry no SARS-CoV-2 test results (checked: VIW_FNT, VIW_FNT_DATADOT
and the other FLUMART views list influenza and RSV only), so there is no positivity series.

## Cleaning and storage

`pipeline/src/ei_pipeline/sources/covid.py` and `ingest/covid.py`; counts are in each
run's report (`ingestion_runs.quality_report`).

| Rule | 2026-11-11 run |
|---|---|
| Every Date_reported is a Sunday, and the value is the total reported to WHO from the Monday six days earlier to that Sunday (checked against WHO's daily file for Italy, the USA, Brazil and India in 2020, 2022 and 2024), so the row goes to the ISO week starting that Monday. | 0 non-Sunday dates |
| `International conveyance (…)` rows (cruise ships, WHO_region `OTHER`) are dropped: they are not countries. | 2,130 rows |
| An empty value means "not reported" (unknown, not zero). Rows with neither cases nor deaths are dropped. | 29,524 rows |
| Negative values (WHO's downward corrections) are removed from that week, which stays unknown for that measure. | 31 values |
| ISO2 → ISO3 through the countries table; eight territories without ISO2 in our reference data are mapped by code (Bonaire etc. BES, French Guiana GUF, Gibraltar GIB, Guadeloupe GLP, Martinique MTQ, Réunion REU, Tokelau TKL, Mayotte MYT). `NA` is Namibia, not a missing value. | 0 unknown codes |
| Areas new to the countries table are added without a boundary (Gibraltar). | 1 area |

Rows go to `surveillance_weekly` (disease `covid19`, cases and deaths) through the shared
weekly loader (`ingest/weekly_reports.py`, also used by cholera): changed weeks keep
their previous values in `surveillance_revisions`, and the latest **4 weeks are
provisional** because reports arrive late. The weekly job downloads the file fresh each
Wednesday; a failure is logged and does not stop the job (stored data stays).

## Dashboard

- **Overview / Global Surveillance:** cases per 100,000 per week (World Bank population)
  on the globe in a violet ramp, reported cases, deaths, countries reporting, weekly trend.
- **Country pages:** weekly cases and rate, the reporting record, and reported cases and
  deaths by year (sums of the weekly reports; the current year is marked incomplete). The
  history chart opens on the shortest range that contains the country's latest report.
- **About the Data:** source, measures and the limitations below.
- **Not shown:** case fatality rate. Deaths ÷ reported cases is meaningful for cholera,
  but for COVID-19 most infections after 2022 were never tested or reported, so the ratio
  overstates how deadly it is.

## Limitations

- **Reporting collapsed after 2022.** Countries reporting at least once in a year:
  232 (2022), 213 (2023), 147 (2024), 118 (2025), 98 (2026 so far); about 60 report in
  a typical recent 4-week window. Large countries stopped (the USA's last case report
  was in May 2023, though it still reports deaths). A missing week is unknown, never zero.
- **Reported cases understate infections**, increasingly so after testing wound down.
  Compare a country with itself, and years with care.
- **Report week, not onset week:** values are dated by when they reached WHO; backlogs
  can show up as spikes.
- **Why no forecasting or detection:** the spec allowed COVID-19 forecasting "with
  caveats". With reporting this sparse and its meaning changing over time (testing
  policy, not epidemiology, drives much of the recent series), a backtest would score
  reporting artefacts rather than epidemic dynamics, and seasonal baselines from
  2020–2022 do not describe today's reporting. Revisit if a stable signal (e.g.
  sentinel SARS-CoV-2 positivity) becomes available.
- Hospital and ICU admissions (a separate WHO file, few countries) are not loaded.
