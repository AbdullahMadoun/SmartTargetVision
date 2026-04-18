from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Protocol

from .camera_capture import CameraFrameCapture
from .flight_control import DEFAULT_DRONE_ID, DroneStatus


@dataclass(frozen=True, slots=True)
class TrackingObservation:
    detected: bool
    target_class: str = ""
    confidence: float = 0.0
    center_x_norm: float = 0.5
    center_y_norm: float = 0.5
    area_norm: float = 0.0
    bbox: tuple[float, float, float, float] = ()
    track_id: int | None = None
    frame_width: int = 0
    frame_height: int = 0
    source: str = "none"

    @classmethod
    def from_bbox(
        cls,
        *,
        bbox: tuple[float, float, float, float],
        frame_width: int,
        frame_height: int,
        target_class: str,
        confidence: float,
        track_id: int | None = None,
        source: str = "detector",
    ) -> "TrackingObservation":
        x1, y1, x2, y2 = bbox
        width = max(frame_width, 1)
        height = max(frame_height, 1)
        center_x = ((x1 + x2) * 0.5) / width
        center_y = ((y1 + y2) * 0.5) / height
        area = max(0.0, (x2 - x1) * (y2 - y1)) / float(width * height)
        return cls(
            detected=True,
            target_class=target_class,
            confidence=confidence,
            center_x_norm=center_x,
            center_y_norm=center_y,
            area_norm=area,
            bbox=bbox,
            track_id=track_id,
            frame_width=frame_width,
            frame_height=frame_height,
            source=source,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "detected": self.detected,
            "target_class": self.target_class,
            "confidence": self.confidence,
            "center_x_norm": self.center_x_norm,
            "center_y_norm": self.center_y_norm,
            "area_norm": self.area_norm,
            "bbox": list(self.bbox),
            "track_id": self.track_id,
            "frame_width": self.frame_width,
            "frame_height": self.frame_height,
            "source": self.source,
        }


@dataclass(frozen=True, slots=True)
class TrackingCommand:
    forward_m_s: float = 0.0
    right_m_s: float = 0.0
    down_m_s: float = 0.0
    yaw_rate_deg_s: float = 0.0
    mode: str = "idle"

    def to_dict(self) -> dict[str, object]:
        return {
            "forward_m_s": self.forward_m_s,
            "right_m_s": self.right_m_s,
            "down_m_s": self.down_m_s,
            "yaw_rate_deg_s": self.yaw_rate_deg_s,
            "mode": self.mode,
        }


@dataclass(frozen=True, slots=True)
class TrackingConfig:
    target_class: str = "person"
    confidence_threshold: float = 0.35
    target_area_norm: float = 0.12
    area_deadzone_norm: float = 0.02
    horizontal_deadzone_norm: float = 0.06
    vertical_deadzone_norm: float = 0.06
    forward_gain: float = 5.0
    lateral_gain: float = 2.2
    vertical_gain: float = 1.4
    yaw_gain: float = 90.0
    max_forward_speed_m_s: float = 1.5
    max_right_speed_m_s: float = 1.0
    max_down_speed_m_s: float = 0.6
    max_yaw_rate_deg_s: float = 45.0
    scan_yaw_rate_deg_s: float = 18.0
    enable_vertical_control: bool = False
    loop_interval_s: float = 0.5
    camera_topic: str = ""
    container_name: str = ""
    model_path: str = ""
    detector_backend: str = "ultralytics"

    def to_dict(self) -> dict[str, object]:
        return {
            "target_class": self.target_class,
            "confidence_threshold": self.confidence_threshold,
            "target_area_norm": self.target_area_norm,
            "area_deadzone_norm": self.area_deadzone_norm,
            "horizontal_deadzone_norm": self.horizontal_deadzone_norm,
            "vertical_deadzone_norm": self.vertical_deadzone_norm,
            "forward_gain": self.forward_gain,
            "lateral_gain": self.lateral_gain,
            "vertical_gain": self.vertical_gain,
            "yaw_gain": self.yaw_gain,
            "max_forward_speed_m_s": self.max_forward_speed_m_s,
            "max_right_speed_m_s": self.max_right_speed_m_s,
            "max_down_speed_m_s": self.max_down_speed_m_s,
            "max_yaw_rate_deg_s": self.max_yaw_rate_deg_s,
            "scan_yaw_rate_deg_s": self.scan_yaw_rate_deg_s,
            "enable_vertical_control": self.enable_vertical_control,
            "loop_interval_s": self.loop_interval_s,
            "camera_topic": self.camera_topic,
            "container_name": self.container_name,
            "model_path": self.model_path,
            "detector_backend": self.detector_backend,
        }


