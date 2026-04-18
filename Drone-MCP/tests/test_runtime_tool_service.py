from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from drone_mcp.runtime_tool_service import RuntimeToolService
from drone_mcp.sim_runtime import RuntimeStatus, SimulatorNotReadyError
from drone_mcp.vision_tracking import TrackingCommand, TrackingObservation, TrackingStatus


class FakeRuntime:
    def __init__(self, status: RuntimeStatus, logs: str = "", wait_error: Exception | None = None) -> None:
        self._status = status
        self._logs = logs
        self._wait_error = wait_error
        self.calls: list[str] = []
        self.config: dict[str, object] = {}

    def ensure_image(self, force_rebuild: bool = False) -> None:
        self.calls.append("ensure_image")

    def start(self) -> None:
        self.calls.append("start")

    def stop(self) -> None:
        self.calls.append("stop")

    def reset(self) -> None:
        self.calls.append("reset")

    def status(self) -> RuntimeStatus:
        self.calls.append("status")
        return self._status

    def wait_until_ready(self, timeout_s: int = 120, poll_interval_s: float = 3.0) -> RuntimeStatus:
        self.calls.append(f"wait_until_ready:{timeout_s}")
        if self._wait_error:
            raise self._wait_error
        return self._status

    def logs_tail(self, lines: int = 200) -> str:
        self.calls.append(f"logs_tail:{lines}")
        return self._logs


class FakeService(RuntimeToolService):
    def __init__(self, runtime: FakeRuntime, tracking=None) -> None:
        super().__init__(tracking=tracking)
        self._runtime = runtime

    def runtime(
        self,
        image: str = "",
        container_name: str = "",
        dockerfile: str = "",
        model: str = "",
        headless: str = "",
        require_gui: str = "",
        require_camera: str = "",
        network_host: str = "",
        ports: str = "",
        environment: str = "",
    ) -> FakeRuntime:
        parsed_ports = ()
        if ports:
            parsed = json.loads(ports) if ports.startswith("[") else [item.strip() for item in ports.split(",") if item.strip()]
            parsed_ports = tuple(parsed)
        parsed_environment = {}
        if environment:
            parsed_environment = json.loads(environment) if environment.startswith("{") else {}
        self._runtime.config = {
            "image": image,
            "container_name": container_name,
            "dockerfile": dockerfile,
            "model": model,
            "headless": headless,
            "require_gui": require_gui,
            "require_camera": require_camera,
            "network_host": network_host,
            "ports": ports,
            "environment": environment,
        }
        self._runtime.image = image or "drone-mcp/sim-monocam:test"
        self._runtime.container_name = container_name or "drone-mcp-test"
        self._runtime.dockerfile = dockerfile or "docker/sim-monocam.Dockerfile"
        self._runtime.model = model or "gz_x500_mono_cam"
        self._runtime.headless = False if headless == "false" else True
        self._runtime.require_gui = require_gui == "true"
        self._runtime.require_camera = False if require_camera == "false" else True
        self._runtime.network_host = network_host == "true"
        self._runtime.ports = parsed_ports or ("14540:14540/udp",)
        self._runtime.environment = parsed_environment
        return self._runtime


class FakeTrackingService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []
        self.payload = TrackingStatus(
            active=True,
            drone_id="drone-1",
            authorized=True,
            detector_backend="fake",
            target_class="person",
            step_count=3,
            updated_at=1.0,
            last_command=TrackingCommand(
                forward_m_s=0.5,
                right_m_s=0.1,
                down_m_s=0.0,
                yaw_rate_deg_s=5.0,
                mode="tracking",
            ),
            last_observation=TrackingObservation(
                detected=True,
                target_class="person",
                confidence=0.9,
                center_x_norm=0.55,
                center_y_norm=0.5,
                area_norm=0.12,
                bbox=(1.0, 2.0, 3.0, 4.0),
                track_id=7,
                frame_width=640,
                frame_height=480,
                source="fake",
            ),
        )

    def start(self, *, drone_id, config):
        self.calls.append(("start", {"drone_id": drone_id, "config": config}))
        return self.payload

    def run_once(self, *, drone_id, config):
        self.calls.append(("run_once", {"drone_id": drone_id, "config": config}))
        return self.payload

    def stop(self, *, drone_id):
        self.calls.append(("stop", {"drone_id": drone_id}))
        return TrackingStatus(
            active=False,
            drone_id=drone_id,
            authorized=False,
            detector_backend=self.payload.detector_backend,
            target_class=self.payload.target_class,
            step_count=self.payload.step_count,
            updated_at=self.payload.updated_at,
            last_command=TrackingCommand(mode="stopped"),
            last_observation=self.payload.last_observation,
        )

    def status(self, drone_id=""):
        self.calls.append(("status", {"drone_id": drone_id}))
        return TrackingStatus(
            active=self.payload.active,
            drone_id=drone_id or self.payload.drone_id,
            authorized=self.payload.authorized,
            detector_backend=self.payload.detector_backend,
            target_class=self.payload.target_class,
            step_count=self.payload.step_count,
            updated_at=self.payload.updated_at,
            last_command=self.payload.last_command,
            last_observation=self.payload.last_observation,
        )


