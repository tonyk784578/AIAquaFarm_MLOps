"""Unit tests for PSI / KL drift computation."""

from __future__ import annotations

import numpy as np

from mlops.evaluation.drift_detector import (
    PSI_WARNING,
    DriftDetector,
    _psi_status,
    compute_kl,
    compute_psi,
)


def test_identical_distribution_has_low_psi() -> None:
    rng = np.random.default_rng(seed=42)
    ref = rng.normal(loc=10.0, scale=1.0, size=2_000)
    cur = rng.normal(loc=10.0, scale=1.0, size=2_000)
    assert compute_psi(ref, cur) < 0.1


def test_shifted_distribution_triggers_drift() -> None:
    rng = np.random.default_rng(seed=42)
    ref = rng.normal(loc=10.0, scale=1.0, size=2_000)
    cur = rng.normal(loc=14.0, scale=1.0, size=2_000)  # 4-sigma shift
    assert compute_psi(ref, cur) >= PSI_WARNING


def test_kl_is_non_negative() -> None:
    rng = np.random.default_rng(seed=1)
    a = rng.normal(size=500)
    b = rng.normal(loc=2.0, size=500)
    assert compute_kl(a, b) >= 0
    assert compute_kl(a, a) < 0.05


def test_psi_status_thresholds() -> None:
    assert _psi_status(0.05) == "stable"
    assert _psi_status(0.15) == "warning"
    assert _psi_status(0.25) == "drift"


def test_check_features_handles_missing_columns(tmp_path) -> None:
    pd = _import_pandas()
    if pd is None:
        return  # pandas not installed in this env — skip silently

    ref = pd.DataFrame({"temperature_c": np.linspace(20, 25, 100)})
    cur = pd.DataFrame({"temperature_c": np.linspace(20, 25, 100)})

    detector = DriftDetector()
    report = detector._check_features("WaterQualityPredictor", ref, cur, ["temperature_c", "missing"])
    assert report.max_psi < 0.1
    assert not report.should_retrain
    assert any(f.feature == "temperature_c" for f in report.features)


def _import_pandas():
    try:
        import pandas as pd

        return pd
    except ImportError:
        return None
