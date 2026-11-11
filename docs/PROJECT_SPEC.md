# M.I.N.E.R.V.A. — Project Specification (v2)

> Revised version of the original master prompt. Changes from v1 are listed in
> [§14 Revision log](#14-revision-log). This document is the source of truth for scope;
> anything not described here is out of scope until the spec is updated.

---

## 1. Purpose

M.I.N.E.R.V.A. (Monitoring & Intelligence Network for Epidemic Risk, Visualisation and Alerts) is a global disease-surveillance and outbreak-forecasting platform.
It combines real public-health datasets, a 3D geographic interface, and validated
machine-learning models to let a user:

1. See where a disease is active worldwide, on an interactive 3D globe.
2. Drill into any country's history, trend, population context and forecast.
3. Identify statistically significant geographic hotspots.
4. Forecast reported cases 1, 2 and 4 weeks ahead, with prediction intervals.
5. Detect unusual increases against historical and seasonal baselines.
6. Read structured, evidence-backed intelligence summaries and alerts.

It is an analytical and educational tool. It is **not** a diagnostic tool and not a
substitute for official public-health guidance; the UI says so.

---

## 2. Disease coverage and data granularity

The architecture is multi-disease from day one, but diseases are added one at a time,
and each disease's capabilities follow from what its data can honestly support.

| Order | Disease | Primary source | Granularity | Supports forecasting? |
|---|---|---|---|---|
| **1 (MVP)** | **Influenza** | WHO FluNet (lab-confirmed positives and specimens tested, not case counts) | Weekly, country, 1995– | Yes — 1/2/4-week horizons |
| 2 | Dengue | OpenDengue; WHO dengue dashboard | Mixed weekly/monthly/yearly; national + some subnational | Yes where weekly/monthly series exist; climate features |
| C1 ✓ | Malaria | WHO GHO (World Malaria Report) — see datasets/malaria.md | Annual, country, 2000– | No — trends and mapping only |
| C2 ✓ | Cholera | WHO Global Cholera and AWD Dashboard (weekly, 2023–) + GHO (yearly, 1949–2016) — see datasets/cholera.md | Weekly outbreak reports; yearly history | No — trends and mapping only |
| C3 ✓ | COVID-19 | WHO COVID-19 dashboard (weekly cases and deaths, 2020–) — see datasets/covid19.md | Weekly, country; yearly sums | No — reporting after 2022 too sparse and inconsistent (planned "with caveats"; reasons in datasets/covid19.md) |

Rules:
- A disease's **capability flags** (`supports_forecast`, `supports_anomaly`,
  `supports_hotspots`, `native_granularity`) are stored in the database and drive the
  UI. Features a disease's data cannot support are hidden or shown as unavailable —
  never filled with fabricated values.
- Every source must be verified before integration: existence, geographic resolution,
  historical coverage, reporting frequency, licence and API limits, known gaps.
  Findings are recorded in `docs/datasets/<source>.md`.

### Supporting data

| Data | Source | Use |
|---|---|---|
| Country boundaries | Natural Earth (public domain) | Globe polygons, centroids, neighbour graph |
| Population | World Bank (WDI) | Incidence per 100k, choropleth normalisation |
| Weather | Open-Meteo (historical + forecast) | Temperature, precipitation, humidity features |
| Health system | World Bank / WHO GHO (e.g. hospital beds per 1,000, physicians per 1,000) | Healthcare-impact context, annual, country-level |
| Subnational population (later) | WorldPop | Only if subnational disease data is added |

Weather handling:
- Open-Meteo is point-based. Country-level weather is a **population-weighted average
  over sample points** (largest cities / population centroids), not a single centroid.
- Weather forecasts reach ~16 days. Models therefore use **lagged observed weather
  only**; no future observed weather is ever used as a feature.

---

## 3. Design and UX

### Direction
A dark-mode epidemiological command centre: dense but calm, closer to a professional
geospatial analytics tool than a marketing site.

- "Observatory" palette (redesign, Nov 2026): deep ink-teal surfaces, warm amber accent,
  ivory text, teal as the secondary hue. Tokens in `apps/web/src/app/globals.css`.
