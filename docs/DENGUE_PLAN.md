# Post-MVP phase P1 — Dengue + weather (proposal)

Status: **approved 2026-11-10.** D1 (ingestion) built 2026-11-10 — see
[datasets/dengue.md](datasets/dengue.md) and the generated
[datasets/dengue_profile.md](datasets/dengue_profile.md). D2 (dashboard) built 2026-11-10 —
rules in [datasets/dengue.md](datasets/dengue.md#dashboard-values-d2). D3 (weather) built
2026-11-10 — [datasets/weather.md](datasets/weather.md); NASA POWER was evaluated as a
quota-free alternative and rejected (drift against ERA5). D4 (forecasting, detection, alerts,
reports) built 2026-11-10 — [datasets/dengue.md](datasets/dengue.md#forecasting-and-detection-d4)
and the generated model card [models/dengue-incidence.md](models/dengue-incidence.md).
D5 (endemic channel for dengue risk, replacing MEM) built 2026-11-11 —
[datasets/dengue.md](datasets/dengue.md#endemic-channel-and-risk-d5).

## 1. Sources (verified 2026-11-09)

| Source | What it is | Access | Licence | Verified facts |
|---|---|---|---|---|
| **WHO Global Dengue Surveillance** | Live national case reporting to WHO since 2024 (back-filled from 2007 for some countries) | `https://xmart-api-public.who.int/ARBOV/V_DENGUE_GLOBAL_VALIDATED_PUBLIC?$format=csv` (same xMart platform as FluNet) | WHO terms; attribute WHO | 44,747 rows, 199 countries; grains: epi-week (55 countries, Sunday start), ISO week (77), month (73); 53 epi-week and 61 monthly reporters have data after Sep 2026 |
| **OpenDengue v1.3.1** (3 Nov 2026) | Research archive compiled by LSHTM from published sources | GitHub `OpenDengue/master-repo` release extracts | CC BY 4.0 (per LSHTM repository) | 29,540 national rows, 128 countries, 1924–2025; weekly series end Dec 2024 — **historical only** |
| **Open-Meteo Historical Weather API** | ERA5-based daily reanalysis | `archive-api.open-meteo.com/v1/archive` | Data CC BY 4.0; free API for non-commercial use (600 calls/min observed) | Daily mean temperature, precipitation sum, mean relative humidity returned for any point |

Quality issues found in the WHO export (to be handled by validation, as with FluNet in M2):
rows dated up to **2029**, **84 negative** case counts, **20 % missing** case values, **58
duplicate** (country, grain, start) keys, mixed grains within some countries, and "monthly"
rows that start on days other than the 1st. Case definitions vary by country (suspected,
probable, confirmed), so counts compare **within a country over time**, not across countries.

*Corrected in D1 (measured 2026-11-10):* the "duplicate keys" were 60 rows with a missing
start date (rebuildable from year and period number, not duplicates); every monthly row
starts on the 1st (the earlier check looked at the weekday); only 5 rows with case values
are dated in the future (Malaysia/Singapore 2027–2029), the rest are empty placeholders;
the missing case values (8,954) are periods not yet reported.

## 2. Decisions proposed

1. **WHO dengue surveillance is the primary (and only live) source.** OpenDengue is not mixed
   in: its case definitions and coverage differ, and it stops in 2024. It can be added later
   as a clearly labelled historical layer.
2. **Metric:** reported cases and incidence per 100,000 (World Bank population, already
   loaded). Dengue has no test denominator, so there is no positivity.
3. **Time grain:** weekly where a country reports weekly. Epi-weeks (Sunday start) are mapped
   to the ISO week that contains them (start + 1 day), so dengue and influenza share Monday
   weeks. Monthly reporters are kept monthly and shown monthly; they are not split into
   invented weeks.
4. **Weather:** one representative point per country (the Natural Earth label point, already
   stored). Weekly mean temperature, total precipitation and mean humidity, used as lagged
   features (dengue responds to weather with a delay of roughly 1–3 months). Limitation shown
   in the UI: a single point does not represent large or climatically varied countries.
5. **Forecasting:** the existing rolling-origin backtest, baselines and XGBoost/RF with
   conformal intervals, on log-incidence for weekly countries, with and without weather
   features. Weather features are kept only if the backtest shows they help — the same rule
   as the neighbour features in M6.
6. **Detection:** anomalies (seasonal EWMA) and hotspots (Gi*) on incidence. MEM thresholds
   only where a country has enough complete seasons; otherwise no risk level (as for
   year-round influenza countries).
7. **Dashboard:** the "Disease" chip in the top bar becomes a selector (Influenza / Dengue).
   Pages read metric names and units from the API's disease capabilities, so they label
   "cases" and "incidence" instead of "positivity". A weather panel on dengue country pages.

## 3. Milestones

| # | Scope | Done when |
|---|---|---|
| D1 ✓ | WHO dengue ingestion with validation report, coverage tiers, revisions; profile doc | Weekly job loads dengue; validation numbers documented |
| D2 ✓ | Multi-disease API + disease selector; Overview, Surveillance, Countries, country page for dengue | Dengue browsable on the live site with correct units |
| D3 ✓ | Open-Meteo weather ingestion + weekly weather features; weather panel | Weather stored for all dengue countries; panel shown |
| D4 ✓ | Dengue forecasting (with/without weather), detection, alerts, reports | Backtest report shows whether weather helps; dengue in alerts and reports |
| D5 ✓ | Endemic channel for dengue risk (MEM covered 4 countries) | Risk for every forecast country with 5 complete years; channel chart on the country page; influenza unchanged |

Each milestone ends with the usual report and waits for approval.

## 4. Risks

- WHO marks the global system as under development with uneven sensitivity between countries.
- Open-Meteo's free tier is for non-commercial use; a commercial deployment would need a plan.
  Its daily quota means the weather history loads over about a week (D3).
- Weekly job time grows (weather download, second set of models); the estimate is +10–15
  minutes, within the 120-minute limit.
- Neon free storage: dengue adds an estimated 20–40 MB including weather.
