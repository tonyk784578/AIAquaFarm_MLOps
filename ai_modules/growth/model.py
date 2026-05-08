"""Growth AI vision model wrapper.

Wraps a YOLOv8-based fish detection model for inference.
Model weights are loaded from a local .pt file or the MLflow model registry.

Requires the optional vision extras for full functionality:
    pip install 'ai_modules[vision]'   # installs ultralytics + opencv
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
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
    """YOLOv8-based fish detection model.

    Loads ultralytics YOLO weights (.pt file or MLflow URI) and returns
    per-frame bounding box detections for downstream size estimation and
    population counting.

    Attributes:
        model: Loaded ultralytics YOLO model instance (None until load() called).
        model_version: Version string derived from file stem or MLflow stage.
        is_loaded: True once model weights are successfully loaded.
    """

    def __init__(self) -> None:
        self.model: Any = None
        self.model_version: str = "not_loaded"
        self.is_loaded: bool = False

    def load(self, model_path: str) -> None:
        """Load YOLOv8 model weights.

        Args:
            model_path: Path to a .pt weights file (e.g. 'runs/detect/train/weights/best.pt')
                        or an MLflow models URI (e.g. 'models:/FishDetection/Production').
                        MLflow URIs are downloaded via mlflow.artifacts and loaded as YOLO.

        Raises:
            ImportError: If ultralytics is not installed (install ai_modules[vision]).
            RuntimeError: If the weights file cannot be loaded.
        """
        logger.info("loading_fish_detection_model", model_path=model_path)
        try:
            from ultralytics import YOLO  # optional vision dep
        except ImportError:
            logger.error(
                "ultralytics_not_installed",
                hint="pip install 'ai_modules[vision]' to enable fish detection",
            )
            return

        try:
            if model_path.startswith("models:/"):
                # Download MLflow artifact to a temp dir and load as YOLO
                import tempfile
                import mlflow.artifacts

                with tempfile.TemporaryDirectory() as tmp:
                    local_pt = mlflow.artifacts.download_artifacts(
                        artifact_uri=model_path, dst_path=tmp
                    )
                    self.model = YOLO(local_pt)
                self.model_version = model_path.rsplit("/", 1)[-1]
            else:
                self.model = YOLO(model_path)
                self.model_version = Path(model_path).stem

            self.is_loaded = True
            logger.info(
                "fish_detection_model_loaded",
                version=self.model_version,
                path=model_path,
            )
        except Exception as exc:
            logger.error("fish_detection_model_load_failed", path=model_path, error=str(exc))

    def predict(self, frame: Any) -> list[dict[str, Any]]:
        """Run YOLOv8 detection on a single frame.

        Args:
            frame: numpy array (H, W, 3) in BGR or RGB format, or a path/bytes
                   accepted by ultralytics YOLO.

        Returns:
            List of detection dicts, each with keys:
                bbox        — [x1, y1, x2, y2] pixel coordinates
                confidence  — float in [0, 1]
                class_id    — int YOLO class index
        """
        if not self.is_loaded or self.model is None:
            logger.debug("fish_detection_model_not_loaded_returning_empty")
            return []

        results = self.model(frame, verbose=False)
        detections: list[dict[str, Any]] = []
        for result in results:
            for box in result.boxes:
                detections.append({
                    "bbox": box.xyxy[0].tolist(),       # [x1, y1, x2, y2]
                    "confidence": float(box.conf[0]),
                    "class_id": int(box.cls[0]),
                })
        return detections

    def get_version(self) -> str:
        return self.model_version
