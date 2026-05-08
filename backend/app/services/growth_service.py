"""Growth AI inference service.

Provides:
    GrowthInferenceEngine  — singleton; holds FishDetectionModel + helpers.
    GrowthService          — per-request service; runs inference and returns
                             GrowthInferenceOutput.
"""

from __future__ import annotations

import time

import structlog
from ai_modules.growth.counter import FishCounter
from ai_modules.growth.model import FishDetectionModel
from ai_modules.growth.schemas import (
    FishDetection,
    GrowthInferenceInput,
    GrowthInferenceOutput,
)
from ai_modules.growth.size_estimator import SizeEstimator

logger = structlog.get_logger()


class GrowthInferenceEngine:
    """Application-scoped singleton holding growth AI components.

    Attributes:
        model: FishDetectionModel (YOLOv8 wrapper).
        size_estimator: Converts bbox → length/weight.
        counter: Per-tank fish population tracker.
        is_ready: True once model weights are loaded.
    """

    def __init__(self) -> None:
        self.model = FishDetectionModel()
        self.size_estimator = SizeEstimator()
        self.counters: dict[str, FishCounter] = {}
        self.is_ready: bool = False
        self._model_path: str = ""

    @classmethod
    def from_checkpoint(cls, model_path: str) -> GrowthInferenceEngine:
        """Load from a local YOLOv8 .pt checkpoint.

        Args:
            model_path: Path to YOLO .pt weights file.

        Returns:
            Initialised engine. Falls back gracefully if load fails.
        """
        engine = cls()
        engine._model_path = model_path
        engine.model.load(model_path)
        engine.is_ready = engine.model.is_loaded
        if engine.is_ready:
            logger.info("growth_engine_ready", path=model_path)
        else:
            logger.warning("growth_engine_degraded", path=model_path)
        return engine

    @classmethod
    def from_mlflow(
        cls,
        tracking_uri: str,
        model_name: str = "FishDetection",
        stage: str = "Production",
    ) -> GrowthInferenceEngine:
        """Load from the MLflow model registry.

        Args:
            tracking_uri: MLflow server URL.
            model_name: Registered model name.
            stage: Model stage ('Production', 'Staging').

        Returns:
            Initialised engine. Falls back gracefully if MLflow unreachable.
        """
        engine = cls()
        uri = f"models:/{model_name}/{stage}"
        engine._model_path = f"{tracking_uri} | {uri}"
        try:
            import mlflow
            mlflow.set_tracking_uri(tracking_uri)
            engine.model.load(uri)
            engine.is_ready = engine.model.is_loaded
            logger.info("growth_engine_ready_from_mlflow", uri=uri)
        except Exception as exc:
            logger.warning("growth_engine_mlflow_unavailable", error=str(exc))
        return engine

    def _get_counter(self, tank_id: str) -> FishCounter:
        if tank_id not in self.counters:
            self.counters[tank_id] = FishCounter()
        return self.counters[tank_id]

    def run_inference(self, inp: GrowthInferenceInput) -> GrowthInferenceOutput:
        """Run full growth inference pipeline on one frame.

        Args:
            inp: GrowthInferenceInput with frame bytes and tank metadata.

        Returns:
            GrowthInferenceOutput with detections, counts, and biomass estimate.
        """
        t0 = time.perf_counter()

        pixel_per_cm = inp.pixel_per_cm_ratio or self.size_estimator.pixel_per_cm
        estimator = SizeEstimator(pixel_per_cm=pixel_per_cm)

        raw_detections = self.model.predict(inp.frame_bytes)

        fish_detections: list[FishDetection] = []
        lengths_cm: list[float] = []

        for det in raw_detections:
            length_cm = estimator.bbox_to_length_cm(det["bbox"])
            weight_g = estimator.length_to_weight_g(length_cm)
            fish_detections.append(
                FishDetection(
                    bbox=det["bbox"],
                    confidence=det["confidence"],
                    estimated_length_cm=round(length_cm, 2),
                    estimated_weight_g=round(weight_g, 2),
                )
            )
            lengths_cm.append(length_cm)

        counter = self._get_counter(inp.tank_id)
        fish_count = counter.update(raw_detections)

        biomass_kg = estimator.estimate_biomass_kg(lengths_cm, fish_count=fish_count)

        elapsed_ms = (time.perf_counter() - t0) * 1000

        return GrowthInferenceOutput(
            tank_id=inp.tank_id,
            timestamp=inp.timestamp,
            fish_count=fish_count,
            detections=fish_detections,
            avg_length_cm=round(sum(lengths_cm) / len(lengths_cm), 2) if lengths_cm else None,
            avg_weight_g=round(
                sum(estimator.length_to_weight_g(lc) for lc in lengths_cm) / len(lengths_cm), 2
            ) if lengths_cm else None,
            biomass_kg=round(biomass_kg, 3),
            model_version=self.model.get_version(),
            inference_time_ms=round(elapsed_ms, 1),
        )

    def status(self) -> dict:
        return {
            "model_name": "FishDetection",
            "is_loaded": self.is_ready,
            "model_version": self.model.get_version(),
            "model_path": self._model_path,
            "device": "cpu",
            "tracked_tanks": list(self.counters.keys()),
        }


class GrowthService:
    """Per-request service wrapping the GrowthInferenceEngine."""

    def __init__(self, engine: GrowthInferenceEngine) -> None:
        self.engine = engine

    def detect(self, inp: GrowthInferenceInput) -> GrowthInferenceOutput:
        """Run fish detection and return growth inference output.

        Args:
            inp: Frame and tank metadata.

        Returns:
            GrowthInferenceOutput.

        Raises:
            RuntimeError: If engine is not ready and no fallback is possible.
        """
        result = self.engine.run_inference(inp)
        logger.info(
            "growth_inference_done",
            tank_id=inp.tank_id,
            fish_count=result.fish_count,
            biomass_kg=result.biomass_kg,
            ms=result.inference_time_ms,
        )
        return result
