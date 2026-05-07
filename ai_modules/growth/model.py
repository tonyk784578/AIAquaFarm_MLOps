"""Growth AI vision model wrapper.

Wraps a YOLO-based fish detection model for inference.
Model weights are loaded from the MLflow model registry.

TODO (Phase 2): Load model from MLflow registry using mlflow.pyfunc.load_model().
TODO (Phase 2): Implement GPU/CPU device selection and batch inference.
TODO (Phase 2): Add TensorRT optimisation for edge deployment.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

import structlog

logger = structlog.get_logger()


class BaseVisionModel(ABC):
    """Abstract base class for all vision inference models."""

    @abstractmethod
    def load(self, model_path: str) -> None:
        """Load model weights from the given path.

        Args:
            model_path: Path to model weights file or MLflow model URI.
        """

    @abstractmethod
    def predict(self, frame: Any) -> list[dict[str, Any]]:
        """Run inference on a single frame.

        Args:
            frame: Input frame as numpy array (H, W, C) in BGR format.

        Returns:
            List of detection dicts with keys: bbox, confidence, class_id.
        """

    @abstractmethod
    def get_version(self) -> str:
        """Return the model version string."""


class FishDetectionModel(BaseVisionModel):
    """YOLOv8-based fish detection and size estimation model.

    Attributes:
        model: Loaded ultralytics YOLO model instance.
        model_version: Version string from MLflow registry.
        is_loaded: Whether model weights have been loaded.
    """

    def __init__(self) -> None:
        self.model: Any = None
        self.model_version: str = "not_loaded"
        self.is_loaded: bool = False

    def load(self, model_path: str) -> None:
        """Load YOLOv8 model weights.

        Args:
            model_path: Path to .pt weights file or 'models:/FishDetection/latest'.

        TODO (Phase 2): Use mlflow.pyfunc.load_model() for registry models.
        """
        logger.info("loading_fish_detection_model", model_path=model_path)
        # TODO (Phase 2):
        # from ultralytics import YOLO
        # self.model = YOLO(model_path)
        # self.is_loaded = True
        logger.warning("fish_detection_model_stub", msg="Model not yet implemented")

    def predict(self, frame: Any) -> list[dict[str, Any]]:
        """Run YOLOv8 detection on a frame.

        Args:
            frame: numpy array (H, W, 3) BGR frame.

        Returns:
            List of detection dicts.

        TODO (Phase 2): Implement real inference with ultralytics YOLO.
        """
        if not self.is_loaded:
            logger.warning("model_not_loaded_returning_empty")
            return []
        # TODO (Phase 2): results = self.model(frame); return parse_results(results)
        return []

    def get_version(self) -> str:
        return self.model_version
