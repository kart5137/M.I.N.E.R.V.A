# M.I.N.E.R.V.A. pipeline (ingestion, forecasting, detection, weekly report).
#   docker build -f pipeline/Dockerfile --build-arg GIT_SHA=$(git rev-parse HEAD) -t ei-pipeline .
#   docker run --rm -e DATABASE_URL=... ei-pipeline            # the full weekly job
#   docker run --rm -e DATABASE_URL=... ei-pipeline ei detect run
FROM python:3.13-slim

# libgomp: OpenMP runtime for XGBoost and scikit-learn.
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

ARG GIT_SHA=""
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONIOENCODING=utf-8 \
    PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1 \
    EI_ROOT=/app EI_GIT_SHA=${GIT_SHA}

WORKDIR /app
COPY packages/ei_db packages/ei_db
COPY services/api services/api
COPY pipeline pipeline
# The API package provides the report generator used at the end of the weekly job.
RUN pip install ./packages/ei_db ./services/api ./pipeline \
    && useradd --system --uid 10001 --home-dir /app app \
    && mkdir -p data/raw models docs/models && chown -R app /app/data /app/models /app/docs

USER app
WORKDIR /app/services/api
CMD ["sh", "/app/pipeline/scripts/weekly.sh"]
