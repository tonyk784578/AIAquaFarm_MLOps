"""Dashboard API — aggregated overview endpoint for the main UI panel.

Returns a snapshot combining water quality, fish growth, feeding status,
and active alerts into a single response to minimise frontend round-trips.
"""

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.redis import get_redis
from app.db.session import get_db
from app.services.monitoring_service import MonitoringService

router = APIRouter()


@router.get(
    "/summary",
    summary="Get dashboard summary",
    description=(
        "Aggregated snapshot of the latest water quality, fish growth, "
        "feeding, and active alerts."
    ),
)
async def get_dashboard_summary(
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> dict:
    """Return the latest data across all AI modules for the dashboard.

    Args:
        db: Injected async DB session.
        redis: Injected Redis client for 5 s response caching.

    Returns:
        Dict with keys: water_quality, fish_growth, feeding, active_alerts.
    """
    service = MonitoringService(db, redis=redis)
    return await service.get_dashboard_summary()


@router.get("/tanks", summary="List all monitored tanks")
async def list_tanks() -> list[dict]:
    """Return a list of all monitored tank IDs sourced from application settings.

    Tank IDs are configured via DEFAULT_TANK_IDS in settings (loaded from
    .env / Docker Compose environment). Status is reported as 'online' for all
    configured tanks; a future phase can query a tank-registry table for live
    connectivity status.

    Returns:
        List of tank status dicts with tank_id, name, and status.
    """
    settings = get_settings()
    return [
        {
            "tank_id": tid,
            "name": f"{i + 1}번 수조",
            "status": "online",
        }
        for i, tid in enumerate(settings.default_tank_ids)
    ]
