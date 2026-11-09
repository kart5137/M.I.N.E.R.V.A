# Epidemic Intelligence

Global influenza surveillance and outbreak-forecasting platform with a 3D geographic
dashboard, built on public WHO FluNet data.

> Analytical and educational tool. Not a diagnostic tool and not a substitute for
> official public-health guidance.

**Status:** Milestone M1 (foundation). See [docs/DESIGN.md](docs/DESIGN.md#9-milestones).

| Doc | |
|---|---|
| [docs/PROJECT_SPEC.md](docs/PROJECT_SPEC.md) | Scope and requirements |
| [docs/DESIGN.md](docs/DESIGN.md) | Architecture, schema, ML pipeline, milestones |
| [docs/datasets/](docs/datasets/README.md) | Verified data sources and coverage profile |

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
- **Node.js 24 LTS** (see `.nvmrc`; ≥ 20.19 required by Tailwind 4.3)
- **Docker Desktop** (for the PostGIS database)

## Setup

```powershell
# from the repo root
copy .env.example .env

# Python (one virtualenv for API + pipeline)
py -3.13 -m venv .venv
.venv\Scripts\python -m pip install -e packages/ei_db -e "services/api[dev]" -r pipeline/requirements.txt

# Web
cd apps/web
npm ci
```

## Run

```powershell
# 1. Database
docker compose -f infra/docker-compose.yml up -d

# 2. Schema (once the first migration exists — see M1 status below)
cd packages/ei_db
..\..\.venv\Scripts\alembic upgrade head

# 3. API → http://localhost:8000/docs
cd services/api
..\..\.venv\Scripts\uvicorn app.main:app --reload --port 8000

# 4. Web → http://localhost:3000
cd apps/web
npm run dev
```

The dashboard shows live platform readiness (API → database → schema → data) in the
top-right status pill and on the Overview page.

## Test

```powershell
.venv\Scripts\ruff check packages services pipeline
cd services/api; ..\..\.venv\Scripts\pytest -q
cd apps/web; npm run lint; npm run typecheck; npm run build
```

CI runs the same checks: [.github/workflows/ci.yml](.github/workflows/ci.yml).

## Data profiling

```powershell
.venv\Scripts\python pipeline\scripts\profile_flunet.py --download
```

Writes `docs/datasets/flunet_profile.md` and `data/profiles/flunet_country_profile.csv`.

## Attribution

- Influenza data: WHO FluNet, Global Influenza Surveillance and Response System (GISRS).
- Country boundaries: Natural Earth (public domain).
