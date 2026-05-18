"""Unit tests for the MLOps append-only audit log."""

from __future__ import annotations

from pathlib import Path

from mlops.orchestrator.audit_log import AuditEvent, AuditLog


def test_log_and_tail(tmp_path: Path) -> None:
    log = AuditLog(tmp_path / "audit.jsonl")
    log.log("automl", model="", data={"summary": "first"})
    log.log("automl", model="WaterQualityPredictor", data={"new_samples": 1200})
    log.log("promotion", model="WaterQualityPredictor", data={"version": "3"})

    events = log.tail(n=10)
    assert len(events) == 3
    assert events[0].kind == "automl"
    assert events[-1].kind == "promotion"


def test_filter_by_kind_and_model(tmp_path: Path) -> None:
    log = AuditLog(tmp_path / "audit.jsonl")
    log.log("automl", model="A")
    log.log("drift", model="A")
    log.log("drift", model="B")

    drift_only = log.tail(n=10, kind="drift")
    assert len(drift_only) == 2
    assert all(e.kind == "drift" for e in drift_only)

    only_a = log.tail(n=10, model="A")
    assert len(only_a) == 2
    assert all(e.model == "A" for e in only_a)


def test_latest_returns_newest(tmp_path: Path) -> None:
    log = AuditLog(tmp_path / "audit.jsonl")
    log.log("promotion", model="X", data={"v": "1"})
    log.log("promotion", model="X", data={"v": "2"})
    latest = log.latest("promotion", model="X")
    assert latest is not None
    assert latest.data["v"] == "2"


def test_missing_file_returns_empty(tmp_path: Path) -> None:
    log = AuditLog(tmp_path / "does_not_exist.jsonl")
    assert log.tail() == []
    assert log.latest("automl") is None


def test_corrupt_lines_are_skipped(tmp_path: Path) -> None:
    path = tmp_path / "audit.jsonl"
    log = AuditLog(path)
    log.log("automl", model="A")

    with open(path, "a", encoding="utf-8") as fh:
        fh.write("this is not json\n")
        fh.write('{"missing": "fields"}\n')

    log.log("automl", model="B")
    events = log.tail(n=10)
    assert {e.model for e in events} == {"A", "B"}


def test_rotation_truncates_oldest(tmp_path: Path) -> None:
    path = tmp_path / "audit.jsonl"
    log = AuditLog(path, max_bytes=512)  # tiny → rotation kicks in quickly

    for i in range(200):
        log.write(AuditEvent.now("automl", model=f"M{i}"))

    assert path.stat().st_size <= 1024
    kept = log.tail(n=1000)
    # The newest entries must survive rotation
    assert kept[-1].model.startswith("M")
