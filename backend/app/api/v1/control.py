"""Control API — remote equipment command interface.

Accepts control commands from the dashboard or AI optimization agent
and dispatches them to edge devices via Redis pub/sub.

Security note: In production, all control endpoints require authentication
and the caller's role must include CONTROL_WRITE permission.
"""

from __future__ import annotations

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Path, Request, status
from pydantic import BaseModel, Field

from app.core.limiter import (
    LIMIT_CONTROL_WRITE,
    is_internal_service,
    limiter,
)
from app.db.redis import get_redis
from app.services.control_service import ControlService

router = APIRouter()

# tank_id must match the convention used in Redis channel names: cmd:{tank_id}:{device}
_TANK_ID_FIELD = Field(..., min_length=1, max_length=32, pattern=r"^[A-Z0-9][A-Z0-9_\-]*$")
_TANK_ID_PATH = Path(..., min_length=1, max_length=32, pattern=r"^[A-Z0-9][A-Z0-9_\-]*$")


class FeedingTriggerRequest(BaseModel):
    tank_id: str = _TANK_ID_FIELD
    amount_kg: float = Field(..., gt=0.0, le=500.0)
    duration_s: int = Field(default=0, ge=0, le=3600)


class FeedingAdjustRequest(BaseModel):
    tank_id: str = _TANK_ID_FIELD
    reduction_factor: float = Field(..., ge=0.0, le=1.0)


class AerationBoostRequest(BaseModel):
    tank_id: str = _TANK_ID_FIELD
    boost_pct: float = Field(default=30.0, ge=0.0, le=200.0)


class WaterExchangeRequest(BaseModel):
    tank_id: str = _TANK_ID_FIELD
    exchange_pct: float = Field(default=10.0, gt=0.0, le=50.0)


def _svc(redis: aioredis.Redis = Depends(get_redis)) -> ControlService:
    return ControlService(redis)


@router.post(
    "/feeding/trigger",
    summary="Manually trigger feeding",
    status_code=status.HTTP_202_ACCEPTED,
)
@limiter.limit(LIMIT_CONTROL_WRITE, exempt_when=is_internal_service)
async def trigger_feeding(
    request: Request,
    body: FeedingTriggerRequest,
    svc: ControlService = Depends(_svc),
) -> dict:
    """Dispatch a manual feeding command. Published to `cmd:{tank_id}:feeder`."""
    try:
        return await svc.trigger_feeding(body.tank_id, body.amount_kg, body.duration_s)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))


@router.post(
    "/feeding/stop/{tank_id}",
    summary="Emergency stop feeding",
    status_code=status.HTTP_202_ACCEPTED,
)
@limiter.limit(LIMIT_CONTROL_WRITE, exempt_when=is_internal_service)
async def stop_feeding(
    request: Request,
    tank_id: str = _TANK_ID_PATH,
    svc: ControlService = Depends(_svc),
) -> dict:
    """Send emergency STOP to feeder. Published to `cmd:{tank_id}:feeder`."""
    try:
        return await svc.stop_feeding(tank_id)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))


@router.post(
    "/feeding/adjust",
    summary="Adjust next feeding amount",
    status_code=status.HTTP_202_ACCEPTED,
)
@limiter.limit(LIMIT_CONTROL_WRITE, exempt_when=is_internal_service)
async def adjust_feeding(
    request: Request,
    body: FeedingAdjustRequest,
    svc: ControlService = Depends(_svc),
) -> dict:
    """Apply a reduction factor to the next scheduled feed. Published to `cmd:{tank_id}:feeder`."""
    try:
        return await svc.adjust_feeding(body.tank_id, body.reduction_factor)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))


@router.post(
    "/pump/{tank_id}/{action}",
    summary="Control circulation pump",
    status_code=status.HTTP_202_ACCEPTED,
)
@limiter.limit(LIMIT_CONTROL_WRITE, exempt_when=is_internal_service)
async def control_pump(
    request: Request,
    tank_id: str = _TANK_ID_PATH,
    action: str = Path(..., pattern=r"^(start|stop)$"),
    svc: ControlService = Depends(_svc),
) -> dict:
    """Start or stop the circulation pump. Published to `cmd:{tank_id}:pump`."""
    try:
        return await svc.control_pump(tank_id, action)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))


@router.post(
    "/aeration/increase",
    summary="Boost aeration blower",
    status_code=status.HTTP_202_ACCEPTED,
)
@limiter.limit(LIMIT_CONTROL_WRITE, exempt_when=is_internal_service)
async def increase_aeration(
    request: Request,
    body: AerationBoostRequest,
    svc: ControlService = Depends(_svc),
) -> dict:
    """Increase aeration speed. Published to `cmd:{tank_id}:aeration`."""
    try:
        return await svc.increase_aeration(body.tank_id, body.boost_pct)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))


@router.post(
    "/water-exchange",
    summary="Trigger partial water exchange",
    status_code=status.HTTP_202_ACCEPTED,
)
@limiter.limit(LIMIT_CONTROL_WRITE, exempt_when=is_internal_service)
async def trigger_water_exchange(
    request: Request,
    body: WaterExchangeRequest,
    svc: ControlService = Depends(_svc),
) -> dict:
    """Trigger water exchange valve. Published to `cmd:{tank_id}:exchange`."""
    try:
        return await svc.trigger_water_exchange(body.tank_id, body.exchange_pct)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
