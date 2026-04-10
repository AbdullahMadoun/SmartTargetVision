"""
pipeline.py
Orchestrates the full VLM → YOLO detector → display loop.

Design decisions:
  · The VLM query runs on a background thread so it never blocks the
    video loop. The detector always uses the most recently returned vocab.
  · VLM is re-queried on a configurable interval (default: 10 s) rather
    than every frame — VLM latency is 1-5 s; camera runs at 30 fps.
  · A single reference image is sent to the VLM; the camera feed is
    separate (live detection, not analysed by the VLM).
"""

import logging
import os
import tempfile
import threading
import time
from pathlib import Path

import cv2
import numpy as np

from detector import build_detector
from detector.base import DetectionResult
from utils.camera import CameraSource
from utils.display import Renderer
from utils.tracking import TargetFollower
from vlm import build_vlm

log = logging.getLogger(__name__)


class Pipeline:
    """
    Main pipeline controller.

    Args:
        config: Full parsed config.yaml dict.
    """

    def __init__(self, config: dict) -> None:
        self._cfg = config
        self._vlm = build_vlm(config["vlm"])
        self._detector = build_detector(config["detector"])
        self._renderer = Renderer(config=config["display"])
        self._follower = TargetFollower(config.get("tracking", {}))
        self._tracking_enabled = self._follower.enabled
        self._last_tracking_classes: tuple[str, ...] = ()

        self._refresh_interval = float(
            config["pipeline"].get("vlm_refresh_interval", 10.0)
        )
        self._save_output = config["pipeline"].get("save_output", False)
        self._output_dir = Path(config["pipeline"].get("output_dir", "./output"))

        # Shared state between VLM thread and video loop
        self._lock = threading.Lock()
        self._active_classes: list[str] = []
        self._last_vlm_time: float = 0.0
        self._vlm_thread: threading.Thread | None = None
        self._stop_event = threading.Event()

        if self._save_output:
            self._output_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ #
    # Public entry point
    # ------------------------------------------------------------------ #

    def run(self, reference_image: str | Path) -> None:
        """
        Start the pipeline.

        1. Immediately queries the VLM with `reference_image`.
        2. Opens the live camera feed.
        3. Runs the configured YOLO detector on every frame using the
           VLM-generated vocabulary.
        4. Periodically re-queries the VLM on a background thread.
        5. Exits cleanly when the user presses Q or ESC.

        Args:
            reference_image: Path to the image describing what to search for.
        """
        reference_image = Path(reference_image)
        if not reference_image.exists():
            raise FileNotFoundError(f"Reference image not found: {reference_image}")

        log.info("Pipeline starting — reference image: %s", reference_image)

        # Blocking first VLM query (so we have classes before the camera opens)
        self._run_vlm_query(reference_image)

        cam = CameraSource(self._cfg["camera"])
        cam.open()

        window = self._cfg["display"]["window_name"]
        cv2.namedWindow(window, cv2.WINDOW_NORMAL)

        try:
            for frame in cam.frames():
                # Trigger background VLM refresh if interval elapsed
                self._maybe_schedule_vlm(reference_image)

                # Run detection
                with self._lock:
                    classes = list(self._active_classes)

                class_key = tuple(classes)
                if class_key != self._last_tracking_classes:
                    self._last_tracking_classes = class_key
                    self._follower.reset()
                    self._detector.reset_tracking()

                if classes:
                    self._detector.set_classes(classes)
                result: DetectionResult = self._detector.detect(
                    frame,
                    track=self._tracking_enabled,
                )
                if self._tracking_enabled:
                    refined = self._follower.refine_detections(
                        result.detections,
                        frame.shape,
                        classes,
                    )
                    result = DetectionResult(
                        detections=refined,
                        inference_ms=result.inference_ms,
                    )
                    follow_state = self._follower.update(
                        result.detections,
                        frame.shape,
                        classes,
                        prepared=True,
                    )
                else:
                    follow_state = None

                # Render
                time_to_next = max(
                    0.0,
                    self._refresh_interval - (time.monotonic() - self._last_vlm_time),
                )
                annotated = self._renderer.draw(
                    frame,
                    result,
                    classes,
                    time_to_next,
                    follow_state=follow_state,
                )

                if self._save_output:
                    ts = int(time.time() * 1000)
                    cv2.imwrite(str(self._output_dir / f"frame_{ts}.jpg"), annotated)

                cv2.imshow(window, annotated)

                key = cv2.waitKey(1) & 0xFF
                if key in (ord("q"), ord("Q"), 27):  # Q or ESC
                    log.info("User requested exit.")
                    break

                # Manual VLM refresh: press R
                if key in (ord("r"), ord("R")):
                    log.info("Manual VLM refresh triggered.")
                    self._schedule_vlm_async(reference_image, force=True)

        finally:
            self._stop_event.set()
            if self._vlm_thread and self._vlm_thread.is_alive():
                self._vlm_thread.join(timeout=5)
            cam.close()
            cv2.destroyAllWindows()
            log.info("Pipeline stopped.")

    # ------------------------------------------------------------------ #
    # Snapshot helper (capture a frame and use it as the reference image)
    # ------------------------------------------------------------------ #

    def run_with_snapshot(self) -> None:
        """
        Opens the camera, shows a live preview, and waits for the user to
        press SPACE to capture a reference frame.  Then uses that frame as
        the VLM input and continues into the normal detection loop.
        """
        cam = CameraSource(self._cfg["camera"])
        cam.open()
        window = self._cfg["display"]["window_name"]
        cv2.namedWindow(window, cv2.WINDOW_NORMAL)

        log.info("Snapshot mode — press SPACE to capture reference, Q to quit.")
        snapshot_path: Path | None = None

        for frame in cam.frames():
            preview = frame.copy()
            cv2.putText(
                preview,
                "Press SPACE to snapshot  |  Q to quit",
                (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7,
                (200, 240, 200), 2, cv2.LINE_AA,
            )
            cv2.imshow(window, preview)
            key = cv2.waitKey(1) & 0xFF
            if key == ord(" "):
                tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
                cv2.imwrite(tmp.name, frame)
                snapshot_path = Path(tmp.name)
                log.info("Snapshot saved: %s", snapshot_path)
                break
            if key in (ord("q"), 27):
                cam.close()
                cv2.destroyAllWindows()
                return

        cam.close()
        cv2.destroyAllWindows()

        if snapshot_path:
            self.run(snapshot_path)
            try:
                os.unlink(snapshot_path)
            except OSError:
                pass

    # ------------------------------------------------------------------ #
    # VLM helpers
    # ------------------------------------------------------------------ #

    def _run_vlm_query(self, image_path: Path) -> None:
        """Synchronously query the VLM and update active classes."""
        try:
            log.info("Querying VLM …")
            raw = self._vlm.describe(image_path)
            classes = self._vlm.parse_classes(raw)
            log.info("VLM → %d classes: %s", len(classes), classes)
            with self._lock:
                self._active_classes = classes
            self._last_vlm_time = time.monotonic()
        except Exception as exc:
            log.error("VLM query failed: %s", exc, exc_info=True)

    def _maybe_schedule_vlm(self, image_path: Path) -> None:
        elapsed = time.monotonic() - self._last_vlm_time
        if elapsed >= self._refresh_interval:
            self._schedule_vlm_async(image_path)

    def _schedule_vlm_async(self, image_path: Path, force: bool = False) -> None:
        if self._vlm_thread and self._vlm_thread.is_alive() and not force:
            return  # Previous query still running; skip
        self._vlm_thread = threading.Thread(
            target=self._run_vlm_query, args=(image_path,), daemon=True
        )
        self._vlm_thread.start()
