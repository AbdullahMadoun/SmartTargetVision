from __future__ import annotations

import sys
import time
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from drone_mcp.camera_capture import CameraFrameCapture
from drone_mcp.flight_control import DroneStatus
from drone_mcp.vision_tracking import (
    TrackingConfig,
    TrackingObservation,
    VisualTrackingService,
    compute_tracking_command,
)


class FakeDetector:
    backend_name = "fake"

    def __init__(self, observation: TrackingObservation) -> None:
        self.observation = observation
        self.calls: list[tuple[str, float]] = []

    def detect(self, capture: CameraFrameCapture, *, target_class: str, confidence_threshold: float) -> TrackingObservation:
        self.calls.append((target_class, confidence_threshold))
        return self.observation


def _capture() -> CameraFrameCapture:
    return CameraFrameCapture(
        container_name="sim",
        topic="/camera/topic",
        command=("gz", "topic"),
        width=640,
        height=480,
        pixel_format_type="RGB_INT8",
        mime_type="image/png",
        encoding="png",
        image_bytes=b"frame",
        image_base64="ZnJhbWU=",
    )


def _authorized_status() -> DroneStatus:
    return DroneStatus(
        connected=True,
        armed=True,
        in_air=True,
        latitude_deg=47.397742,
        longitude_deg=8.545594,
        absolute_altitude_m=490.0,
        relative_altitude_m=10.0,
        battery_percent=85.0,
        flight_mode="OFFBOARD",
    )


class VisionTrackingTest(unittest.TestCase):
    def test_compute_tracking_command_searches_when_target_missing(self) -> None:
        command = compute_tracking_command(
            TrackingObservation(detected=False),
            TrackingConfig(scan_yaw_rate_deg_s=18.0, max_yaw_rate_deg_s=30.0),
        )

        self.assertEqual(command.mode, "searching")
        self.assertEqual(command.forward_m_s, 0.0)
        self.assertEqual(command.yaw_rate_deg_s, 18.0)

    def test_run_once_captures_and_sends_command_for_authorized_drone(self) -> None:
        captures: list[tuple[str, str]] = []
        commands: list[dict[str, object]] = []
        detector = FakeDetector(
            TrackingObservation.from_bbox(
                bbox=(220.0, 120.0, 420.0, 360.0),
                frame_width=640,
                frame_height=480,
                target_class="person",
                confidence=0.92,
                track_id=5,
                source="fake",
            )
        )
        service = VisualTrackingService(
            capture_provider=lambda container_name, topic: captures.append((container_name, topic)) or _capture(),
            status_provider=lambda drone_id: _authorized_status(),
            command_sender=lambda **kwargs: commands.append(kwargs) or "ok",
            stop_sender=lambda drone_id: "stopped",
            detector_factory=lambda config: detector,
        )

        status = service.run_once(
            drone_id="drone-1",
            config=TrackingConfig(
                container_name="sim",
                camera_topic="/camera/topic",
                target_class="person",
            ),
        )

        self.assertTrue(status.active)
        self.assertTrue(status.authorized)
        self.assertEqual(status.step_count, 1)
        self.assertEqual(status.last_command.mode, "tracking")
        self.assertEqual(captures, [("sim", "/camera/topic")])
        self.assertEqual(len(commands), 1)
        self.assertEqual(commands[0]["drone_id"], "drone-1")
        self.assertGreaterEqual(detector.calls[0][1], 0.0)

    def test_run_once_pauses_when_drone_is_not_airborne(self) -> None:
        captures: list[tuple[str, str]] = []
        commands: list[dict[str, object]] = []
        detector = FakeDetector(TrackingObservation(detected=False))
        service = VisualTrackingService(
            capture_provider=lambda container_name, topic: captures.append((container_name, topic)) or _capture(),
            status_provider=lambda drone_id: DroneStatus(
                connected=True,
                armed=False,
                in_air=False,
                latitude_deg=0.0,
                longitude_deg=0.0,
                absolute_altitude_m=0.0,
                relative_altitude_m=0.0,
                battery_percent=90.0,
                flight_mode="HOLD",
            ),
            command_sender=lambda **kwargs: commands.append(kwargs) or "ok",
            stop_sender=lambda drone_id: "stopped",
            detector_factory=lambda config: detector,
        )

        status = service.run_once(
            drone_id="drone-1",
            config=TrackingConfig(container_name="sim", camera_topic="/camera/topic"),
        )

        self.assertTrue(status.active)
        self.assertFalse(status.authorized)
        self.assertEqual(status.last_command.mode, "paused")
        self.assertIn("paused", status.last_error.lower())
        self.assertEqual(captures, [])
        self.assertEqual(commands, [])

    def test_stop_calls_stop_sender_for_running_session(self) -> None:
        stop_calls: list[str] = []
        detector = FakeDetector(TrackingObservation(detected=False))
        service = VisualTrackingService(
            capture_provider=lambda container_name, topic: _capture(),
            status_provider=lambda drone_id: _authorized_status(),
            command_sender=lambda **kwargs: "ok",
            stop_sender=lambda drone_id: stop_calls.append(drone_id) or "stopped",
            detector_factory=lambda config: detector,
        )

        service.start(
            drone_id="drone-1",
            config=TrackingConfig(container_name="sim", camera_topic="/camera/topic", loop_interval_s=0.05),
        )
        time.sleep(0.08)
        status = service.stop(drone_id="drone-1")

        self.assertFalse(status.active)
        self.assertEqual(stop_calls, ["drone-1"])


if __name__ == "__main__":
    unittest.main()
