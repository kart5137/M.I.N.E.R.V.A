#!/bin/sh
# The scheduled weekly job (M8). Used by the pipeline image and the GitHub Actions
# workflow. Stops at the first failing step, so a red run never publishes a report
# built on half-updated data.
set -eu

ROOT="${EI_ROOT:-$(cd "$(dirname "$0")/../.." && pwd)}"

echo "== migrations"
alembic -c "$ROOT/packages/ei_db/alembic.ini" upgrade head

echo "== ingest, forecast, detect, prune"
ei weekly ${EI_WEEKLY_ARGS:-}

echo "== weekly global report"
cd "$ROOT/services/api"
python -m app.cli report --scope global --weeks "${EI_REPORT_WEEKS:-4}"
