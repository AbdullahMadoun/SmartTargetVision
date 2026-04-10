"""
detector/yoloe.py
YOLOE open-vocabulary detector with optional tracker-backed live inference.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

import numpy as np

from detector.base import Detection, DetectionResult, DetectorBase

log = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parent


class YOLOEDetector(DetectorBase):
    """
    Wraps the Ultralytics YOLOE model.

    Text classes remain dynamic via `set_classes()`. Live video can optionally
    route through Ultralytics tracking so detections carry stable track IDs that
    a higher-level follower can lock onto.
    """

    def __init__(self, config: dict) -> None:
        super().__init__(config)

        try:
            from ultralytics import YOLOE  # noqa: PLC0415
        except ImportError as exc:
            raise ImportError(
                "ultralytics is required for YOLOE.\n"
                "Install with: pip install ultralytics"
            ) from exc

        weights = _resolve_local_path(config.get("weights", "yoloe-11s-seg.pt"))
        self._device = config.get("device", "cpu")
        self._conf = float(config.get("confidence", 0.25))
        self._track_conf = float(config.get("track_confidence", self._conf))
        self._iou = float(config.get("iou", 0.45))
        self._imgsz = int(config.get("imgsz", 640))
        self._max_classes = int(config.get("max_classes", 15))
        self._tracker = config.get("tracker", "bytetrack.yaml")
        self._persist_tracks = bool(config.get("persist_tracks", True))
        self._agnostic_nms = bool(config.get("agnostic_nms", True))

        log.info("Loading YOLOE weights: %s on %s", weights, self._device)
        self._model = YOLOE(str(weights), verbose=False)
        self._model.to(self._device)

        self._current_classes: list[str] = ["object"]
        self._model.set_classes(self._current_classes)

    def set_classes(self, classes: list[str]) -> None:
        """
        Update the open-vocabulary target classes.

        YOLOE re-encodes text embeddings when the class list changes. Tracker
        state is reset when the vocabulary changes to avoid stale associations.
        """
        if not classes:
            log.warning("Empty class list passed to set_classes; keeping previous.")
            return

        trimmed = classes[: self._max_classes]
        if trimmed != self._current_classes:
            log.info("Updating YOLOE vocabulary (%d classes): %s", len(trimmed), trimmed)
            self._model.set_classes(trimmed)
            self._current_classes = trimmed
            self.reset_tracking()

    def detect(self, frame: np.ndarray, track: bool = False) -> DetectionResult:
        """
        Run YOLOE inference on a single BGR frame.

        When `track=True`, YOLOE uses its configured tracker backend and returns
        detections with `track_id` values when available.
        """
        t0 = time.perf_counter()

        kwargs = {
            "source": frame,
            "conf": self._track_conf if track else self._conf,
            "iou": self._iou,
            "imgsz": self._imgsz,
            "device": self._device,
            "verbose": False,
            "agnostic_nms": self._agnostic_nms,
        }
        if track:
            results = self._model.track(
                persist=self._persist_tracks,
                tracker=self._tracker,
                **kwargs,
            )
        else:
            results = self._model.predict(**kwargs)

        inference_ms = (time.perf_counter() - t0) * 1000.0
        detections: list[Detection] = []

        if results and results[0].boxes is not None:
            boxes = results[0].boxes
            track_ids = []
            if getattr(boxes, "id", None) is not None:
                track_ids = boxes.id.int().cpu().tolist()

            for idx in range(len(boxes)):
                cls_id = int(boxes.cls[idx])
                label = (
                    self._current_classes[cls_id]
                    if cls_id < len(self._current_classes)
                    else str(cls_id)
                )
                conf = float(boxes.conf[idx])
                x1, y1, x2, y2 = (int(v) for v in boxes.xyxy[idx].tolist())
                track_id = int(track_ids[idx]) if idx < len(track_ids) else None
                detections.append(
                    Detection(
                        label=label,
                        confidence=conf,
                        box=(x1, y1, x2, y2),
                        track_id=track_id,
                    )
                )

        return DetectionResult(detections=detections, inference_ms=inference_ms)

    def reset_tracking(self) -> None:
        """Reset any tracker instances currently attached to the predictor."""
        predictor = getattr(self._model, "predictor", None)
        trackers = getattr(predictor, "trackers", None)
        if not trackers:
            return
        for tracker in trackers:
            reset = getattr(tracker, "reset", None)
            if callable(reset):
                reset()

    @property
    def current_classes(self) -> list[str]:
        return list(self._current_classes)


def _resolve_local_path(path_value: str) -> Path:
    path = Path(path_value)
    if path.is_absolute():
        return path
    return (ROOT / path).resolve()
