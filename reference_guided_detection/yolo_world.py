"""
detector/yolo_world.py
YOLO-World open-vocabulary detector.

YOLO-World (Ultralytics implementation) accepts a list of class-name
strings as its vocabulary at runtime — no re-training required.

Model weight options (auto-downloaded on first run):
  yolov8s-world.pt   ~  26 MB   fastest / smallest
  yolov8m-world.pt   ~  89 MB   balanced
  yolov8l-world.pt   ~ 200 MB   most accurate

Reference: https://docs.ultralytics.com/models/yolo-world/
"""

import logging
import time
from pathlib import Path

import numpy as np

from detector.base import DetectionResult, Detection, DetectorBase

log = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parent


class YOLOWorldDetector(DetectorBase):
    """
    Wraps Ultralytics YOLOWorld model.

    The key design point is that `set_classes()` is cheap once the model is
    loaded — it just updates an internal vocabulary tensor without reloading
    weights. This makes it practical to update prompts every few seconds from
    the VLM without stalling the video loop.
    """

    def __init__(self, config: dict) -> None:
        super().__init__(config)

        try:
            from ultralytics import YOLOWorld  # noqa: PLC0415
        except ImportError as exc:
            raise ImportError(
                "ultralytics is required for YOLO-World.\n"
                "Install with: pip install ultralytics"
            ) from exc

        weights = _resolve_local_path(config.get("weights", "yolov8s-world.pt"))
        self._device = config.get("device", "cpu")
        self._conf = float(config.get("confidence", 0.25))
        self._iou = float(config.get("iou", 0.45))
        self._imgsz = int(config.get("imgsz", 640))
        self._max_classes = int(config.get("max_classes", 15))

        log.info("Loading YOLO-World weights: %s on %s", weights, self._device)
        self._model = YOLOWorld(str(weights))
        self._model.to(self._device)

        # Placeholder vocabulary until VLM provides real classes
        self._current_classes: list[str] = ["object"]
        self._model.set_classes(self._current_classes)

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def set_classes(self, classes: list[str]) -> None:
        """
        Update the open-vocabulary detection targets.

        YOLO-World re-encodes class embeddings on `set_classes` — this is
        fast (< 50 ms on CPU) and does not reload weights.
        """
        if not classes:
            log.warning("Empty class list passed to set_classes; keeping previous.")
            return

        # Trim to model's comfortable working range
        trimmed = classes[: self._max_classes]
        if trimmed != self._current_classes:
            log.info("Updating YOLO-World vocabulary (%d classes): %s", len(trimmed), trimmed)
            self._model.set_classes(trimmed)
            self._current_classes = trimmed

    def detect(self, frame: np.ndarray, track: bool = False) -> DetectionResult:
        """
        Run YOLO-World inference on a single BGR frame and return detections.
        """
        if track:
            log.debug("Tracking requested on YOLO-World backend; using plain detection.")
        t0 = time.perf_counter()

        results = self._model.predict(
            source=frame,
            conf=self._conf,
            iou=self._iou,
            imgsz=self._imgsz,
            device=self._device,
            verbose=False,
        )

        inference_ms = (time.perf_counter() - t0) * 1000.0
        detections: list[Detection] = []

        if results and results[0].boxes is not None:
            for box in results[0].boxes:
                cls_id = int(box.cls[0])
                label = (
                    self._current_classes[cls_id]
                    if cls_id < len(self._current_classes)
                    else str(cls_id)
                )
                conf = float(box.conf[0])
                x1, y1, x2, y2 = (int(v) for v in box.xyxy[0])
                detections.append(Detection(label=label, confidence=conf, box=(x1, y1, x2, y2)))

        return DetectionResult(detections=detections, inference_ms=inference_ms)

    @property
    def current_classes(self) -> list[str]:
        return list(self._current_classes)


def _resolve_local_path(path_value: str) -> Path:
    path = Path(path_value)
    if path.is_absolute():
        return path
    return (ROOT / path).resolve()
