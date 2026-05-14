"""Feeding activity vision model wrapper.

Classifies feeding activity level from camera frames using a
ResNet18-based regression model trained on RAS feeding footage.

Architecture:
    ResNet18 backbone (pretrained on ImageNet, optional)
      └─ FC(512 → 1) + Sigmoid  →  activity score [0.0, 1.0]

Score interpretation:
    0.0–0.3  Low activity (satiation or illness — reduce/stop feed)
    0.3–0.7  Normal feeding activity
    0.7–1.0  High activity (fish are hungry — can increase feed)

Requires the optional vision extras for full functionality:
    pip install 'ai_modules[vision]'   # installs torchvision + opencv
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any

import numpy as np
import structlog
import torch
import torch.nn as nn

from ai_modules.growth.model import BaseVisionModel

logger = structlog.get_logger()

# Input resolution expected by ResNet18
_IMG_SIZE = 224


def _build_cnn() -> nn.Module:
    """Build ResNet18 regression head for activity score prediction.

    Returns torchvision ResNet18 with the classifier head replaced by a
    single neuron with Sigmoid activation. Falls back to a lightweight
    MobileNet-style stub if torchvision is not installed.
    """
    try:
        from torchvision import models

        backbone = models.resnet18(weights=None)
        # Replace FC: 512 → 1, Sigmoid clamps output to [0, 1]
        backbone.fc = nn.Sequential(nn.Linear(512, 1), nn.Sigmoid())
        return backbone
    except ImportError:
        logger.warning(
            "torchvision_not_installed",
            hint="pip install 'ai_modules[vision]' for full CNN support; using fallback",
        )
        # Minimal fallback: global-avg-pool → linear — still loadable/saveable
        return nn.Sequential(
            nn.AdaptiveAvgPool2d(1),
            nn.Flatten(),
            nn.Linear(1, 1),
            nn.Sigmoid(),
        )


def _decode_frame(frame: Any) -> torch.Tensor:
    """Decode a frame (bytes, numpy, or path) to a (1, 3, H, W) float tensor.

    Normalises pixel values to [0, 1] and resizes to _IMG_SIZE × _IMG_SIZE.
    Returns a zero tensor if decoding fails, so the service degrades gracefully.
    """
    try:
        if isinstance(frame, bytes):
            try:
                import cv2  # optional vision dep

                buf = np.frombuffer(frame, dtype=np.uint8)
                img_bgr = cv2.imdecode(buf, cv2.IMREAD_COLOR)
                if img_bgr is None:
                    raise ValueError("cv2.imdecode returned None")
                img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
                img_rgb = cv2.resize(img_rgb, (_IMG_SIZE, _IMG_SIZE))
                arr = img_rgb.astype(np.float32) / 255.0
            except ImportError:
                # cv2 not installed: try PIL
                from PIL import Image  # type: ignore[import-untyped]

                img = Image.open(io.BytesIO(frame)).convert("RGB").resize((_IMG_SIZE, _IMG_SIZE))
                arr = np.array(img, dtype=np.float32) / 255.0

        elif isinstance(frame, np.ndarray):
            # Assume (H, W, 3) uint8 BGR or RGB
            arr = frame.astype(np.float32) / 255.0
            if arr.shape[:2] != (_IMG_SIZE, _IMG_SIZE):
                try:
                    import cv2
                    arr = cv2.resize(arr, (_IMG_SIZE, _IMG_SIZE))
                except ImportError:
                    arr = arr[:_IMG_SIZE, :_IMG_SIZE] if arr.shape[0] >= _IMG_SIZE else arr
        else:
            arr = np.zeros((_IMG_SIZE, _IMG_SIZE, 3), dtype=np.float32)

        # (H, W, C) → (1, C, H, W)
        return torch.from_numpy(arr).permute(2, 0, 1).unsqueeze(0)

    except Exception as exc:
        logger.warning("frame_decode_failed", error=str(exc))
        return torch.zeros(1, 3, _IMG_SIZE, _IMG_SIZE)


class FeedingActivityModel(BaseVisionModel):
    """ResNet18-based regression model for feeding activity score estimation.

    Attributes:
        _net: PyTorch nn.Module (ResNet18 or fallback).
        model_version: Version string from checkpoint or MLflow.
        is_loaded: True once weights are successfully loaded.
        device: Torch device used for inference.
    """

    def __init__(self, device: str = "cpu") -> None:
        self._net: nn.Module | None = None
        self.model_version: str = "not_loaded"
        self.is_loaded: bool = False
        self.device = torch.device(device)

    def load(self, model_path: str) -> None:
        """Load checkpoint weights into the ResNet18 regression model.

        Checkpoint format (saved by training script)::

            {
                "model_state_dict": ...,
                "version": "v1.0",
                "config": {"arch": "resnet18", "img_size": 224},
            }

        Plain state-dict files are also accepted.

        Args:
            model_path: Path to .pt checkpoint or MLflow models URI.
        """
        logger.info("loading_feeding_activity_model", path=model_path)

        try:
            if model_path.startswith("models:/"):
                import tempfile
                import mlflow.artifacts

                with tempfile.TemporaryDirectory() as tmp:
                    model_path = mlflow.artifacts.download_artifacts(
                        artifact_uri=model_path, dst_path=tmp
                    )

            net = _build_cnn().to(self.device)
            ckpt = torch.load(model_path, map_location=self.device, weights_only=True)

            state = ckpt.get("model_state_dict", ckpt)
            net.load_state_dict(state)
            net.eval()

            self._net = net
            self.model_version = ckpt.get("version", Path(model_path).stem) if isinstance(ckpt, dict) else Path(model_path).stem
            self.is_loaded = True
            logger.info("feeding_activity_model_loaded", version=self.model_version)

        except Exception as exc:
            logger.error("feeding_activity_model_load_failed", path=model_path, error=str(exc))

    @torch.no_grad()
    def predict(self, frame: Any) -> list[dict[str, Any]]:
        """Return activity score for a single frame.

        Args:
            frame: Raw frame as bytes (JPEG/PNG), numpy array (H, W, 3),
                   or any type accepted by _decode_frame().

        Returns:
            Single-element list with dict:
                activity_score  — float in [0, 1]
                confidence      — 1.0 if model loaded, 0.0 otherwise
        """
        if not self.is_loaded or self._net is None:
            return [{"activity_score": 0.5, "confidence": 0.0}]

        tensor = _decode_frame(frame).to(self.device)
        score = float(self._net(tensor).squeeze().item())
        return [{"activity_score": round(score, 4), "confidence": 1.0}]

    def pytorch_model(self) -> nn.Module:
        """Return the underlying PyTorch model (for training loops)."""
        if self._net is None:
            self._net = _build_cnn().to(self.device)
        return self._net

    def save_checkpoint(self, path: str, version: str = "dev") -> None:
        """Save weights and metadata to a .pt checkpoint.

        Args:
            path: Destination file path.
            version: Version string embedded in checkpoint.
        """
        if self._net is None:
            raise RuntimeError("No model to save — call load() or build the model first")
        torch.save(
            {
                "model_state_dict": self._net.state_dict(),
                "version": version,
                "config": {"arch": "resnet18", "img_size": _IMG_SIZE},
            },
            path,
        )
        logger.info("feeding_model_checkpoint_saved", path=path, version=version)

    def get_version(self) -> str:
        return self.model_version
