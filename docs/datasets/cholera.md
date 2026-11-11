# Cholera — WHO Global Cholera and AWD Dashboard (weekly) and WHO GHO (yearly history)

Milestone C2 (2026-11-11). Weekly maps and trends since 2023, cases and deaths, with
yearly history from 1949; no forecasting, anomaly or hotspot detection, alerts or reports
(outbreak-only reporting since 2023 is too short and patchy).

## Sources (verified 2026-11-11)

| | Weekly | Yearly history |
|---|---|---|
| What | Cases and deaths per country and reporting week, from Member States' preliminary reports | Cases, deaths and case fatality rate reported to WHO each year |
| Where | WHO Global Cholera and AWD Dashboard, public CSV `cholera_adm0_week` (ArcGIS item `6d435a537d534bac95b072fd6d999355`; mirrored on HDX) | GHO OData `CHOLERA_0000000001` (cases), `…0002` (deaths), `…0003` (CFR %) |
| Coverage | 43 countries, 2023-01-02 → 2026-10-19 (5,339 rows) | 160 countries, 1949–2016 |
| Licence | CC BY-IGO (WHO, via the Humanitarian Data Exchange) | WHO dataset terms (CC BY 4.0, data.who.int; older GHO metadata: CC BY-NC-SA 3.0 IGO) — used non-commercially, unmodified, attributed |
| Loader | `ei ingest cholera` (`pipeline/src/ei_pipeline/ingest/cholera.py`), in the weekly job as an optional step | same step |

**2017–2022** exist only in WHO's yearly reports (Weekly Epidemiological Record, PDF). No
figures are typed in by hand: country charts show those years as a gap. From 2023 the
yearly values are the sums of the weekly reports (computed by the API, not stored twice);
the current year is marked incomplete.

## Cleaning and storage

- **Dates:** 98% of `date_wk` are Mondays. Sundays (69 rows) start an epidemiological week
  that overlaps the following ISO week and move forward one day (as for dengue); other
  weekdays (14 rows) go to the ISO week that contains them. One country-week then
  appeared twice and was summed.
- **Values:** rows with neither cases nor deaths are dropped (2); a row with deaths but no
  case count keeps cases empty, never zero; negatives would be dropped (none). A reported
  0 stays 0.
- **Stored in** `surveillance_weekly` (`cases`, new `deaths` column) with revision history,
  and yearly history in `surveillance_annual` (`reported_cases`, `reported_deaths`, `cfr`).
- **Provisional:** the latest 4 weeks of the file (outbreak reports keep arriving late);
  the reference week is 4 weeks before the latest week.
- **Missing weeks** are unknown, not zero: countries report while an outbreak lasts.
- **GHO quirk:** for most cholera case rows `NumericValue` is empty and the count is only in
  the display `Value` (e.g. "2937"); plain numbers there are parsed (`gho.numeric`).

Local load 2026-11-11: 5,334 country-weeks, 43 countries, 2,491,300 cases and 21,412
deaths since 2023 (0.86% overall); 20 countries reported in the last 8 weeks.

## Dashboard

- **Overview, Global Surveillance, Countries:** weekly cases, cases per 100,000 per week
  (World Bank population), a "Total cases" fill, deaths and case fatality in
  the globe's hover card. Case fatality (deaths ÷ cases in the window) only from 20 cases.
- **Country page:** weekly cases since 2023, and reported cases and deaths by year from
  1949 with the 2017–2022 gap.
- **Not available** (pages explain why): Prediction Center, Hotspots, risk, Reports &
  Alerts, Analytics. The About page lists sources, measures and limitations.

## Limitations

- Preliminary reports, revised by WHO; outbreak reporting only.
- Case definitions (suspected or confirmed) differ by country and over time; compare a
  country with itself.
- The yearly WHO figures (to 2016) and the dashboard's weekly sums (from 2023) are
  compiled differently; the break between them is not a trend.
- Deaths are often reported later than cases, so recent case fatality can be low.
