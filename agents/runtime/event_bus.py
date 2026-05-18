"""Redis pub/sub event bus for live agent progress.

Every graph node can call ``EventBus.publish(...)`` to emit a structured
event. A FastAPI Server-Sent Events endpoint (``/events/stream`` in
main.py) subscribes to the same channel and forwards events to connected
browser clients. This is what powers the live cycle visualization on the
``/agents`` page.

Channel: ``agents:events`` (single channel — events are typed).

Event types (kind):
    cycle_started, cycle_completed, node_started, node_completed,
    decision_made, command_executed, command_failed,
    optimization_started, optimization_completed,
    error

Each event is one JSON object::

    {
      "ts": "2026-05-17T10:00:00+00:00",
      "kind": "node_completed",
      "tank_id": "TANK-01",
      "data": {"node": "analyse_situation", "duration_ms": 4210}
    }
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Literal

import structlog

logger = structlog.get_logger()

EVENT_CHANNEL = "agents:events"

EventKind = Literal[
    "cycle_started",
    "cycle_completed",
    "node_started",
    "node_completed",
    "decision_made",
    "command_executed",
    "command_failed",
    "optimization_started",
    "optimization_completed",
    "error",
]


@dataclass
class AgentEvent:
    """One event published to the agent event channel."""

    ts: str
    kind: EventKind
    tank_id: str = ""
    data: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def now(
        cls, kind: EventKind, tank_id: str = "", data: dict[str, Any] | None = None
    ) -> "AgentEvent":
        return cls(
            ts=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            kind=kind,
            tank_id=tank_id,
            data=data or {},
        )

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, default=str)


class EventBus:
    """Async Redis publish/subscribe wrapper for agent events.

    The bus is robust to a missing Redis (no-op publish, empty subscribe)
    so tests and dev environments still work.

    Attributes:
        redis: Async Redis client.
        channel: pub/sub channel name.
    """

    def __init__(self, redis_client: Any | None, channel: str = EVENT_CHANNEL) -> None:
        self.redis = redis_client
        self.channel = channel

    @property
    def is_available(self) -> bool:
        return self.redis is not None

    # ── Publish ──────────────────────────────────────────────────────────────

    async def publish(
        self,
        kind: EventKind,
        tank_id: str = "",
        data: dict[str, Any] | None = None,
    ) -> AgentEvent:
        """Build and publish an event. Returns the event regardless of success."""
        event = AgentEvent.now(kind=kind, tank_id=tank_id, data=data)
        if self.redis is None:
            return event
        try:
            await self.redis.publish(self.channel, event.to_json())
        except Exception as exc:
            logger.warning("event_publish_failed", kind=kind, error=str(exc))
        return event

    # ── Node timing helper ────────────────────────────────────────────────────

    def timed_node(self, node_name: str, tank_id: str = ""):
        """Async context manager that emits node_started + node_completed.

        Usage::

            async with bus.timed_node("analyse_situation", tank_id="TANK-01"):
                ...
        """
        return _NodeTimer(self, node_name, tank_id)

    # ── Subscribe (for SSE) ──────────────────────────────────────────────────

    async def subscribe(self) -> AsyncIterator[str]:
        """Yield raw event JSON strings as they arrive.

        Yields nothing and returns immediately if Redis is unavailable —
        callers should fall back to polling.
        """
        if self.redis is None:
            return

        pubsub = self.redis.pubsub()
        await pubsub.subscribe(self.channel)
        try:
            while True:
                msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if msg is None:
                    # Periodic keep-alive (None payload) so SSE clients don't time out
                    yield ""
                    await asyncio.sleep(0.05)
                    continue
                payload = msg.get("data")
                if isinstance(payload, bytes):
                    payload = payload.decode()
                yield payload or ""
        finally:
            try:
                await pubsub.unsubscribe(self.channel)
                await pubsub.close()
            except Exception:
                pass


class _NodeTimer:
    """Async context manager emitting node_started and node_completed events."""

    def __init__(self, bus: EventBus, node_name: str, tank_id: str) -> None:
        self.bus = bus
        self.node_name = node_name
        self.tank_id = tank_id
        self._start: float = 0.0

    async def __aenter__(self) -> "_NodeTimer":
        self._start = time.perf_counter()
        await self.bus.publish("node_started", tank_id=self.tank_id, data={"node": self.node_name})
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        duration_ms = int((time.perf_counter() - self._start) * 1000)
        if exc is None:
            await self.bus.publish(
                "node_completed",
                tank_id=self.tank_id,
                data={"node": self.node_name, "duration_ms": duration_ms},
            )
        else:
            await self.bus.publish(
                "error",
                tank_id=self.tank_id,
                data={"node": self.node_name, "duration_ms": duration_ms, "error": str(exc)},
            )
