FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /srv/backend
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/app ./app
COPY postgres /srv/postgres
RUN useradd --create-home --uid 10001 appuser && mkdir /data && chown appuser:appuser /data

FROM base AS test
COPY backend/requirements-dev.txt ./
RUN pip install --no-cache-dir -r requirements-dev.txt
COPY backend/tests ./tests
COPY pyproject.toml /srv/backend/
CMD ["pytest", "-v"]

FROM base AS runtime
USER appuser
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--no-access-log"]