@dataclass(frozen=True, slots=True)
class TrackingStatus:
    active: bool
    drone_id: str = DEFAULT_DRONE_ID
    authorized: bool = False
    detector_backend: str = ""
    target_class: str = ""
    step_count: int = 0
    last_error: str = ""
    updated_at: float = 0.0
    last_command: TrackingCommand = field(default_factory=TrackingCommand)
    last_observation: TrackingObservation = field(default_factory=lambda: TrackingObservation(detected=False))

    def to_dict(self) -> dict[str, object]:
        return {
            "active": self.active,
            "drone_id": self.drone_id,
            "authorized": self.authorized,
            "detector_backend": self.detector_backend,
            "target_class": self.target_class,
            "step_count": self.step_count,
            "last_error": self.last_error,
            "updated_at": self.updated_at,
            "last_command": self.last_command.to_dict(),
            "last_observation": self.last_observation.to_dict(),
        }


class TrackingDetector(Protocol):
    backend_name: str

    def detect(
        self,
        capture: CameraFrameCapture,
        *,
        target_class: str,
        confidence_threshold: float,
    ) -> TrackingObservation: ...


class UltralyticsTrackingDetector:
    backend_name = "ultralytics"

    def __init__(self, model_path: str = "") -> None:
        try:
            import cv2  # type: ignore
            import numpy as np  # type: ignore
            from ultralytics import YOLO  # type: ignore
        except ImportError as exc:
            raise RuntimeError(
                "Ultralytics detector requires optional dependencies: ultralytics, numpy, and opencv-python-headless."
            ) from exc

        self._cv2 = cv2
        self._np = np
        self._model = YOLO(model_path or "yolov8n.pt")

    def detect(
        self,
        capture: CameraFrameCapture,
        *,
        target_class: str,
        confidence_threshold: float,
    ) -> TrackingObservation:
        frame = self._cv2.imdecode(
            self._np.frombuffer(capture.image_bytes, dtype=self._np.uint8),
            self._cv2.IMREAD_COLOR,
        )
        if frame is None:
            raise RuntimeError("Detector could not decode the camera frame.")

        results = self._model.track(frame, persist=True, verbose=False)
        best: TrackingObservation | None = None
        wanted = target_class.strip().lower()

        for result in results:
            boxes = getattr(result, "boxes", None)
            if boxes is None or len(boxes) == 0:
                continue
            names = getattr(result, "names", None) or getattr(self._model, "names", {})
            ids = getattr(boxes, "id", None)
            for index, box in enumerate(boxes):
                class_index = int(box.cls[0])
                class_name = str(names.get(class_index, class_index))
                confidence = float(box.conf[0])
                if wanted and class_name.lower() != wanted:
                    continue
                if confidence < confidence_threshold:
                    continue
                bbox = tuple(float(value) for value in box.xyxy[0].tolist())
                track_id = None
                if ids is not None:
                    try:
                        track_id = int(ids[index])
                    except Exception:
                        track_id = None
                candidate = TrackingObservation.from_bbox(
                    bbox=bbox,
                    frame_width=capture.width,
                    frame_height=capture.height,
                    target_class=class_name,
                    confidence=confidence,
                    track_id=track_id,
                    source=self.backend_name,
                )
                if best is None or candidate.confidence > best.confidence:
                    best = candidate

        return best or TrackingObservation(
            detected=False,
            frame_width=capture.width,
            frame_height=capture.height,
            source=self.backend_name,
        )


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def compute_tracking_command(
    observation: TrackingObservation,
    config: TrackingConfig,
) -> TrackingCommand:
    if not observation.detected:
        return TrackingCommand(
            yaw_rate_deg_s=_clamp(
                config.scan_yaw_rate_deg_s,
                -config.max_yaw_rate_deg_s,
                config.max_yaw_rate_deg_s,
            ),
            mode="searching",
        )

    horizontal_error = observation.center_x_norm - 0.5
    vertical_error = observation.center_y_norm - 0.5
    area_error = config.target_area_norm - observation.area_norm

    right_m_s = 0.0
    yaw_rate_deg_s = 0.0
    forward_m_s = 0.0
    down_m_s = 0.0

    if abs(horizontal_error) > config.horizontal_deadzone_norm:
        right_m_s = _clamp(
            horizontal_error * config.lateral_gain,
            -config.max_right_speed_m_s,
            config.max_right_speed_m_s,
        )
        yaw_rate_deg_s = _clamp(
            horizontal_error * config.yaw_gain,
            -config.max_yaw_rate_deg_s,
            config.max_yaw_rate_deg_s,
        )
    if abs(area_error) > config.area_deadzone_norm:
        forward_m_s = _clamp(
            area_error * config.forward_gain,
            -config.max_forward_speed_m_s,
            config.max_forward_speed_m_s,
        )
    if config.enable_vertical_control and abs(vertical_error) > config.vertical_deadzone_norm:
        down_m_s = _clamp(
            vertical_error * config.vertical_gain,
            -config.max_down_speed_m_s,
            config.max_down_speed_m_s,
        )

    return TrackingCommand(
        forward_m_s=forward_m_s,
        right_m_s=right_m_s,
        down_m_s=down_m_s,
        yaw_rate_deg_s=yaw_rate_deg_s,
        mode="tracking",
    )


