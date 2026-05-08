"""LangChain tools available to the management agent.

These tools wrap backend API calls so Claude can invoke them via tool use.
Each tool validates inputs via Pydantic and handles HTTP errors gracefully.
"""

from __future__ import annotations

from typing import Any

import httpx
import structlog
from langchain_core.tools import tool

from agents.config import get_agent_settings

logger = structlog.get_logger()
settings = get_agent_settings()

_TIMEOUT = httpx.Timeout(10.0)


def _service_headers() -> dict[str, str]:
    key = settings.backend_api_key
    return {"X-Service-Key": key} if key else {}


async def _get(path: str, **params: Any) -> dict[str, Any]:
    """GET helper — returns response JSON or empty dict on failure."""
    async with httpx.AsyncClient(timeout=_TIMEOUT, headers=_service_headers()) as client:
        try:
            resp = await client.get(f"{settings.backend_url}{path}", params=params or None)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            logger.warning("tool_get_failed", path=path, error=str(exc))
            return {"error": str(exc)}


async def _post(path: str, body: dict[str, Any]) -> dict[str, Any]:
    """POST helper — returns response JSON or error dict on failure."""
    async with httpx.AsyncClient(timeout=_TIMEOUT, headers=_service_headers()) as client:
        try:
            resp = await client.post(f"{settings.backend_url}{path}", json=body)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            logger.warning("tool_post_failed", path=path, error=str(exc))
            return {"error": str(exc)}


# ── Tools ──────────────────────────────────────────────────────────────────────

@tool
async def get_water_quality(tank_id: str) -> dict[str, Any]:
    """Retrieve the latest water quality readings for a tank.

    Args:
        tank_id: The tank identifier (e.g. 'TANK-01').

    Returns:
        Latest water quality dict with temperature, pH, dissolved_oxygen,
        ammonia_ppm, nitrite_ppm, and confidence scores.
    """
    result = await _get(
        "/api/v1/monitoring/water-quality/latest",
        tank_id=tank_id,
        limit=1,
    )
    if isinstance(result, list):
        return result[0] if result else {}
    return result


@tool
async def get_growth_metrics(tank_id: str) -> dict[str, Any]:
    """Retrieve current fish population count and biomass estimate.

    Args:
        tank_id: The tank identifier.

    Returns:
        Dict with fish_count, model_version, queried_at.
    """
    return await _get(f"/api/v1/growth/count/{tank_id}")


@tool
async def get_feed_recommendation(
    tank_id: str,
    biomass_kg: float,
    current_fcr: float | None = None,
    water_quality_penalty: float = 0.0,
) -> dict[str, Any]:
    """Get a feed amount recommendation from the feeding AI module.

    Args:
        tank_id: The tank identifier.
        biomass_kg: Current estimated biomass in kg.
        current_fcr: Most recent feed conversion ratio (optional).
        water_quality_penalty: Water quality risk score 0–1 (0 = safe).

    Returns:
        FeedOptimizationOutput with recommended_amount_kg and reasoning.
    """
    return await _post(
        "/api/v1/feeding/recommend",
        {
            "tank_id": tank_id,
            "biomass_kg": biomass_kg,
            "current_fcr": current_fcr,
            "water_quality_penalty": water_quality_penalty,
        },
    )


@tool
async def trigger_feeding(tank_id: str, amount_kg: float) -> dict[str, Any]:
    """Trigger a feeding event for the specified tank.

    Args:
        tank_id: The tank identifier.
        amount_kg: Amount of feed to dispense in kilograms.

    Returns:
        Command acknowledgement with job_id and Redis channel.
    """
    return await _post(
        "/api/v1/control/feeding/trigger",
        {"tank_id": tank_id, "amount_kg": amount_kg},
    )


@tool
async def stop_feeding(tank_id: str) -> dict[str, Any]:
    """Emergency stop the feeder for a tank.

    Args:
        tank_id: The tank identifier.

    Returns:
        Stop command acknowledgement.
    """
    async with httpx.AsyncClient(timeout=_TIMEOUT, headers=_service_headers()) as client:
        try:
            resp = await client.post(
                f"{settings.backend_url}/api/v1/control/feeding/stop/{tank_id}"
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            return {"error": str(exc)}


@tool
async def adjust_feeding(tank_id: str, reduction_factor: float) -> dict[str, Any]:
    """Reduce the next feeding amount by a factor (0.0 = stop, 1.0 = unchanged).

    Args:
        tank_id: The tank identifier.
        reduction_factor: Multiplier in [0.0, 1.0].

    Returns:
        Adjustment command acknowledgement.
    """
    return await _post(
        "/api/v1/control/feeding/adjust",
        {"tank_id": tank_id, "reduction_factor": reduction_factor},
    )


@tool
async def increase_aeration(tank_id: str, boost_pct: float = 30.0) -> dict[str, Any]:
    """Boost the aeration blower speed to improve dissolved oxygen.

    Args:
        tank_id: The tank identifier.
        boost_pct: Percentage increase above current speed (default 30%).

    Returns:
        Command acknowledgement.
    """
    return await _post(
        "/api/v1/control/aeration/increase",
        {"tank_id": tank_id, "boost_pct": boost_pct},
    )


@tool
async def trigger_water_exchange(tank_id: str, exchange_pct: float = 10.0) -> dict[str, Any]:
    """Trigger a partial water exchange to dilute ammonia/nitrite.

    Args:
        tank_id: The tank identifier.
        exchange_pct: Percentage of tank volume to exchange (default 10%, max 50%).

    Returns:
        Command acknowledgement.
    """
    return await _post(
        "/api/v1/control/water-exchange",
        {"tank_id": tank_id, "exchange_pct": exchange_pct},
    )


@tool
async def create_alert(
    tank_id: str,
    severity: str,
    category: str,
    title: str,
    message: str,
) -> dict[str, Any]:
    """Create an alert notification for the farm operator.

    Args:
        tank_id: The affected tank identifier.
        severity: 'critical', 'warning', or 'info'.
        category: 'water_quality', 'fish_growth', or 'feeding'.
        title: Short alert title (max 100 characters).
        message: Detailed alert message.

    Returns:
        Created alert record.
    """
    return await _post(
        "/api/v1/alerts/",
        {
            "tank_id": tank_id,
            "severity": severity,
            "category": category,
            "title": title,
            "message": message,
            "source": "management_agent",
        },
    )


# ── Tool registry ──────────────────────────────────────────────────────────────

MANAGEMENT_AGENT_TOOLS = [
    get_water_quality,
    get_growth_metrics,
    get_feed_recommendation,
    trigger_feeding,
    stop_feeding,
    adjust_feeding,
    increase_aeration,
    trigger_water_exchange,
    create_alert,
]
