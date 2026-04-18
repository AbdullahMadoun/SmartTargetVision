from __future__ import annotations

import shlex
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .camera_capture import CameraFrameCapture, parse_gz_topic_camera_frame


PLUGIN_ERROR_MARKERS = (
    "Error while loading the library",
    "Failed to load system plugin",
)

CAMERA_TOPIC_FRAGMENT = "/sensor/camera/"
GUI_WINDOW_MARKERS = (
    "Gazebo Sim",
    "Gazebo GUI",
)
GUI_BLOCKING_WINDOW_MARKERS = (
    "\"xmessage\"",
    "xmessage",
)


@dataclass(slots=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


class RuntimeCommandError(RuntimeError):
    """Raised when a runtime shell command fails."""


class SimulatorNotReadyError(RuntimeError):
    """Raised when the simulator does not become ready in time."""


@dataclass(frozen=True, slots=True)
class RuntimeStatus:
    image: str
    container_name: str
    image_present: bool
    running: bool
    ready: bool
    camera_ready: bool
    gui_ready: bool
    status_text: str
    camera_topics: tuple[str, ...]
    plugin_errors: tuple[str, ...]
    gui_windows: tuple[str, ...]
    gui_blockers: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "image": self.image,
            "container_name": self.container_name,
            "image_present": self.image_present,
            "running": self.running,
            "ready": self.ready,
            "camera_ready": self.camera_ready,
            "gui_ready": self.gui_ready,
            "status_text": self.status_text,
            "camera_topics": list(self.camera_topics),
            "plugin_errors": list(self.plugin_errors),
            "gui_windows": list(self.gui_windows),
            "gui_blockers": list(self.gui_blockers),
        }


class CommandRunner(Protocol):
    def run(self, args: list[str], *, timeout: int = 600, check: bool = True) -> CommandResult:
        """Run a subprocess command and return a normalized result."""


