FROM python:3.11-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    curl \
    openssh-client \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
RUN pip install --no-cache-dir \
    "mlflow>=2.13.0" \
    "boto3>=1.34.0" \
    "pandas>=2.2.0" \
    "numpy>=1.26.0" \
    "scikit-learn>=1.5.0" \
    "torch>=2.3.0" \
    "torchvision>=0.18.0" \
    "opencv-python-headless>=4.10.0" \
    "ultralytics>=8.2.0" \
    "httpx>=0.27.0" \
    "redis[asyncio]>=5.0.0" \
    "pydantic>=2.7.0" \
    "pydantic-settings>=2.3.0" \
    "structlog>=24.2.0" \
    "schedule>=1.2.0" \
    "fastapi>=0.115.0" \
    "uvicorn[standard]>=0.30.0" \
    "pytest>=8.2.0" \
    "prometheus-fastapi-instrumentator>=7.0.0" \
    "opentelemetry-api>=1.27.0" \
    "opentelemetry-sdk>=1.27.0" \
    "opentelemetry-exporter-otlp-proto-grpc>=1.27.0" \
    "opentelemetry-instrumentation-fastapi>=0.48b0" \
    "opentelemetry-instrumentation-httpx>=0.48b0" \
    "opentelemetry-instrumentation-requests>=0.48b0"

# Mount the source so the package is importable as ``mlops.*``.
COPY . /app/mlops

# Default command — the scheduler. docker-compose overrides this for the
# api and collector services.
CMD ["python", "-m", "mlops", "scheduler"]
