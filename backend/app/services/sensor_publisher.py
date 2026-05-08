"""Background sensor publisher — streams water quality predictions to Redis
and persists readings to PostgreSQL.

Runs as an asyncio background task (started in FastAPI lifespan).
Every `poll_interval` seconds it:
    1. Runs the ODE virtual sensor to produce a synthetic reading.
    2. Publishes a JSON WSMessage to the Redis channel ``wq:{tank_id}``
       so connected WebSocket clients receive the update in real-time.
    3. Persists the reading to the ``water_quality_readings`` table via the
       POST /api/v1/monitoring/water-quality endpoint so the dashboard
       summary has data to query.

Redis channel format::

    wq:TANK-01  →  {"type":"water_quality","tank_id":"TANK-01",
                    "timestamp":"…","data":{WaterQualityReading fields}}
"""

from __future__ import annotations

import asyncio
import json
import math
import random
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import structlog

logger = structlog.get_logger()

# ── ODE-based synthetic sensor (no DB/model required) ─────────────────────────
# Keeps per-tank state so readings evolve realistically between ticks.

_K_NIT_BASE = 0.18
_K_NOX_BASE = 0.30
_THETA = 1.07
_T_REF = 25.0
_FEED_HOURS = {7, 12, 18}


def _k_nit(temp_c: float) -> float:
    return _K_NIT_BASE * _THETA ** (temp_c - _T_REF)


def _k_nox(temp_c: float) -> float:
    return _K_NOX_BASE * _THETA ** (temp_c - _T_REF)


class _TankState:
    """Minimal per-tank ODE state for realistic synthetic readings."""

    def __init__(self, tank_id: str, seed: int = 0) -> None:
        rng = random.Random(seed)
        self.tank_id = tank_id
        self.nh3 = rng.uniform(0.05, 0.15)
        self.no2 = rng.uniform(0.01, 0.05)
        self.temp_c = rng.uniform(22.0, 24.0)
        self._rng = rng

    def step(self, dt: float = 1.0 / 60.0) -> dict[str, float]:
        """Advance ODE by dt hours and return a synthetic reading."""
        hour = datetime.now(UTC).hour
        loading = 0.12 if hour in _FEED_HOURS else 0.0

        kn = _k_nit(self.temp_c)
        ko = _k_nox(self.temp_c)
        kx = 0.05  # water exchange dilution

        dnh3 = loading - kn * self.nh3 - kx * self.nh3
        dno2 = kn * self.nh3 - ko * self.no2 - kx * self.no2

        self.nh3 = max(0.0, self.nh3 + dnh3 * dt)
        self.no2 = max(0.0, self.no2 + dno2 * dt)

        # Diurnal temperature oscillation ± 1 °C
        t_hour = datetime.now(UTC).hour + datetime.now(UTC).minute / 60.0
        self.temp_c = 23.0 + math.sin((t_hour - 6) * math.pi / 12) + self._rng.gauss(0, 0.05)

        ph = 7.2 + self._rng.gauss(0, 0.05) - self.nh3 * 0.3
        do_mgl = 8.5 - self.temp_c * 0.1 + self._rng.gauss(0, 0.1)
        turb = 2.5 + self.nh3 * 3 + self._rng.gauss(0, 0.2)

        return {
            "temperature_c": round(self.temp_c, 3),
            "ph": round(max(6.0, min(9.0, ph)), 3),
            "dissolved_oxygen_mgl": round(max(4.0, min(12.0, do_mgl)), 3),
            "turbidity_ntu": round(max(0.0, turb), 3),
            "ammonia_ppm": round(self.nh3, 4),
            "nitrite_ppm": round(self.no2, 4),
            "ammonia_confidence": round(self._rng.uniform(0.85, 0.98), 3),
            "nitrite_confidence": round(self._rng.uniform(0.85, 0.98), 3),
            "source": "virtual_sensor",
        }


# ── Publisher ──────────────────────────────────────────────────────────────────

