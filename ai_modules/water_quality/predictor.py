"""Water quality predictor — high-level async interface.

Called by the FastAPI service layer after the feature window has been
fetched from TimescaleDB.  Applies the FeatureScaler, runs MC-Dropout
inference, and returns a VirtualSensorPrediction.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Optional

import numpy as np
import structlog

from ai_modules.water_quality.feature_engineering import FeatureScaler
from ai_modules.water_quality.model import WaterQualityPredictionModel
from ai_modules.water_quality.schemas import VirtualSensorPrediction, WaterQualityFeatures
from ai_modules.water_quality.virtual_sensor import VirtualSensor

logger = structlog.get_logger()


class WaterQualityPredictor:
    """High-level async predictor used by the FastAPI service layer.

    Wraps VirtualSensor with async support.  The singleton model and scaler
    are injected at construction time (loaded once at application start-up).

    Attributes:
        sensor: Underlying VirtualSensor instance.
        latest_predictions: Cache of most recent prediction per tank.
    """

    def __init__(
        self,
        model: Optional[WaterQualityPredictionModel] = None,
        scaler: Optional[FeatureScaler] = None,
        ammonia_threshold_ppm: float = 0.5,
        nitrite_threshold_ppm: float = 0.1,
    ) -> None:
        self.sensor = VirtualSensor(
            model=model,
            scaler=scaler,
            ammonia_threshold_ppm=ammonia_threshold_ppm,
            nitrite_threshold_ppm=nitrite_threshold_ppm,
        )
        self.latest_predictions: dict[str, VirtualSensorPrediction] = {}

    async def predict_from_window(
        self,
        tank_id: str,
        window: np.ndarray,
        timestamp: Optional[datetime] = None,
        mc_samples: Optional[int] = None,
    ) -> VirtualSensorPrediction:
        """Run inference on a pre-fetched feature window.

        This is the primary entry point for the backend service.  The window
        comes from TimescaleDB (already sorted, imputed, and trimmed to SEQ_LEN
        rows) and does NOT need further gap-filling here.

        Args:
            tank_id: Tank identifier.
            window: Raw (un-normalised) feature array, shape (seq_len, n_features).
            timestamp: Prediction timestamp; defaults to UTC now.
            mc_samples: Override MC-Dropout sample count.

        Returns:
            VirtualSensorPrediction with CI bounds and alert flags.
        """
        ts = timestamp or datetime.now(timezone.utc)

        # Run in a thread pool to avoid blocking the event loop
        prediction = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: self._run_inference(tank_id, window, ts, mc_samples),
        )
        self.latest_predictions[tank_id] = prediction
        logger.info(
            "water_quality_prediction_updated",
            tank_id=tank_id,
            ammonia_ppm=round(prediction.ammonia_ppm, 4),
            nitrite_ppm=round(prediction.nitrite_ppm, 4),
            ammonia_alert=prediction.ammonia_alert,
        )
        return prediction

    def _run_inference(
        self,
        tank_id: str,
        window: np.ndarray,
        timestamp: datetime,
        mc_samples: Optional[int],
    ) -> VirtualSensorPrediction:
        """Synchronous inference; called via run_in_executor."""
        scaler = self.sensor.scaler
        normalised = scaler.transform_features(window) if scaler.is_fitted else window
        raw = self.sensor.model.predict(normalised, mc_samples=mc_samples)

        ammonia = raw["ammonia_ppm"]
        nitrite = raw["nitrite_ppm"]

        if scaler.is_fitted:
            arr = np.array([[ammonia, nitrite]])
            restored = scaler.inverse_transform_targets(arr)[0]
            ammonia = float(np.clip(restored[0], 0.0, None))
            nitrite = float(np.clip(restored[1], 0.0, None))

        return VirtualSensorPrediction(
            tank_id=tank_id,
            timestamp=timestamp,
            ammonia_ppm=ammonia,
            nitrite_ppm=nitrite,
            ammonia_confidence=raw["ammonia_confidence"],
            nitrite_confidence=raw["nitrite_confidence"],
            ammonia_ci_lower=raw["ammonia_ci_lower"],
            ammonia_ci_upper=raw["ammonia_ci_upper"],
            nitrite_ci_lower=raw["nitrite_ci_lower"],
            nitrite_ci_upper=raw["nitrite_ci_upper"],
            model_version=self.sensor.model.get_version(),
            ammonia_alert=ammonia >= self.sensor.ammonia_threshold_ppm,
            nitrite_alert=nitrite >= self.sensor.nitrite_threshold_ppm,
        )

    async def process_sensor_reading(
        self, reading: WaterQualityFeatures
    ) -> VirtualSensorPrediction:
        """Process an individual sensor reading by appending to the rolling buffer.

        Used by streaming / edge-push scenarios where readings arrive one at
        a time rather than as a DB-fetched window.

        Args:
            reading: Physical sensor features from the data collector.

        Returns:
            Latest VirtualSensorPrediction for the tank.
        """
        prediction = await asyncio.get_event_loop().run_in_executor(
            None, lambda: self.sensor.update(reading)
        )
        self.latest_predictions[reading.tank_id] = prediction
        return prediction

    def get_latest(self, tank_id: str) -> Optional[VirtualSensorPrediction]:
        """Return the most recent prediction for a tank, or None."""
        return self.latest_predictions.get(tank_id)

    def get_risk_score(self, tank_id: str) -> float:
        """Compute a combined water quality risk score (0.0–1.0).

        Args:
            tank_id: Tank identifier.

        Returns:
            Risk score (0.0 = safe, 1.0 = critical).
        """
        pred = self.latest_predictions.get(tank_id)
        if not pred:
            return 0.0
        ammonia_risk = min(1.0, pred.ammonia_ppm / max(self.sensor.ammonia_threshold_ppm, 1e-6))
        nitrite_risk = min(1.0, pred.nitrite_ppm / max(self.sensor.nitrite_threshold_ppm, 1e-6))
        return max(ammonia_risk, nitrite_risk)
