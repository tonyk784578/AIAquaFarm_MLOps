"""Growth detection API endpoints.

Routes
------
POST /api/v1/growth/detect
    Run fish detection on a single uploaded frame.

GET  /api/v1/growth/status
    Return model load status and per-tank tracker info.

GET  /api/v1/growth/count/{tank_id}
    Return the current fish count estimate for a tank.
"""

from __future__ import annotations

from datetime import UTC, datetime

from ai_modules.growth.schemas import GrowthInferenceInput, GrowthInferenceOutput
from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.services.growth_service import GrowthInferenceEngine, GrowthService

router = APIRouter()


def _get_engine(request: Request) -> GrowthInferenceEngine:
    """FastAPI dependency: retrieve the growth engine from app.state."""
    engine: GrowthInferenceEngine = getattr(request.app.state, "growth_engine", None)
    if engine is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Growth inference engine not initialised",
        )
    return engine


def _get_service(
    engine: GrowthInferenceEngine = Depends(_get_engine),
) -> GrowthService:
    return GrowthService(engine)


@router.post(
    "/detect",
    response_model=GrowthInferenceOutput,
    summary="Detect fish and estimate size/biomass from a camera frame",
)
async def detect_fish(
    body: GrowthInferenceInput,
    service: GrowthService = Depends(_get_service),
) -> GrowthInferenceOutput:
    """Run YOLOv8 fish detection on a single frame.

    The frame is provided as raw bytes (JPEG/PNG) in the JSON body.
    Returns bounding boxes, per-fish length/weight estimates, population
    count, and total biomass.

    Body fields:
    - **tank_id**: Tank identifier
    - **frame_bytes**: Base64-encoded JPEG/PNG frame
    - **timestamp**: Frame capture time (ISO 8601)
    - **camera_id**: Camera identifier (default: "default")
    - **pixel_per_cm_ratio**: Camera calibration ratio (optional)
    """
    try:
        return service.detect(body)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Detection failed: {exc}",
        )


@router.get(
    "/status",
    summary="Growth model status",
)
def get_status(engine: GrowthInferenceEngine = Depends(_get_engine)) -> dict:
    """Return current model version, load status, and tracked tanks."""
    return engine.status()


@router.get(
    "/count/{tank_id}",
    summary="Current fish count estimate for a tank",
)
def get_fish_count(
    tank_id: str,
    engine: GrowthInferenceEngine = Depends(_get_engine),
) -> dict:
    """Return the most recent fish count for the given tank.

    Count is maintained across frames via the in-memory FishCounter tracker.
    """
    counter = engine.counters.get(tank_id)
    return {
        "tank_id": tank_id,
        "fish_count": counter.unique_count if counter else 0,
        "model_version": engine.model.get_version(),
        "queried_at": datetime.now(UTC).isoformat(),
    }
