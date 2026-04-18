"""Unit tests for the flight control tools in RuntimeToolService.

Uses a ``FakeMavsdkBackend`` that returns canned telemetry so the tests
run without MAVSDK or a PX4 instance.
"""

from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from drone_mcp.flight_control import DroneController, DroneStatus, MavsdkBackend
from drone_mcp.runtime_tool_service import RuntimeToolService
from drone_mcp.sim_runtime import RuntimeStatus


# --------------------------------------------------------------------------
# Fake MAVSDK backend – no network, no PX4
# --------------------------------------------------------------------------

class FakeMavsdkBackend:
    """In-memory MAVSDK substitute for unit tests."""

    def __init__(self) -> None:
        self.connected = False
        self.armed = False
        self.in_air = False
        self.offboard_started = False
        self.position = (47.397742, 8.545594, 488.0, 0.0)  # lat, lon, abs_alt, rel_alt
        self.battery_percent = 0.85
        self.flight_mode = "HOLD"
        self.groundspeed_m_s = 0.0
        self.heading_deg = 90.0
        self.calls: list[str] = []
        self.body_velocity_commands: list[tuple[float, float, float, float]] = []

    async def connect(self, system_address: str) -> None:
        self.calls.append(f"connect:{system_address}")
        self.connected = True

    async def wait_for_connected(self, timeout: float) -> bool:
        self.calls.append("wait_for_connected")
        return self.connected

    async def wait_for_gps_ready(self, timeout: float) -> bool:
        self.calls.append("wait_for_gps_ready")
        return True

    async def arm(self) -> None:
        self.calls.append("arm")
        self.armed = True

    async def disarm(self) -> None:
        self.calls.append("disarm")
        self.armed = False

    async def takeoff(self) -> None:
        self.calls.append("takeoff")
        self.in_air = True
        self.position = (self.position[0], self.position[1], self.position[2] + 5, 5.0)

    async def land(self) -> None:
        self.calls.append("land")

    async def set_takeoff_altitude(self, altitude_m: float) -> None:
        self.calls.append(f"set_takeoff_altitude:{altitude_m}")

    async def goto_location(
        self, latitude_deg: float, longitude_deg: float, absolute_altitude_m: float, yaw_deg: float,
    ) -> None:
        self.calls.append(f"goto:{latitude_deg},{longitude_deg},{absolute_altitude_m},{yaw_deg}")
        self.position = (latitude_deg, longitude_deg, absolute_altitude_m, absolute_altitude_m - 488)
        self.groundspeed_m_s = 4.5
        self.heading_deg = yaw_deg

    async def hold(self) -> None:
        self.calls.append("hold")
        self.flight_mode = "HOLD"

    async def return_to_launch(self) -> None:
        self.calls.append("rtl")
        self.flight_mode = "RETURN_TO_LAUNCH"

    async def set_maximum_speed(self, speed_m_s: float) -> None:
        self.calls.append(f"set_max_speed:{speed_m_s}")

    async def start_offboard(self) -> None:
        self.calls.append("start_offboard")
        self.offboard_started = True

    async def stop_offboard(self) -> None:
        self.calls.append("stop_offboard")
        self.offboard_started = False

    async def set_velocity_body(
        self,
        forward_m_s: float,
        right_m_s: float,
        down_m_s: float,
        yaw_rate_deg_s: float,
    ) -> None:
        self.calls.append(f"set_velocity_body:{forward_m_s},{right_m_s},{down_m_s},{yaw_rate_deg_s}")
        self.body_velocity_commands.append((forward_m_s, right_m_s, down_m_s, yaw_rate_deg_s))

    async def get_status(self) -> DroneStatus:
        self.calls.append("get_status")
        lat, lon, abs_alt, rel_alt = self.position
        return DroneStatus(
            connected=True,
            armed=self.armed,
            in_air=self.in_air,
            latitude_deg=lat,
            longitude_deg=lon,
            absolute_altitude_m=abs_alt,
            relative_altitude_m=rel_alt,
            battery_percent=self.battery_percent * 100,
            flight_mode=self.flight_mode,
            groundspeed_m_s=self.groundspeed_m_s,
            heading_deg=self.heading_deg,
        )


def _make_fake_service() -> tuple[RuntimeToolService, FakeMavsdkBackend]:
    backend = FakeMavsdkBackend()
    controller = DroneController(backend=backend)
    service = RuntimeToolService(drone=controller)
    return service, backend


