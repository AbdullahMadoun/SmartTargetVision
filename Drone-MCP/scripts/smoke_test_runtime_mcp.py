from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
IMAGE = "drone-mcp/runtime-mcp:smoke"
SIM_CONTAINER = "drone-mcp-mcp-smoke-sim"


class McpSmokeError(RuntimeError):
    """Raised when the runtime MCP smoke test fails."""


def run(*args: str, check: bool = True, timeout: int = 600) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        args,
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if check and completed.returncode != 0:
        raise McpSmokeError(
            f"Command failed: {' '.join(args)}\nSTDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}"
        )
    return completed


def build_image() -> None:
    run(
        "docker",
        "build",
        "-f",
        str(ROOT / "docker" / "mcp-server.Dockerfile"),
        "-t",
        IMAGE,
        str(ROOT),
        timeout=1800,
    )


def cleanup() -> None:
    run("docker", "rm", "-f", SIM_CONTAINER, check=False, timeout=30)


def send_message(process: subprocess.Popen[str], payload: dict[str, object]) -> None:
    process.stdin.write(json.dumps(payload) + "\n")
    process.stdin.flush()


def read_response(process: subprocess.Popen[str], expected_id: int, timeout_s: int = 180) -> dict[str, object]:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        line = process.stdout.readline()
        if not line:
            stderr = process.stderr.read()
            raise McpSmokeError(f"Server closed unexpectedly.\nSTDERR:\n{stderr}")
        message = json.loads(line)
        if message.get("id") == expected_id:
            return message
    raise McpSmokeError(f"Timed out waiting for response id={expected_id}.")


def call_tool(process: subprocess.Popen[str], request_id: int, name: str, arguments: dict[str, str]) -> str:
    send_message(
        process,
        {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "tools/call",
            "params": {
                "name": name,
                "arguments": arguments,
            },
        },
    )
    response = read_response(process, request_id, timeout_s=600)
    result = response.get("result", {})
    content = result.get("content", [])
    if result.get("isError"):
        raise McpSmokeError(f"Tool {name} failed: {content}")
    if not content:
        raise McpSmokeError(f"Tool {name} returned no content.")
    return content[0]["text"]


def main() -> int:
    cleanup()
    process: subprocess.Popen[str] | None = None
    try:
        print("[1/5] Building MCP server image...")
        build_image()
        print("[2/5] Starting MCP server over stdio...")
        process = subprocess.Popen(
            [
                "docker",
                "run",
                "--rm",
                "-i",
                "-v",
                "/var/run/docker.sock:/var/run/docker.sock",
                "-e",
                f"DRONE_MCP_SIM_CONTAINER={SIM_CONTAINER}",
                "-e",
                "DRONE_MCP_SIM_IMAGE=drone-mcp/sim-monocam:mcp-smoke",
                IMAGE,
            ],
            cwd=ROOT,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        print("[3/5] Initializing MCP session...")
        send_message(
            process,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-03-26",
                    "capabilities": {},
                    "clientInfo": {
                        "name": "drone-mcp-smoke-client",
                        "version": "0.1.0",
                    },
                },
            },
        )
        initialize_response = read_response(process, 1)
        protocol_version = initialize_response["result"]["protocolVersion"]
        send_message(
            process,
            {
                "jsonrpc": "2.0",
                "method": "notifications/initialized",
            },
        )

        print("[4/5] Listing tools and exercising runtime controls...")
        send_message(process, {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        tools_response = read_response(process, 2)
        tool_names = [tool["name"] for tool in tools_response["result"]["tools"]]
        expected = {
            "start_simulation",
            "stop_simulation",
            "reset_simulation",
            "get_runtime_health",
            "get_simulation_logs",
        }
        if set(tool_names) != expected:
            raise McpSmokeError(f"Unexpected tool set: {tool_names}")

        start_text = call_tool(process, 3, "start_simulation", {"timeout": "180"})
        if "✅ Simulation started and is ready." not in start_text:
            raise McpSmokeError(f"Unexpected start response:\n{start_text}")

        health_text = call_tool(process, 4, "get_runtime_health", {})
        if "Ready: yes" not in health_text:
            raise McpSmokeError(f"Unexpected health response:\n{health_text}")

        logs_text = call_tool(process, 5, "get_simulation_logs", {"lines": "20"})
        if "Simulation logs" not in logs_text:
            raise McpSmokeError(f"Unexpected logs response:\n{logs_text}")

        stop_text = call_tool(process, 6, "stop_simulation", {})
        if "Simulation stop command completed." not in stop_text:
            raise McpSmokeError(f"Unexpected stop response:\n{stop_text}")

        print("[5/5] MCP runtime smoke test passed.")
        print(f"Negotiated protocol version: {protocol_version}")
        return 0
    except McpSmokeError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    finally:
        cleanup()
        if process is not None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()


if __name__ == "__main__":
    raise SystemExit(main())
