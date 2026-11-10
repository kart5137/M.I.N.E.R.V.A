# WHO Global Dengue Surveillance

**Status:** verified 2026-11-10 · **Role:** primary (and only live) source for dengue
(post-MVP phase P1, milestone D1). Coverage numbers: the generated
[dengue_profile.md](dengue_profile.md).

## What it is

WHO's global dengue surveillance collects national dengue case reports. Reporting
through it began in 2024; some countries' series were back-filled (Americas from ~2014,
Australia and Indonesia from 2007). WHO describes the system as still under development,
with uneven sensitivity between countries.

**Counts are cases as each country defines them** (suspected, probable or confirmed),
not laboratory results, and there is no test denominator. Case definitions, testing
practice and reporting completeness differ by country, so counts are comparable
**within a country over time, not across countries**. Incidence per 100,000 (from World
Bank population) arrives with the dashboard in D2.

## Access

| | |
|---|---|
| Endpoint | `https://xmart-api-public.who.int/ARBOV/V_DENGUE_GLOBAL_VALIDATED_PUBLIC?$format=csv` (same xMart platform as FluNet) |
| Auth | None |
| Size | ~3 MB CSV, 44,747 rows, 16 columns, 199 areas (10 Nov 2026) |
| Encoding | UTF-8 (e.g. "Réunion", "Côte d'Ivoire") |
| Update frequency | Weekly/monthly as countries report; recent periods back-filled |
| Grains | `DATE_TYPE`: `epiweek` (CDC/PAHO, Sunday start), `isoweek` (Monday start), `month` |
| Licence | WHO data policy — reuse with attribution to WHO. Confirm the wording before public deployment of dengue pages. |

## Columns used

| Column | Meaning | Use |
|---|---|---|
| `ISO3`, `COUNTRY`, `WHO_REGION` | Area | Key, name for new areas, WHO region where ours is missing |
| `DATE_TYPE`, `YEAR`, `DATE_NUM`, `START_DATE` | Period | Grain, period label, start date |
| `CASES` | Reported cases (country definition) | Target; a period is "reported" when present (0 counts) |
| `CONFIRMED_CASES`, `SEVERE_CASES`, `DEATHS` | Sub-counts | Stored in `breakdown` |
| `SERO_1`…`SERO_4` | Serotype circulating (TRUE/FALSE) | Stored in `breakdown.serotypes` |

`POPULATION` is not used: World Bank population (already loaded) is used for incidence
so dengue and influenza share one denominator.

## Cleaning rules

Implemented in `pipeline/src/ei_pipeline/sources/dengue.py`; every action is counted in
the run's quality report and in the [profile](dengue_profile.md).

1. **Missing start dates** (60 rows: Australia and Indonesia monthly 2007–2009) are
   rebuilt from `YEAR`/`DATE_NUM`. Where both exist they agree in 100% of rows,
   including all 24,106 epi-weeks. One Sudan row labelled ISO week 53 of 2024 (a year
   with 52 ISO weeks) cannot be dated and is dropped.
2. **Rows without a case value are not reports** and are dropped (8,954 rows; 350 of
   them empty future placeholders up to the end of the year).
3. **Epi-weeks are mapped to the ISO week that contains them** (start + 1 day), so dengue
   and influenza share Monday weeks. Epi-week and ISO-week numbers differ in some years;
   the Monday date, not the number, is the key.
4. **Monthly rows stay monthly** (`surveillance_monthly`). They are never split into
   invented weeks. All monthly rows start on the 1st.
5. **Negative values**: a negative *case* count (84 rows, e.g. Dominican Republic
   −4,150 in Dec 2023 — most likely a correction posted as a negative week) fails
   validation and is excluded. Negative confirmed/severe/death values are cleared
   individually (116/124/42).
6. **Same Monday at two grains** (epi-week and ISO week): the ISO-week row is kept. None
   occur today; Singapore switched from ISO weeks to epi-weeks at the 2025/26 boundary
   without overlap.

## Loading (`ei ingest dengue`)

Implemented in `pipeline/src/ei_pipeline/ingest/dengue.py`, same approach as FluNet:

- Validation (`quality/validation.py`). Hard checks exclude the row: country code
  format, Monday weeks matching the ISO year/week, months starting on the 1st, no
  future periods (5 rows: Malaysia and Singapore weeks dated 2027–2029, evidently
  mistyped years), no negative cases. Warnings are counted only: confirmed > cases
  (492 weeks), deaths > cases (90), zero-case periods.
