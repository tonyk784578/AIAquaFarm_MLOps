FROM python:3.11-slim AS base

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# ── Development ────────────────────────────────────────────────
FROM base AS development

# ai_modules lives at project root; installed as an editable package
# so hot-reload picks up changes without rebuilding the image.
COPY ai_modules/ /app/ai_modules/
RUN pip install -e /app/ai_modules

COPY backend/pyproject.toml /app/pyproject.toml
RUN pip install -e ".[dev]"

COPY backend/ /app/

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# ── Production ─────────────────────────────────────────────────
FROM base AS production

COPY ai_modules/ /app/ai_modules/
RUN pip install /app/ai_modules

COPY backend/pyproject.toml /app/pyproject.toml
RUN pip install --no-deps .

COPY backend/ /app/

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
