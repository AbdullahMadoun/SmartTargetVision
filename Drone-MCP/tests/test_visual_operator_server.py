from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import visual_operator_server as server


class FakeToolService:
    def __init__(self) -> None:
        self._drones = [
            {"drone_id": "drone-1", "label": "Primary Test Drone"},
            {"drone_id": "drone-2", "label": "Secondary"},
        ]

    def list_drones_data(self) -> list[dict[str, object]]:
        return [dict(item) for item in self._drones]

    def get_runtime_health_data(self) -> dict[str, object]:
        return {
            "ready": True,
            "running": True,
            "status_text": "healthy",
        }

    def get_runtime_health(self) -> str:
        return "✅ Runtime healthy."

    def get_runtime_profile_data(self) -> dict[str, object]:
        return {
            "image": "drone-mcp/sim-monocam:test",
            "container_name": "drone-mcp-test",
            "dockerfile": "docker/sim-monocam.Dockerfile",
            "model": "gz_x500_mono_cam",
            "headless": True,
            "require_gui": False,
            "require_camera": True,
            "network_host": False,
            "ports": ["14540:14540/udp", "14550:14550/udp"],
            "environment": {},
        }

    def get_drone_status_data(self, drone_id: str = "") -> dict[str, object]:
        return {
            "connected": True,
            "armed": True,
            "in_air": False,
            "drone_id": drone_id or "drone-1",
            "latitude_deg": 24.7136,
            "longitude_deg": 46.6753,
            "absolute_altitude_m": 512.4,
            "relative_altitude_m": 12.4,
            "battery_percent": 87.0,
            "flight_mode": "HOLD",
            "groundspeed_m_s": 0.4,
            "heading_deg": 92.0,
            "distance_from_home_m": 2.5,
        }

    def get_fleet_status_data(self) -> dict[str, dict[str, object]]:
        return {item["drone_id"]: self.get_drone_status_data(item["drone_id"]) for item in self._drones}

    def list_recordings_data(self) -> list[dict[str, object]]:
        return [{"recording_id": "rec-1", "drone_id": "drone-1", "active": False}]

    def get_geofence_data(self) -> dict[str, float]:
        return {
            "max_altitude_m": 120.0,
            "max_distance_from_home_m": 500.0,
            "min_battery_percent_for_rtl": 20.0,
        }

    def get_visual_tracking_status_data(self, drone_id: str = "") -> dict[str, object]:
        return {
            "active": True,
            "drone_id": drone_id or "drone-1",
            "authorized": True,
            "detector_backend": "fake",
            "target_class": "person",
            "step_count": 4,
            "last_error": "",
            "updated_at": 1.0,
            "last_command": {
                "forward_m_s": 0.5,
                "right_m_s": 0.0,
                "down_m_s": 0.0,
                "yaw_rate_deg_s": 5.0,
                "mode": "tracking",
            },
            "last_observation": {
                "detected": True,
                "target_class": "person",
                "confidence": 0.9,
                "center_x_norm": 0.5,
                "center_y_norm": 0.5,
                "area_norm": 0.1,
                "bbox": [1, 2, 3, 4],
                "track_id": 1,
                "frame_width": 640,
                "frame_height": 480,
                "source": "fake",
            },
        }


class FailingToolService(FakeToolService):
    def get_runtime_health_data(self) -> dict[str, object]:
        raise RuntimeError("runtime unavailable")

    def get_runtime_health(self) -> str:
        raise RuntimeError("runtime unavailable")

    def get_runtime_profile_data(self) -> dict[str, object]:
        raise RuntimeError("runtime unavailable")

    def get_drone_status_data(self, drone_id: str = "") -> dict[str, object]:
        raise RuntimeError("status unavailable")

    def list_recordings_data(self) -> list[dict[str, object]]:
        raise RuntimeError("recordings unavailable")

    def get_geofence_data(self) -> dict[str, float]:
        raise RuntimeError("geofence unavailable")


class VisualOperatorServerTest(unittest.TestCase):
    def setUp(self) -> None:
        self._original_tool_service = server.tool_service

    def tearDown(self) -> None:
        server.tool_service = self._original_tool_service

    def test_config_exposes_single_drone_and_template_catalog(self) -> None:
        server.tool_service = FakeToolService()

        config = server.config()

        self.assertEqual(config["server_mode"], "single-drone")
        self.assertEqual(config["drone_id"], "drone-1")
        self.assertEqual(config["drone"]["drone_id"], "drone-1")
        self.assertEqual(config["active_drone"]["drone_id"], "drone-1")
        self.assertEqual(config["template_catalog_url"], "/api/templates")
        self.assertIsInstance(config["simulation_templates"], list)
        self.assertGreaterEqual(len(config["simulation_templates"]), 3)
        self.assertTrue(any(template["recommended"] for template in config["simulation_templates"]))
        self.assertEqual(config["tracking"]["drone_id"], "drone-1")
        self.assertEqual(config["runtime_profile"]["model"], "gz_x500_mono_cam")

    def test_status_prioritizes_one_active_drone_and_keeps_aliases(self) -> None:
        server.tool_service = FakeToolService()

        snapshot = server.status(drone_id="")

        self.assertEqual(snapshot["server_mode"], "single-drone")
        self.assertEqual(snapshot["drone_id"], "drone-1")
        self.assertEqual(snapshot["drone"]["drone_id"], "drone-1")
        self.assertEqual(snapshot["telemetry"]["drone_id"], "drone-1")
        self.assertEqual(snapshot["status"]["drone_id"], "drone-1")
        self.assertEqual(snapshot["selected_status"]["drone_id"], "drone-1")
        self.assertEqual(snapshot["connection"]["drone_id"], "drone-1")
        self.assertEqual(snapshot["drone_count"], 2)
        self.assertEqual(snapshot["connection"]["quality"], "excellent")
        self.assertEqual(snapshot["fleet_status"]["drone-1"]["drone_id"], "drone-1")
        self.assertTrue(snapshot["tracking"]["active"])
        self.assertEqual(snapshot["autonomy"]["target_class"], "person")
        self.assertEqual(snapshot["runtime_profile"]["container_name"], "drone-mcp-test")

    def test_status_falls_back_cleanly_when_runtime_is_unavailable(self) -> None:
        server.tool_service = FailingToolService()

        snapshot = server.status(drone_id="")

        self.assertEqual(snapshot["server_mode"], "single-drone")
        self.assertFalse(snapshot["drone"]["connected"])
        self.assertEqual(snapshot["drone"]["drone_id"], "drone-1")
        self.assertEqual(snapshot["connection"]["quality"], "offline")
        self.assertIn("Connection error", snapshot["runtime_text"])
        self.assertEqual(snapshot["geofence"], {})
        self.assertEqual(snapshot["recordings"], [])
        self.assertEqual(snapshot["runtime_profile"], {})

    def test_template_catalog_endpoint_returns_presets(self) -> None:
        server.tool_service = FakeToolService()

        payload = server.templates()

        self.assertEqual(payload["server_mode"], "single-drone")
        self.assertEqual(payload["drone_id"], "drone-1")
        self.assertIsInstance(payload["template_catalog"], list)
        template_ids = {item["template_id"] for item in payload["template_catalog"]}
        self.assertTrue({"default", "fast", "visual", "vision-follow", "survey"}.issubset(template_ids))


if __name__ == "__main__":
    unittest.main()
