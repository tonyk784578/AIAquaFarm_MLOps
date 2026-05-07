"""Dashboard API — aggregated overview endpoint for the main UI panel.

Returns a snapshot combining water quality, fish growth, feeding status,
and active alerts into a single response to minimise frontend round-trips.

TODO (Phase 2): Add WebSocket endpoint for real-time dashboard push.
TODO (Phase 3): Cache aggregated response in Redis with 5 s TTL.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.alert import AlertRead
from app.schemas.feeding import FeedingRead
from app.schemas.fish_growth import FishGrowthRead
from app.schemas.water_quality import WaterQualityRead
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
) -> dict:
    """Return the latest data across all AI modules for the dashboard.

    Args:
        db: Injected async DB session.

    Returns:
        Dict with keys: water_quality, fish_growth, feeding, active_alerts.
    """
    service = MonitoringService(db)
    return await service.get_dashboard_summary()


@router.get("/tanks", summary="List all monitored tanks")
async def list_tanks(db: AsyncSession = Depends(get_db)) -> list[dict]:
    """Return a list of all tank IDs with their online/offline status.

    TODO (Phase 2): Implement tank registry and status tracking.

    Args:
        db: Injected async DB session.

    Returns:
        List of tank status dicts.
    """
    # TODO (Phase 2): Query tank registry from DB
    return [
        {"tank_id": "T001", "name": "1번 수조", "status": "online"},
        {"tank_id": "T002", "name": "2번 수조", "status": "online"},
        {"tank_id": "T003", "name": "3번 수조", "status": "offline"},
    ]
