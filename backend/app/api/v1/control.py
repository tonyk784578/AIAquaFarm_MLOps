"""Control API — remote equipment command interface.

Accepts control commands from the dashboard or AI optimization agent
and dispatches them to edge devices via Redis pub/sub.

Security note: In production, all control endpoints require authentication
and the caller's role must include CONTROL_WRITE permission.

TODO (Phase 3): Wire up to optimization agent command output.
TODO (Phase 3): Add command audit log to PostgreSQL.
TODO (Phase 4): Implement RBAC middleware.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.feeding import FeedingCommand
from app.services.control_service import ControlService

router = APIRouter()


@router.post(
    "/feeding/trigger",
    summary="Manually trigger feeding",
    status_code=status.HTTP_202_ACCEPTED,
)
async def trigger_feeding(
    command: FeedingCommand,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Dispatch a manual feeding command to the specified tank.

    Args:
        command: Feeding command payload (tank_id, amount_kg, duration_s).
        db: Injected async DB session.

    Returns:
        Command acknowledgement with a job ID.

    Raises:
        HTTPException: 404 if tank not found, 409 if feeding already in progress.

    TODO (Phase 3): Check tank status before issuing command.
    TODO (Phase 3): Publish command to Redis channel `cmd:{tank_id}`.
    """
    service = ControlService(db)
    return await service.trigger_feeding(command)


@router.post(
    "/feeding/stop/{tank_id}",
    summary="Emergency stop feeding",
    status_code=status.HTTP_202_ACCEPTED,
)
async def stop_feeding(
    tank_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Send emergency stop signal to the feeder in the specified tank.

    Args:
        tank_id: Target tank identifier.
        db: Injected async DB session.

    Returns:
        Stop command acknowledgement.

    TODO (Phase 3): Publish STOP command to Redis channel `cmd:{tank_id}`.
    """
    service = ControlService(db)
    return await service.stop_feeding(tank_id)


@router.post(
    "/pump/{tank_id}/{action}",
    summary="Control circulation pump",
    status_code=status.HTTP_202_ACCEPTED,
)
async def control_pump(
    tank_id: str,
    action: str,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Start or stop the circulation pump for a tank.

    Args:
        tank_id: Target tank identifier.
        action: One of 'start' or 'stop'.
        db: Injected async DB session.

    Returns:
        Command acknowledgement.

    Raises:
        HTTPException: 400 if action is invalid.

    TODO (Phase 3): Publish pump command to Redis.
    """
    if action not in {"start", "stop"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid pump action '{action}'. Must be 'start' or 'stop'.",
        )
    service = ControlService(db)
    return await service.control_pump(tank_id, action)