class RuntimeToolServiceTest(unittest.TestCase):
    def make_status(self, *, ready: bool = True, running: bool = True) -> RuntimeStatus:
        return RuntimeStatus(
            image="drone-mcp/sim-monocam:test",
            container_name="drone-mcp-test",
            image_present=True,
            running=running,
            ready=ready,
            camera_ready=ready,
            gui_ready=ready,
            status_text="Up 18 seconds" if running else "",
            camera_topics=(
                "/world/default/model/x500_mono_cam_0/link/camera_link/sensor/camera/image",
            )
            if ready
            else (),
            plugin_errors=(),
            gui_windows=(
                '0x1000012 "Gazebo Sim": ("gz-sim-gui" "Gazebo GUI")  1280x720+10+10  +10+10',
            )
            if ready
            else (),
            gui_blockers=(),
        )

    def test_start_simulation_formats_success_and_waits(self) -> None:
        runtime = FakeRuntime(self.make_status())
        service = FakeService(runtime)

        result = service.start_simulation(timeout="30")

        self.assertIn("✅ Simulation started and is ready.", result)
        self.assertIn("Ready: yes", result)
        self.assertIn("Camera Ready: yes", result)
        self.assertIn("GUI Ready: yes", result)
        self.assertEqual(runtime.calls, ["ensure_image", "start", "wait_until_ready:30"])

    def test_start_simulation_returns_error_text(self) -> None:
        runtime = FakeRuntime(
            self.make_status(ready=False),
            wait_error=SimulatorNotReadyError("simulator not ready"),
        )
        service = FakeService(runtime)

        result = service.start_simulation(timeout="20")

        self.assertEqual(result, "❌ Error: simulator not ready")

    def test_start_simulation_accepts_runtime_profile_arguments(self) -> None:
        runtime = FakeRuntime(self.make_status())
        service = FakeService(runtime)

        result = service.start_simulation(
            image="custom:image",
            container_name="custom-container",
            dockerfile="docker/custom.Dockerfile",
            model="gz_custom_model",
            headless="false",
            require_gui="true",
            require_camera="false",
            network_host="true",
            ports='["14540:14540/udp"]',
            environment='{"VNC_GEOMETRY":"1600x900"}',
            timeout="15",
        )

        self.assertIn("✅ Simulation started and is ready.", result)
        self.assertEqual(runtime.config["image"], "")
        self.assertEqual(runtime.config["container_name"], "")
        self.assertEqual(service._runtime_profile["image"], "custom:image")
        self.assertEqual(service._runtime_profile["container_name"], "custom-container")
        self.assertEqual(service._runtime_profile["dockerfile"], "docker/custom.Dockerfile")
        self.assertEqual(service._runtime_profile["model"], "gz_custom_model")
        self.assertFalse(service._runtime_profile["headless"])
        self.assertTrue(service._runtime_profile["require_gui"])
        self.assertFalse(service._runtime_profile["require_camera"])
        self.assertTrue(service._runtime_profile["network_host"])
        self.assertEqual(service._runtime_profile["ports"], ("14540:14540/udp",))
        self.assertEqual(service._runtime_profile["environment"], {"VNC_GEOMETRY": "1600x900"})

    def test_stop_simulation_reports_state(self) -> None:
        runtime = FakeRuntime(self.make_status(ready=False, running=False))
        service = FakeService(runtime)

        result = service.stop_simulation()

        self.assertIn("✅ Simulation stop command completed.", result)
        self.assertIn("Running: no", result)
        self.assertEqual(runtime.calls, ["stop", "status"])

    def test_get_runtime_health_reports_warning_when_not_ready(self) -> None:
        runtime = FakeRuntime(self.make_status(ready=False))
        service = FakeService(runtime)

        result = service.get_runtime_health()

        self.assertIn("⚠️ Runtime health snapshot.", result)
        self.assertIn("Ready: no", result)
        self.assertIn("Camera Ready: no", result)
        self.assertIn("GUI Ready: no", result)

    def test_get_simulation_logs_uses_default_line_count(self) -> None:
        runtime = FakeRuntime(self.make_status(), logs="hello log")
        service = FakeService(runtime)

        result = service.get_simulation_logs()

        self.assertEqual(result, "📁 Simulation logs:\nhello log")
        self.assertEqual(runtime.calls, ["logs_tail:200"])

    def test_invalid_integer_parameter_returns_error(self) -> None:
        runtime = FakeRuntime(self.make_status())
        service = FakeService(runtime)

        result = service.get_simulation_logs(lines="0")

        self.assertEqual(result, "❌ Error: lines must be at least 1.")

    def test_tool_definitions_include_visual_tracking_and_velocity_tools(self) -> None:
        runtime = FakeRuntime(self.make_status())
        service = FakeService(runtime)

        names = [tool["function"]["name"] for tool in service.list_tool_definitions()]

        for expected in [
            "send_body_velocity",
            "stop_body_velocity_control",
            "start_visual_tracking",
            "run_visual_tracking_step",
            "stop_visual_tracking",
            "get_visual_tracking_status",
        ]:
            self.assertIn(expected, names)

    def test_start_visual_tracking_uses_injected_tracking_service(self) -> None:
        runtime = FakeRuntime(self.make_status())
        tracking = FakeTrackingService()
        service = FakeService(runtime, tracking=tracking)

        result = service.start_visual_tracking(
            drone_id="drone-1",
            container_name="vision-container",
            camera_topic="/camera/topic",
            target_class="person",
            confidence_threshold="0.5",
        )

        self.assertIn("✅ Visual tracking loop started.", result)
        self.assertIn("Target Class: person", result)
        self.assertEqual(tracking.calls[0][0], "start")
        self.assertEqual(tracking.calls[0][1]["drone_id"], "drone-1")
        self.assertEqual(tracking.calls[0][1]["config"].camera_topic, "/camera/topic")

    def test_get_visual_tracking_status_formats_snapshot(self) -> None:
        runtime = FakeRuntime(self.make_status())
        tracking = FakeTrackingService()
        service = FakeService(runtime, tracking=tracking)

        result = service.get_visual_tracking_status("drone-1")

        self.assertIn("🎯 Visual Tracking:", result)
        self.assertIn("Active: yes", result)
        self.assertIn("Observation: detected person", result)


if __name__ == "__main__":
    unittest.main()