- Data colours validated with the dataviz palette checker: amber single-hue positivity
  scale, blue ↔ coral diverging scales, amber ordinal risk; teal detection columns.
- Bricolage Grotesque for headings and readouts, Geist for body text; slim icon rail;
  one shared `.panel` card surface and a `.panel-glass` variant for overlays on the globe.
- Responsive down to tablet; mobile shows a simplified read-only layout.

Avoid: generic AI landing pages, heavy gradients, oversized cards, decorative
animation, and any number without a traceable source.

### 3D globe (core visual)
- **MapLibre GL JS** (open source, globe projection) as the base map, with
  **deck.gl** layers on top. No proprietary token required.
- Layers: country choropleth (incidence), 3D extruded columns (case volume),
  hotspot significance overlay, anomaly markers, forecast-change layer.
- Interactions: rotate/zoom/pan, hover tooltips, click-to-select country (opens the
  country panel), smooth fly-to, toggle between globe and flat projection,
  time slider bound to the global date filter.

### Layout
Persistent left sidebar + top bar.

**Top bar:** global search (countries and diseases), disease selector, date range,
region filter (WHO region / continent), data-status indicator (last refresh, DEMO
badge when applicable).

Deferred until there is a real user system (see §11): user profile, notification
centre. Alerts are reachable via the sidebar instead.

---

## 4. Pages

Six pages (v1 had nine; overlapping pages were merged).

| # | Page | Contents |
|---|---|---|
| 1 | **Overview** | KPI strip, 3D globe, global trend, top countries, latest alerts |
| 2 | **Global Surveillance** | Full-screen globe, layer controls, time slider, country side panel |
| 3 | **Country Intelligence** | Country drill-down: history, seasonality, population, health-system context, forecast, anomalies, hotspot status |
| 4 | **Hotspots & Anomalies** | Significant clusters, anomaly timeline, historical vs. current comparison |
| 5 | **Prediction Center** | Forecast charts with intervals, horizon/model selection, backtest metrics, model comparison, SHAP explanations |
| 6 | **Analytics** | Disease/country comparisons, weekly/monthly/yearly trends, seasonal profiles, growth rates |
| 7 | **Reports & Alerts** | Alert feed, generated intelligence reports, export |
| — | **About the Data** | Sources, licences, coverage, limitations, model cards |

Healthcare-impact content (beds, physicians, population at risk) lives in Country
Intelligence rather than a separate page; unavailable metrics are shown as
"Not available", never estimated.

KPI definitions (Overview), all computed from stored data for the selected disease
and date range:
- Reported cases (period total) and change vs. previous equivalent period.
- Countries reporting in the period.
- Countries with an active anomaly.
- Countries with a significant hotspot classification.
- Countries above epidemic threshold (forecast-based, next 2 weeks).

---

## 5. Machine learning

Each component is a separate, reusable module with its own evaluation and model card.

### A. Forecasting (core)
- **Target:** depends on the disease's data. For influenza (FluNet) there are no case
  counts, only lab results, so the targets are weekly **lab-confirmed positives**
  (`INF_ALL`, log1p scale) and **test positivity** (`INF_ALL / SPEC_PROCESSED_NB`),
  which is less sensitive to changes in testing volume. For dengue/COVID: weekly
  reported cases (log1p scale).
- **Horizons:** 1, 2 and 4 weeks ahead (direct multi-horizon strategy).
- **Models:**
  1. Baselines — seasonal naive (same week last year), last-value naive, moving average.
  2. Random Forest regressor.
  3. XGBoost regressor (expected primary model).
  4. LSTM — only if backtests show it beats XGBoost; otherwise documented as not justified.
- **Features (known at prediction time only):** lagged cases (1–4, 52 weeks),
  rolling means/std, ISO week (sin/cos), hemisphere/season, lagged weather,
  population, country-level static attributes.
- **Prediction intervals:** quantile models (XGBoost quantile objective) or
  conformal intervals from backtest residuals.
- **Validation:** rolling-origin (expanding-window) backtesting; no random splits.
- **Metrics:** MAE, RMSE, sMAPE/MASE (MAPE is undefined near zero counts, so not used
  as the headline metric); skill vs. seasonal-naive baseline.
