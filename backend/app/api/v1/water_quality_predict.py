"""Water quality prediction API endpoints.

Routes
------
POST /api/v1/water-quality/predict
    Run inference for a specific tank and persist the result.

GET  /api/v1/water-quality/forecast/{tank_id}
    Return a 6-hour autoregressive forecast.

GET  /api/v1/water-quality/model-status
    Return model load status, version, and scaler info.
"""

from ai_modules.water_quality.schemas import (
    ForecastResponse,
    ModelStatusResponse,
    PredictRequest,
    PredictResponse,
)
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services.water_quality_service import (
    WaterQualityInferenceEngine,
    WaterQualityService,
)

router = APIRouter()


def _get_engine(request: Request) -> WaterQualityInferenceEngine:
    """FastAPI dependency: retrieve the inference engine from app.state."""
    engine: WaterQualityInferenceEngine = getattr(request.app.state, "wq_engine", None)
    if engine is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Water quality inference engine not initialised",
        )
    return engine


def _get_service(
    db: AsyncSession = Depends(get_db),
    engine: WaterQualityInferenceEngine = Depends(_get_engine),
) -> WaterQualityService:
    return WaterQualityService(db, engine)


@router.post(
    "/predict",
    response_model=PredictResponse,
    summary="Run water quality inference for a tank",
)
async def predict_water_quality(
    body: PredictRequest,
    service: WaterQualityService = Depends(_get_service),
) -> PredictResponse:
    """Fetch the last 24-hour feature window from TimescaleDB, run the
    LSTM/Transformer model with MC-Dropout, and persist the prediction.

    Returns ammonia and nitrite point estimates with 95% confidence
    intervals and alert flags.
    """
    try:
        return await service.predict_and_save(body.tank_id, mc_samples=body.mc_samples)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Inference failed: {exc}",
        )


@router.get(
    "/forecast/{tank_id}",
    response_model=ForecastResponse,
    summary="6-hour autoregressive water quality forecast",
)
async def get_forecast(
    tank_id: str,
    service: WaterQualityService = Depends(_get_service),
) -> ForecastResponse:
    """Return a 6-step-ahead (hourly) forecast using autoregressive rollout."""
    try:
        return await service.get_6h_forecast(tank_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Forecast failed: {exc}",
        )


@router.get(
    "/model-status",
    response_model=ModelStatusResponse,
    summary="Water quality model load status",
)
def get_model_status(
    engine: WaterQualityInferenceEngine = Depends(_get_engine),
) -> ModelStatusResponse:
    """Return the current model version, architecture, and scaler status."""
    return engine.status()