@dataclass(slots=True)
class _TrackingSession:
    drone_id: str
    config: TrackingConfig
    detector: TrackingDetector
    stop_event: threading.Event = field(default_factory=threading.Event)
    thread: threading.Thread | None = None
    status: TrackingStatus = field(
        default_factory=lambda: TrackingStatus(active=False, last_observation=TrackingObservation(detected=False))
    )


class VisualTrackingService:
    def __init__(
        self,
        *,
        capture_provider: Callable[[str, str], CameraFrameCapture],
        status_provider: Callable[[str], DroneStatus],
        command_sender: Callable[..., str],
        stop_sender: Callable[[str], str],
        detector_factory: Callable[[TrackingConfig], TrackingDetector] | None = None,
    ) -> None:
        self.capture_provider = capture_provider
        self.status_provider = status_provider
        self.command_sender = command_sender
        self.stop_sender = stop_sender
        self.detector_factory = detector_factory or self._make_detector
        self._sessions: dict[str, _TrackingSession] = {}
        self._lock = threading.RLock()

    def _make_detector(self, config: TrackingConfig) -> TrackingDetector:
        backend = config.detector_backend.strip().lower() or "ultralytics"
        if backend == "ultralytics":
            return UltralyticsTrackingDetector(config.model_path)
        raise ValueError(f"Unsupported detector backend: {config.detector_backend}")

    def start(self, *, drone_id: str, config: TrackingConfig) -> TrackingStatus:
        detector = self.detector_factory(config)
        session = _TrackingSession(drone_id=drone_id or DEFAULT_DRONE_ID, config=config, detector=detector)
        session.status = TrackingStatus(
            active=True,
            drone_id=session.drone_id,
            detector_backend=detector.backend_name,
            target_class=config.target_class,
            updated_at=time.time(),
            last_observation=TrackingObservation(detected=False),
        )
        session.thread = threading.Thread(
            target=self._run_loop,
            args=(session,),
            daemon=True,
            name=f"tracking-{session.drone_id}",
        )
        with self._lock:
            previous = self._sessions.get(session.drone_id)
            self._sessions[session.drone_id] = session
        if previous is not None:
            previous.stop_event.set()
            if previous.thread is not None:
                previous.thread.join(timeout=5)
        session.thread.start()
        return session.status

    def stop(self, *, drone_id: str) -> TrackingStatus:
        normalized = drone_id or DEFAULT_DRONE_ID
        with self._lock:
            session = self._sessions.get(normalized)
        if session is None:
            return TrackingStatus(active=False, drone_id=normalized, last_observation=TrackingObservation(detected=False))
        session.stop_event.set()
        if session.thread is not None:
            session.thread.join(timeout=5)
        try:
            self.stop_sender(normalized)
        except Exception:
            pass
        inactive = TrackingStatus(
            active=False,
            drone_id=normalized,
            detector_backend=session.status.detector_backend,
            target_class=session.status.target_class,
            step_count=session.status.step_count,
            last_error=session.status.last_error,
            updated_at=time.time(),
            last_command=TrackingCommand(mode="stopped"),
            last_observation=session.status.last_observation,
        )
        with self._lock:
            self._sessions.pop(normalized, None)
        return inactive

    def status(self, drone_id: str = "") -> TrackingStatus:
        normalized = drone_id or DEFAULT_DRONE_ID
        with self._lock:
            session = self._sessions.get(normalized)
            if session is None:
                return TrackingStatus(active=False, drone_id=normalized, last_observation=TrackingObservation(detected=False))
            return session.status

    def run_once(self, *, drone_id: str, config: TrackingConfig) -> TrackingStatus:
        detector = self.detector_factory(config)
        session = _TrackingSession(drone_id=drone_id or DEFAULT_DRONE_ID, config=config, detector=detector)
        self._run_step(session)
        return session.status

    def _run_loop(self, session: _TrackingSession) -> None:
        while not session.stop_event.is_set():
            self._run_step(session)
            session.stop_event.wait(session.config.loop_interval_s)

    def _run_step(self, session: _TrackingSession) -> None:
        updated_at = time.time()
        try:
            drone_status = self.status_provider(session.drone_id)
            authorized = bool(drone_status.connected and drone_status.armed and drone_status.in_air)
            if not authorized:
                session.status = TrackingStatus(
                    active=True,
                    drone_id=session.drone_id,
                    authorized=False,
                    detector_backend=session.detector.backend_name,
                    target_class=session.config.target_class,
                    step_count=session.status.step_count,
                    updated_at=updated_at,
                    last_error="Tracking paused until the drone is armed and airborne.",
                    last_command=TrackingCommand(mode="paused"),
                    last_observation=session.status.last_observation,
                )
                return

            capture = self.capture_provider(session.config.container_name, session.config.camera_topic)
            observation = session.detector.detect(
                capture,
                target_class=session.config.target_class,
                confidence_threshold=session.config.confidence_threshold,
            )
            command = compute_tracking_command(observation, session.config)
            self.command_sender(
                drone_id=session.drone_id,
                forward_m_s=command.forward_m_s,
                right_m_s=command.right_m_s,
                down_m_s=command.down_m_s,
                yaw_rate_deg_s=command.yaw_rate_deg_s,
            )
            session.status = TrackingStatus(
                active=True,
                drone_id=session.drone_id,
                authorized=True,
                detector_backend=session.detector.backend_name,
                target_class=session.config.target_class,
                step_count=session.status.step_count + 1,
                updated_at=updated_at,
                last_error="",
                last_command=command,
                last_observation=observation,
            )
        except Exception as exc:
            session.status = TrackingStatus(
                active=True,
                drone_id=session.drone_id,
                authorized=False,
                detector_backend=getattr(session.detector, "backend_name", ""),
                target_class=session.config.target_class,
                step_count=session.status.step_count,
                updated_at=updated_at,
                last_error=str(exc),
                last_command=TrackingCommand(mode="error"),
                last_observation=session.status.last_observation,
            )