- Weekly rows are upserted into `surveillance_weekly` (`cases`, `breakdown`; the
  influenza columns stay NULL), monthly rows into `surveillance_monthly`. Revised values
  are appended to `surveillance_revisions` / `surveillance_monthly_revisions` first.
- `is_provisional` is set after the **reference week** (last week with ≥ 80% of the
  typical number of reporting countries) and, for monthly rows, after the **reference
  month** (same rule over months).
- Areas not yet in `countries` are added without geometry (Bonaire/Sint Eustatius/Saba,
  Madeira, Mayotte, Réunion, Tokelau). Existing countries keep their metadata, except
  that a missing WHO region is filled from the dengue export (32 countries). WHO's
  dengue export places Indonesia in SEAR; the stored WPR value (FluNet, current WHO
  membership) is kept.
- Coverage tiers are stored in `coverage_profiles` with `grain` = `week` or `month`.
- Rows in the database but no longer in the source are not deleted; they are counted.
- The weekly job (`ei weekly`) re-downloads and loads dengue after FluNet.

## Coverage tiers

Each area is profiled in the grain of its **most recent** report (Bangladesh, Sri
Lanka, Nepal and Afghanistan moved from weekly to monthly; Réunion the other way).
The window is **3 years** (156 weeks / 36 months), not FluNet's 5: most areas joined
WHO's system in 2024, and a 5-year window would rate nearly all of them incomplete.

| Tier | Rule |
|---|---|
| A | Weekly; ≥ 85% weeks reported, longest gap ≤ 8 weeks, last report ≤ 8 weeks old, cases in ≥ 50% of reported weeks |
| B | Weekly; ≥ 60% weeks reported, last report ≤ 26 weeks old, cases in ≥ 50% of reported weeks |
| C | Some data in the window: every monthly reporter, and weekly series that are mostly zeros |
| D | No data in the window |

The case-volume condition exists because 37 otherwise-complete weekly series report zero
cases in most weeks (sporadic or imported cases only; Canada reported none in the whole
window). They cannot support a meaningful forecast and are shown as map and trends only.

## Dashboard values (D2)

Implemented in `services/api/app/queries/cases.py`. The same endpoints serve influenza and
dengue (`?disease=dengue`); dengue responses fill `cases` / `incidence` fields and leave
the laboratory fields null.

- **Incidence** = reported cases per 100,000 population per week, over reported periods
  only (gaps are not zeros). Population: latest World Bank value up to the window's year.
  No population → cases are shown, the rate is not.
- **One grain per country per window.** A country's weekly reports in the window are used
  when it has any; otherwise the calendar months overlapping the window. Weekly and
  monthly values are never added together, so a country that switched grain (e.g.
  Bangladesh) shows weekly values for 2023 windows and monthly ones for 2026.
- **Totals, trend and largest changes use weekly reports only.** A calendar month does not
  fit a weekly window. "Countries reporting" counts weekly and monthly reporters and says
  how many of each. The dashboard states this next to the totals.
- **Largest changes** rank weekly reporters with ≥ 50 cases in both windows by the size of
  the relative change in incidence, symmetric for rises and falls (|ln(current/previous)|).
- **Map colours**: 6 amber steps (the validated positivity steps) with breaks at 0.1, 1,
  5, 20 and 50 per 100,000 per week; grey = reported but no population; land colour = no
  report. The legend notes that case definitions differ by country.
- **Not yet for dengue** (phase D4): forecasts, anomalies, hot spots, thresholds, alerts,
  reports and analytics. Those endpoints answer `422 not_available`; the dashboard shows a
  "planned for a later phase" panel with a working switch back to influenza.

## Known limitations

- **Different case definitions** between countries; no cross-country comparison of
  counts. Within a country, definitions can also change over time.
- **Reporting delay.** On 2026-11-10 the reference week was 3 Aug 2026; weeks after it
  are provisional (48 → 3 reporting countries in the eight weeks after).
- **Mixed grains.** Afghanistan reported both weekly and monthly for Mar 2024 – Nov 2025;
  both are stored, and the dashboard must show one (its primary grain) to avoid double
  counting.
- **Overseas territories.** French Guiana, Guadeloupe, Martinique, Mayotte and Réunion
  report separately but have no own boundary in Natural Earth (part of France's
  geometry), so they cannot be drawn as separate map areas. 16 small areas have no
  World Bank population, so no incidence.
- **Negative corrections** are excluded, so the adjacent positive weeks may overstate
  cases slightly for those countries.
- **Weather** (D3) is not loaded yet.
