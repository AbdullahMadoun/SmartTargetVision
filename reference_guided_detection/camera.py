"""
utils/camera.py
Thin wrapper around OpenCV VideoCapture that yields BGR frames.
Works with webcams (int index), RTSP streams, and video files.
"""

import logging
import sys
import time
from contextlib import contextmanager
from typing import Generator

import cv2
import numpy as np

log = logging.getLogger(__name__)


class CameraSource:
    """
    OpenCV-based frame source.

    Usage:
        cam = CameraSource(config["camera"])
        with cam:
            for frame in cam.frames():
                process(frame)
    """

    def __init__(self, config: dict) -> None:
        source = config.get("source", 0)
        # Coerce numeric-string sources (e.g. "0") to int for cv2
        try:
            self._source = int(source)
        except (ValueError, TypeError):
            self._source = source  # RTSP URL or file path

        self._width = int(config.get("width", 1280))
        self._height = int(config.get("height", 720))
        self._fps_limit = float(config.get("fps_limit", 30))
        self._backend = str(config.get("backend", "auto")).lower()
        self._cap: cv2.VideoCapture | None = None
        self._frame_interval = 1.0 / self._fps_limit if self._fps_limit > 0 else 0.0

    # ------------------------------------------------------------------ #
    # Context manager
    # ------------------------------------------------------------------ #

    def open(self) -> None:
        candidates = self._backend_candidates()
        last_error = f"Cannot open camera/stream: {self._source!r}"

        for backend_name, backend_id in candidates:
            cap = self._open_capture(backend_id)
            if cap is None:
                last_error = (
                    f"Unable to open source {self._source!r} with backend {backend_name}"
                )
                continue

            if self._is_webcam_source() and not self._validate_capture(cap):
                cap.release()
                last_error = (
                    f"Backend {backend_name} opened source {self._source!r} "
                    "but failed to read a frame"
                )
                log.warning("%s", last_error)
                continue

            self._cap = cap
            log.info(
                "Camera opened: source=%r  resolution=%dx%d  backend=%s",
                self._source, self._width, self._height, backend_name,
            )
            return

        raise RuntimeError(last_error)

    def close(self) -> None:
        if self._cap and self._cap.isOpened():
            self._cap.release()
            log.info("Camera released.")

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, *_):
        self.close()

    # ------------------------------------------------------------------ #
    # Frame iterator
    # ------------------------------------------------------------------ #

    def frames(self) -> Generator[np.ndarray, None, None]:
        """
        Yield BGR frames continuously until the stream ends or read fails.
        Respects fps_limit by sleeping between frames when needed.
        """
        if self._cap is None or not self._cap.isOpened():
            raise RuntimeError("Camera is not open. Call open() first.")

        last_ts = 0.0
        while True:
            ret, frame = self._cap.read()
            if not ret:
                log.warning("Frame read failed — end of stream or camera disconnected.")
                break

            now = time.monotonic()
            if self._frame_interval > 0:
                elapsed = now - last_ts
                if elapsed < self._frame_interval:
                    time.sleep(self._frame_interval - elapsed)
            last_ts = time.monotonic()

            yield frame

    def read_one(self) -> np.ndarray | None:
        """Read a single frame; returns None if unavailable."""
        if self._cap is None or not self._cap.isOpened():
            return None
        ret, frame = self._cap.read()
        return frame if ret else None

    def _is_webcam_source(self) -> bool:
        return isinstance(self._source, int)

    def _backend_candidates(self) -> list[tuple[str, int | None]]:
        if not self._is_webcam_source():
            return [("any", None)]

        configured = self._backend
        if configured != "auto":
            return [(configured, _backend_id(configured))]

        if sys.platform.startswith("win"):
            return [
                ("dshow", _backend_id("dshow")),
                ("any", None),
                ("msmf", _backend_id("msmf")),
            ]
        return [("any", None)]

    def _open_capture(self, backend_id: int | None) -> cv2.VideoCapture | None:
        cap = (
            cv2.VideoCapture(self._source)
            if backend_id is None
            else cv2.VideoCapture(self._source, backend_id)
        )
        if not cap.isOpened():
            cap.release()
            return None

        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self._width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self._height)
        return cap

    @staticmethod
    def _validate_capture(cap: cv2.VideoCapture, attempts: int = 5) -> bool:
        for _ in range(attempts):
            ret, _frame = cap.read()
            if ret:
                return True
            time.sleep(0.05)
        return False


def _backend_id(name: str) -> int | None:
    mapping = {
        "any": None,
        "dshow": getattr(cv2, "CAP_DSHOW", None),
        "msmf": getattr(cv2, "CAP_MSMF", None),
    }
    backend_id = mapping.get(name)
    if name not in mapping:
        raise ValueError(f"Unknown camera backend: {name}")
    if name != "any" and backend_id is None:
        raise ValueError(f"Camera backend not available in this OpenCV build: {name}")
    return backend_id


@contextmanager
def open_camera(config: dict) -> Generator[CameraSource, None, None]:
    """Convenience context manager."""
    cam = CameraSource(config)
    cam.open()
    try:
        yield cam
    finally:
        cam.close()
