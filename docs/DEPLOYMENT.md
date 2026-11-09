# Deployment

Three hosted pieces plus a scheduled job. Each runs on a free tier; free-tier limits change, so
check the provider's current terms before relying on them.

| Piece | Host | What runs | Configured by |
|---|---|---|---|
| Database | Neon (or Supabase) | PostgreSQL 16 + PostGIS | connection string |
| API | Render (Docker) | `services/api/Dockerfile` | `render.yaml` |
| Web | Vercel | `apps/web` (Next.js) | Vercel project settings |
| Weekly job | GitHub Actions | `.github/workflows/weekly.yml` → `pipeline/scripts/weekly.sh` | `DATABASE_URL` secret |

```
browser ──► Vercel (web) ──fetch──► Render (API) ──► Neon (PostGIS)
                                                       ▲
GitHub Actions, Wednesdays 06:00 UTC: migrate → ingest → forecast → detect → prune → report
```

## Order of setup

1. **Push the repo to GitHub.** CI (`ci.yml`) runs lint, tests with coverage gates, the web
   build and a Docker build + smoke test on every push and pull request.

2. **Database (Neon).** Create a project (PostgreSQL 16). Copy two connection strings from the
   dashboard:
   - *direct* (host without `-pooler`) for the weekly job, which runs migrations;
   - *pooled* (host with `-pooler`) for the API.

   Plain `postgresql://…?sslmode=require` URLs work as given; the code switches them to the
   psycopg driver. The first migration runs `CREATE EXTENSION postgis`, which Neon and Supabase
   both allow. The full database is ~110 MB. Each forecast run adds ~10 MB; `ei prune` (part of
   the weekly job) trims runs older than the latest 8 to their pooled metrics and forecasts,
   which by our estimate leaves growth at a few MB a week.

3. **Load the data.** In GitHub: *Settings → Secrets and variables → Actions*, add
   `DATABASE_URL` = the direct connection string. Then *Actions → Weekly pipeline → Run
   workflow*. On an empty database this migrates, ingests every source, trains and selects the
   forecast models, runs detection and alerts, and writes the first weekly report (see the run
   summary for each step's counts). Without the secret the same workflow runs against a
   throwaway database, which is a safe way to test it first.

4. **API (Render).** *New → Blueprint*, pick the repo; Render reads `render.yaml`. Enter:
   - `DATABASE_URL` — the pooled connection string;
   - `API_CORS_ORIGINS` — the web URL from step 5 (comma-separated if several);
   - `API_CORS_ORIGIN_REGEX` — optional, to allow Vercel preview URLs.

   Check `https://<service>.onrender.com/api/v1/meta/status`. Free instances sleep when idle,
   so the first request after a quiet period takes up to a minute; the web app shows
   "Checking…" meanwhile and then loads.

5. **Web (Vercel).** *Add New → Project*, import the repo, set **Root Directory** to
   `apps/web` (framework: Next.js, detected) and add the environment variable
   `NEXT_PUBLIC_API_BASE_URL = https://<service>.onrender.com/api/v1`. The value is compiled
   into the browser bundle, so redeploy after changing it. Then put the Vercel URL into the
   API's `API_CORS_ORIGINS`.

## Weekly job

`weekly.yml` runs every Wednesday at 06:00 UTC and on demand (*Run workflow*; tick *fast*
for a quick check with small models). It stops at the first failing step, so a report is only
written from fully updated data; a red run leaves the previous data in place.

Known source issue (Nov 2026): WHO serves the FluNet export through a CDN that caches each
`Accept-Encoding` variant separately, and one variant was a stale, truncated copy. The
downloader therefore checks that every record has the header's field count, tries the other
request variants when it does not, and fails the job (keeping the previous file) if none is
complete. A red run with `MalformedExport` means the source was broken, not the pipeline;
re-run later.

Model artefacts and the model card of each run are kept as workflow artifacts for 30 days;
the database keeps what the app needs (registry, metrics, forecasts, explanations).

## Schema changes

The API does not migrate on start. After merging a migration, run the weekly workflow (it
migrates first), or locally:

```bash
DATABASE_URL=<direct url> alembic -c packages/ei_db/alembic.ini upgrade head
```

Migrations so far only add tables or columns or relax constraints, so deploying the API first
and migrating right after is safe; a migration that renames or drops something must run
first.

## Running the images yourself

```bash
# Full stack on one machine (database, API on :8000, web on :3000)
docker compose -f infra/docker-compose.yml --profile app up -d --build
docker compose -f infra/docker-compose.yml --profile jobs run --rm pipeline   # load data

# Individual images (build from the repo root; web from apps/web)
docker build -f services/api/Dockerfile -t ei-api .
docker build -f pipeline/Dockerfile --build-arg GIT_SHA=$(git rev-parse HEAD) -t ei-pipeline .
docker build --build-arg NEXT_PUBLIC_API_BASE_URL=https://api.example.org/api/v1 -t ei-web apps/web
```

| Image | Size | Runs as | Health check |
|---|---|---|---|
| API | ~290 MB | uid 10001 | `GET /api/v1/health` |
| Web | ~450 MB | `node` | `GET /` |
| Pipeline | ~1.8 GB (XGBoost, SHAP) | uid 10001 | batch job, exit code |

## Configuration reference

| Variable | Used by | Default | Notes |
|---|---|---|---|
| `DATABASE_URL` | API, pipeline | local Docker DB | `postgres://`, `postgresql://` or `postgresql+psycopg://` |
| `API_CORS_ORIGINS` | API | `http://localhost:3000` | comma-separated exact origins |
| `API_CORS_ORIGIN_REGEX` | API | none | extra origins by pattern |
| `API_CACHE_MAX_AGE` | API | `300` | seconds browsers/CDNs may cache GETs; `0` disables |
| `FORWARDED_ALLOW_IPS` | API image | `*` | proxies trusted for client IPs (rate limit) |
| `NEXT_PUBLIC_API_BASE_URL` | web build | `http://localhost:8000/api/v1` | build-time |
| `EI_ROOT` | pipeline | repo root | where `data/raw`, `models`, `docs/models` live |
| `EI_WEEKLY_ARGS` | weekly script | none | e.g. `--fast`, `--keep 12` |
| `EI_REPORT_WEEKS` | weekly script | `4` | period of the weekly report |
| `EI_GIT_SHA` | pipeline | git / `GITHUB_SHA` | stored with each model version |

## Hardening in place

- API responses carry `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`,
  `Referrer-Policy: no-referrer`; successful GETs are cacheable for 5 minutes, while status,
  reports and errors are `no-store`.
- CORS allows only the configured origins and `GET`/`POST`.
- The only write endpoint (`POST /reports/generate`) is rate-limited per client address
  (10/min, in memory per process; behind the platform proxy the real address comes from
  `X-Forwarded-For`).
- No credentials in the repo: every secret is an environment variable or GitHub secret.
- Containers run as non-root users and have health checks.
