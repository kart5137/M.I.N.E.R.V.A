# M.I.N.E.R.V.A.

**Monitoring & Intelligence Network for Epidemic Risk, Visualisation and Alerts**

Global influenza surveillance and outbreak-forecasting platform with a 3D geographic
dashboard, built on public WHO FluNet data.

> Analytical and educational tool. Not a diagnostic tool and not a substitute for
> official public-health guidance.

**Live:** https://m-i-n-e-r-v-a.vercel.app · API https://minerva-api-0d86.onrender.com/docs (free tier: the first request after an idle spell can take up to a minute).

**Status:** MVP complete (M0–M8). Data refreshes every Wednesday via [the weekly workflow](.github/workflows/weekly.yml); hosting is described in [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md). See [docs/DESIGN.md](docs/DESIGN.md#9-milestones).

| Doc | |
|---|---|
| [docs/PROJECT_SPEC.md](docs/PROJECT_SPEC.md) | Scope and requirements |
| [docs/DESIGN.md](docs/DESIGN.md) | Architecture, schema, ML pipeline, milestones |
| [docs/datasets/](docs/datasets/README.md) | Verified data sources and coverage profile |
| [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) | Hosting, weekly job, images, configuration |

## Layout

```
apps/web          Next.js dashboard (3D globe: MapLibre GL + deck.gl)
services/api      FastAPI REST API
pipeline          Ingestion, profiling and (later) ML jobs
packages/ei_db    Shared SQLAlchemy models + Alembic migrations
infra             Docker Compose (PostgreSQL 16 + PostGIS 3.4)
```

## Prerequisites

- **Python 3.12+** (3.13 used in development)
- **Node.js 26 LTS** (see `.nvmrc`; ≥ 20.19 required by Tailwind 4.3)
- **Docker Desktop** with **WSL2** (for the PostGIS database; on Windows Home run `wsl --install` as administrator first)

## Setup

```powershell
# from the repo root
copy .env.example .env

# Python (one virtualenv for API + pipeline)
py -3.13 -m venv .venv
.venv\Scripts\python -m pip install -e packages/ei_db -e "services/api[dev]" -e "pipeline[dev]"

# Web
cd apps/web
npm ci
```

## Run

```powershell
# 1. Database
docker compose -f infra/docker-compose.yml up -d

# 2. Schema
cd packages/ei_db
..\..\.venv\Scripts\alembic upgrade head

# 3. Data (downloads WHO FluNet, Natural Earth, World Bank; ~1 min)
cd ../..
.venv\Scripts\ei ingest all

# 4. Forecasts: backtest, model selection, training, SHAP (~15-20 min; writes
#    models/ artefacts and docs/models/influenza-positivity.md)
.venv\Scripts\ei forecast run

# 4b. Detection + alerts: MEM thresholds, risk, anomalies, hotspots, alerts
#     (~1 min; run after 4). Reports are generated on demand in the web app
#     (Reports & Alerts) or with POST /api/v1/reports/generate.
.venv\Scripts\ei detect run

# Or 3-4b plus pruning in one go, as the scheduled job does (re-downloads
# FluNet), followed by the weekly report:
.venv\Scripts\ei weekly
cd services/api; ..\..\.venv\Scripts\python -m app.cli report --weeks 4

# 5. API → http://localhost:8000/docs
cd services/api
..\..\.venv\Scripts\uvicorn app.main:app --reload --port 8000

# 6. Web → http://localhost:3000
cd apps/web
npm run dev
```

Everything in containers instead (database, API, web; then load data):

```powershell
docker compose -f infra/docker-compose.yml --profile app up -d --build
docker compose -f infra/docker-compose.yml --profile jobs run --rm pipeline
```

The dashboard shows live platform readiness (API → database → schema → data) in the
top-right status pill and on the Overview page.

## Test

```powershell
.venv\Scripts\ruff check packages services pipeline
cd services/api; ..\..\.venv\Scripts\pytest -q --cov=app       # CI gate: 90% coverage
cd pipeline; ..\.venv\Scripts\pytest -q --cov=ei_pipeline     # separate test database
cd apps/web; npm run lint; npm run typecheck; npm test; npm run build
```

CI runs the same checks plus a Docker build and smoke test
([.github/workflows/ci.yml](.github/workflows/ci.yml)); the scheduled weekly job is
[.github/workflows/weekly.yml](.github/workflows/weekly.yml).

## Data profiling

```powershell
.venv\Scripts\python pipeline\scripts\profile_flunet.py --download
```

Writes `docs/datasets/flunet_profile.md` and `data/profiles/flunet_country_profile.csv`.

The dengue equivalent is `pipeline\scripts\profile_dengue.py [--download]`
(writes `docs/datasets/dengue_profile.md` and `data/profiles/dengue_country_profile.csv`).

## Attribution

- Influenza data: WHO FluNet, Global Influenza Surveillance and Response System (GISRS).
- Country boundaries: Natural Earth (public domain).
- Population: World Bank, World Development Indicators (CC BY 4.0).
