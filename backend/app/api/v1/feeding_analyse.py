"""Feeding activity analysis API endpoints.

Routes
------
POST /api/v1/feeding/analyse
    Analyse a single camera frame during a feeding session.

POST /api/v1/feeding/recommend
    Compute feed recommendation from the current session statistics.

POST /api/v1/feeding/reset/{tank_id}
    Reset the feeding session for a tank (call between feeding periods).

GET  /api/v1/feeding/status
    Return model load status and active session list.
"""

from __future__ import annotations

from ai_modules.feeding.schemas import (
    FeedingActivityOutput,
    FeedingAnalysisInput,
    FeedOptimizationOutput,
)
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.services.feeding_service import FeedingInferenceEngine, FeedingService

router = APIRouter()


class RecommendRequest(BaseModel):
    tank_id: str
    biomass_kg: float = Field(..., gt=0.0, description="Current estimated biomass in kg")
    current_fcr: float | None = Field(None, gt=0.0, description="Feed conversion ratio")
    water_quality_penalty: float = Field(
        default=0.0, ge=0.0, le=1.0,
        description="Penalty from water quality AI (0=OK, 1=critical)",
    )


def _get_engine(request: Request) -> FeedingInferenceEngine:
    engine: FeedingInferenceEngine = getattr(request.app.state, "feeding_engine", None)
    if engine is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Feeding inference engine not initialised",
        )
    return engine


def _get_service(
    engine: FeedingInferenceEngine = Depends(_get_engine),
) -> FeedingService:
    return FeedingService(engine)


@router.post(
    "/analyse",
    response_model=FeedingActivityOutput,
    summary="Analyse feeding activity from a camera frame",
)
async def analyse_frame(
    body: FeedingAnalysisInput,
    service: FeedingService = Depends(_get_service),
) -> FeedingActivityOutput:
    """Process a single feeding-period frame and update the tank session.

    Frames are accumulated per-tank. Call this endpoint for each camera
    frame during a feeding window to build session statistics used by
    the recommendation endpoint.

    Body fields:
    - **tank_id**: Tank identifier
    - **frame_bytes**: Base64-encoded JPEG/PNG frame
    - **timestamp**: Frame capture time (ISO 8601)
    - **current_feed_amount_kg**: Feed dispensed so far this session
    - **feeding_duration_s**: Session duration elapsed (seconds)
    """
    try:
        return service.analyse_frame(body)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Frame analysis failed: {exc}",
        )


@router.post(
    "/recommend",
    response_model=FeedOptimizationOutput,
    summary="Compute next-feed recommendation from current session statistics",
)
async def get_recommendation(
    body: RecommendRequest,
    service: FeedingService = Depends(_get_service),
) -> FeedOptimizationOutput:
    """Return the optimal feed amount for the next feeding event.

    Uses accumulated session activity scores plus biomass and water quality
    inputs to compute a rule-based (Phase 2) or RL (Phase 4) recommendation.
    """
    try:
        return service.get_recommendation(
            tank_id=body.tank_id,
            biomass_kg=body.biomass_kg,
            current_fcr=body.current_fcr,
            water_quality_penalty=body.water_quality_penalty,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Recommendation failed: {exc}",
        )


@router.post(
    "/reset/{tank_id}",
    summary="Reset feeding session for a tank",
)
async def reset_session(
    tank_id: str,
    engine: FeedingInferenceEngine = Depends(_get_engine),
) -> dict:
    """Clear the accumulated frame statistics for the given tank.

    Call this at the start of each new feeding period so the recommendation
    engine starts fresh.
    """
    engine.reset_session(tank_id)
    return {"tank_id": tank_id, "message": "session reset"}


@router.get(
    "/status",
    summary="Feeding model status",
)
def get_status(engine: FeedingInferenceEngine = Depends(_get_engine)) -> dict:
    """Return current model version, load status, and active tank sessions."""
    return engine.status()
