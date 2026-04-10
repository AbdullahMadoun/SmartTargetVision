"""YOLO detector wrapper used by the separate face-recognition demo."""

from __future__ import annotations

from pathlib import Path

from .types import Detection


class PromptableDetector:
    def __init__(self, config: dict, root_dir: Path) -> None:
        backend = config.get("backend", "yolo_world").lower()
        try:
            if backend == "yolo_world":
                from ultralytics import YOLOWorld

                self._model = YOLOWorld(
                    str(_resolve_path(root_dir, config.get("weights", "../yolov8s-world.pt")))
                )
                self._mode = "open_vocab"
            elif backend in {"yolo", "yolo_standard", "yolo_small"}:
                from ultralytics import YOLO

                self._model = YOLO(
                    str(_resolve_path(root_dir, config.get("weights", "../yolov8s.pt")))
                )
                self._mode = "closed_set"
            else:
                raise ValueError(f"Unsupported detector backend for local demo: {backend}")
        except ImportError as exc:
            raise ImportError("ultralytics is required for the detector backend.") from exc

        self._device = config.get("device", "cpu")
        self._model.to(self._device)
        self._conf = float(config.get("confidence", 0.25))
        self._iou = float(config.get("iou", 0.45))
        self._imgsz = int(config.get("imgsz", 640))
        self._max_classes = int(config.get("max_classes", 12))
        self._max_det = int(config.get("max_det", 2))
        self._configured_class_names = [
            str(name).strip().lower()
            for name in config.get("class_names", ["face"])
            if str(name).strip()
        ]
        self._classes: list[str] = ["face"]
        self._class_filter_ids = self._resolve_class_ids(self._configured_class_names)
        if self._mode == "open_vocab":
            self._model.set_classes(self._classes)

    def set_classes(self, classes: list[str]) -> list[str]:
        trimmed = [str(item).strip().lower() for item in classes if str(item).strip()]
        trimmed = trimmed[: self._max_classes]

        if self._mode == "open_vocab":
            if not trimmed:
                trimmed = ["face"]
            self._classes = trimmed
            self._model.set_classes(self._classes)
            return list(self._classes)

        requested_ids = self._resolve_class_ids(trimmed)
        if requested_ids:
            self._class_filter_ids = requested_ids
        elif self._class_filter_ids is None:
            self._class_filter_ids = self._resolve_class_ids(self._configured_class_names)
        self._classes = trimmed or list(self._configured_class_names) or ["face"]
        return list(self._classes)

    def detect(self, frame) -> list[Detection]:
        predict_kwargs = {
            "source": frame,
            "conf": self._conf,
            "iou": self._iou,
            "imgsz": self._imgsz,
            "device": self._device,
            "verbose": False,
            "max_det": self._max_det,
        }
        if self._mode == "closed_set" and self._class_filter_ids:
            predict_kwargs["classes"] = self._class_filter_ids

        results = self._model.predict(**predict_kwargs)
        detections: list[Detection] = []
        if results and results[0].boxes is not None:
            for box in results[0].boxes:
                cls_id = int(box.cls[0])
                if self._mode == "open_vocab":
                    label = self._classes[cls_id] if cls_id < len(self._classes) else str(cls_id)
                else:
                    label = _name_from_model(self._model, cls_id)
                conf = float(box.conf[0])
                x1, y1, x2, y2 = (int(v) for v in box.xyxy[0])
                detections.append(Detection(label=label, confidence=conf, box=(x1, y1, x2, y2)))
        return detections

    def _resolve_class_ids(self, names: list[str]) -> list[int] | None:
        if self._mode != "closed_set":
            return None
        model_names = getattr(self._model, "names", None) or {}
        if not model_names:
            return None
        reverse = {str(label).lower(): int(idx) for idx, label in model_names.items()}
        class_ids = [reverse[name] for name in names if name in reverse]
        return class_ids or None


def _resolve_path(root_dir: Path, path_value: str) -> Path:
    path = Path(path_value)
    if path.is_absolute():
        return path
    return (root_dir / path).resolve()


def _name_from_model(model, cls_id: int) -> str:
    names = getattr(model, "names", None) or {}
    if cls_id in names:
        return str(names[cls_id])
    return str(cls_id)
