"""
detector/base.py
Abstract base for object detectors.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import numpy as np


@dataclass
class Detection:
    """Single bounding-box detection result."""

    label: str
    confidence: float
    box: tuple[int, int, int, int]
    track_id: int | None = None


@dataclass
class DetectionResult:
    """All detections for a single frame."""

    detections: list[Detection] = field(default_factory=list)
    inference_ms: float = 0.0

    @property
    def count(self) -> int:
        return len(self.detections)


class DetectorBase(ABC):
    """Contract for detector implementations."""

    def __init__(self, config: dict) -> None:
        self.config = config

    @abstractmethod
    def set_classes(self, classes: list[str]) -> None:
        """Update the detector vocabulary."""

    @abstractmethod
    def detect(self, frame: np.ndarray, track: bool = False) -> DetectionResult:
        """Run inference on a BGR frame."""

    def detect_in_roi(
        self,
        frame: np.ndarray,
        roi_box: tuple[int, int, int, int],
        track: bool = False,
    ) -> DetectionResult:
        """
        Run inference on a cropped ROI and remap detections back to full-frame
        coordinates. Backends can override this if they need custom behavior.
        """
        h, w = frame.shape[:2]
        x1, y1, x2, y2 = roi_box
        x1 = max(0, min(w - 1, x1))
        x2 = max(0, min(w, x2))
        y1 = max(0, min(h - 1, y1))
        y2 = max(0, min(h, y2))
        if x2 <= x1 or y2 <= y1:
            return DetectionResult()

        cropped = frame[y1:y2, x1:x2]
        result = self.detect(cropped, track=track)
        remapped = [
            Detection(
                label=det.label,
                confidence=det.confidence,
                box=(
                    det.box[0] + x1,
                    det.box[1] + y1,
                    det.box[2] + x1,
                    det.box[3] + y1,
                ),
                track_id=det.track_id,
            )
            for det in result.detections
        ]
        return DetectionResult(detections=remapped, inference_ms=result.inference_ms)

    def reset_tracking(self) -> None:
        """Clear any backend tracker state."""

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}"
            f"(weights={self.config.get('weights', '?')})"
        )
