"""Control service — dispatches equipment commands to edge devices via Redis pub/sub.

Commands are published as JSON to Redis channels. Edge device processes
subscribe and actuate the physical equipment.

Channel naming convention: `cmd:{tank_id}:{device_type}`
  cmd:T001:feeder    — feeder on/off, amount_kg
  cmd:T001:pump      — circulation pump
  cmd:T001:aeration  — aeration blower
  cmd:T001:exchange  — water exchange valve
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

import structlog

logger = structlog.get_logger()


def _job_id() -> str:
    return str(uuid.uuid4())


def _now_iso() -> str:
    return datetime.now(tz=UTC).isoformat()


def _command_payload(job_id: str, action: str, **kwargs: Any) -> str:
    """Serialise a command to JSON for Redis publish."""
    return json.dumps(
        {
            "job_id": job_id,
            "action": action,
            "dispatched_at": _now_iso(),
            **kwargs,
        }
    )


class ControlService:
    """Handles equipment control commands dispatched via Redis pub/sub.

    All methods publish to the appropriate Redis channel and return an
    acknowledgement dict. The edge device is responsible for actually
    actuating the equipment and optionally publishing a completion event.

    Args:
        redis: Async Redis client (injected from app.db.redis).
    """

    def __init__(self, redis: Any) -> None:
        self._redis = redis

    async def _publish(self, channel: str, payload: str) -> None:
        """Publish payload to a Redis channel, logging the result."""
        try:
            receivers = await self._redis.publish(channel, payload)
            logger.info(
                "command_published",
                channel=channel,
                receivers=receivers,
            )
        except Exception as exc:
            logger.error("redis_publish_failed", channel=channel, error=str(exc))
            raise

    async def trigger_feeding(self, tank_id: str, amount_kg: float, duration_s: int = 0) -> dict:
        """Dispatch a feeding command to the edge feeder device.

        Args:
            tank_id: Target tank identifier.
            amount_kg: Feed amount in kilograms.
            duration_s: Feeder run duration in seconds (0 = auto from amount).

        Returns:
            Job acknowledgement dict.
        """
        job_id = _job_id()
        channel = f"cmd:{tank_id}:feeder"
        payload = _command_payload(
            job_id, "feed",
            tank_id=tank_id,
            amount_kg=amount_kg,
            duration_s=duration_s,
        )
        await self._publish(channel, payload)
        logger.info("feeding_command_dispatched", job_id=job_id, tank_id=tank_id, kg=amount_kg)
        return {
            "job_id": job_id,
            "status": "accepted",
            "tank_id": tank_id,
            "amount_kg": amount_kg,
            "channel": channel,
            "dispatched_at": _now_iso(),
        }

    async def stop_feeding(self, tank_id: str) -> dict:
        """Send emergency stop to the feeder device.

        Args:
            tank_id: Target tank identifier.

        Returns:
            Stop command acknowledgement.
        """
        job_id = _job_id()
        channel = f"cmd:{tank_id}:feeder"
        payload = _command_payload(job_id, "stop", tank_id=tank_id)
        await self._publish(channel, payload)
        logger.warning("feeding_emergency_stop", job_id=job_id, tank_id=tank_id)
        return {
            "job_id": job_id,
            "status": "stop_accepted",
            "tank_id": tank_id,
            "channel": channel,
            "dispatched_at": _now_iso(),
        }

    async def adjust_feeding(self, tank_id: str, reduction_factor: float) -> dict:
        """Adjust the next feeding amount by a factor.

        Args:
            tank_id: Target tank identifier.
            reduction_factor: Multiplier in [0, 1] applied to baseline feed amount.

        Returns:
            Adjustment command acknowledgement.
        """
        job_id = _job_id()
        channel = f"cmd:{tank_id}:feeder"
        payload = _command_payload(
            job_id, "adjust",
            tank_id=tank_id,
            reduction_factor=reduction_factor,
        )
        await self._publish(channel, payload)
        return {
            "job_id": job_id,
            "status": "accepted",
            "tank_id": tank_id,
            "reduction_factor": reduction_factor,
            "channel": channel,
            "dispatched_at": _now_iso(),
        }

    async def control_pump(self, tank_id: str, action: str) -> dict:
        """Start or stop the circulation pump.

        Args:
            tank_id: Target tank identifier.
            action: 'start' or 'stop'.

        Returns:
            Command acknowledgement.
        """
        job_id = _job_id()
        channel = f"cmd:{tank_id}:pump"
        payload = _command_payload(job_id, action, tank_id=tank_id)
        await self._publish(channel, payload)
        return {
            "job_id": job_id,
            "status": "accepted",
            "tank_id": tank_id,
            "action": action,
            "channel": channel,
            "dispatched_at": _now_iso(),
        }

    async def increase_aeration(self, tank_id: str, boost_pct: float = 30.0) -> dict:
        """Boost aeration blower speed.

        Args:
            tank_id: Target tank identifier.
            boost_pct: Percentage increase above current speed (default 30%).

        Returns:
            Command acknowledgement.
        """
        job_id = _job_id()
        channel = f"cmd:{tank_id}:aeration"
        payload = _command_payload(
            job_id, "boost",
            tank_id=tank_id,
            boost_pct=boost_pct,
        )
        await self._publish(channel, payload)
        logger.info("aeration_boost_dispatched", tank_id=tank_id, boost_pct=boost_pct)
        return {
            "job_id": job_id,
            "status": "accepted",
            "tank_id": tank_id,
            "boost_pct": boost_pct,
            "channel": channel,
            "dispatched_at": _now_iso(),
        }

    async def trigger_water_exchange(self, tank_id: str, exchange_pct: float = 10.0) -> dict:
        """Trigger a partial water exchange.

        Args:
            tank_id: Target tank identifier.
            exchange_pct: Percentage of tank volume to exchange (default 10%).

        Returns:
            Command acknowledgement.
        """
        job_id = _job_id()
        channel = f"cmd:{tank_id}:exchange"
        payload = _command_payload(
            job_id, "exchange",
            tank_id=tank_id,
            exchange_pct=exchange_pct,
        )
        await self._publish(channel, payload)
        logger.info("water_exchange_dispatched", tank_id=tank_id, exchange_pct=exchange_pct)
        return {
            "job_id": job_id,
            "status": "accepted",
            "tank_id": tank_id,
            "exchange_pct": exchange_pct,
            "channel": channel,
            "dispatched_at": _now_iso(),
        }
