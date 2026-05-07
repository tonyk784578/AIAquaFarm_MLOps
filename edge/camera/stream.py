"""Edge camera streaming module.

Captures frames from USB/RTSP camera and forwards to the AI modules
for real-time inference or stores to data lake for training.

TODO (Phase 2): Implement real OpenCV capture and RTSP streaming.
TODO (Phase 3): Add hardware acceleration (NVENC/V4L2) for edge GPU.
"""

import asyncio
from datetime import datetime, timezone

import structlog

logger = structlog.get_logger()

CAMERA_INDEX = 0  # 0 = default USB camera; override with RTSP URL string
CAPTURE_FPS = 5   # Capture 5 frames/second for AI inference


async def run_camera(camera_source: str | int = CAMERA_INDEX) -> None:
    """Main camera capture loop — runs until interrupted.

    Args:
        camera_source: Camera device index or RTSP URL.

    TODO (Phase 2):
        cap = cv2.VideoCapture(camera_source)
        while True:
            ret, frame = cap.read()
            if ret: await process_frame(frame)
            await asyncio.sleep(1 / CAPTURE_FPS)
    """
    logger.info("edge_camera_stub", source=camera_source, fps=CAPTURE_FPS)
    while True:
        logger.debug("frame_capture_stub", timestamp=datetime.now(tz=timezone.utc).isoformat())
        await asyncio.sleep(1 / CAPTURE_FPS)


if __name__ == "__main__":
    asyncio.run(run_camera())
