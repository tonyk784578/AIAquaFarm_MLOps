"""Unit tests for QualityGate logic (no MLflow server required)."""

from __future__ import annotations

from mlops.evaluation.evaluator import QUALITY_GATES, QualityGate


def test_gate_passes_when_all_metrics_meet_threshold() -> None:
    gate = QualityGate(metrics={"val_loss": (0.01, "min"), "mAP50": (0.6, "max")})
    ok, results = gate.check({"val_loss": 0.005, "mAP50": 0.7})
    assert ok is True
    assert results == {"val_loss": True, "mAP50": True}


def test_gate_fails_on_missing_metric() -> None:
    gate = QualityGate(metrics={"val_loss": (0.01, "min")})
    ok, results = gate.check({})
    assert ok is False
    assert results == {"val_loss": False}


def test_gate_min_direction_rejects_higher_value() -> None:
    gate = QualityGate(metrics={"val_loss": (0.01, "min")})
    ok, _ = gate.check({"val_loss": 0.02})
    assert ok is False


def test_gate_max_direction_rejects_lower_value() -> None:
    gate = QualityGate(metrics={"mAP50": (0.65, "max")})
    ok, _ = gate.check({"mAP50": 0.5})
    assert ok is False


def test_all_registered_models_have_gates() -> None:
    expected = {"FishDetection", "FeedingActivityClassifier", "WaterQualityPredictor"}
    assert expected.issubset(QUALITY_GATES.keys())
    # Each gate must define at least one metric
    for name, gate in QUALITY_GATES.items():
        assert gate.metrics, f"Empty gate for {name}"
