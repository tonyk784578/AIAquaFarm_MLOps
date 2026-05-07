"""Pydantic schemas for growth AI module inputs and outputs."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class GrowthInferenceInput(BaseModel):
    """Input to the growth AI module."""

    tank_id: str
    frame_bytes: bytes = Field(..., description="Raw JPEG/PNG frame bytes")
    timestamp: datetime
    camera_id: str = "default"
    pixel_per_cm_ratio: Optional[float] = Field(
        None, description="Calibration ratio for size estimation"
    )


class FishDetection(BaseModel):
    """Single fish detection result from the vision model."""

    bbox: list[float] = Field(..., description="[x1, y1, x2, y2] bounding box")
    confidence: float = Field(..., ge=0.0, le=1.0)
    estimated_length_cm: Optional[float] = None
    estimated_weight_g: Optional[float] = None


class GrowthInferenceOutput(BaseModel):
    """Output from the growth AI module inference pass."""

    tank_id: str
    timestamp: datetime
    fish_count: int
    detections: list[FishDetection]
    avg_length_cm: Optional[float] = None
    avg_weight_g: Optional[float] = None
    biomass_kg: Optional[float] = None
    model_version: str = "unknown"
    inference_time_ms: Optional[float] = None
