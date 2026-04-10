"""
detector package facade for the flattened source layout.
"""

from detector.base import Detection, DetectionResult, DetectorBase


def build_detector(detector_config: dict) -> DetectorBase:
    """Instantiate the configured detector backend."""
    kind = detector_config.get("type", "yolo_world").lower()

    if kind in {"yoloe", "yolo-e"}:
        from detector.yoloe import YOLOEDetector

        return YOLOEDetector(detector_config)

    if kind in {"yolo_world", "yolo-world", "yoloworld"}:
        from detector.yolo_world import YOLOWorldDetector

        return YOLOWorldDetector(detector_config)

    raise ValueError(
        f"Unknown detector type: '{kind}'. "
        "Set detector.type to 'yolo_world' or 'yoloe' in config.yaml."
    )


__all__ = ["Detection", "DetectionResult", "DetectorBase", "build_detector"]
