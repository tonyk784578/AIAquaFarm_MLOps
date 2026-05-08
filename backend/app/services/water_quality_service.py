"""Water quality inference service.

Provides:
    WaterQualityInferenceEngine  — singleton; holds the loaded model+scaler.
    WaterQualityService          — per-request service; queries TimescaleDB,
                                   runs inference, persists results.

The engine is initialised once in the FastAPI lifespan and stored on
``app.state`` so it survives across requests.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
import pandas as pd
import structlog
from ai_modules.water_quality.feature_engineering import (
    FeatureScaler,
    WindowBuilder,
    impute_window,
)
from ai_modules.water_quality.model import (
    FEATURE_NAMES,
    SEQ_LEN,
    WaterQualityPredictionModel,
)
from ai_modules.water_quality.predictor import WaterQualityPredictor
from ai_modules.water_quality.schemas import (
    ForecastPoint,
    ForecastResponse,
    ModelStatusResponse,
    PredictResponse,
)
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.water_quality import WaterQualityReading

logger = structlog.get_logger()

# TimescaleDB query — hourly buckets for the last SEQ_LEN hours
_FEATURE_WINDOW_SQL = text("""
SELECT
    time_bucket('1 hour', measured_at)              AS bucket,
    avg(temperature_c)                              AS temperature_c,
    avg(ph)                                         AS ph,
    avg(dissolved_oxygen_mgl)                       AS dissolved_oxygen_mgl,
    avg(turbidity_ntu)                              AS turbidity_ntu,
    avg(conductivity_us_cm)                         AS conductivity_us_cm,
    avg(feeding_amount_kg_24h)                      AS feeding_amount_kg_24h,
    avg(biomass_kg)                                 AS biomass_kg,
    avg(water_exchange_rate_pct)                    AS water_exchange_rate_pct
FROM water_quality_readings
WHERE
    tank_id    = :tank_id
    AND measured_at >= NOW() - INTERVAL '25 hours'
