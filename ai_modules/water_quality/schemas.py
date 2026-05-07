"""Pydantic schemas for water quality AI module."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class WaterQualityFeatures(BaseModel):
    """Input features for the virtual sensor model."""

    tank_id: str
    timestamp: datetime

    # Physical sensor inputs (model features)
    temperature_c: float = Field(..., ge=0.0, le=50.0)
    ph: float = Field(..., ge=0.0, le=14.0)
    dissolved_oxygen_mgl: float = Field(..., ge=0.0, le=30.0)
    turbidity_ntu: Optional[float] = Field(None, ge=0.0)
    conductivity_us_cm: Optional[float] = Field(None, ge=0.0)

    # Operational context
    feeding_amount_kg_24h: Optional[float] = Field(None, ge=0.0)
    biomass_kg: Optional[float] = Field(None, ge=0.0)
    water_exchange_rate_pct: Optional[float] = Field(None, ge=0.0, le=100.0)


class VirtualSensorPrediction(BaseModel):
    """Output of the virtual sensor model."""

    tank_id: str
    timestamp: datetime

    # Predicted values
    ammonia_ppm: float = Field(..., ge=0.0)
    nitrite_ppm: float = Field(..., ge=0.0)
    nitrate_ppm: Optional[float] = Field(None, ge=0.0)

    # Prediction uncertainty
    ammonia_confidence: float = Field(..., ge=0.0, le=1.0)
    nitrite_confidence: float = Field(..., ge=0.0, le=1.0)
    ammonia_ci_lower: float = 0.0
    ammonia_ci_upper: float = 0.0
    nitrite_ci_lower: float = 0.0
    nitrite_ci_upper: float = 0.0

    model_version: str = "unknown"

    # Threshold breach flags
    ammonia_alert: bool = False
    nitrite_alert: bool = False


# ── API request / response schemas ────────────────────────────────────────────

class PredictRequest(BaseModel):
    """Request body for POST /api/v1/water-quality/predict."""

    tank_id: str = Field(..., description="Tank identifier")
    mc_samples: Optional[int] = Field(
        None, ge=1, le=200, description="MC-Dropout samples; defaults to model config"
    )


class PredictResponse(BaseModel):
    """Response from POST /api/v1/water-quality/predict."""

    tank_id: str
    predicted_at: datetime

    ammonia_ppm: float
    nitrite_ppm: float

    ammonia_confidence: float
    nitrite_confidence: float

    ammonia_ci_lower: float
    ammonia_ci_upper: float
    nitrite_ci_lower: float
    nitrite_ci_upper: float

    ammonia_alert: bool
    nitrite_alert: bool

    model_version: str
    window_hours: int


class ForecastPoint(BaseModel):
    """Single timestep in a multi-step forecast."""

    timestamp: datetime
    ammonia_ppm: float
    nitrite_ppm: float
    ammonia_confidence: float
    nitrite_confidence: float


class ForecastResponse(BaseModel):
    """Response from GET /api/v1/water-quality/forecast/{tank_id}."""

    tank_id: str
    generated_at: datetime
    horizon_hours: int
    forecast: list[ForecastPoint]
    model_version: str


class ModelStatusResponse(BaseModel):
    """Response from GET /api/v1/water-quality/model-status."""

    is_loaded: bool
    model_version: str
    architecture: str
    device: str
    scaler_fitted: bool
    mlflow_uri: str
