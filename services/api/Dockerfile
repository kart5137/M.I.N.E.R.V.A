# M.I.N.E.R.V.A. API. Build from the repo root:
#   docker build -f services/api/Dockerfile -t ei-api .
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1 \
    # Trust X-Forwarded-For from the platform's proxy (Render/Fly), so the report
    # rate limit sees real client addresses. Set to the proxy's address if known.
    FORWARDED_ALLOW_IPS="*" \
    PORT=8000

WORKDIR /app
COPY packages/ei_db packages/ei_db
COPY services/api services/api
RUN pip install ./packages/ei_db ./services/api     && useradd --system --uid 10001 --no-create-home app

USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import os,urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ[\"PORT\"]}/api/v1/health', timeout=4)"
# Migrations: docker run --rm -e DATABASE_URL=... ei-api alembic -c packages/ei_db/alembic.ini upgrade head
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port \"$PORT\" --proxy-headers"]
