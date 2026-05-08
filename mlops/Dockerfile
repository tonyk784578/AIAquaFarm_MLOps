FROM python:3.11-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    curl \
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
    "schedule>=1.2.0"

COPY . .

CMD ["python", "-m", "data_collector.sensor_collector"]
