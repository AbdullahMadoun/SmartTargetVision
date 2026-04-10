"""
vlm/base.py
Abstract base class that every VLM backend must implement.
Swap providers by changing config.yaml — no pipeline code changes needed.
"""

from abc import ABC, abstractmethod
from pathlib import Path
import re


class VLMBase(ABC):
    """
    Contract for VLM backends.

    Implementors receive a config dict (the `vlm` section of config.yaml)
    and must expose a single `describe(image_path)` method that returns a
    comma-separated string of YOLO-friendly detection classes.
    """

    def __init__(self, config: dict) -> None:
        self.config = config

    @abstractmethod
    def describe(
        self,
        image_path: str | Path,
        instruction: str | None = None,
        history: list[dict[str, str]] | None = None,
    ) -> str:
        """
        Send `image_path` to the VLM and return a comma-separated list of
        noun phrases describing what should be detected in the scene.

        Args:
            image_path: Path to a JPEG/PNG image on disk.
            instruction: Optional user intent to refine the detector classes.
            history: Optional prior user/assistant turns for iterative chat.

        Returns:
            A comma-separated string, e.g.
            "coffee mug, wooden table, laptop keyboard"
        """

    def parse_classes(self, raw: str) -> list[str]:
        """
        Utility: normalise raw VLM output into a clean list of class names.
        Strips whitespace, removes empties, and de-duplicates while preserving
        order.
        """
        seen: set[str] = set()
        classes: list[str] = []
        for item in raw.split(","):
            label = _clean_label(item)
            if label and label not in seen:
                seen.add(label)
                classes.append(label)
        return classes

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(model={self.config.get('model', '?')})"


def _clean_label(item: str) -> str:
    label = item.strip().lower()
    label = re.sub(r"^[\s\-*\d\.\)\(]+", "", label)
    label = label.strip(" '\"`.;:!?")
    label = re.sub(r"\s+", " ", label)
    return label
