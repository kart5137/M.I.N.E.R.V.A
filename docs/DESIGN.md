# M.I.N.E.R.V.A. — Design Package

**Status:** draft for approval · 2026-11-09
Builds on [PROJECT_SPEC.md](PROJECT_SPEC.md) (scope) and [datasets/](datasets/README.md)
(verified data). Nothing here is implemented yet except the FluNet profiler.

Contents
1. [Architecture](#1-architecture)
2. [First disease and datasets](#2-first-disease-and-datasets)
3. [Database schema](#3-database-schema)
4. [Frontend page hierarchy](#4-frontend-page-hierarchy)
5. [API](#5-api)
6. [ML pipeline](#6-ml-pipeline)
7. [Data flow](#7-data-flow)
8. [Folder structure](#8-folder-structure)
9. [Milestones](#9-milestones)
10. [Risks and open decisions](#10-risks-and-open-decisions)

---

## 1. Architecture

Three runtime parts and one database. The API is **read-mostly**: all heavy work
(ingestion, training, forecasting, detection) runs in the pipeline as scheduled batch
jobs and writes results to the database. The API serves those stored results.

```mermaid
flowchart LR
    subgraph Sources
        FN[WHO FluNet API]
        NE[Natural Earth]
        WB[World Bank API]
        OM[Open-Meteo<br/>later]
    end

    subgraph Pipeline["pipeline/ (Python batch jobs, weekly)"]
        ING[Ingest + validate]
        FEAT[Feature builder]
        TRAIN[Train + backtest]
        PRED[Forecast]
        DET[Anomalies · Hotspots · Risk]
        REP[Alerts + Reports]
    end

    DB[(PostgreSQL + PostGIS)]
    ART[(Model artefacts<br/>models/)]

    subgraph API["services/api (FastAPI)"]
        R[REST /api/v1]
    end

    subgraph Web["apps/web (Next.js)"]
        UI[Dashboard + 3D globe]
    end

    FN & NE & WB & OM --> ING --> DB
    DB --> FEAT --> TRAIN --> ART
    TRAIN --> DB
    ART --> PRED --> DB
    DB --> DET --> DB
    DB --> REP --> DB
    DB --> R --> UI
```

| Part | Responsibility | Tech |
|---|---|---|
| `apps/web` | UI, globe, charts, filters. No business logic beyond presentation. | Next.js (App Router), TypeScript, Tailwind, shadcn/ui, ECharts, MapLibre GL + deck.gl, TanStack Query |
| `services/api` | Validated, paginated, cached read endpoints; report generation trigger. | FastAPI, Pydantic v2, SQLAlchemy 2, GeoAlchemy2 |
| `pipeline` | Ingestion, quality checks, features, training, backtesting, forecasting, detection, alerts, reports. CLI entry points. | pandas, scikit-learn, XGBoost, SHAP, PySAL (esda/libpysal), GeoPandas |
| `packages/ei_db` | Shared SQLAlchemy models + Alembic migrations, used by both API and pipeline. | SQLAlchemy, Alembic |
| Database | Single source of truth for data and results. | PostgreSQL 16 + PostGIS 3 |

Why batch, not on-request ML: forecasts change weekly with the data; precomputing keeps
the API fast, makes every displayed number traceable to a stored model run, and avoids
running training inside a web server.

**Scheduling:** one weekly job (`ei run-weekly`) chains all pipeline steps. Locally run
by hand; in deployment via GitHub Actions cron.

---

## 2. First disease and datasets

**Influenza via WHO FluNet** — confirmed by profiling ([flunet_profile.md](datasets/flunet_profile.md)):
weekly, 189 countries/areas, 1995–2026; **88 countries forecast-ready (Tier A)**,
44 usable with caution (Tier B), spread across all six WHO regions.

| Dataset | Used for | Milestone | Status |
|---|---|---|---|
| WHO FluNet | Positives, specimens, positivity | M2 | Ingested |
| Natural Earth 1:50m Admin-0 | Globe polygons, centroids, spatial weights | M1–M2 | Ingested |
| World Bank WDI `SP.POP.TOTL` | Population, per-capita normalisation | M2 | Ingested |
| World Bank WDI: hospital beds, physicians, nurses per 1,000; health expenditure % GDP; population 65+ | Country health-system context | M4 | Ingested |
| Open-Meteo | Weather features (dengue phase) | Post-MVP | Partly verified |
| OpenDengue | Dengue | Post-MVP | Licence open |

Key data facts that shape the design:
- FluNet values are **lab results, not cases** → UI says "lab-confirmed detections" and
  "test positivity", never "cases", for influenza.
- Last ~3 weeks are **provisional** → stored with `is_provisional`, shown hatched/greyed,
  excluded from training and anomaly detection.
- **2020-03 → 2022-06** (COVID-19 disruption) → excluded from training targets and
  seasonal baselines by default, kept for display.

---

## 3. Database schema

Conventions: `iso3 CHAR(3)` country key; `week_start DATE` (ISO Monday) as time key with
`iso_year`/`iso_week` alongside; SRID 4326; `created_at`/`updated_at` on mutable tables;
every data row references its `source_id` and `ingestion_run_id`.

### ER diagram

```mermaid
erDiagram
    countries ||--o{ surveillance_weekly : has
    countries ||--o{ population_annual : has
    countries ||--o{ health_indicators : has
    countries ||--o{ forecasts : for
    countries ||--o{ anomalies : for
    countries ||--o{ hotspot_results : for
    countries ||--o{ risk_assessments : for
    countries ||--o{ seasonal_thresholds : for
    countries ||--o{ coverage_profiles : for
    diseases ||--o{ surveillance_weekly : of
    diseases ||--o{ model_versions : of
    data_sources ||--o{ ingestion_runs : produced
    ingestion_runs ||--o{ surveillance_weekly : loaded
    surveillance_weekly ||--o{ surveillance_revisions : history
    model_versions ||--o{ model_evaluations : scored_by
    model_versions ||--o{ forecasts : produced
    forecasts ||--o{ forecast_explanations : explained_by
    forecasts ||--o| risk_assessments : basis
    seasonal_thresholds ||--o{ risk_assessments : basis
    alerts }o--o| anomalies : from
    alerts }o--o| hotspot_results : from
    alerts }o--o| risk_assessments : from
    intelligence_reports }o--o{ alerts : cites
```

### Tables

**Reference**

| Table | Key columns |
|---|---|
| `countries` | `iso3` PK, `iso2`, `name`, `who_region`, `hemisphere`, `transmission_zone`, `continent`, `geom MULTIPOLYGON`, `centroid POINT` · GiST index on `geom` |
| `country_code_aliases` | `alias` PK, `iso3` FK, `source_id` — maps source codes (e.g. `XKX`, `X09`) |
| `diseases` | `id` PK, `key` (`influenza`), `name`, `native_granularity`, `primary_metric`, `metric_label`, `supports_forecast`, `supports_anomaly`, `supports_hotspots` |
| `data_sources` | `id` PK, `key`, `name`, `url`, `licence`, `attribution_text`, `notes` |
| `ingestion_runs` | `id` PK, `source_id` FK, `started_at`, `finished_at`, `status`, `raw_rows`, `loaded_rows`, `raw_sha256`, `quality_report JSONB` |

**Observations**

| Table | Key columns |
|---|---|
| `surveillance_weekly` | `id` PK, `disease_id` FK, `iso3` FK, `week_start`, `iso_year`, `iso_week`, `specimens_tested`, `positives`, `cases` (NULL for influenza), `positivity`, `breakdown JSONB` (subtypes), `is_provisional`, `source_id`, `ingestion_run_id`, `updated_at` · UNIQUE(`disease_id`,`iso3`,`week_start`) · index (`disease_id`,`week_start`) |
| `surveillance_revisions` | `id` PK, `surveillance_id` FK, `previous_values JSONB`, `revised_at`, `ingestion_run_id` — append-only history when a source revises a past week |
| `population_annual` | (`iso3`,`year`) PK, `population`, `source_id` |
| `health_indicators` | (`iso3`,`indicator_code`,`year`) PK, `value`, `unit`, `source_id` |
| `weather_weekly` (post-MVP) | (`iso3`,`week_start`) PK, `temp_mean`, `precip_sum`, `rh_mean`, `n_points`, `source_id` |
| `coverage_profiles` | (`disease_id`,`iso3`,`reference_week`) PK, `tier`, `completeness`, `longest_gap`, `median_tests`, `weeks_since_last` — output of the profiler, drives which countries get forecasts |

**Models and outputs**

| Table | Key columns |
|---|---|
| `model_versions` | `id` PK, `disease_id`, `run_key` (one training run), `model_type` (`seasonal_naive`,`last_value`,`moving_average_4`,`random_forest`,`xgboost`), `kind` (`baseline`/`ml`), `target`, `horizon_weeks`, `train_start`, `train_end`, `features JSONB`, `hyperparams JSONB`, `global_importance JSONB`, `artefact_uri`, `git_sha`, `trained_at`, `is_active` (one per horizon), `selection_note` · UNIQUE(`run_key`,`model_type`,`target`,`horizon_weeks`) — *M5: one version per model × horizon* |
| `model_evaluations` | `id` PK, `model_version_id` FK, `iso3` (NULL = pooled), `metric` (`mae`,`rmse`,`mase`,`skill_vs_snaive`,`coverage_80`,`coverage_95`), `value`, `n_obs`, `n_origins`, `eval_start`, `eval_end` |
| `forecasts` | `id` PK, `model_version_id` FK, `disease_id`, `iso3`, `origin_week`, `target_week`, `horizon_weeks`, `target`, `point`, `lo80`, `hi80`, `lo95`, `hi95`, `explanation_base` (SHAP expected value), `created_at` · UNIQUE(`model_version_id`,`iso3`,`origin_week`) |
| `forecast_explanations` | (`forecast_id`,`feature`) PK, `shap_value`, `feature_value`, `rank` — top-k contributors |
| `backtest_predictions` | `id` PK, `model_version_id` FK, `iso3`, `origin_week`, `target_week`, `point`, `lo80`…`hi95`, `actual` — out-of-sample backtest detail, kept for the current run only (M5) |
| `detection_runs` | `id` PK, `disease_id`, `run_key`, `reference_week`, `latest_week`, `started_at`, `finished_at`, `git_sha`, `summary JSONB` (settings, counts, not-assessed reasons) — *M6: each run replaces the outputs below* |
| `seasonal_thresholds` | `id` PK, `run_id`, `disease_id`, `iso3`, `season`, `season_start`, `method` (`mem`), `epidemic_threshold`, `post_threshold`, `medium`, `high`, `very_high`, `n_seasons_used`, `seasons_used JSONB`, `mean_epidemic_weeks`, `quality_note` (NULL = usable) |
| `risk_assessments` | `id` PK, `run_id`, `disease_id`, `iso3`, `assessed_week`, `target_week`, `risk_level` (`low`,`moderate`,`high`), `rule`, `forecast_point`, `forecast_lo80`, `forecast_hi80`, `model_type` (copied so the row survives a forecast rerun), `forecast_id` FK (SET NULL), `threshold_id` FK, `season`, `epidemic_threshold`, `high_threshold`, `method` (`mem`/`endemic_channel`, D5). Current levels = rows of the disease's latest detection run |
| `endemic_channels` | D5 (dengue): `id` PK, `run_id`, `disease_id`, `iso3`, `year`, `iso_week`, `week_start`, `median`, `q75`, `p90`, `n_values`, `years_used JSONB`, `excluded_years JSONB` — see `datasets/dengue.md` |
| `anomalies` | `id` PK, `run_id`, `disease_id`, `iso3`, `week_start`, `metric`, `method` (`seasonal_ewma`/`isolation_forest`), `observed`, `expected`, `upper_band`, `score`, `ewma`, `ewma_limit`, `specimens_tested`, `severity`, `is_provisional`, `detected_at` |
| `hotspot_results` | `id` PK, `run_id`, `disease_id`, `iso3`, `window_end`, `window_weeks`, `statistic` (`gi_star`,`local_moran`), `value`, `stat_value`, `z_score`, `p_value`, `p_fdr`, `classification`, `n_neighbours`, `neighbour_source` (`queen`/`knn`), `weights_spec` |
| `alerts` | `id` PK, `disease_id`, `iso3`, `alert_type`, `severity` (`low`/`medium`/`high`), `week_start`, `title`, `details JSONB`, `status` (`active`/`retracted`), `anomaly_id`/`hotspot_id`/`risk_id` FKs (SET NULL), `first_run_id`, `last_run_id`, `created_at`, `updated_at`, `retracted_at` · UNIQUE(`disease_id`,`iso3`,`alert_type`,`week_start`) — *M7: upserted each run; never deleted* |
| `intelligence_reports` | `id` PK, `disease_id`, `scope` (`global`/`country`), `iso3`, `region`, `period_start`, `period_end`, `weeks`, `title`, `content JSONB` (canonical facts), `rendered_md`, `generator` (`template`), `template_version`, `inputs_sha256`, `created_at` |
| `report_alerts` | (`report_id`,`alert_id`) PK |

Migrations: Alembic in `packages/ei_db/migrations/`, one revision per milestone.

---

## 4. Frontend page hierarchy

```
/                         Overview
/surveillance             Global Surveillance (full-screen globe)
/countries                Country index (search, sortable table, tiers)
/countries/[iso3]         Country Intelligence
/hotspots                 Hotspots & Anomalies
/predictions              Prediction Center
/predictions/models/[id]  Model detail (backtest, SHAP global importance)
/analytics                Analytics
/reports                  Reports & Alerts (tabs: Alerts | Reports)
/reports/[id]             Report detail
/about                    About the Data (sources, licences, limitations, model cards)
```

**Shell (every page):** left sidebar (collapsible), top bar with search (countries,
diseases), disease selector, date range, WHO-region filter, data-status pill
(reference week, provisional weeks, last refresh). Filters live in the URL query
string so every view is shareable and back-button safe.

| Page | Main components |
|---|---|
| Overview | KPI strip (5 KPIs from spec §4) · globe (positivity choropleth) · global positivity trend with provisional shading · top movers table · latest alerts |
| Global Surveillance | Globe full-bleed · layer panel (positivity, detections columns, anomalies, hotspots, forecast change, risk) · time slider · legend · country side panel on click |
| Country Intelligence | Header (name, region, tier, data badges) · history chart (positivity + tests, provisional shading) · seasonal profile (this season vs. past seasons + thresholds) · forecast chart with 80/95% bands · anomalies timeline · hotspot status · population & health-system context ("Not available" where missing) |
| Hotspots & Anomalies | Globe/flat map of Gi\* classes · hotspot table (z, p_fdr) · anomaly feed · historical comparison |
| Prediction Center | Country + horizon + model selectors · forecast chart · backtest metrics table vs. seasonal-naive · interval coverage · per-forecast SHAP waterfall |
| Analytics | Multi-country comparison · weekly/monthly/yearly aggregation · seasonal heatmap (week × year) · growth rates · subtype mix (A/B) |
| Reports & Alerts | Alert list with filters · report list · generate report (country/global) |
| About | Source cards with licence + attribution · coverage tiers · known limitations · model cards |

Globe rendering plan: MapLibre GL v5 globe projection, Natural Earth polygons as a
GeoJSON source (no third-party basemap needed for the dark "command centre" look),
deck.gl for 3D columns/arcs. **M1 includes a spike** to confirm MapLibre-globe + deck.gl
interop; fallback is MapLibre-native `fill-extrusion` layers.

---

## 5. API

All under `/api/v1`, JSON, OpenAPI docs at `/docs`. Common query params: `disease`
(default `influenza`), `region` (WHO code), `page`, `page_size`. Surveillance responses
include a `meta` block with `first_week`, `reference_week`, `provisional_from`,
`latest_week`, `sources` and `demo: false`.

**Windows (M3).** Map and Overview endpoints take `to` (any date, snapped to its ISO-week
Monday; default = reference week) and `weeks` (1–52). The comparison window is the
`weeks` immediately before. Time series take `from`/`to`.

**Aggregation rules (M3)**, implemented once in `services/api/app/queries/common.py`:
- *Detections* = sum of `positives` over all rows in the window.
- *Positivity* = Σ positives / Σ specimens, pooled over rows whose weekly positivity is
  valid (tests > 0, positives ≤ tests). Not a mean of country rates; high-testing
  countries weigh more.
- A country-week is *reported* when specimens tested > 0. Time series return a complete
  weekly calendar with `reported: false` for gaps (never zero-filled).
- *Top movers*: largest absolute positivity change vs. the previous window among
  countries with ≥ 50 valid specimens in both windows (`movers_min_specimens`).
- Indicators from later milestones (anomalies, hotspots, threshold exceedances) are
  returned as `pending` with the milestone that adds them, never as numbers.
- *Rates from few specimens* (< 10 in the window or week) are not ranked, not used
  for season peaks and not plotted as positivity; they are shown muted or grey.
- *Monthly / yearly buckets* (M4): a week belongs to the month of its Thursday and to
  its ISO year. A bucket that extends past the reference week is `partial`.
- Validation errors use the same envelope: `{"error": {"code": "invalid_parameter", ...}}`.

| Endpoint | Serves |
|---|---|
| `GET /meta/status` | Reference week, provisional weeks, last ingestion/training runs |
| `GET /diseases` | Diseases + capability flags (M3) |
| `GET /countries` | Country list with tier and 4-week values to the reference week; `q`, `region`, `sort`, `order`, paginated (M4) |
| `GET /countries/{iso3}` | Profile: metadata, season type, population, health indicators (latest year each, null = not available), coverage, recent 4-week values |
| `GET /countries/{iso3}/timeseries` | Weekly series (+ provisional flags) |
| `GET /countries/{iso3}/seasons` | Season-aligned curves (NH: W40–W39; SH/YR: ISO year), peaks, COVID flag, MEM thresholds per season (M6) |
| `GET /overview` | KPIs, global trend, top movers |
| `GET /surveillance/global` | Per-country values for one week/window (map layers) |
| `GET /geo/countries` | Simplified country geometries (GeoJSON, cached) |
| `GET /analytics/trends` | Weekly/monthly/yearly buckets per series (ISO3, `region:<code>`, `world`; max 6): positivity, detections, specimens, A/B mix, change vs previous bucket, `partial` flag (M4) |
| `GET /analytics/heatmap` | Pooled positivity by ISO week × ISO year for one series (M4) |
| `GET /forecasts?iso3=` | Stored forecasts for one country from the current run, all models; reason when none (M5) |
| `GET /forecasts/{id}/explanation` | SHAP contributors |
| `GET /models` · `GET /models/{id}` | Current run with pooled metrics · one version: metrics vs seasonal naive, error by origin, per-country metrics, global importance (M5) |
| `GET /backtest?iso3=&model_version_id=` | Out-of-sample backtest predictions vs actuals for one country (M5) |
| `GET /anomalies?to&weeks&region&iso3&method` | Anomalous country-weeks in a window + per-country summary (M6) |
| `GET /hotspots?to&region` | Gi* and Local Moran per country for the 4-week window ending at `to` (M6) |
| `GET /detection/history` | Weekly counts of hot/cold-spot and anomaly countries (M6) |
| `GET /risk?region` | Risk per country + not-assessed countries with reasons (M6) |
| `GET /countries/{iso3}/detection` | Thresholds, risk, last-52-week anomalies, hotspot status (M6) |
| `GET /forecasts/global?horizon` | Active model's latest forecasts for every country (forecast-change layer, M6) |
| `GET /alerts?region&iso3&type&severity&status&from&to` | Alerts with facet counts and rule texts (M7) |
| `GET /reports` · `GET /reports/{id}` | Stored reports (M7) |
| `POST /reports/generate` | Build a template report from stored data; reuses an identical one (M7) |
| `GET /reports/{id}/verify` | Regenerate and compare hash and Markdown (M7) |
| `GET /about` | Sources with licences and stored rows, coverage tiers, current forecast and detection runs, limitations (M7) |

No auth in MVP: everything is read-only public data except `POST /reports/generate`,
which only reads stored results (rate-limited).

---

## 6. ML pipeline

### 6.1 Data preparation
1. Load cleaned weekly series for countries in Tier A and B.
2. Reindex to a complete weekly calendar; mark missing weeks (not zero-filled).
3. Mask: provisional weeks, COVID disruption window, weeks with < 10 tests (positivity
   too noisy).

### 6.2 Forecasting
- **Primary target (MVP):** weekly **positivity** per country (modelled on logit scale).
  Second target, added once positivity is done: `log1p(positives)`.
- **Horizons:** 1, 2, 4 weeks; **direct** strategy (one model per horizon).
- **Model scope:** one **pooled global model** per horizon across all eligible countries
  (much more training data than per-country models), with country descriptors as
  features. Baselines are per country.
- **Features** (all computed from data available at the forecast origin):

| Group | Features |
|---|---|
| Autoregressive | positivity lags 1–4, rolling mean/std 4 and 8 weeks, change over 1/2/4 weeks |
| Seasonal memory | positivity at same ISO week last year (±1 week mean), last season's peak |
| Calendar | ISO week sin/cos, weeks since hemisphere season start |
| Testing | log specimens tested lag 1, testing trend |
| Spatial | mean positivity of the other countries in the transmission zone (M5); mean of spatial neighbours (queen, else 4 nearest) at the origin and its 2-week change (M6 — backtest MASE 0.378/0.451/0.578 vs 0.378/0.452/0.580 without: a negligible gain, kept) |
| Static | hemisphere, transmission zone, latitude of centroid |

- **Models:** seasonal-naive, last-value, 4-week moving average (baselines) → Random
  Forest → XGBoost. LSTM only evaluated post-MVP, adopted only if it beats XGBoost.
- **Backtesting:** rolling origin, expanding window. Origins every 2 weeks from
  2024-10 to the reference week (two full northern and southern seasons). Training
  window at each origin ends at the origin; no future data, no random splits.
- **Metrics:** MAE, RMSE, MASE (scaled by in-sample seasonal-naive), skill vs.
  seasonal-naive, interval coverage at 80% and 95%. Reported pooled and per country.
- **Intervals:** split conformal prediction from backtest residuals, per model and
  horizon, normalised by 8-week volatility (floor 0.3 logit). Score =
  |logit(observed) − logit(forecast)| with observed positivity clipped to [0.1%, 99.9%];
  a bound that reaches the clip becomes 0% / 100%. *M5 finding:* scoring against the
  smoothed target left every 0%-positivity week (12% of cases) outside the interval and
  gave 72% / 84% coverage; the consistent score gives ~79% / 94%. Backtest coverage
  is sequential (calibrated on earlier origins only); the first 6 origins have none.
  **Mondrian by testing volume** (4-week mean specimens/week at the origin: < 50,
  50–200, 200–1000, ≥ 1000; pooled fallback below 30 scores): pooled quantiles let
  sampling noise from low-volume countries widen every interval (US 1-week 95%: 0–66%);
  per-group calibration keeps coverage in every group and gives ~2–15% for the US.
- **Backtest cadence (M5):** ML models are refitted every 8 weeks of origins (expanding
  window) rather than at every origin, to keep a run under ~15 minutes.
- **Selection:** per horizon, the active model is the best on backtest MASE **and** must
  beat seasonal-naive; otherwise the baseline stays active and the UI says so. The
  selection note also reports the margin over the strongest baseline (often
  last-value), which is the more demanding comparison.
- **Explainability:** SHAP TreeExplainer for RF/XGBoost — global importance per model
  version; top-8 contributors stored per forecast.
- **Registry:** each training run writes a `model_versions` row, `model_evaluations`
  rows, an artefact under `models/<disease>/<target>/<version>/` (model + config +
  feature list), and a model card in `docs/models/`.

### 6.3 Seasonal thresholds and risk
- Per country per season, compute an **epidemic threshold** and **intensity levels**
  (medium/high/very high) from previous non-COVID seasons, following the Moving
  Epidemic Method approach used in WHO's PISA guidance. Implemented in Python and
  checked against the reference R `mem` package on a few countries.
- Countries with < 3 usable past seasons get no thresholds → risk "Not assessed".
- *M6 implementation:* `pipeline/src/ei_pipeline/detection/mem.py` ports `memmodel()` (R
  `mem` 2.19, default settings: slope criterion 2.8 on the smoothed MAP curve; epidemic
  threshold = one-sided 95% point limit of the arithmetic mean of the n highest pre-epidemic
  values, n = round(30/seasons); intensity = one-sided 40/90/97.5% limits of the geometric
  mean of the n highest epidemic values). **Validated:** identical to R to 1e-8 on mem's
  `flucyl` data, a synthetic set with zeros and a 53-week season, and 12 FluNet countries
  (`scripts/validate_mem.R`, R run in Docker). One difference: gaps inside a season are
  linearly interpolated (R uses a cross-validated kernel smoother); usable seasons are
  ≥ 75% complete, non-COVID and finished.
- *M6 finding — scope:* MEM assumes one epidemic per season. For year-round (FluNet `YR`)
  countries the calendar-year season cuts through several waves; 49 of 70 gave an
  epidemic threshold above medium intensity. MEM is therefore applied to NH/SH countries
  only; YR countries are "not assessed" with that reason. A quality gate (levels ordered,
  epidemic > 0, very high < 100%) flags MEM output that is unusable (e.g. JPN, POL, GBR,
  where some weeks report > 90% positivity); flagged levels are stored with the note and
  never drive risk. Result at reference week 2026-10-12: 32 countries with usable
  current-season levels, 28 with a risk level.
- **Risk rule** (shown in UI): forecast at horizon 2 below epidemic threshold = Low;
  between epidemic threshold and high intensity = Moderate; at or above high intensity =
  High. The interval is shown alongside the level.
- **Dengue (D5)** uses the endemic channel instead of MEM: the same rule with the target
  week's top of the channel (75th percentile) and 90th percentile (`datasets/dengue.md`).

### 6.4 Anomaly detection
- Expected value = seasonal baseline (median and 90th percentile of the same ISO week
  ±1 over the last 5 usable seasons).
- Flag when observed positivity exceeds the upper band **and** an EWMA control chart on
  the residual signals; severity from the standardised residual.
- Isolation Forest (positivity, tests, growth) as a secondary signal, reported
  separately, never alone as an alert trigger.
- *M6 implementation:* baseline = same ISO week ±1 in the latest 5 years with data,
  outside the COVID window (needs ≥ 3 years); residual standardised by
  (p90 − median)/1.2816, floored at 2 pp; EWMA λ 0.3, L 3 over consecutive valid weeks
  after the COVID window. Severity: r < 3 moderate, 3–5 high, ≥ 5 severe. Stored for
  weeks from 2023 (history for timelines). 7.9% of checked country-weeks since 2023 are
  flagged; flags cluster in seasons that started early or late relative to the 5-year
  baseline (e.g. the early 2026/27 rise in USA, CAN, GBR, DNK).

### 6.5 Hotspot detection
- Input: 4-week mean positivity per country ending at the reference week.
- Spatial weights: queen contiguity from Natural Earth polygons, plus k-nearest
  neighbours (k=4) for islands/countries without land neighbours; row-standardised.
- Statistics: Getis-Ord Gi\* (hot/cold spots) and Local Moran's I (cluster/outlier
  type), 999 permutations, Benjamini–Hochberg FDR at 0.05.
- Only countries with data in the window participate; the UI marks the rest as "no
  data", not "cold".
- *M6 implementation:* participants need ≥ 10 specimens in the window and a polygon;
  kNN fallback applies to countries with no participating land neighbour. Inference is
  conditional permutation as in PySAL `esda`, with one change: ties count against
  significance on both sides (with many countries at 0% positivity, esda's `>=` folding
  calls a tie at the minimum "extreme", p = 0.001). Computed for every week from
  2025-01-06 (history and the time slider). Finding: after FDR only ~1 hot and ~1 cold
  spot per week pass (≈ 18% of countries have uncorrected p < 0.05); the map shows
  uncorrected p < 0.05 in a lighter tone, labelled as suggestive. Gi* describes the
  neighbourhood, so a high-positivity country among low neighbours can be a "cold spot"
  (Local Moran calls it an HL outlier); the UI explains both.

### 6.6 Alerts and reports
Rules generate alerts from stored outputs (new anomaly, new hotspot, risk escalation,
sustained growth > documented rate). Reports are deterministic templates over stored
facts; each report stores its input hash so it can be reproduced.

*M7 implementation* (`pipeline/src/ei_pipeline/intelligence/alerts.py`, run at the end of
`ei detect run`; alerts from 2025-01-06):
- **new_anomaly**: first week of a seasonal-EWMA anomaly episode; severity moderate/high/
  severe → low/medium/high.
- **new_hotspot**: enters a Gi* hot spot (FDR < 0.05) this week, not last week; medium.
- **risk_escalation**: risk moderate or high, first assessment or up from the previous one.
  Risk rows are therefore kept across runs (one per country and assessed week; thresholds
  copied in) — the only detection output with history.
- **sustained_growth**: positivity up 3 consecutive weeks, ≥ 5 pp in total, ≥ 50 specimens
  each week; medium when ≥ 10 pp.
- Alerts are upserted on (country, type, week); an alert a rerun no longer produces is
  marked `retracted`, never deleted, so report links stay valid. First run: 630 active
  alerts (339 anomaly, 252 growth, 37 hotspot, 2 risk).

Reports (`services/api/app/reports/`): `facts.gather()` collects summary, weekly values,
movers, forecasts, MEM levels, risk, anomalies, clusters and alerts for a scope (global,
WHO region or country) and period, in canonical JSON (floats to 6 decimals, fixed order,
no timestamps); `render.render_markdown()` is a pure function of those facts (fixed month
names, no locale). `inputs_sha256` = SHA-256 of the canonical facts. Generating with
identical inputs reuses the existing report. `GET /reports/{id}/verify` checks that the
stored facts re-render to the stored Markdown and that gathering again gives the same hash
and Markdown; when data has changed since (new ingestion, forecast or detection run) it
lists the changed sections. `POST /reports/generate` is rate-limited (10/min per client).

---

## 7. Data flow

Weekly run (`pipeline/scripts/weekly.sh`: migrations → `ei weekly` → `python -m app.cli report` (global report per disease);
scheduled by `.github/workflows/weekly.yml`, Wednesdays 06:00 UTC), each step idempotent
and recorded; the first failing step stops the run:

```mermaid
sequenceDiagram
    participant S as Sources
    participant P as Pipeline
    participant DB as Postgres/PostGIS
    participant M as models/
    participant A as API
    participant W as Web

    P->>S: download FluNet CSV (+ population, yearly)
    P->>P: clean · validate · quality report
    P->>DB: upsert surveillance_weekly, log revisions, ingestion_runs
    P->>DB: recompute coverage_profiles (tiers), provisional flags
    P->>DB: read eligible series
    P->>P: build features · backtest · fit
    P->>M: save artefacts
    P->>DB: model_versions, model_evaluations
    P->>DB: forecasts + SHAP, thresholds, risk, anomalies, hotspots
    P->>DB: alerts, reports
    W->>A: GET /overview?disease=influenza&...
    A->>DB: query stored results
    A-->>W: JSON + meta (reference week, sources)
```

Retraining cadence: *as built (M8)*, every weekly run does the full backtest, selection
and retrain, which fits comfortably in the CI time budget; the planned monthly retrain
with weekly re-forecasting remains an option if runtime grows. `ei prune` keeps
per-country metrics and SHAP detail for the latest 8 forecast runs only (older runs keep
pooled metrics and forecasts). Deployment: [DEPLOYMENT.md](DEPLOYMENT.md).

---

## 8. Folder structure

```
M.I.N.E.R.V.A/
├── apps/
│   └── web/                       Next.js app
│       ├── src/app/               routes (see §4)
│       ├── src/components/
│       │   ├── layout/            sidebar, topbar, filters
│       │   ├── globe/             MapLibre + deck.gl layers
│       │   ├── charts/            ECharts wrappers
│       │   └── ui/                shadcn/ui primitives
│       ├── src/lib/               api client, query hooks, formatters
│       └── src/styles/            design tokens
├── services/
│   └── api/
│       ├── app/
│       │   ├── main.py
│       │   ├── routers/           one module per resource
│       │   ├── schemas/           Pydantic response models
│       │   ├── queries/           SQL/ORM query functions
│       │   └── core/              config, db session, errors, caching
│       └── tests/
├── pipeline/
│   ├── src/ei_pipeline/
│   │   ├── sources/               flunet.py, natural_earth.py, worldbank.py
│   │   ├── ingest/                load to DB, revisions, quality checks
│   │   ├── features/
│   │   ├── models/                baselines, rf, xgb, conformal, registry
│   │   ├── evaluation/            backtesting, metrics
│   │   ├── detection/             anomalies, hotspots, thresholds, risk
│   │   ├── reporting/             alerts, report templates
│   │   └── cli.py                 `ei` command
│   ├── scripts/                   one-off analysis (profile_flunet.py)
│   └── tests/
├── packages/
│   └── ei_db/                     SQLAlchemy models + Alembic migrations
├── models/                        trained artefacts (gitignored)
├── data/
│   ├── raw/                       downloads (gitignored)
│   └── profiles/                  generated profiles
├── docs/
│   ├── PROJECT_SPEC.md
│   ├── DESIGN.md
│   ├── datasets/
│   └── models/                    model cards
├── infra/
│   └── docker-compose.yml         postgres+postgis (+ api, web)
├── .github/workflows/             ci.yml, weekly-pipeline.yml
├── .env.example
└── README.md
```

---

## 9. Milestones

Each ends with: what was built, files changed, how to run, how to test.

| # | Milestone | Delivers | Done when |
|---|---|---|---|
| M0 | Spec + data verification | Spec v2, FluNet profiler, dataset docs | ✅ done |
| M1 ✅ | Foundation | Monorepo skeleton, Postgres+PostGIS running, `ei_db` with core tables (reference + observations) and first migration, FastAPI `/health` + `/meta/status`, Next.js shell with design tokens, sidebar/topbar, **globe spike** rendering Natural Earth countries, CI (lint + tests) | `docker compose up` (or local equivalent) → web shows shell + rotating globe; API tests pass |
| M2 ✅ | Data ingestion | Natural Earth, World Bank population, FluNet ingestion into DB with code aliases, quality report, revisions, provisional flags, coverage tiers; `ei ingest …` CLI | DB holds ~146k country-weeks; re-running is idempotent; quality report stored |
| M3 ✅ | Surveillance core | API: countries, timeseries, overview, surveillance/global, geo · Web: Overview + Global Surveillance wired to real data (choropleth, columns, time slider, country panel) | Every number on both pages traces to DB rows; filters work end-to-end |
| M4 ✅ | Country + Analytics | Country Intelligence (history, seasons, context) and Analytics pages; health indicators ingestion | Drill-down from globe to country works for all 189 areas, "Not available" where missing |
| M5 ✅ | Forecasting | Feature builder, baselines, RF, XGBoost, rolling-origin backtest, conformal intervals, registry, SHAP; Prediction Center + model detail pages | Backtest report generated; active model beats seasonal-naive or baseline is shown as active |
| M6 ✅ | Detection | Seasonal thresholds, risk, anomalies, Gi\*/Local Moran hotspots; Hotspots & Anomalies page; globe layers | Outputs stored per weekly run; layers toggle on globe |
| M7 ✅ | Intelligence | Alerts, template reports, Reports & Alerts page, About the Data, model cards | Report regenerates identically from stored inputs |
| M8 ✅ | Hardening + deploy | Test coverage, accessibility/responsive pass, Docker images, weekly GitHub Actions pipeline, deployment (Vercel + Render/Fly + Supabase/Neon) | Public URL with live data; weekly job green |
| Post-MVP | Expansion | Dengue + Open-Meteo weather, positives target, LSTM evaluation, optional LLM summaries, auth | — |

---

## 10. Risks and open decisions

| Item | Notes |
|---|---|
| Local database setup | **Resolved in M1.** Docker Desktop (WSL2) with `postgis/postgis:16-3.4` via Compose, matching deployment. |
| MapLibre globe + deck.gl interop | **Resolved in M1 spike.** deck.gl 9.4 *interleaved* mode renders nothing on MapLibre 6 (no error); *overlaid* mode works on globe and flat projections. Consequence: deck layers always draw above map layers. MapLibre 6 also needs its worker served explicitly (`setWorkerUrl`, copied by `apps/web/scripts/copy-maplibre-worker.mjs`). |
| Node.js version | Tailwind 4.3 needs `require(esm)` → Node ≥ 20.19. Project standard: Node 26 LTS (`.nvmrc`). Node 20 is end-of-life. |
| Boundary resolution | **Resolved in M2.** 1:50m boundaries in PostGIS, served by `GET /api/v1/geo/countries` (simplified, gzip ~0.5 MB, ETag). Overseas departments (GLP, GUF, MTQ) have no own geometry — see [natural_earth.md](datasets/natural_earth.md). |
| MEM thresholds in Python | **Resolved in M6.** Python port validated against R `mem` 2.19 (exact match). MEM applies to temperate (NH/SH) countries only; year-round countries have no thresholds or risk level. A documented alternative for tropical countries (e.g. percentile thresholds) is an open option. |
| Data revisions | FluNet back-fills; ingestion keeps revision history and forecasts record which data snapshot they used. |
| Hosting cost | All target hosts have free tiers. The database is ~110 MB; each forecast run adds ~10 MB before `ei prune` trims runs beyond the latest 8 (M8), keeping within ~0.5 GB free-tier storage. Free Render instances sleep when idle (cold start up to a minute). |
| FluNet export integrity | **Found in M8.** WHO's CDN cached a stale, truncated copy of the export for the default `Accept-Encoding` variant. Downloads are now checked record by record; other request variants are tried; a malformed export fails the run and keeps the previous file. |
| Licences | Confirm FluNet attribution wording before public deployment. |
