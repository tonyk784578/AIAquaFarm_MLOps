"""Camera data collector — captures and stores frames from RTSP streams.

Connects to edge camera RTSP streams, captures frames at a configured
interval, and stores them in the data lake for labelling and training.

TODO (Phase 2): Implement RTSP capture with OpenCV VideoCapture.
TODO (Phase 2): Add motion-triggered capture to reduce storage.
TODO (Phase 3): Stream frames to growth and feeding AI modules in real-time.
"""

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import structlog

logger = structlog.get_logger()

CAPTURE_INTERVAL_SECONDS = 30  # Capture one frame every 30 seconds


class CameraCollector:
    """Captures frames from an RTSP camera stream.

    Attributes:
        tank_id: Associated tank identifier.
        stream_url: RTSP or HTTP stream URL.
        output_dir: Local directory for captured frames.
        capture_interval: Seconds between captures.
    """

    def __init__(
        self,
        tank_id: str,
        stream_url: str,
        output_dir: Path,
        capture_interval: int = CAPTURE_INTERVAL_SECONDS,
    ) -> None:
        self.tank_id = tank_id
        self.stream_url = stream_url
        self.output_dir = output_dir
        self.capture_interval = capture_interval
        self._cap: Optional[object] = None

    def connect(self) -> bool:
        """Open connection to the camera stream.

        Returns:
            True if connection was successful.

        TODO (Phase 2): Use cv2.VideoCapture(self.stream_url).
        """
        logger.info("camera_connect_stub", tank_id=self.tank_id, url=self.stream_url)
        # TODO (Phase 2):
        # import cv2
        # self._cap = cv2.VideoCapture(self.stream_url)
        # return self._cap.isOpened()
        return False

    def capture_frame(self) -> Optional[bytes]:
        """Capture a single JPEG frame from the stream.

        Returns:
            JPEG bytes, or None if capture failed.

        TODO (Phase 2): ret, frame = self._cap.read(); encode to JPEG.
        """
        # TODO (Phase 2): Implement real frame capture
        return None

    def save_frame(self, frame_bytes: bytes) -> Path:
        """Save a captured frame to the data lake directory.

        Args:
            frame_bytes: JPEG encoded frame.

        Returns:
            Path to the saved file.
        """
        ts = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename = self.output_dir / f"{self.tank_id}_{ts}.jpg"
        filename.write_bytes(frame_bytes)
        return filename

    async def run(self) -> None:
        """Main capture loop — runs until cancelled.

        TODO (Phase 2): Connect to stream and capture at interval.
        """
        logger.info(
            "camera_collector_started",
            tank_id=self.tank_id,
            interval_s=self.capture_interval,
        )
        while True:
            frame = self.capture_frame()
            if frame:
                path = self.save_frame(frame)
                logger.debug("frame_saved", path=str(path))
            await asyncio.sleep(self.capture_interval)
