"""Fish population counter using detection tracking.

Counts unique fish across video frames using object tracking to avoid
double-counting fish that appear in multiple frames.

TODO (Phase 2): Implement ByteTrack or SORT multi-object tracker.
TODO (Phase 2): Handle fish occlusion and re-entry events.
"""

from collections import defaultdict
from typing import Any

import structlog

logger = structlog.get_logger()


class FishCounter:
    """Estimates fish population by tracking detections across frames.

    Uses a simple IoU-based tracker as a placeholder until ByteTrack
    is integrated in Phase 2.

    Attributes:
        track_history:  Dict mapping track_id to detection list.
        unique_count:   Current estimate of unique fish seen.
    """

    def __init__(self, iou_threshold: float = 0.3) -> None:
        self.iou_threshold = iou_threshold
        self.track_history: dict[int, list[dict[str, Any]]] = defaultdict(list)
        self._next_id: int = 0
        self.unique_count: int = 0

    def update(self, detections: list[dict[str, Any]]) -> int:
        """Update tracker with new frame detections.

        Args:
            detections: List of detection dicts from FishDetectionModel.predict().

        Returns:
            Current unique fish count estimate.

        TODO (Phase 2): Replace with ByteTrack update() call.
        """
        # Stub: count detections in each frame directly
        if detections:
            self.unique_count = max(self.unique_count, len(detections))
        logger.debug("fish_count_updated", count=self.unique_count, frame_detections=len(detections))
        return self.unique_count

    def reset(self) -> None:
        """Reset tracker state for a new session.

        Call between sessions (e.g., at each feeding period start).
        """
        self.track_history.clear()
        self._next_id = 0
        self.unique_count = 0

    @staticmethod
    def _iou(box_a: list[float], box_b: list[float]) -> float:
        """Compute Intersection over Union between two bounding boxes.

        Args:
            box_a: [x1, y1, x2, y2]
            box_b: [x1, y1, x2, y2]

        Returns:
            IoU score in [0, 1].
        """
        xa = max(box_a[0], box_b[0])
        ya = max(box_a[1], box_b[1])
        xb = min(box_a[2], box_b[2])
        yb = min(box_a[3], box_b[3])
        inter = max(0, xb - xa) * max(0, yb - ya)
        area_a = (box_a[2] - box_a[0]) * (box_a[3] - box_a[1])
        area_b = (box_b[2] - box_b[0]) * (box_b[3] - box_b[1])
        union = area_a + area_b - inter
        return inter / union if union > 0 else 0.0
