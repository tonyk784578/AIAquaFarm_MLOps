FROM python:3.11-slim

# /src is the project root; source lives in /src/agents/ so `import agents` works.
WORKDIR /src

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy pyproject first so dependency layer is cached separately from source.
COPY pyproject.toml .
# Install dependencies only (package itself has no source yet — use --no-build-isolation
# with hatchling to allow dep pre-install without full build).
RUN pip install --no-cache-dir \
    "fastapi>=0.115.0" \
    "uvicorn[standard]>=0.30.0" \
    langgraph \
    langchain-anthropic \
    langchain-core \
    "anthropic>=0.40.0" \
    "httpx>=0.27.0" \
    "redis[asyncio]>=5.0.0" \
    "pydantic>=2.7.0" \
    "pydantic-settings>=2.3.0" \
    "structlog>=24.2.0" \
    "tenacity>=8.3.0"

# Place source in agents/ so hatchling can find the package.
COPY . agents/

# Install the package itself (deps already present, so --no-deps is safe).
RUN pip install --no-cache-dir --no-deps .

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
  CMD curl -f http://localhost:8001/health || exit 1

CMD ["uvicorn", "agents.main:app", "--host", "0.0.0.0", "--port", "8001"]
