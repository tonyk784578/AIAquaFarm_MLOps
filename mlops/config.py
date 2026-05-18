"""MLOps settings — environment-driven configuration for the runtime.

A single ``Settings`` object is shared across the orchestrator, API, and CLI
entry points. Values come from environment variables (``.env`` via
``pydantic-settings``), so the same image can run as scheduler, API, or
ad-hoc CLI.

Usage::

    from mlops.config import get_settings
    settings = get_settings()
    mlflow_uri = settings.mlflow_tracking_uri
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """MLOps runtime settings.

    Attributes mirror the env-vars set in ``docker-compose.yml`` for the
    mlops_scheduler / mlops_api services. Any field can be overridden via the
    matching upper-case env variable.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ── Tracking + storage ─────────────────────────────────────────────────────
    mlflow_tracking_uri: str = Field(
        default="http://mlflow:5000",
        validation_alias="MLFLOW_TRACKING_URI",
    )
    s3_endpoint_url: str | None = Field(default=None, validation_alias="S3_ENDPOINT_URL")
    s3_access_key: str | None = Field(default=None, validation_alias="S3_ACCESS_KEY")
    s3_secret_key: str | None = Field(default=None, validation_alias="S3_SECRET_KEY")
    s3_bucket_name: str = Field(
        default="aquafarm-datalake", validation_alias="S3_BUCKET_NAME"
    )

    # ── Local paths ────────────────────────────────────────────────────────────
    data_dir: Path = Field(default=Path("/data"), validation_alias="MLOPS_DATA_DIR")
    audit_log_path: Path = Field(
        default=Path("/data/audit/automl.jsonl"),
        validation_alias="MLOPS_AUDIT_LOG",
    )
    artifact_dir: Path = Field(
        default=Path("/data/artifacts"), validation_alias="MLOPS_ARTIFACT_DIR"
    )

    # ── Scheduler cadence (minutes) ────────────────────────────────────────────
    automl_interval_minutes: int = Field(
        default=60, validation_alias="MLOPS_AUTOML_INTERVAL_MIN", ge=1
    )
    drift_only_interval_minutes: int = Field(
        default=15, validation_alias="MLOPS_DRIFT_INTERVAL_MIN", ge=1
    )

    # ── Drift detection CSV pairs (optional) ──────────────────────────────────
    wq_reference_csv: str | None = Field(default=None, validation_alias="MLOPS_WQ_REF_CSV")
    wq_current_csv: str | None = Field(default=None, validation_alias="MLOPS_WQ_CUR_CSV")
    feeding_reference_csv: str | None = Field(default=None, validation_alias="MLOPS_FEEDING_REF_CSV")
    feeding_current_csv: str | None = Field(default=None, validation_alias="MLOPS_FEEDING_CUR_CSV")
    growth_reference_csv: str | None = Field(default=None, validation_alias="MLOPS_GROWTH_REF_CSV")
    growth_current_csv: str | None = Field(default=None, validation_alias="MLOPS_GROWTH_CUR_CSV")

    # ── Training data paths ────────────────────────────────────────────────────
    wq_training_csv: str | None = Field(default=None, validation_alias="MLOPS_WQ_TRAIN_CSV")
    feeding_training_dir: str | None = Field(default=None, validation_alias="MLOPS_FEEDING_TRAIN_DIR")
    growth_training_yaml: str | None = Field(default=None, validation_alias="MLOPS_GROWTH_TRAIN_YAML")

    # ── API auth ───────────────────────────────────────────────────────────────
    internal_api_key: str = Field(
        default="change-me", validation_alias="INTERNAL_API_KEY"
    )
    api_host: str = Field(default="0.0.0.0", validation_alias="MLOPS_API_HOST")
    api_port: int = Field(default=8002, validation_alias="MLOPS_API_PORT")
    cors_origins: str = Field(
        default="",
        validation_alias="MLOPS_CORS_ORIGINS",
        description=(
            "Comma-separated browser origins permitted to call the MLOps API "
            "directly. Empty (default) blocks all browser CORS — clients must "
            "go through the backend proxy at /api/v1/mlops/*."
        ),
    )

    # ── Edge deployment (optional) ─────────────────────────────────────────────
    edge_host: str | None = Field(default=None, validation_alias="MLOPS_EDGE_HOST")
    edge_user: str = Field(default="aquafarm", validation_alias="MLOPS_EDGE_USER")
    edge_ssh_key: str | None = Field(default=None, validation_alias="MLOPS_EDGE_SSH_KEY")
    edge_deploy_path: str = Field(
        default="/opt/aquafarm/models", validation_alias="MLOPS_EDGE_DEPLOY_PATH"
    )

    # ── Runtime ────────────────────────────────────────────────────────────────
    device: str = Field(default="cpu", validation_alias="MLOPS_DEVICE")
    dry_run: bool = Field(default=False, validation_alias="MLOPS_DRY_RUN")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached MLOps Settings singleton."""
    return Settings()