class SensorPublisher:
    """Periodically generates sensor readings, publishes them to Redis, and
    persists them to PostgreSQL.

    Attributes:
        tank_ids: List of tank identifiers to simulate.
        poll_interval: Seconds between publications per tank.
        redis: Async Redis client.
        session_factory: Callable that returns an AsyncSession (injected from lifespan).
        _states: Per-tank ODE state objects.
        _task: Background asyncio task handle.
        _db_write_every: Write to DB every N ticks (default 6 = every 30 s at 5 s interval).
        _tick_counters: Per-tank tick counter for DB write throttling.
    """

    def __init__(
        self,
        tank_ids: list[str],
        poll_interval: int,
        redis: Any,
        session_factory: Callable | None = None,
        db_write_every: int = 6,
    ) -> None:
        self.tank_ids = tank_ids
        self.poll_interval = poll_interval
        self._redis = redis
        self._session_factory = session_factory
        self._db_write_every = db_write_every
        self._states: dict[str, _TankState] = {
            tid: _TankState(tid, seed=i) for i, tid in enumerate(tank_ids)
        }
        self._task: asyncio.Task | None = None
        self._tick_counters: dict[str, int] = {tid: 0 for tid in tank_ids}

    async def _persist_reading(self, tank_id: str, reading: dict) -> None:
        """Write one reading to PostgreSQL via MonitoringService.

        Runs in its own short-lived DB session. Errors are logged and swallowed
        so a DB hiccup never crashes the publishing loop.
        """
        if self._session_factory is None:
            return
        try:
            from datetime import datetime

            from app.schemas.water_quality import WaterQualityCreate
            from app.services.monitoring_service import MonitoringService

            payload = WaterQualityCreate(
                tank_id=tank_id,
                measured_at=datetime.now(UTC),
                temperature_c=reading.get("temperature_c"),
                ph=reading.get("ph"),
                dissolved_oxygen_mgl=reading.get("dissolved_oxygen_mgl"),
                turbidity_ntu=reading.get("turbidity_ntu"),
                ammonia_ppm=reading.get("ammonia_ppm"),
                nitrite_ppm=reading.get("nitrite_ppm"),
                ammonia_confidence=reading.get("ammonia_confidence"),
                nitrite_confidence=reading.get("nitrite_confidence"),
                source="virtual_sensor",
            )
            async with self._session_factory() as session:
                async with session.begin():
                    svc = MonitoringService(session, redis=self._redis)
                    await svc.create_water_quality_reading(payload)
        except Exception as exc:
            logger.warning("sensor_db_persist_failed", tank_id=tank_id, error=str(exc))

    async def _publish_tick(self, tank_id: str) -> None:
        """Generate and publish one reading for a tank, and optionally persist to DB."""
        state = self._states[tank_id]
        reading = state.step(dt=self.poll_interval / 3600.0)
        reading["tank_id"] = tank_id

        now_iso = datetime.now(UTC).isoformat()
        msg = json.dumps({
            "type": "water_quality",
            "tank_id": tank_id,
            "timestamp": now_iso,
            "data": reading,
        })
        channel = f"wq:{tank_id}"
        try:
            await self._redis.publish(channel, msg)
            logger.debug("sensor_published", channel=channel, nh3=reading["ammonia_ppm"])
        except Exception as exc:
            logger.warning("sensor_publish_failed", channel=channel, error=str(exc))

        # Throttle DB writes: persist every _db_write_every ticks
        self._tick_counters[tank_id] = (self._tick_counters.get(tank_id, 0) + 1)
        if self._tick_counters[tank_id] % self._db_write_every == 0:
            await self._persist_reading(tank_id, reading)

    async def _run_loop(self) -> None:
        """Main background loop — tick all tanks every poll_interval seconds."""
        logger.info(
            "sensor_publisher_started",
            tanks=self.tank_ids,
            interval_s=self.poll_interval,
        )
        while True:
            for tank_id in self.tank_ids:
                await self._publish_tick(tank_id)
            await asyncio.sleep(self.poll_interval)

    def start(self) -> None:
        """Start the background task. Call from FastAPI lifespan startup."""
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run_loop())
            logger.info("sensor_publisher_task_created")

    async def stop(self) -> None:
        """Cancel the background task. Call from FastAPI lifespan shutdown."""
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            logger.info("sensor_publisher_stopped")
