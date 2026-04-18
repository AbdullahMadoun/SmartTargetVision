from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from drone_mcp.sim_runtime import (
    CAMERA_TOPIC_FRAGMENT,
    CommandResult,
    DockerSimulatorRuntime,
    SimulatorNotReadyError,
)


class StubRunner:
    def __init__(self, responses: list[CommandResult]) -> None:
        self.responses = list(responses)
        self.calls: list[list[str]] = []

    def run(self, args: list[str], *, timeout: int = 600, check: bool = True) -> CommandResult:
        self.calls.append(args)
        if not self.responses:
            raise AssertionError(f"No stubbed response left for command: {args}")
        return self.responses.pop(0)


class SimulatorRuntimeTest(unittest.TestCase):
    def make_runtime(self, runner: StubRunner) -> DockerSimulatorRuntime:
        return DockerSimulatorRuntime(
            ROOT,
            image="drone-mcp/sim-monocam:test",
            container_name="drone-mcp-test",
            runner=runner,
        )

    def test_build_image_and_start_emit_expected_commands(self) -> None:
        runner = StubRunner(
            [
                CommandResult(0, "", ""),
                CommandResult(0, "", ""),
                CommandResult(0, "abc123", ""),
            ]
        )
        runtime = self.make_runtime(runner)

        runtime.build_image()
        runtime.start()

        self.assertEqual(runner.calls[0][:3], ["docker", "build", "-f"])
        self.assertEqual(runner.calls[1], ["docker", "rm", "-f", "drone-mcp-test"])
        self.assertEqual(runner.calls[2][0:4], ["docker", "run", "-d", "--rm"])
        self.assertIn("PX4_SIM_MODEL=gz_x500_mono_cam", runner.calls[2])

    def test_start_includes_custom_environment_variables(self) -> None:
        runner = StubRunner(
            [
                CommandResult(0, "", ""),
                CommandResult(0, "abc123", ""),
            ]
        )
        runtime = DockerSimulatorRuntime(
            ROOT,
            image="drone-mcp/sim-monocam:test",
            container_name="drone-mcp-test",
            environment={"VNC_GEOMETRY": "1600x900", "DRONE_MCP_MODEL_WAIT_SECONDS": "180"},
            runner=runner,
        )

        runtime.start()

        self.assertIn("VNC_GEOMETRY=1600x900", runner.calls[1])
        self.assertIn("DRONE_MCP_MODEL_WAIT_SECONDS=180", runner.calls[1])

    def test_status_is_ready_when_camera_topics_exist_and_logs_are_clean(self) -> None:
        runner = StubRunner(
            [
                CommandResult(0, "[]", ""),
                CommandResult(0, "Up 12 seconds\n", ""),
                CommandResult(0, "", ""),
                CommandResult(
                    0,
                    "\n".join(
                        [
                            "/clock",
                            f"/world/default/model/x500_mono_cam_0/link/camera_link/sensor/camera/image",
                            f"/world/default/model/x500_mono_cam_0/link/camera_link/sensor/camera/camera_info",
                        ]
                    ),
                    "",
                ),
            ]
        )
        runtime = self.make_runtime(runner)

        status = runtime.status()

        self.assertTrue(status.running)
        self.assertTrue(status.ready)
        self.assertTrue(status.camera_ready)
        self.assertTrue(status.gui_ready)
        self.assertTrue(status.image_present)
        self.assertEqual(len(status.plugin_errors), 0)
        self.assertEqual(len(status.camera_topics), 2)
        self.assertEqual(status.gui_windows, ())
        self.assertEqual(status.gui_blockers, ())
        self.assertTrue(all(CAMERA_TOPIC_FRAGMENT in topic for topic in status.camera_topics))

    def test_status_detects_plugin_failures(self) -> None:
        runner = StubRunner(
            [
                CommandResult(0, "[]", ""),
                CommandResult(0, "Up 12 seconds\n", ""),
                CommandResult(
                    0,
                    "Error while loading the library [/opt/px4-gazebo/lib/gz/plugins/libGstCameraSystem.so]",
                    "",
                ),
                CommandResult(0, "", ""),
            ]
        )
        runtime = self.make_runtime(runner)

        status = runtime.status()

        self.assertTrue(status.running)
        self.assertFalse(status.ready)
        self.assertFalse(status.camera_ready)
        self.assertTrue(status.gui_ready)
        self.assertTrue(status.image_present)
        self.assertEqual(len(status.plugin_errors), 1)

    def test_status_handles_missing_container(self) -> None:
        runner = StubRunner(
            [
                CommandResult(1, "", "Error: No such image"),
                CommandResult(0, "", ""),
                CommandResult(1, "", "Error: No such container"),
            ]
        )
        runtime = self.make_runtime(runner)

        status = runtime.status()

        self.assertFalse(status.running)
        self.assertFalse(status.ready)
        self.assertFalse(status.camera_ready)
        self.assertTrue(status.gui_ready)
        self.assertFalse(status.image_present)
        self.assertEqual(status.status_text, "")
        self.assertEqual(status.camera_topics, ())

    def test_status_requires_gui_window_when_configured(self) -> None:
        runner = StubRunner(
            [
                CommandResult(0, "[]", ""),
                CommandResult(0, "Up 12 seconds\n", ""),
                CommandResult(0, "", ""),
                CommandResult(
                    0,
                    "\n".join(
                        [
                            "/clock",
                            "/world/default/model/x500_mono_cam_0/link/camera_link/sensor/camera/image",
                        ]
                    ),
                    "",
                ),
                CommandResult(
                    0,
                    "xwininfo: Window id: 0x50d (the root window) (has no name)\n"
                    "  0 children.\n",
                    "",
                ),
            ]
        )
        runtime = DockerSimulatorRuntime(
            ROOT,
            image="drone-mcp/sim-visual:test",
            container_name="drone-mcp-test",
            dockerfile="docker/sim-visual.Dockerfile",
            headless=False,
            require_gui=True,
            ports=("5900:5900", "6080:6080"),
            runner=runner,
        )

        status = runtime.status()

        self.assertTrue(status.running)
        self.assertFalse(status.ready)
        self.assertTrue(status.camera_ready)
        self.assertFalse(status.gui_ready)
        self.assertEqual(status.gui_windows, ())
        self.assertEqual(status.gui_blockers, ())

    def test_status_detects_gui_window_and_popup_blocker(self) -> None:
        runner = StubRunner(
            [
                CommandResult(0, "[]", ""),
                CommandResult(0, "Up 12 seconds\n", ""),
                CommandResult(0, "", ""),
                CommandResult(
                    0,
                    "\n".join(
                        [
                            "/clock",
                            "/world/default/model/x500_mono_cam_0/link/camera_link/sensor/camera/image",
                        ]
                    ),
                    "",
                ),
                CommandResult(
                    0,
                    '\n'.join(
                        [
                            '0x1000012 "Gazebo Sim": ("gz-sim-gui" "Gazebo GUI")  1280x720+10+10  +10+10',
                            '0x40001d "xmessage": ("xmessage" "Xmessage")  300x100+50+50  +50+50',
                        ]
                    ),
                    "",
                ),
            ]
        )
        runtime = DockerSimulatorRuntime(
            ROOT,
            image="drone-mcp/sim-visual:test",
            container_name="drone-mcp-test",
            dockerfile="docker/sim-visual.Dockerfile",
            headless=False,
            require_gui=True,
            ports=("5900:5900", "6080:6080"),
            runner=runner,
        )

        status = runtime.status()

        self.assertFalse(status.ready)
        self.assertTrue(status.camera_ready)
        self.assertFalse(status.gui_ready)
        self.assertEqual(len(status.gui_windows), 1)
        self.assertEqual(len(status.gui_blockers), 1)

    def test_status_can_be_ready_without_camera_topics_when_camera_is_optional(self) -> None:
        runner = StubRunner(
            [
                CommandResult(0, "[]", ""),
                CommandResult(0, "Up 12 seconds\n", ""),
                CommandResult(0, "", ""),
                CommandResult(0, "", ""),
                CommandResult(
                    0,
                    '0x1000012 "Gazebo Sim": ("gz-sim-gui" "Gazebo GUI")  1280x720+10+10  +10+10',
                    "",
                ),
            ]
        )
        runtime = DockerSimulatorRuntime(
            ROOT,
            image="drone-mcp/sim-visual:test",
            container_name="drone-mcp-test",
            dockerfile="docker/sim-visual.Dockerfile",
            headless=False,
            require_gui=True,
            require_camera=False,
            ports=("5900:5900", "6080:6080"),
            runner=runner,
        )

        status = runtime.status()

        self.assertTrue(status.running)
        self.assertTrue(status.ready)
        self.assertFalse(status.camera_ready)
        self.assertTrue(status.gui_ready)

    def test_wait_until_ready_raises_on_plugin_error(self) -> None:
        runner = StubRunner(
            [
                CommandResult(0, "[]", ""),
                CommandResult(0, "Up 12 seconds\n", ""),
                CommandResult(0, "", ""),
                CommandResult(0, "", ""),
                CommandResult(0, "[]", ""),
                CommandResult(0, "Up 12 seconds\n", ""),
                CommandResult(
                    0,
                    "Failed to load system plugin: libGstCameraSystem.so",
                    "",
                ),
                CommandResult(0, "", ""),
            ]
        )
        runtime = self.make_runtime(runner)

        with self.assertRaises(SimulatorNotReadyError):
            runtime.wait_until_ready(timeout_s=1, poll_interval_s=0)

    def test_wait_until_ready_raises_on_gui_popup(self) -> None:
        runner = StubRunner(
            [
                CommandResult(0, "[]", ""),
                CommandResult(0, "Up 12 seconds\n", ""),
                CommandResult(0, "", ""),
                CommandResult(
                    0,
                    "/world/default/model/x500_mono_cam_0/link/camera_link/sensor/camera/image",
                    "",
                ),
                CommandResult(
                    0,
                    '\n'.join(
                        [
                            '0x1000012 "Gazebo Sim": ("gz-sim-gui" "Gazebo GUI")  1280x720+10+10  +10+10',
                            '0x40001d "xmessage": ("xmessage" "Xmessage")  300x100+50+50  +50+50',
                        ]
                    ),
                    "",
                ),
                CommandResult(0, "[]", ""),
                CommandResult(0, "Up 12 seconds\n", ""),
                CommandResult(0, "", ""),
                CommandResult(
                    0,
                    "/world/default/model/x500_mono_cam_0/link/camera_link/sensor/camera/image",
                    "",
                ),
                CommandResult(
                    0,
                    '\n'.join(
                        [
                            '0x1000012 "Gazebo Sim": ("gz-sim-gui" "Gazebo GUI")  1280x720+10+10  +10+10',
                            '0x40001d "xmessage": ("xmessage" "Xmessage")  300x100+50+50  +50+50',
                        ]
                    ),
                    "",
                ),
            ]
        )
        runtime = DockerSimulatorRuntime(
            ROOT,
            image="drone-mcp/sim-visual:test",
            container_name="drone-mcp-test",
            dockerfile="docker/sim-visual.Dockerfile",
            headless=False,
            require_gui=True,
            ports=("5900:5900", "6080:6080"),
            runner=runner,
        )

        with self.assertRaises(SimulatorNotReadyError):
            runtime.wait_until_ready(timeout_s=1, poll_interval_s=0)

    def test_ensure_image_builds_when_missing(self) -> None:
        runner = StubRunner(
            [
                CommandResult(1, "", "Error: No such image"),
                CommandResult(0, "", ""),
            ]
        )
        runtime = self.make_runtime(runner)

        runtime.ensure_image()

        self.assertEqual(
            runner.calls,
            [
                ["docker", "image", "inspect", "drone-mcp/sim-monocam:test"],
                [
                    "docker",
                    "build",
                    "-f",
                    str(ROOT / "docker" / "sim-monocam.Dockerfile"),
                    "-t",
                    "drone-mcp/sim-monocam:test",
                    str(ROOT),
                ],
            ],
        )

    def test_reset_reuses_start_logic(self) -> None:
        runner = StubRunner(
            [
                CommandResult(0, "", ""),
                CommandResult(0, "abc123", ""),
            ]
        )
        runtime = self.make_runtime(runner)

        runtime.reset()

        self.assertEqual(runner.calls, [
            ["docker", "rm", "-f", "drone-mcp-test"],
            [
                "docker",
                "run",
                "-d",
                "--rm",
                "--name",
                "drone-mcp-test",
                "-e",
                "PX4_SIM_MODEL=gz_x500_mono_cam",
                "-e",
                "HEADLESS=1",
                "-p",
                "14540:14540/udp",
                "-p",
                "14550:14550/udp",
                "-p",
                "8888:8888/udp",
                "drone-mcp/sim-monocam:test",
            ],
        ])

    def test_start_with_network_host_skips_port_mapping(self) -> None:
        runner = StubRunner(
            [
                CommandResult(0, "", ""),
                CommandResult(0, "abc123", ""),
            ]
        )
        runtime = DockerSimulatorRuntime(
            ROOT,
            image="drone-mcp/sim-visual:test",
            container_name="drone-mcp-test",
            dockerfile="docker/sim-visual.Dockerfile",
            headless=False,
            network_host=True,
            ports=("5900:5900", "6080:6080"),
            runner=runner,
        )

        runtime.start()

        start_cmd = runner.calls[1]
        self.assertIn("--network", start_cmd)
        self.assertIn("host", start_cmd)
        self.assertIn("--gpus", start_cmd)
        self.assertNotIn("-p", start_cmd)


if __name__ == "__main__":
    unittest.main()