- Reporting delay: the most recent 1–2 weeks are flagged as provisional.

### B. Anomaly detection
- Per-country seasonal baseline (same-week historical mean/quantiles) + rolling z-score.
- Statistical control limits (e.g. CUSUM or EWMA) as the primary signal.
- Isolation Forest as an optional multivariate secondary signal.
- Output: anomaly flag, severity, expected vs. observed, and method used.

### C. Hotspot detection
- Data is country-level (areal), so the methods are spatial-autocorrelation statistics:
  **Local Moran's I** and **Getis-Ord Gi\*** on population-normalised incidence,
  using a contiguity / k-nearest-neighbour spatial weights matrix (PySAL).
- Output: hot spot / cold spot / not significant, with p-values (FDR-corrected).
- DBSCAN / kernel density estimation are reserved for future point or fine
  subnational data; not used on country centroids.
- Detected (historical) hotspots and forecast-implied future hotspots are always
  visually distinct.

### D. Risk classification
- Risk levels are defined by **documented thresholds**, not by an opaque classifier:
  for influenza, epidemic and intensity thresholds per country via the **Moving
  Epidemic Method (MEM)** or a seasonal-percentile equivalent.
- Risk = where the forecast (with its interval) sits relative to those thresholds:
  Low / Moderate / High, with the rule shown in the UI.
- A supervised classifier is only added if it measurably improves on this rule.

### E. Explainability
- SHAP values for tree models: global feature importance and per-forecast
  contributions shown in Prediction Center and in reports.

### F. MLOps (lightweight)
- Reproducible training (fixed seeds, pinned dependencies, config files).
- Model registry table (`model_versions`) with training data range, features,
  hyperparameters, metrics and artefact path.
- Model cards in `docs/models/`.
- Never display a metric that was not produced by a stored evaluation run.

---

## 6. Intelligence reports and alerts

- **Alert triggers:** new anomaly, new significant hotspot, forecast crossing a risk
  threshold, sustained growth above a documented rate.
- **Report structure:** region, disease, observation period, observed trend, detected
  anomaly, forecast with interval, risk level and rule, top SHAP contributors, data
  caveats, sources.
- **Generation:** deterministic templates filled from stored data (default).
- **Optional LLM summary:** only rewrites the already-computed structured facts into
  prose; inputs and outputs are stored; it may not add findings. Requires an API key
  in env vars and is off by default.

---

## 7. Technical stack

| Layer | Choice |
|---|---|
| Frontend | Next.js (App Router), React, TypeScript, Tailwind CSS, shadcn/ui |
| Charts | Apache ECharts |
| Map | MapLibre GL JS (globe) + deck.gl |
| Data fetching | TanStack Query |
| Backend | Python, FastAPI, Pydantic, SQLAlchemy, Alembic |
| ML | pandas, NumPy, scikit-learn, XGBoost, PyTorch (LSTM only), SHAP, PySAL, GeoPandas |
| Database | PostgreSQL + PostGIS |
| Jobs | Python CLI ingestion/training jobs; scheduled via cron / GitHub Actions |
| Infra | Docker Compose for local dev; GitHub |
| Deploy (target) | Vercel (frontend), Render or Fly.io (API), Supabase or Neon (Postgres + PostGIS) |

Principles: clear separation of `frontend`, `backend` (API), `pipeline`
(ingestion + ML), and `db`; configuration and secrets only via environment variables.

---

## 8. Data conventions

- **Country key:** ISO 3166-1 alpha-3 everywhere; mapping table for source-specific names.
- **Time key:** ISO year + ISO week (`epi_week`) for weekly data, with week-start date.
- **Normalisation:** incidence per 100,000 using the matching year's population.
- **Provenance:** every record references its `data_source` and ingestion run.
- **Revisions:** sources revise history; ingestion upserts and keeps a revision timestamp.
- **Quality checks:** duplicates, negative or impossible values, missing weeks,
  unknown country codes, sudden reporting-pattern changes; results stored per run.
- **Attribution:** source and licence displayed wherever data is shown and on the
  About the Data page.

---

## 9. Database (outline — full schema is a later deliverable)

