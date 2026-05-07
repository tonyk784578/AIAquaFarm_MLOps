"""Application configuration via pydantic-settings.

All configuration is loaded from environment variables (or .env file).
No hard-coded secrets or connection strings anywhere in the codebase.
"""

import json
from functools import lru_cache
from typing import List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Centralised settings loaded from environment variables.

    Usage:
        from app.config import get_settings
        settings = get_settings()
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Application ────────────────────────────────────────────
    app_name: str = "AIAquafarm"
    debug: bool = False
    log_level: str = "info"
    secret_key: str = Field(
        default="dev_secret_change_me",
        description="JWT signing secret — override in production",
    )
    access_token_expire_minutes: int = 60 * 24  # 24 hours

    # ── Database (PostgreSQL + TimescaleDB) ────────────────────
    database_url: str = Field(
        default="postgresql+asyncpg://aquafarm:aquafarm_secret@localhost:5432/aquafarm",
        description="Async PostgreSQL connection URL (asyncpg driver)",
    )
    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_pool_timeout: int = 30

    # ── Redis ──────────────────────────────────────────────────
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        description="Redis connection URL",
    )
    redis_max_connections: int = 20

    # ── MLflow ─────────────────────────────────────────────────
    mlflow_tracking_uri: str = "http://localhost:5000"

    # ── CORS ───────────────────────────────────────────────────
    cors_origins: List[str] = Field(
        default=["http://localhost:3000", "http://localhost"],
        description="Allowed CORS origins",
    )

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: str | List[str]) -> List[str]:
        """Accept CORS origins as JSON string or Python list."""
        if isinstance(v, str):
            return json.loads(v)
        return v

    # ── AI / LLM ───────────────────────────────────────────────
    anthropic_api_key: str = Field(
        default="",
        description="Anthropic API key for LangGraph agents",
    )

    # ── Edge Devices ───────────────────────────────────────────
    camera_stream_url: str = "rtsp://edge-camera:554/stream"
    sensor_poll_interval: int = Field(
        default=5,
        description="Sensor data poll interval in seconds",
    )

    # ── Water Quality Alert Thresholds ─────────────────────────
    ammonia_threshold_ppm: float = Field(default=0.5, ge=0.0)
    nitrite_threshold_ppm: float = Field(default=0.1, ge=0.0)
    dissolved_oxygen_min_mgl: float = Field(default=6.0, ge=0.0)
    ph_min: float = Field(default=6.5, ge=0.0, le=14.0)
    ph_max: float = Field(default=8.5, ge=0.0, le=14.0)
    temperature_min_c: float = Field(default=18.0)
    temperature_max_c: float = Field(default=28.0)

    # ── Storage (Data Lake) ────────────────────────────────────
    # ── Water Quality Model (inference) ───────────────────────────────────
    wq_model_name: str = Field(
        default="WaterQualityPredictor",
        description="Registered model name in MLflow",
    )
    wq_model_stage: str = Field(
        default="Production",
        description="MLflow model stage to load (Production, Staging)",
    )
    wq_model_device: str = Field(
        default="cpu",
        description="PyTorch device (cpu, cuda, mps)",
    )
    wq_mc_samples: int = Field(
        default=50,
        ge=1,
        description="MC-Dropout forward passes for uncertainty estimation",
    )
    wq_checkpoint_path: str = ""
    wq_scaler_path: str = ""

    # ── Storage (Data Lake) ────────────────────────────────────────────────
    s3_endpoint_url: str = ""
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_bucket_name: str = "aquafarm-datalake"


@lru_cache
def get_settings() -> Settings:
    """Return the cached application settings singleton.

    The @lru_cache ensures settings are read from the environment only once,
    making this safe to call in dependency injection contexts.

    Returns:
        Cached Settings instance.
    """
    return Settings()