GROUP BY bucket
ORDER BY bucket ASC
""")


class WaterQualityInferenceEngine:
    """Application-scoped singleton holding the loaded model and scaler.

    Constructed once during FastAPI lifespan and stored on ``app.state``.
    Falls back gracefully when MLflow is unavailable (e.g., local dev).

    Attributes:
        model: Loaded WaterQualityPredictionModel.
        scaler: Fitted FeatureScaler.
        predictor: WaterQualityPredictor wrapping model+scaler.
        is_ready: True once a model has been loaded.
    """

    def __init__(self) -> None:
        self.model: WaterQualityPredictionModel = WaterQualityPredictionModel()
        self.scaler: FeatureScaler = FeatureScaler()
        self.predictor: WaterQualityPredictor = WaterQualityPredictor()
        self.is_ready: bool = False
        self._mlflow_uri: str = ""

    @classmethod
    def from_mlflow(
        cls,
        tracking_uri: str,
        model_name: str = "WaterQualityPredictor",
        stage: str = "Production",
        device: str = "cpu",
    ) -> WaterQualityInferenceEngine:
        """Construct by loading from the MLflow registry.

        Args:
            tracking_uri: MLflow server URL.
            model_name: Registered model name.
            stage: Model stage to load.
            device: PyTorch device string.

        Returns:
            Initialised engine.  If MLflow is unreachable, returns an engine
            with ``is_ready=False`` and logs a warning.
        """
        engine = cls()
        engine._mlflow_uri = f"{tracking_uri} | models:/{model_name}/{stage}"
        try:
            from ai_modules.water_quality.mlflow_loader import (
                load_production_model_and_scaler,
            )

            model, scaler = load_production_model_and_scaler(
                tracking_uri=tracking_uri,
                model_name=model_name,
                stage=stage,
                device=device,
            )
            engine.model = model
            engine.scaler = scaler
            settings = get_settings()
            engine.predictor = WaterQualityPredictor(
                model=model,
                scaler=scaler,
                ammonia_threshold_ppm=settings.ammonia_threshold_ppm,
                nitrite_threshold_ppm=settings.nitrite_threshold_ppm,
            )
            engine.is_ready = True
            logger.info("wq_inference_engine_ready", uri=engine._mlflow_uri)
        except Exception as exc:
            logger.warning(
                "wq_inference_engine_mlflow_unavailable",
                error=str(exc),
                msg="Running without water quality model",
            )
        return engine

    @classmethod
    def from_checkpoint(
        cls, checkpoint_path: str, scaler_path: str, device: str = "cpu"
    ) -> WaterQualityInferenceEngine:
        """Construct from local checkpoint files (useful for local dev / CI)."""
        engine = cls()
        engine._mlflow_uri = f"file://{checkpoint_path}"
        try:
            engine.model = WaterQualityPredictionModel(device=device)
            engine.model.load_from_checkpoint(checkpoint_path)
            engine.scaler = FeatureScaler.load(scaler_path)
            settings = get_settings()
            engine.predictor = WaterQualityPredictor(
                model=engine.model,
                scaler=engine.scaler,
                ammonia_threshold_ppm=settings.ammonia_threshold_ppm,
                nitrite_threshold_ppm=settings.nitrite_threshold_ppm,
            )
            engine.is_ready = True
            logger.info("wq_inference_engine_ready_from_checkpoint", path=checkpoint_path)
        except Exception as exc:
            logger.warning("wq_inference_engine_checkpoint_failed", error=str(exc))
        return engine

    def status(self) -> ModelStatusResponse:
        """Return a status summary for the /model-status endpoint."""
        return ModelStatusResponse(
            is_loaded=self.is_ready,
            model_version=self.model.get_version(),
            architecture=self.model.cfg.arch,
            device=str(self.model.device),
            scaler_fitted=self.scaler.is_fitted,
            mlflow_uri=self._mlflow_uri,
        )


class WaterQualityService:
    """Per-request service for water quality inference and persistence.

    Args:
        db: Async SQLAlchemy session (injected by FastAPI dependency).
        engine: Application-scoped inference engine.
    """

    def __init__(self, db: AsyncSession, engine: WaterQualityInferenceEngine) -> None:
        self.db = db
        self.engine = engine
        self._builder = WindowBuilder(seq_len=SEQ_LEN, feature_cols=FEATURE_NAMES)

    async def fetch_feature_window(self, tank_id: str) -> np.ndarray:
        """Query the last SEQ_LEN hourly buckets from TimescaleDB.

        Args:
            tank_id: Tank identifier.

        Returns:
            Float32 array of shape (seq_len, n_features).

        Raises:
            ValueError: If there are insufficient rows after imputation.
        """
        result = await self.db.execute(_FEATURE_WINDOW_SQL, {"tank_id": tank_id})
        rows = result.mappings().all()

        if not rows:
            raise ValueError(f"No data found for tank '{tank_id}'")

        df = pd.DataFrame(rows)
        df = df.set_index("bucket")
        df.index = pd.to_datetime(df.index)
        df = df.astype(float)

        df_imputed = impute_window(df, expected_freq="1h", expected_len=SEQ_LEN)

        if len(df_imputed) < SEQ_LEN:
            raise ValueError(
                f"Insufficient history for tank '{tank_id}': "
                f"need {SEQ_LEN} hours, got {len(df_imputed)}"
            )

        return self._builder.build_inference_window(df_imputed)

    async def predict_for_tank(
        self, tank_id: str, mc_samples: int | None = None
    ) -> PredictResponse:
        """Fetch window + run inference for a tank.

        Args:
            tank_id: Tank identifier.
            mc_samples: Optional MC-Dropout sample override.

        Returns:
            PredictResponse with point estimates, CI, and alert flags.
        """
        window = await self.fetch_feature_window(tank_id)
        now = datetime.now(UTC)
        prediction = await self.engine.predictor.predict_from_window(
            tank_id=tank_id,
            window=window,
            timestamp=now,
            mc_samples=mc_samples,
        )
        settings = get_settings()
        return PredictResponse(
            tank_id=tank_id,
            predicted_at=now,
            ammonia_ppm=round(prediction.ammonia_ppm, 4),
            nitrite_ppm=round(prediction.nitrite_ppm, 4),
            ammonia_confidence=prediction.ammonia_confidence,
            nitrite_confidence=prediction.nitrite_confidence,
            ammonia_ci_lower=round(prediction.ammonia_ci_lower, 4),
            ammonia_ci_upper=round(prediction.ammonia_ci_upper, 4),
            nitrite_ci_lower=round(prediction.nitrite_ci_lower, 4),
            nitrite_ci_upper=round(prediction.nitrite_ci_upper, 4),
            ammonia_alert=prediction.ammonia_ppm >= settings.ammonia_threshold_ppm,
            nitrite_alert=prediction.nitrite_ppm >= settings.nitrite_threshold_ppm,
            model_version=prediction.model_version,
            window_hours=SEQ_LEN,
        )

    async def predict_and_save(
        self, tank_id: str, mc_samples: int | None = None
    ) -> PredictResponse:
        """Run inference and persist the result to water_quality_readings.

        Args:
            tank_id: Tank identifier.
            mc_samples: Optional MC-Dropout sample override.

        Returns:
            PredictResponse (same as predict_for_tank).
        """
        response = await self.predict_for_tank(tank_id, mc_samples=mc_samples)
        reading = WaterQualityReading(
            tank_id=tank_id,
            measured_at=response.predicted_at,
            ammonia_ppm=response.ammonia_ppm,
            nitrite_ppm=response.nitrite_ppm,
            ammonia_confidence=response.ammonia_confidence,
            nitrite_confidence=response.nitrite_confidence,
            source="virtual_sensor",
        )
        self.db.add(reading)
        await self.db.flush()
        logger.info(
            "wq_prediction_saved",
            tank_id=tank_id,
            ammonia_ppm=response.ammonia_ppm,
            nitrite_ppm=response.nitrite_ppm,
        )
        return response

    async def get_6h_forecast(self, tank_id: str) -> ForecastResponse:
        """Autoregressive 6-step-ahead forecast (each step = 1 hour).

        Rolls the feature window forward by appending each predicted
        output as the next timestep's ammonia/nitrite proxy.

        Args:
            tank_id: Tank identifier.

        Returns:
            ForecastResponse with 6 ForecastPoint entries.
        """
        window = await self.fetch_feature_window(tank_id)
        scaler = self.engine.scaler
        model = self.engine.model
        now = datetime.now(UTC)
        horizon = 6
        points: list[ForecastPoint] = []

        rolling = window.copy()  # (seq_len, n_features)

        for step in range(horizon):
            normalised = scaler.transform_features(rolling) if scaler.is_fitted else rolling
            raw = model.predict(normalised)

            ammonia = raw["ammonia_ppm"]
            nitrite = raw["nitrite_ppm"]
            if scaler.is_fitted:
                restored = scaler.inverse_transform_targets(np.array([[ammonia, nitrite]]))[0]
                ammonia = float(np.clip(restored[0], 0.0, None))
                nitrite = float(np.clip(restored[1], 0.0, None))

            ts = now + timedelta(hours=step + 1)
            points.append(
                ForecastPoint(
                    timestamp=ts,
                    ammonia_ppm=round(ammonia, 4),
                    nitrite_ppm=round(nitrite, 4),
                    ammonia_confidence=raw["ammonia_confidence"],
                    nitrite_confidence=raw["nitrite_confidence"],
                )
            )

            # Advance rolling window: drop oldest row, append new row with
            # predicted ammonia/nitrite proxied into the feature vector.
            # Columns feeding_amount_kg_24h, biomass_kg, exchange_rate are
            # copied from the last known row (last timestep) as-is.
            new_row = rolling[-1].copy()
            rolling = np.roll(rolling, -1, axis=0)
            rolling[-1] = new_row

        return ForecastResponse(
            tank_id=tank_id,
            generated_at=now,
            horizon_hours=horizon,
            forecast=points,
            model_version=model.get_version(),
        )