# --------------------------------------------------------------------------
# Flight control tool service tests
# --------------------------------------------------------------------------

class FlightControlToolServiceTest(unittest.TestCase):

    def test_connect_drone_returns_success(self) -> None:
        service, backend = _make_fake_service()
        result = service.call_tool("connect_drone")
        self.assertIn("✅ Connected to PX4", result)
        self.assertIn("GPS: ready", result)
        self.assertTrue(backend.connected)

    def test_arm_without_connect_returns_error(self) -> None:
        service, _ = _make_fake_service()
        result = service.call_tool("arm_drone")
        self.assertIn("❌", result)
        self.assertIn("not connected", result.lower())

    def test_arm_after_connect_succeeds(self) -> None:
        service, backend = _make_fake_service()
        service.call_tool("connect_drone")
        result = service.call_tool("arm_drone")
        self.assertIn("✅ Drone armed", result)
        self.assertTrue(backend.armed)

    def test_takeoff_with_altitude(self) -> None:
        service, backend = _make_fake_service()
        service.call_tool("connect_drone")
        result = service.call_tool("takeoff", {"altitude": "10"})
        self.assertIn("✅ Takeoff initiated", result)
        self.assertIn("10.0", result)
        self.assertIn("set_takeoff_altitude:10.0", backend.calls)

    def test_takeoff_invalid_altitude_returns_error(self) -> None:
        service, _ = _make_fake_service()
        service.call_tool("connect_drone")
        result = service.call_tool("takeoff", {"altitude": "abc"})
        self.assertIn("❌", result)
        self.assertIn("Invalid", result)

    def test_takeoff_altitude_out_of_range(self) -> None:
        service, _ = _make_fake_service()
        service.call_tool("connect_drone")
        result = service.call_tool("takeoff", {"altitude": "200"})
        self.assertIn("❌", result)
        self.assertIn("max altitude is 120.0 m", result)

    def test_land_succeeds(self) -> None:
        service, backend = _make_fake_service()
        service.call_tool("connect_drone")
        result = service.call_tool("land")
        self.assertIn("✅ Landing initiated", result)
        self.assertIn("land", backend.calls)

    def test_go_to_location_with_coordinates(self) -> None:
        service, backend = _make_fake_service()
        service.call_tool("connect_drone")
        result = service.call_tool("go_to_location", {
            "latitude": "47.40",
            "longitude": "8.55",
            "altitude": "15",
        })
        self.assertIn("✅ Flying to", result)
        self.assertIn("47.40", result)
        self.assertTrue(any("goto:47.4,8.55,503.0,0.0" in c for c in backend.calls))

    def test_go_to_location_blocks_on_geofence_distance(self) -> None:
        service, _ = _make_fake_service()
        service.call_tool("connect_drone")
        service.call_tool("set_geofence", {"max_distance": "10"})
        result = service.call_tool("go_to_location", {
            "latitude": "47.500000",
            "longitude": "8.700000",
            "altitude": "15",
        })
        self.assertIn("❌", result)
        self.assertIn("geofence", result.lower())

    def test_tools_accept_drone_id(self) -> None:
        service, backend = _make_fake_service()
        result = service.call_tool("connect_drone", {"drone_id": "drone-1"})
        self.assertIn("✅", result)
        self.assertIn("connect:udp://:14540", backend.calls[0])

    def test_go_to_location_missing_coords_returns_error(self) -> None:
        service, _ = _make_fake_service()
        service.call_tool("connect_drone")
        result = service.call_tool("go_to_location", {"altitude": "10"})
        self.assertIn("❌", result)
        self.assertIn("required", result.lower())

    def test_get_drone_status_returns_telemetry(self) -> None:
        service, _ = _make_fake_service()
        service.call_tool("connect_drone")
        result = service.call_tool("get_drone_status")
        self.assertIn("📡 Drone Status", result)
        self.assertIn("Position:", result)
        self.assertIn("Battery:", result)
        self.assertIn("Flight Mode:", result)
        self.assertIn("Heading:", result)
        self.assertIn("Ground Speed:", result)

    def test_hold_position_succeeds(self) -> None:
        service, backend = _make_fake_service()
        service.call_tool("connect_drone")
        result = service.call_tool("hold_position")
        self.assertIn("✅ Holding position", result)
        self.assertIn("hold", backend.calls)

    def test_return_to_launch_succeeds(self) -> None:
        service, backend = _make_fake_service()
        service.call_tool("connect_drone")
        result = service.call_tool("return_to_launch")
        self.assertIn("✅ Returning to launch", result)
        self.assertIn("rtl", backend.calls)

    def test_send_body_velocity_starts_offboard_once(self) -> None:
        service, backend = _make_fake_service()
        service.call_tool("connect_drone")

        first = service.call_tool("send_body_velocity", {
            "forward_m_s": "1.2",
            "right_m_s": "0.4",
            "down_m_s": "-0.1",
            "yaw_rate_deg_s": "12",
        })
        second = service.call_tool("send_body_velocity", {
            "forward_m_s": "0.5",
            "right_m_s": "0.0",
            "down_m_s": "0.0",
            "yaw_rate_deg_s": "0",
        })

        self.assertIn("✅ Body velocity command applied", first)
        self.assertIn("✅ Body velocity command applied", second)
        self.assertEqual(backend.calls.count("start_offboard"), 1)
        self.assertEqual(len(backend.body_velocity_commands), 2)
        self.assertTrue(backend.offboard_started)

    def test_stop_body_velocity_control_stops_offboard(self) -> None:
        service, backend = _make_fake_service()
        service.call_tool("connect_drone")
        service.call_tool("send_body_velocity", {"forward_m_s": "1.0"})

        result = service.call_tool("stop_body_velocity_control")

        self.assertIn("✅ Offboard body control stopped", result)
        self.assertIn("stop_offboard", backend.calls)
        self.assertFalse(backend.offboard_started)

    def test_takeoff_stops_offboard_before_standard_flight_mode(self) -> None:
        service, backend = _make_fake_service()
        service.call_tool("connect_drone")
        service.call_tool("send_body_velocity", {"forward_m_s": "1.0"})

        result = service.call_tool("takeoff", {"altitude": "10"})

        self.assertIn("✅ Takeoff initiated", result)
        stop_index = backend.calls.index("stop_offboard")
        takeoff_index = backend.calls.index("takeoff")
        self.assertLess(stop_index, takeoff_index)
        self.assertFalse(backend.offboard_started)

    def test_tool_definitions_include_flight_tools(self) -> None:
        service, _ = _make_fake_service()
        names = [t["function"]["name"] for t in service.list_tool_definitions()]
        for expected in [
            "connect_drone", "arm_drone", "takeoff", "land",
            "go_to_location", "get_drone_status", "hold_position", "return_to_launch",
            "send_body_velocity", "stop_body_velocity_control",
        ]:
            self.assertIn(expected, names, f"Missing tool definition: {expected}")

    def test_full_mission_sequence(self) -> None:
        """End-to-end: connect → takeoff → goto → status → land."""
        service, backend = _make_fake_service()

        r1 = service.call_tool("connect_drone")
        self.assertIn("✅", r1)

        r2 = service.call_tool("takeoff", {"altitude": "10"})
        self.assertIn("✅", r2)

        r3 = service.call_tool("go_to_location", {
            "latitude": "47.40", "longitude": "8.55", "altitude": "10",
        })
        self.assertIn("✅", r3)

        r4 = service.call_tool("get_drone_status")
        self.assertIn("47.40", r4)

        r5 = service.call_tool("land")
        self.assertIn("✅", r5)


