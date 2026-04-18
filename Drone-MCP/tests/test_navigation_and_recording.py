from __future__ import annotations

import sys
import tempfile
import time
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from drone_mcp.flight_control import DroneStatus
from drone_mcp.navigation import GeoPoint, generate_lawnmower_pattern, haversine_distance_m
from drone_mcp.recording import FlightRecordingManager


class NavigationTest(unittest.TestCase):
    def test_haversine_distance_is_zero_for_same_point(self) -> None:
        distance = haversine_distance_m(47.397742, 8.545594, 47.397742, 8.545594)
        self.assertAlmostEqual(distance, 0.0, places=6)

    def test_generate_lawnmower_pattern_returns_multiple_points(self) -> None:
        polygon = [
            GeoPoint(47.397700, 8.545500),
            GeoPoint(47.397700, 8.545900),
            GeoPoint(47.398000, 8.545900),
            GeoPoint(47.398000, 8.545500),
        ]

        pattern = generate_lawnmower_pattern(
            polygon,
            strip_spacing_m=10.0,
            waypoint_spacing_m=10.0,
        )

        self.assertGreaterEqual(len(pattern), 4)
        self.assertTrue(all(isinstance(point, GeoPoint) for point in pattern))


class RecordingTest(unittest.TestCase):
    def test_recording_manager_writes_and_reads_json_log(self) -> None:
        samples = [
            DroneStatus(
                connected=True,
                armed=True,
                in_air=True,
                latitude_deg=47.397742,
                longitude_deg=8.545594,
                absolute_altitude_m=490.0,
                relative_altitude_m=2.0,
                battery_percent=82.0,
                flight_mode="HOLD",
                groundspeed_m_s=1.5,
                heading_deg=90.0,
            ),
            DroneStatus(
                connected=True,
                armed=True,
                in_air=True,
                latitude_deg=47.397842,
                longitude_deg=8.545694,
                absolute_altitude_m=492.0,
                relative_altitude_m=4.0,
                battery_percent=80.0,
                flight_mode="MISSION",
                groundspeed_m_s=2.0,
                heading_deg=95.0,
            ),
        ]

        index = {"value": 0}

        def provider(_: str) -> DroneStatus:
            sample = samples[min(index["value"], len(samples) - 1)]
            index["value"] += 1
            return sample

        with tempfile.TemporaryDirectory() as temp_dir:
            manager = FlightRecordingManager(Path(temp_dir), status_provider=provider)
            started = manager.start(drone_id="drone-1", interval_s=0.05)
            time.sleep(0.14)
            stopped = manager.stop(recording_id=started["recording_id"])
            payload = manager.get_recording(started["recording_id"])

        self.assertEqual(stopped["recording_id"], started["recording_id"])
        self.assertGreaterEqual(len(payload["samples"]), 2)
        self.assertEqual(payload["drone_id"], "drone-1")


if __name__ == "__main__":
    unittest.main()
