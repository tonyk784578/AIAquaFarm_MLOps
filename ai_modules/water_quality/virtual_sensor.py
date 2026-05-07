"""Virtual sensor — orchestrates real-time water quality prediction.

Maintains a per-tank rolling feature window (SEQ_LEN rows), normalises
features with a FeatureScaler, runs the prediction model, applies threshold
checks, and returns a VirtualSensorPrediction with 95% CI bounds.
"""

from collections import deque
from datetime import datetime, timezone
from typing import Optional

import numpy as np
import structlog

from ai_modules.water_quality.feature_engineering import (
    FEATURE_DEFAULTS,
    FeatureScaler,
)
from ai_modules.water_quality.model import FEATURE_NAMES, SEQ_LEN, WaterQualityPredictionModel
from ai_modules.water_quality.schemas import VirtualSensorPrediction, WaterQualityFeatures

logger = structlog.get_logger()


def _features_to_vector(f: WaterQualityFeatures) -> list[float]:
    """Map WaterQualityFeatures onto the canonical 8-element feature vector."""
    return [
        f.temperature_c,
        f.ph,
        f.dissolved_oxygen_mgl,
        f.turbidity_ntu if f.turbidity_ntu is not None else FEATURE_DEFAULTS["turbidity_ntu"],
        f.conductivity_us_cm if f.conductivity_us_cm is not None else FEATURE_DEFAULTS["conductivity_us_cm"],
        f.feeding_amount_kg_24h if f.feeding_amount_kg_24h is not None else FEATURE_DEFAULTS["feeding_amount_kg_24h"],
        f.biomass_kg if f.biomass_kg is not None else FEATURE_DEFAULTS["biomass_kg"],
        f.water_exchange_rate_pct if f.water_exchange_rate_pct is not None else FEATURE_DEFAULTS["water_exchange_rate_pct"],
    ]


class VirtualSensor:
    """Real-time virtual sensor for ammonia and nitrite monitoring.

    Maintains a per-tank rolling deque of feature vectors, runs the
    prediction model on each new reading, and checks alert thresholds.

    Attributes:
        model: Loaded WaterQualityPredictionModel.
        scaler: FeatureScaler for z-score normalisation.
        window_size: Rolling window length (== SEQ_LEN).
        ammonia_threshold_ppm: Alert threshold for ammonia.
        nitrite_threshold_ppm: Alert threshold for nitrite.
        feature_buffers: Per-tank rolling deque of raw feature vectors.
    """

    def __init__(
        self,
        model: Optional[WaterQualityPredictionModel] = None,
        scaler: Optional[FeatureScaler] = None,
        window_size: int = SEQ_LEN,
        ammonia_threshold_ppm: float = 0.5,
        nitrite_threshold_ppm: float = 0.1,
    ) -> None:
        self.model = model or WaterQualityPredictionModel()
        self.scaler = scaler or FeatureScaler()
        self.window_size = window_size
        self.ammonia_threshold_ppm = ammonia_threshold_ppm
        self.nitrite_threshold_ppm = nitrite_threshold_ppm
        self.feature_buffers: dict[str, deque] = {}

    def update(
        self,
        features: WaterQualityFeatures,
        mc_samples: Optional[int] = None,
    ) -> VirtualSensorPrediction:
        """Process a new physical sensor reading and return a prediction.

        Args:
            features: Current physical sensor features for a tank.
            mc_samples: MC-Dropout passes; defaults to model cfg.

        Returns:
            VirtualSensorPrediction with CI bounds and alert flags.
        """
        tank_id = features.tank_id
        if tank_id not in self.feature_buffers:
            self.feature_buffers[tank_id] = deque(maxlen=self.window_size)

        self.feature_buffers[tank_id].append(_features_to_vector(features))

        if len(self.feature_buffers[tank_id]) < self.window_size:
            logger.info(
                "virtual_sensor_warming_up",
                tank_id=tank_id,
                buffered=len(self.feature_buffers[tank_id]),
                needed=self.window_size,
            )
            return self._default_prediction(tank_id, features.timestamp)

        raw = np.array(list(self.feature_buffers[tank_id]), dtype=np.float32)
        sequence = self.scaler.transform_features(raw) if self.scaler.is_fitted else raw
        prediction = self.model.predict(sequence, mc_samples=mc_samples)

        ammonia = prediction["ammonia_ppm"]
        nitrite = prediction["nitrite_ppm"]

        # Inverse-transform if scaler is fitted with target stats
        if self.scaler.is_fitted:
            raw_preds = np.array([[ammonia, nitrite]])
            restored = self.scaler.inverse_transform_targets(raw_preds)[0]
            ammonia = float(np.clip(restored[0], 0.0, None))
            nitrite = float(np.clip(restored[1], 0.0, None))

        result = VirtualSensorPrediction(
            tank_id=tank_id,
            timestamp=features.timestamp,
            ammonia_ppm=ammonia,
            nitrite_ppm=nitrite,
            ammonia_confidence=prediction["ammonia_confidence"],
            nitrite_confidence=prediction["nitrite_confidence"],
            ammonia_ci_lower=prediction["ammonia_ci_lower"],
            ammonia_ci_upper=prediction["ammonia_ci_upper"],
            nitrite_ci_lower=prediction["nitrite_ci_lower"],
            nitrite_ci_upper=prediction["nitrite_ci_upper"],
            model_version=self.model.get_version(),
            ammonia_alert=ammonia >= self.ammonia_threshold_ppm,
            nitrite_alert=nitrite >= self.nitrite_threshold_ppm,
        )

        if result.ammonia_alert or result.nitrite_alert:
            logger.warning(
                "virtual_sensor_threshold_breach",
                tank_id=tank_id,
                ammonia_ppm=ammonia,
                nitrite_ppm=nitrite,
            )

        return result

    def _default_prediction(
        self, tank_id: str, timestamp: datetime
    ) -> VirtualSensorPrediction:
        """Return a zero-confidence default when the window is not yet full."""
        return VirtualSensorPrediction(
            tank_id=tank_id,
            timestamp=timestamp,
            ammonia_ppm=0.0,
            nitrite_ppm=0.0,
            ammonia_confidence=0.0,
            nitrite_confidence=0.0,
            model_version="warming_up",
        )
