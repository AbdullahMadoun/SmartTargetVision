from __future__ import annotations

import sys
import subprocess
import socket
import time
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from drone_mcp.sim_runtime import DockerSimulatorRuntime, SimulatorNotReadyError
from drone_mcp.visual_checks import (
    analyze_xwd_visual_signal,
    build_viewport_probe_regions,
    extract_window_geometries,
    probe_rfb_banner,
    probe_websocket_upgrade,
)


def reserve_local_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        probe.listen(1)
        return int(probe.getsockname()[1])


def stream_command(*args: str, timeout: int = 600) -> None:
    completed = subprocess.run(
        args,
        cwd=ROOT,
        timeout=timeout,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(args)}")


def main() -> int:
    vnc_port = reserve_local_port()
    web_port = reserve_local_port()
    runtime = DockerSimulatorRuntime(
        ROOT,
        image="drone-mcp/sim-visual:smoke",
        container_name="drone-mcp-sim-visual-smoke",
        dockerfile="docker/sim-visual.Dockerfile",
        headless=False,
        require_gui=True,
        require_camera=False,
        ports=(
            f"{vnc_port}:5900",
            f"{web_port}:6080",
        ),
    )
    try:
        print("[1/7] Building visual simulator image...")
        stream_command(
            "docker",
            "build",
            "--progress=plain",
            "-f",
            str(ROOT / runtime.dockerfile),
            "-t",
            runtime.image,
            str(ROOT),
            timeout=1800,
        )
        print("[2/7] Starting visual simulator container...")
        runtime.start()
        print("[3/7] Waiting for simulator readiness...")
        runtime.wait_until_ready(timeout_s=180)
        print("[4/7] Verifying noVNC HTTP surface...")
        deadline = time.time() + 120
        body = ""
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{web_port}/vnc.html", timeout=10) as response:
                    body = response.read().decode("utf-8", errors="replace")
                if "noVNC" in body or "vnc" in body.lower():
                    break
            except Exception:
                time.sleep(2)
                continue
            time.sleep(2)
        if "vnc" not in body.lower():
            raise RuntimeError("noVNC page did not become reachable.")
        print("[5/7] Verifying VNC transport surfaces...")
        deadline = time.time() + 120
        while time.time() < deadline:
            try:
                probe_rfb_banner("127.0.0.1", vnc_port)
                break
            except Exception:
                time.sleep(2)
        else:
            raise RuntimeError("VNC banner did not become reachable.")

        deadline = time.time() + 120
        while time.time() < deadline:
            try:
                probe_websocket_upgrade("127.0.0.1", web_port, "/websockify")
                break
            except Exception:
                time.sleep(2)
        else:
            raise RuntimeError("WebSocket upgrade did not become reachable.")
        print("[6/7] Inspecting Gazebo GUI windows...")
        window_tree = subprocess.run(
            [
                "docker",
                "exec",
                runtime.container_name,
                "sh",
                "-lc",
                "DISPLAY=:0 xwininfo -root -tree",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        combined_tree = f"{window_tree.stdout}\n{window_tree.stderr}"
        gazebo_windows = extract_window_geometries(combined_tree, ("Gazebo Sim", "Gazebo GUI"))
        if not gazebo_windows:
            raise RuntimeError("Gazebo GUI window did not appear on the X display.")
        if "\"xmessage\"" in combined_tree or "xmessage" in combined_tree:
            raise RuntimeError("An xmessage popup is still present on the X display.")
        largest_window = max(gazebo_windows, key=lambda window: window.area)
        if largest_window.width < 200 or largest_window.height < 150:
            raise RuntimeError(
                "Gazebo GUI window appeared with an implausibly small geometry: "
                f"{largest_window.width}x{largest_window.height}"
            )
        viewport_regions = build_viewport_probe_regions(largest_window)
        print("[7/7] Verifying the rendered frame is not blank...")
        xwd_target = f"-id {largest_window.window_id}" if largest_window.window_id else "-root"
        frame_capture = subprocess.run(
            [
                "docker",
                "exec",
                runtime.container_name,
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
            raise RuntimeError(
                "Failed to capture the X display for visual verification:\n"
                + frame_capture.stderr.decode("utf-8", errors="replace")
            )
        signal_reports = [
            analyze_xwd_visual_signal(frame_capture.stdout, region=region)
            for region in viewport_regions
        ]
        if not all(report.looks_rendered for report in signal_reports):
            details = "; ".join(report.describe() for report in signal_reports)
            raise RuntimeError(
                "Gazebo viewport center looks blank or flat: "
                f"{details}"
            )
        print("Visual simulator smoke test passed.")
        return 0
    except (SimulatorNotReadyError, RuntimeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    finally:
        runtime.stop()


if __name__ == "__main__":
    raise SystemExit(main())
