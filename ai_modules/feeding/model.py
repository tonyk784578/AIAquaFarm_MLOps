"""Feeding activity vision model wrapper.

Classifies feeding activity level from camera frames using a
CNN-based classifier trained on RAS feeding footage.

TODO (Phase 2): Train classifier on labelled feeding activity frames from CVAT.
TODO (Phase 2): Add feed waste detection (uneaten pellet segmentation).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

import structlog

from ai_modules.growth.model import BaseVisionModel

logger = structlog.get_logger()


class FeedingActivityModel(BaseVisionModel):
    """CNN classifier for feeding activity score estimation.

    Outputs a continuous activity score (0.0–1.0) from a single frame.
    Score interpretation:
        0.0–0.3: Low activity (satiation or sickness)
        0.3–0.7: Normal feeding activity
        0.7–1.0: High activity (hungry, increase feed)
    """

    def __init__(self) -> None:
        self.model: Any = None
        self.model_version: str = "not_loaded"
        self.is_loaded: bool = False

    def load(self, model_path: str) -> None:
        """Load feeding activity classifier weights.

        Args:
            model_path: Path to model or MLflow URI.

        TODO (Phase 2): Load torchvision model from MLflow registry.
        """
        logger.info("loading_feeding_activity_model", model_path=model_path)
        # TODO (Phase 2): self.model = torch.load(model_path); self.model.eval()
        logger.warning("feeding_activity_model_stub")

    def predict(self, frame: Any) -> list[dict[str, Any]]:
        """Return activity score for a single frame.

        Args:
            frame: numpy array (H, W, 3) BGR frame.

        Returns:
            List with single dict: {'activity_score': float, 'confidence': float}.

        TODO (Phase 2): Implement real CNN forward pass.
        """
        return [{"activity_score": 0.5, "confidence": 0.0}]

    def get_version(self) -> str:
        return self.model_version
