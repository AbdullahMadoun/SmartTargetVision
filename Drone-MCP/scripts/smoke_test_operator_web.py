from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from drone_mcp.visual_checks import (
    analyze_xwd_visual_signal,
    build_viewport_probe_regions,
    extract_window_geometries,
    probe_rfb_banner,
    probe_websocket_upgrade,
)

OPERATOR_IMAGE = "drone-mcp/operator-web:smoke"
OPERATOR_CONTAINER = "drone-mcp-operator-web-smoke"
SIM_CONTAINER = "drone-mcp-sim-visual-web-smoke"


class SmokeError(RuntimeError):
    """Raised when the operator web smoke test fails."""


def run(*args: str, check: bool = True, timeout: int = 600) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        args,
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if check and completed.returncode != 0:
        raise SmokeError(
            f"Command failed: {' '.join(args)}\nSTDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}"
        )
    return completed


def stream_command(*args: str, timeout: int = 600) -> None:
    completed = subprocess.run(
        args,
        cwd=ROOT,
        timeout=timeout,
        check=False,
    )
    if completed.returncode != 0:
        raise SmokeError(f"Command failed: {' '.join(args)}")


def reserve_local_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        probe.listen(1)
        return int(probe.getsockname()[1])


def cleanup() -> None:
    run("docker", "rm", "-f", OPERATOR_CONTAINER, check=False, timeout=30)
    run("docker", "rm", "-f", SIM_CONTAINER, check=False, timeout=30)


def http_json(url: str, payload: dict[str, object] | None = None) -> dict[str, object]:
    if payload is None:
        request = urllib.request.Request(url)
    else:
        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
    with urllib.request.urlopen(request, timeout=300) as response:
        return json.loads(response.read().decode("utf-8"))


def http_text(url: str) -> str:
    with urllib.request.urlopen(url, timeout=60) as response:
        return response.read().decode("utf-8", errors="replace")