# --------------------------------------------------------------------------
# DroneStatus formatting test
# --------------------------------------------------------------------------

class DroneStatusFormatTest(unittest.TestCase):

    def test_disconnected_format(self) -> None:
        status = DroneStatus(
            connected=False, armed=False, in_air=False,
            latitude_deg=0, longitude_deg=0,
            absolute_altitude_m=0, relative_altitude_m=0,
            battery_percent=0, flight_mode="UNKNOWN",
        )
        self.assertEqual(status.format(), "Drone not connected.")

    def test_connected_format_includes_all_fields(self) -> None:
        status = DroneStatus(
            connected=True, armed=True, in_air=True,
            latitude_deg=47.3977, longitude_deg=8.5456,
            absolute_altitude_m=498.0, relative_altitude_m=10.0,
            battery_percent=85.0, flight_mode="HOLD",
            groundspeed_m_s=4.2, heading_deg=90.0,
        )
        text = status.format()
        self.assertIn("Armed: yes", text)
        self.assertIn("In Air: yes", text)
        self.assertIn("47.397700", text)
        self.assertIn("Battery: 85%", text)
        self.assertIn("Flight Mode: HOLD", text)
        self.assertIn("Heading: 90", text)
        self.assertIn("Ground Speed: 4.2", text)


if __name__ == "__main__":
    unittest.main()
