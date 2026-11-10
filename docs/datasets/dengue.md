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
- **Analytics stays influenza-only**: it compares test positivity with health-system
  indicators and subtype mixes. `/analytics/*?disease=dengue` answers `422 not_available`
  and the page explains why, with a working switch to influenza. Forecasts, detection,
  alerts and reports exist for dengue since D4 (below).

## Forecasting and detection (D4)

Same machinery as influenza, configured per disease (`forecasting/spec.py`,
`detection/config.py` `DetectionSpec`); influenza outputs were checked to be unchanged
(all 11,880 backtest metrics and every threshold, anomaly and hotspot row identical before
and after the refactor).

**Forecasting** (`ei forecast run --disease dengue`; card: `docs/models/dengue-incidence.md`)

- **Who:** weekly reporters in dengue tiers A/B with a World Bank population (49 of 52;
  Guadeloupe, Martinique and Wallis and Futuna have no population). Monthly reporters are
  not forecast.
- **Target:** weekly incidence per 100,000. Model scale y = log(incidence + 100,000 ÷
  population), i.e. log(cases + 1) shifted by log population: a one-case offset per
  country, so a change is a relative change everywhere and a single case is not an
  outbreak.
- **Tree models learn the change** y(t + h) − y(t), not the level: trees cannot predict
  beyond the range seen in training, and dengue reaches record levels.
- **Evidence for both choices** (fast settings, same backtest, 2026-11-10): with
  log(1 + incidence) and level targets no tree model beat *last value* on MASE at any
  horizon; predicting the change cut the 1-week MAE from 2.52 to 2.20 per 100,000 but
  MASE still lost (low-incidence countries were near-linear on that scale); with the
  one-case offset XGBoost beat every baseline at all horizons (MASE 0.271 / 0.329 / 0.509
  vs last value 0.283 / 0.364 / 0.554). Three variants were compared on the backtest, so
  its scores are mildly optimistic.
- **Features:** lagged incidence and trends, same week last year, time of year, reported
  case volume (log 4-week mean), neighbours' incidence and its change, latitude. COVID-19
  weeks are kept for training (dengue kept circulating). The `random_forest_weather` and
  `xgboost_weather` models add 18 ERA5 features (`weather.md`). A weather model is active
  only if it wins selection (lowest MASE, beats seasonal naive) **and** its paired
  comparison with the same algorithm without weather shows a clear benefit (95% bootstrap
  interval of the MAE change entirely below zero); otherwise its twin without weather is
  used (`run.require_weather_benefit`). In the first full run a weather model had the
  lowest MASE at 1 and 4 weeks by 0.001–0.01, within noise, which is why the rule exists. The card's "Does weather help?" section compares each pair on
  the same rows with a bootstrap interval over origins and states how many rows had
  weather.
- **Intervals:** conformal as for influenza, Mondrian groups by reported cases per week
  (< 10, 10–100, 100–1,000, ≥ 1,000), volatility floor 0.10 on the log scale.

**Detection** (`ei detect run --disease dengue`), weekly reporters only:

- **Risk: endemic channel** (D5, below). D4 used MEM thresholds on calendar-year seasons;
  most dengue series gave unordered MEM levels (epidemic years like 2023–24 sit far above
  ordinary ones), so only 4 countries had usable levels and 2 a risk level. MEM is no
  longer run for dengue.
- **Anomalies:** seasonal EWMA on log(incidence + one case per 100,000), residual floor
  0.25 log units (≈ 28%), no COVID gap; expected value and band are reported as
  incidence. Comparable to the endemic channel used in dengue surveillance. Most flagged
  weeks fall in the 2023–24 epidemics (1,370 of 1,571 since 2023).
- **Hotspots:** Gi* and Local Moran on the 4-week mean incidence (≥ 2 reported weeks),
  statistics on log(1 + incidence). Different case definitions make this a map of high
  *reported* incidence.
- **Alerts:** the influenza rules on incidence, except sustained growth: incidence up 3
  weeks in a row by ≥ 50% in total with ≥ 20 cases each week (medium when it at least
  doubled).
- **Reports:** dengue facts carry `"metric": "incidence"` (cases, incidence, movers by
  relative change, monthly table for monthly reporters); influenza report facts are
  unchanged, so stored influenza reports still verify.

## Endemic channel and risk (D5)

`detection/channel.py`, stored in `endemic_channels`; the method used in dengue
surveillance in the Americas (Bortman 1999; PAHO), in its quartile form.

- **Channel of year Y, week w:** the same ISO week ±1 in up to 7 complete calendar years
  before Y (incidence in ≥ 75% of the year's weeks); the year with the highest mean
  incidence is left out, at least 4 must remain (so 5 complete years are needed). Week 53
  uses week 52 in years without one. Levels: median, 75th percentile (top of the channel)
  and 90th percentile of the pooled values (≥ 8). COVID years are used.
- **Risk** (2-week-ahead forecast of the active model): below the top of the channel =
  low; up to the 90th percentile = moderate; at or above it = high. Both levels are at
  least one weekly case (one case per 100,000 population, as incidence), so a country that
  usually reports zero is not "above its range" on a fraction of a forecast case.
- **Coverage** (local run, reference week 3 Aug 2026): 32 countries have a 2026 channel,
  21 of them a forecast and so a risk level (was 2 with MEM): 16 low, 4 moderate, 1 high.
  Countries that started weekly reporting recently show the reason (e.g. "2 complete
  reporting years in 2019–2025").
- **Historical check** (share of observed country-weeks above each week's levels; about
  25% and 10% are expected in a year like those the channel was built from):

  | Year | Countries | Above the channel (75th) | Above the 90th percentile |
  |---|---|---|---|
  | 2023 | 30 | 54.8% | 44.6% |
  | 2024 | 29 | 67.9% | 58.6% |
  | 2025 | 29 | 35.9% | 24.1% |

  The channel separates the 2023–24 epidemic years clearly. 2025 is still above the
  expected shares: reported dengue has risen over the decade (and reporting improved), so
  one left-out year does not remove every high year. The run summary (`detection_runs.
  summary.channels.check`) recomputes this table on every run.
- **Dashboard:** the dengue country page shows the channel chart (this year's reported
  incidence over the usual range, with the 2-week forecast); the risk card, risk map and
  reports name the top of the channel and the 90th percentile.

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
- **Weather** (D3): ERA5 at one point per area, see [weather.md](weather.md).