`countries` (with PostGIS geometry), `regions`, `diseases` (with capability flags),
`data_sources`, `ingestion_runs`, `epidemiological_records`, `population_records`,
`weather_records`, `health_system_indicators`, `model_versions`, `model_evaluations`,
`predictions`, `anomalies`, `hotspot_results`, `risk_assessments`, `alerts`,
`intelligence_reports`.

---

## 10. API (outline)

```
GET  /api/v1/meta/status                 data freshness, demo flags
GET  /api/v1/diseases                    list + capability flags
GET  /api/v1/overview                    KPIs for disease + date range
GET  /api/v1/surveillance/global         per-country values for map layers
GET  /api/v1/countries/{iso3}            country profile
GET  /api/v1/countries/{iso3}/timeseries
GET  /api/v1/analytics/trends
GET  /api/v1/hotspots
GET  /api/v1/anomalies
GET  /api/v1/predictions                 stored forecasts
GET  /api/v1/models/performance          stored evaluation runs
GET  /api/v1/alerts
GET  /api/v1/reports
POST /api/v1/reports/generate
```

Forecasts are produced by the pipeline and stored; the API serves stored results.
On-demand retraining (`POST /predictions/run`) is admin-only and deferred until auth exists.
All list endpoints support filtering and pagination; OpenAPI docs are auto-generated.

---

## 11. Scope control

**In MVP:** influenza end-to-end — ingestion, quality checks, globe, overview,
country intelligence, analytics, forecasting with baselines/RF/XGBoost, anomalies,
hotspots, threshold-based risk, template reports, About the Data.

**Deferred:** authentication and user profiles, notification centre, LLM summaries,
LSTM (unless justified), subnational data, WorldPop, additional diseases beyond the
first two.

---

## 12. Development rules

1. Modular code; no giant files; frontend, API and pipeline are separate.
2. No hardcoded or fabricated statistics, predictions or metrics.
3. Every button, filter and chart is wired to real application data.
4. Demonstration data, if ever needed, carries a visible **DEMO** badge and is never
   mixed with real data in the same view.
5. Secrets and configuration in environment variables (`.env.example` documented).
6. Every dataset and model is documented.
7. Errors are handled and surfaced clearly in the UI.
8. Prefer the simplest architecture that meets the requirement.

---

## 13. Milestone process

Work proceeds one milestone at a time. After each milestone: what was built, which
files changed, how to run it, how to test it. The next deliverable is the full
design package (architecture, verified datasets, schema + ER diagram, page hierarchy,
ML pipeline, data flow, folder structure, milestone plan), which requires approval
before implementation starts.

---

## 14. Revision log

Changes from the original master prompt (v1):

| Area | v1 | v2 | Reason |
|---|---|---|---|
| Map | Mapbox GL JS or Leaflet (2D) | MapLibre GL JS globe + deck.gl | 3D requirement; open source, no token |
| Forecast horizons | 7 / 14 / 30 days | 1 / 2 / 4 weeks | Global sources are weekly or coarser |
| First disease | Unspecified | Influenza (WHO FluNet) | Long weekly country-level history, strong seasonality, established thresholds |
| Hotspots | DBSCAN on regions | Local Moran's I / Getis-Ord Gi\* | DBSCAN is not meaningful on country centroids |
| Risk levels | RF/XGBoost classifier | Documented thresholds (MEM) applied to forecasts | Avoids circular, arbitrary labels |
| Forecast metric | MAPE | MAE, RMSE, sMAPE/MASE, skill vs. baseline | MAPE breaks near zero counts |
| Weather | Generic features | Population-weighted, lagged only | Country averages and future weather were leakage/validity risks |
| Pages | 9 | 7 + About the Data | Merged overlapping pages |
| Auth / profile / notifications | Required in top bar | Deferred | Avoids non-functional UI (rule 3) |
| LLM summaries | Included | Optional, off by default, structured-input only | Avoids invented findings |
| Population | WorldPop | World Bank; WorldPop later | Country-level data doesn't need rasters |
| Additions | — | Disease capability flags, ISO3/epi-week conventions, revisions, scheduled jobs, attribution, hosting for DB/API | Gaps in v1 |
