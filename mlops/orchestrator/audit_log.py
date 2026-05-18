"""Append-only JSON-lines audit log for MLOps events.

Every AutoML cycle, model promotion, drift check, or edge deployment is
recorded as a single JSON object on its own line. The log is the source of
truth for the observability API (``GET /mlops/audit``) and for the dashboard
UI.

File format::

    {"ts": "2026-05-17T10:00:00+00:00", "kind": "automl",
     "model": "WaterQualityPredictor", "data": {...}}
    {"ts": "...", "kind": "promotion", "model": "...", "data": {...}}

The log file is line-atomic: writes are flushed and fsync'd. Concurrent
writers from different processes are serialised by an OS-level advisory
lock (``fcntl.flock``), which is sufficient on a single host. For cluster
deployments swap this for a database-backed log.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Literal

import structlog

logger = structlog.get_logger()

EventKind = Literal[
    "automl",
    "drift",
    "promotion",
    "rollback",
    "deployment",
    "training",
    "error",
]


@dataclass
class AuditEvent:
    """One entry in the MLOps audit log.

    Attributes:
        ts: ISO-8601 UTC timestamp.
        kind: Event category (see ``EventKind``).
        model: Registered model name; empty string for pipeline-level events.
        data: Arbitrary JSON-serialisable payload (e.g. RetrainingResult dict).
    """

    ts: str
    kind: EventKind
    model: str
    data: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def now(cls, kind: EventKind, model: str, data: dict[str, Any] | None = None) -> "AuditEvent":
        return cls(
            ts=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            kind=kind,
            model=model,
            data=data or {},
        )

    def to_json_line(self) -> str:
        return json.dumps(asdict(self), separators=(",", ":"), ensure_ascii=False)


class AuditLog:
    """Append-only JSONL log writer/reader.

    Args:
        path: Destination file; parent directories are created on first write.
        max_bytes: When the file grows past this, the oldest 25% of lines
            are dropped (simple log-rotation in place).

    Thread/process safety: write() takes an fcntl.flock on the file handle
    while writing one record.
    """

    DEFAULT_MAX_BYTES = 8 * 1024 * 1024  # 8 MiB

    def __init__(self, path: str | Path, max_bytes: int | None = None) -> None:
        self.path = Path(path)
        self.max_bytes = max_bytes or self.DEFAULT_MAX_BYTES

    # ── Write ──────────────────────────────────────────────────────────────────

    def write(self, event: AuditEvent) -> None:
        """Append one event. Creates parent dirs and rotates if oversized."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        line = event.to_json_line() + "\n"

        try:
            with open(self.path, "a", encoding="utf-8") as fh:
                self._lock(fh)
                try:
                    fh.write(line)
                    fh.flush()
                    os.fsync(fh.fileno())
                finally:
                    self._unlock(fh)
        except OSError as exc:
            logger.error("audit_write_failed", path=str(self.path), error=str(exc))
            return

        self._maybe_rotate()
        logger.debug("audit_event_written", kind=event.kind, model=event.model)

    def log(
        self,
        kind: EventKind,
        model: str,
        data: dict[str, Any] | None = None,
    ) -> AuditEvent:
        """Convenience helper: build + write an event in one call."""
        event = AuditEvent.now(kind=kind, model=model, data=data)
        self.write(event)
        return event

    # ── Read ───────────────────────────────────────────────────────────────────

    def tail(
        self,
        n: int = 100,
        kind: EventKind | None = None,
        model: str | None = None,
    ) -> list[AuditEvent]:
        """Return the most recent ``n`` events, optionally filtered.

        Reads the whole file (audit logs are small by design). For very large
        logs, switch to seek-from-end byte scanning.
        """
        if not self.path.exists():
            return []

        events: list[AuditEvent] = []
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                for raw in fh:
                    raw = raw.strip()
                    if not raw:
                        continue
                    try:
                        obj = json.loads(raw)
                    except json.JSONDecodeError:
                        continue
                    if kind and obj.get("kind") != kind:
                        continue
                    if model and obj.get("model") != model:
                        continue
                    events.append(AuditEvent(**obj))
        except OSError as exc:
            logger.error("audit_read_failed", error=str(exc))
            return []

        return events[-n:]

    def latest(self, kind: EventKind, model: str | None = None) -> AuditEvent | None:
        """Return the newest event of a given kind (and optionally model)."""
        results = self.tail(n=1, kind=kind, model=model)
        return results[-1] if results else None

    def iter_all(self) -> Iterable[AuditEvent]:
        """Stream all events in chronological order (generator)."""
        if not self.path.exists():
            return
        with open(self.path, "r", encoding="utf-8") as fh:
            for raw in fh:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    yield AuditEvent(**json.loads(raw))
                except (json.JSONDecodeError, TypeError):
                    continue

    # ── Internal helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _lock(fh) -> None:
        try:
            import fcntl

            fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        except (ImportError, OSError):
            pass  # Windows / non-POSIX: best-effort

    @staticmethod
    def _unlock(fh) -> None:
        try:
            import fcntl

            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        except (ImportError, OSError):
            pass

    def _maybe_rotate(self) -> None:
        """Drop the oldest 25% of lines if file exceeds max_bytes."""
        try:
            size = self.path.stat().st_size
        except OSError:
            return
        if size <= self.max_bytes:
            return

        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                lines = fh.readlines()
            keep = lines[len(lines) // 4 :]
            tmp = self.path.with_suffix(self.path.suffix + ".tmp")
            with open(tmp, "w", encoding="utf-8") as fh:
                fh.writelines(keep)
            os.replace(tmp, self.path)
            logger.info(
                "audit_log_rotated",
                path=str(self.path),
                kept=len(keep),
                dropped=len(lines) - len(keep),
            )
        except OSError as exc:
            logger.error("audit_rotate_failed", error=str(exc))