def main() -> int:
    cleanup()
    operator_port = reserve_local_port()
    operator_base_url = f"http://127.0.0.1:{operator_port}"
    try:
        print("[1/8] Building operator web image...")
        stream_command(
            "docker",
            "build",
            "--progress=plain",
            "-f",
            str(ROOT / "docker" / "operator-web.Dockerfile"),
            "-t",
            OPERATOR_IMAGE,
            str(ROOT),
            timeout=1800,
        )
        print("[2/8] Starting operator web container...")
        run(
            "docker",
            "run",
            "-d",
            "--rm",
            "--name",
            OPERATOR_CONTAINER,
            "-v",
            "/var/run/docker.sock:/var/run/docker.sock",
            "-p",
            f"{operator_port}:8080",
            "-e",
            "DRONE_MCP_SIM_IMAGE=drone-mcp/sim-visual:web-smoke",
            "-e",
            f"DRONE_MCP_SIM_CONTAINER={SIM_CONTAINER}",
            "-e",
            "DRONE_MCP_SIM_DOCKERFILE=docker/sim-visual.Dockerfile",
            "-e",
            "DRONE_MCP_SIM_HEADLESS=0",
            "-e",
            "DRONE_MCP_SIM_REQUIRE_GUI=1",
            "-e",
            "DRONE_MCP_SIM_REQUIRE_CAMERA=0",
            "-e",
            "DRONE_MCP_SIM_PORTS=5900:5900,6080:6080",
            *(
                ["-e", f"DOCKER_API_VERSION={os.environ['DOCKER_API_VERSION']}"]
                if os.environ.get("DOCKER_API_VERSION")
                else []
            ),
            OPERATOR_IMAGE,
            timeout=120,
        )

        print("[3/8] Waiting for operator web health...")
        deadline = time.time() + 120
        while time.time() < deadline:
            try:
                health = http_json(f"{operator_base_url}/health")
                if health.get("ok"):
                    break
            except Exception:
                time.sleep(2)
                continue
            time.sleep(2)
        else:
            raise SmokeError("Operator web service did not become healthy.")

        print("[4/8] Starting and checking the visual simulator through the web API...")
        start_result = http_json(
            f"{operator_base_url}/api/tool",
            {"name": "start_simulation", "arguments": {"timeout": "180"}},
        )
        if "Simulation started and is ready" not in start_result["text"]:
            raise SmokeError(f"Unexpected start result:\n{start_result['text']}")

        health_result = http_json(f"{operator_base_url}/api/runtime-health")
        if "Ready: yes" not in health_result["text"]:
            raise SmokeError(f"Unexpected runtime health:\n{health_result['text']}")
        if "GUI Ready: yes" not in health_result["text"]:
            raise SmokeError(f"Unexpected GUI readiness:\n{health_result['text']}")

        print("[5/8] Verifying visual transport surfaces...")
        novnc_text = http_text("http://127.0.0.1:6080/vnc.html")
        if "noVNC" not in novnc_text and "vnc" not in novnc_text.lower():
            raise SmokeError("noVNC page did not become reachable from the operator smoke test.")
        deadline = time.time() + 120
        while time.time() < deadline:
            try:
                probe_rfb_banner("127.0.0.1", 5900)
                break
            except Exception:
                time.sleep(2)
        else:
            raise SmokeError("VNC banner did not become reachable during the operator smoke test.")

        deadline = time.time() + 120
        while time.time() < deadline:
            try:
                probe_websocket_upgrade("127.0.0.1", 6080, "/websockify")
                break
            except Exception:
                time.sleep(2)
        else:
            raise SmokeError("WebSocket upgrade did not become reachable during the operator smoke test.")

        print("[6/8] Inspecting Gazebo GUI windows...")
        window_tree = run(
            "docker",
            "exec",
            SIM_CONTAINER,
            "sh",
            "-lc",
            "DISPLAY=:0 xwininfo -root -tree",
            timeout=60,
        )
        gazebo_windows = extract_window_geometries(window_tree.stdout, ("Gazebo Sim", "Gazebo GUI"))
        if not gazebo_windows:
            raise SmokeError("Gazebo GUI window did not appear during the operator smoke test.")
        if "\"xmessage\"" in window_tree.stdout or "xmessage" in window_tree.stdout:
            raise SmokeError("An xmessage popup is still present during the operator smoke test.")
        largest_window = max(gazebo_windows, key=lambda window: window.area)
        if largest_window.width < 200 or largest_window.height < 150:
            raise SmokeError(
                "Gazebo GUI window appeared with an implausibly small geometry during the operator smoke test: "
                f"{largest_window.width}x{largest_window.height}"
            )
        viewport_regions = build_viewport_probe_regions(largest_window)

        print("[7/8] Verifying the rendered frame is not blank...")
        xwd_target = f"-id {largest_window.window_id}" if largest_window.window_id else "-root"
        frame_capture = subprocess.run(
            [
                "docker",
                "exec",
                SIM_CONTAINER,
                "sh",
                "-lc",
                f"DISPLAY=:0 xwd -silent {xwd_target}",
            ],
            cwd=ROOT,
            capture_output=True,
            timeout=60,
            check=False,
        )
        if frame_capture.returncode != 0:
            raise SmokeError(
                "Failed to capture the X display during the operator smoke test:\n"
                + frame_capture.stderr.decode("utf-8", errors="replace")
            )
        signal_reports = [
            analyze_xwd_visual_signal(frame_capture.stdout, region=region)
            for region in viewport_regions
        ]
        if not all(report.looks_rendered for report in signal_reports):
            details = "; ".join(report.describe() for report in signal_reports)
            raise SmokeError(
                "Gazebo viewport center looks blank or flat during the operator smoke test: "
                f"{details}"
            )

        print("[8/8] Stopping the visual simulator through the web API...")
        stop_result = http_json(
            f"{operator_base_url}/api/tool",
            {"name": "stop_simulation", "arguments": {}},
        )
        if "Simulation stop command completed" not in stop_result["text"]:
            raise SmokeError(f"Unexpected stop result:\n{stop_result['text']}")

        print("Operator web smoke test passed.")
        return 0
    except SmokeError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    finally:
        cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
