"""
detector/base.py
Abstract base for object detectors.
Swap in a different detector by subclassing and registering in __init__.py.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import numpy as np


@dataclass
class Detection:
    """Single bounding-box detection result."""
    label: str
    confidence: float
    # xyxy pixel coords: (x1, y1, x2, y2)
    box: tuple[int, int, int, int]


@dataclass
class DetectionResult:
    """All detections for a single frame."""
    detections: list[Detection] = field(default_factory=list)
    inference_ms: float = 0.0

    @property
    def count(self) -> int:
        return len(self.detections)


class DetectorBase(ABC):
    """
    Contract for detectors.
    A detector receives a BGR numpy frame and a list of class-name strings,
    and returns a DetectionResult.
    """

    def __init__(self, config: dict) -> None:
        self.config = config

    @abstractmethod
    def set_classes(self, classes: list[str]) -> None:
        """
        Update the vocabulary the detector searches for.
        Must be called at least once before `detect`.

        Args:
            classes: List of noun phrases, e.g. ["coffee mug", "laptop"].
        """

    @abstractmethod
    def detect(self, frame: np.ndarray) -> DetectionResult:
        """
        Run inference on a single BGR frame.

        Args:
            frame: OpenCV BGR image as a numpy array.

        Returns:
            DetectionResult with zero or more bounding boxes.
        """

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}"
            f"(weights={self.config.get('weights', '?')})"
        )
