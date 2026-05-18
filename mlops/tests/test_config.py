"""Unit tests for the MLOps Settings loader."""

from __future__ import annotations

import os
from pathlib import Path

from mlops.config import Settings


def test_defaults() -> None:
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert s.mlflow_tracking_uri.startswith("http")
    assert s.api_port == 8002
    assert s.automl_interval_minutes >= 1


def test_env_overrides(monkeypatch) -> None:
    monkeypatch.setenv("MLFLOW_TRACKING_URI", "http://test:5000")
    monkeypatch.setenv("MLOPS_API_PORT", "9999")
    monkeypatch.setenv("MLOPS_AUTOML_INTERVAL_MIN", "5")
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert s.mlflow_tracking_uri == "http://test:5000"
    assert s.api_port == 9999
    assert s.automl_interval_minutes == 5


def test_data_dir_is_path() -> None:
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert isinstance(s.data_dir, Path)