class SubprocessRunner:
    def __init__(self, cwd: Path) -> None:
        self.cwd = cwd

    def run(self, args: list[str], *, timeout: int = 600, check: bool = True) -> CommandResult:
        completed = subprocess.run(
            args,
            cwd=self.cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        result = CommandResult(
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )
        if check and completed.returncode != 0:
            raise RuntimeCommandError(
                f"Command failed: {' '.join(args)}\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
            )
        return result


class DockerSimulatorRuntime:
    def __init__(
        self,
        repo_root: Path,
        *,
        image: str = "drone-mcp/sim-monocam:local",
        container_name: str = "drone-mcp-sim-monocam",
        dockerfile: str = "docker/sim-monocam.Dockerfile",
        model: str = "gz_x500_mono_cam",
        headless: bool = True,
        require_gui: bool = False,
        require_camera: bool = True,
        network_host: bool = False,
        ports: tuple[str, ...] | None = None,
        environment: dict[str, str] | None = None,
        runner: CommandRunner | None = None,
    ) -> None:
        self.repo_root = repo_root
        self.image = image
        self.container_name = container_name
        self.dockerfile = dockerfile
        self.model = model
        self.headless = headless
        self.require_gui = require_gui
        self.require_camera = require_camera
        self.network_host = network_host
        self.ports = ports or (
            "14540:14540/udp",
            "14550:14550/udp",
            "8888:8888/udp",
        )
        self.environment = {
            str(key): str(value)
            for key, value in (environment or {}).items()
            if str(key).strip()
        }
        self.runner = runner or SubprocessRunner(repo_root)

    def build_image(self) -> None:
        self.runner.run(
            [
                "docker",
                "build",
                "-f",
                str(self.repo_root / self.dockerfile),
                "-t",
                self.image,
                str(self.repo_root),
            ],
            timeout=1800,
        )

    def image_exists(self) -> bool:
        result = self.runner.run(
            ["docker", "image", "inspect", self.image],
            check=False,
            timeout=30,
        )
        return result.returncode == 0

    def ensure_image(self, force_rebuild: bool = False) -> None:
        if force_rebuild or not self.image_exists():
            self.build_image()

    def start(self) -> None:
        self.stop()
        command = [
            "docker",
            "run",
            "-d",
            "--rm",
        ]
        if not self.headless:
            command.extend(["--gpus", "all"])
        if self.network_host:
            command.extend(["--network", "host"])
        command.extend([
            "--name",
            self.container_name,
            "-e",
            f"PX4_SIM_MODEL={self.model}",
            "-e",
            f"HEADLESS={1 if self.headless else 0}",
        ])
        for key in sorted(self.environment):
            command.extend(["-e", f"{key}={self.environment[key]}"])
        if not self.network_host:
            for port in self.ports:
                command.extend(["-p", port])
        command.append(self.image)
        self.runner.run(command, timeout=60)

    def stop(self) -> None:
        self.runner.run(
            ["docker", "rm", "-f", self.container_name],
            check=False,
            timeout=30,
        )

    def reset(self) -> None:
        self.start()

    def logs_tail(self, lines: int = 200) -> str:
        result = self.runner.run(
            ["docker", "logs", "--tail", str(lines), self.container_name],
            check=False,
            timeout=30,
        )
        return result.stdout + result.stderr

    def capture_camera_frame(self, topic: str, timeout_s: int = 30) -> CameraFrameCapture:
        """Capture a single camera frame from the running simulator container."""
        if not topic.strip():
            raise ValueError("Camera topic is required.")

        shell_script = f"timeout {max(1, timeout_s)}s gz topic -e -n 1 -t {shlex.quote(topic)}"
        command = [
            "docker",
            "exec",
            self.container_name,
            "sh",
            "-lc",
            shell_script,
        ]
        result = self.runner.run(command, timeout=max(30, timeout_s + 15))
        message_text = result.stdout + ("\n" + result.stderr if result.stderr else "")
        return parse_gz_topic_camera_frame(
            message_text,
            topic=topic,
            container_name=self.container_name,
            command=command,
        )

    def status(self) -> RuntimeStatus:
        image_present = self.image_exists()
        inspect = self.runner.run(
            [
                "docker",
                "ps",
                "-a",
                "--filter",
                f"name={self.container_name}",
                "--format",
                "{{.Status}}",
            ],
            check=False,
            timeout=30,
        )
        status_text = inspect.stdout.strip()
        running = status_text.startswith("Up")
        logs = self.logs_tail()
        plugin_errors = tuple(
            line.strip()
            for line in logs.splitlines()
            if any(marker in line for marker in PLUGIN_ERROR_MARKERS)
        )
        camera_topics = ()
        gui_windows = ()
        gui_blockers = ()
        camera_ready = False
        gui_ready = not self.require_gui
        if running:
            topics_result = self.runner.run(
                [
                    "docker",
                    "exec",
                    self.container_name,
                    "sh",
                    "-lc",
                    "gz topic -l",
                ],
                check=False,
                timeout=60,
            )
            camera_topics = tuple(
                line.strip()
                for line in topics_result.stdout.splitlines()
                if CAMERA_TOPIC_FRAGMENT in line
            )
            camera_ready = bool(camera_topics)
            if self.require_gui:
                window_tree_result = self.runner.run(
                    [
                        "docker",
                        "exec",
                        self.container_name,
                        "sh",
                        "-lc",
                        "DISPLAY=:0 xwininfo -root -tree",
                    ],
                    check=False,
                    timeout=60,
                )
                window_lines = tuple(
                    line.strip()
                    for line in (window_tree_result.stdout + "\n" + window_tree_result.stderr).splitlines()
                    if line.strip()
                )
                gui_windows = tuple(
                    line for line in window_lines if any(marker in line for marker in GUI_WINDOW_MARKERS)
                )
                gui_blockers = tuple(
                    line for line in window_lines if any(marker in line for marker in GUI_BLOCKING_WINDOW_MARKERS)
                )
                gui_ready = window_tree_result.returncode == 0 and bool(gui_windows) and not gui_blockers
        ready = running and not plugin_errors and gui_ready and (camera_ready or not self.require_camera)
        return RuntimeStatus(
            image=self.image,
            container_name=self.container_name,
            image_present=image_present,
            running=running,
            ready=ready,
            camera_ready=camera_ready,
            gui_ready=gui_ready,
            status_text=status_text,
            camera_topics=camera_topics,
            plugin_errors=plugin_errors,
            gui_windows=gui_windows,
            gui_blockers=gui_blockers,
        )

    def wait_until_ready(self, timeout_s: int = 120, poll_interval_s: float = 3.0) -> RuntimeStatus:
        deadline = time.time() + timeout_s
        last_status = self.status()
        while time.time() < deadline:
            last_status = self.status()
            if last_status.plugin_errors:
                raise SimulatorNotReadyError(
                    "Simulator reported plugin load errors:\n"
                    + "\n".join(last_status.plugin_errors)
                )
            if last_status.gui_blockers:
                raise SimulatorNotReadyError(
                    "Simulator desktop has a blocking popup:\n"
                    + "\n".join(last_status.gui_blockers)
                )
            if last_status.ready:
                return last_status
            time.sleep(poll_interval_s)
        raise SimulatorNotReadyError(
            "Timed out waiting for a ready simulator.\n"
            f"Last status: {last_status.to_dict()}"
        )
