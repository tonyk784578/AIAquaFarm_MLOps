"""LangChain tools available to the management agent.

Tools wrap backend API calls so the LLM can invoke them via tool use.

TODO (Phase 3): Implement each tool with real API calls.
TODO (Phase 3): Add input validation using Pydantic schemas.
"""

from typing import Any

import httpx
import structlog
from langchain_core.tools import tool

from agents.config import get_agent_settings

logger = structlog.get_logger()
settings = get_agent_settings()


@tool
async def get_water_quality(tank_id: str) -> dict[str, Any]:
    """Retrieve the latest water quality readings for a specific tank.

    Args:
        tank_id: The tank identifier (e.g., 'T001').

    Returns:
        Latest water quality data dict with temperature, pH, DO, ammonia, nitrite.

    TODO (Phase 3): Add error handling and retry logic.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{settings.backend_url}/api/v1/monitoring/water-quality/latest",
            params={"tank_id": tank_id, "limit": 1},
        )
        resp.raise_for_status()
        data = resp.json()
        return data[0] if data else {}


@tool
async def trigger_feeding(tank_id: str, amount_kg: float) -> dict[str, Any]:
    """Trigger a feeding event for the specified tank.

    Args:
        tank_id: The tank identifier.
        amount_kg: Amount of feed to dispense in kilograms.

    Returns:
        Command acknowledgement with job_id.

    TODO (Phase 3): Add pre-flight check (feeding not already in progress).
    """
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{settings.backend_url}/api/v1/control/feeding/trigger",
            json={"tank_id": tank_id, "amount_kg": amount_kg},
        )
        resp.raise_for_status()
        return resp.json()


@tool
async def create_alert(
    tank_id: str,
    severity: str,
    category: str,
    title: str,
    message: str,
) -> dict[str, Any]:
    """Create a new alert notification for an anomaly.

    Args:
        tank_id: The affected tank identifier.
        severity: Alert severity ('critical', 'warning', 'info').
        category: Alert category ('water_quality', 'fish_growth', 'feeding').
        title: Short alert title.
        message: Detailed alert message.

    Returns:
        Created alert record.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{settings.backend_url}/api/v1/alerts/",
            json={
                "tank_id": tank_id,
                "severity": severity,
                "category": category,
                "title": title,
                "message": message,
                "source": "management_agent",
            },
        )
        resp.raise_for_status()
        return resp.json()


# Tool registry — pass to agent executor
MANAGEMENT_AGENT_TOOLS = [get_water_quality, trigger_feeding, create_alert]
