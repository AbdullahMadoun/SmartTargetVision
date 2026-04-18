#!/usr/bin/env python3

"""HTTP operator surface for remote visual simulation and chat control."""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from openai import OpenAI
from pydantic import BaseModel
import uvicorn


ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
UI = ROOT / "ui"

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from drone_mcp.operator_chat import LlmResponse, OperatorChatEngine, ToolCall
from drone_mcp.flight_control import DEFAULT_DRONE_ID
from drone_mcp.runtime_tool_service import RuntimeCommandError, RuntimeToolService


def _read_openrouter_key() -> str:
    return (
        os.environ.get("OPENROUTER_KEY", "").strip()
        or os.environ.get("OpenRouter_Key", "").strip()
        or os.environ.get("OPENROUTER_API_KEY", "").strip()
    )


def _read_openrouter_model() -> str:
    return os.environ.get("OPENROUTER_MODEL", "openai/gpt-4o-mini").strip()


class ChatRequest(BaseModel):
    message: str
    history: list[dict[str, str]] = []


class ToolRequest(BaseModel):
    name: str
    arguments: dict[str, object] = {}


class GeofenceRequest(BaseModel):
    max_altitude: float | None = None
    max_distance: float | None = None
    min_battery: float | None = None


class OpenRouterClient:
    def __init__(self, api_key: str, model: str) -> None:
        self.client = OpenAI(
            api_key=api_key,
            base_url="https://openrouter.ai/api/v1",
        )
        self.model = model

    def complete(
        self,
        *,
        messages: list[dict[str, object]],
        tools: list[dict[str, object]],
    ) -> LlmResponse:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            tools=tools,
            tool_choice="auto",
        )
        message = response.choices[0].message
        tool_calls = tuple(
            ToolCall(
                id=tool_call.id,
                name=tool_call.function.name,
                arguments=tool_call.function.arguments or "{}",
            )
            for tool_call in (message.tool_calls or [])
        )
        return LlmResponse(
            content=message.content or "",
            tool_calls=tool_calls,
        )


def _normalize_tool_arguments(arguments: dict[str, object]) -> dict[str, str]:
    normalized: dict[str, str] = {}
    for key, value in arguments.items():
        if value is None:
            normalized[str(key)] = ""
        elif isinstance(value, (dict, list)):
            normalized[str(key)] = json.dumps(value, ensure_ascii=True)
        else:
            normalized[str(key)] = str(value)
    return normalized


def _connection_quality(latency_ms: float | None, connected: bool) -> str:
    if not connected:
        return "offline"
    if latency_ms is None:
        return "unknown"
    if latency_ms < 200:
        return "excellent"
    if latency_ms < 500:
        return "good"
    if latency_ms < 1000:
        return "fair"
    return "poor"


def _primary_drone_entry() -> dict[str, object]:
    drones = tool_service.list_drones_data()
    if drones:
        primary = drones[0]
        if isinstance(primary, dict) and primary.get("drone_id"):
            return primary
    return {"drone_id": DEFAULT_DRONE_ID}


def _simulation_ports() -> list[str]:
    raw_ports = os.environ.get("DRONE_MCP_SIM_PORTS", "").strip()
    if raw_ports:
        return [part.strip() for part in raw_ports.split(",") if part.strip()]
    try:
        instance_count = int(os.environ.get("DRONE_MCP_SIM_INSTANCE_COUNT", "1").strip() or "1")
    except ValueError:
        instance_count = 1
    instance_count = max(instance_count, 1)
    ports = [f"{14540 + offset}:{14540 + offset}/udp" for offset in range(instance_count)]
    ports.extend(["14550:14550/udp", "8888:8888/udp"])
    return ports


def _simulation_template_catalog() -> list[dict[str, object]]:
    visual_image = os.environ.get("DRONE_MCP_SIM_VISUAL_IMAGE", "drone-mcp/sim-visual:local").strip()
    visual_dockerfile = os.environ.get("DRONE_MCP_SIM_VISUAL_DOCKERFILE", "docker/sim-visual.Dockerfile").strip()
    defaults = {
        "image": os.environ.get("DRONE_MCP_SIM_IMAGE", "drone-mcp/sim-monocam:local").strip(),
        "container_name": os.environ.get("DRONE_MCP_SIM_CONTAINER", "drone-mcp-sim-monocam").strip(),
        "dockerfile": os.environ.get("DRONE_MCP_SIM_DOCKERFILE", "docker/sim-monocam.Dockerfile").strip(),
        "model": os.environ.get("DRONE_MCP_SIM_MODEL", "gz_x500_mono_cam").strip(),
        "camera_topic": os.environ.get("DRONE_MCP_CAMERA_TOPIC", "").strip(),
        "headless": os.environ.get("DRONE_MCP_SIM_HEADLESS", "1").strip().lower() not in {"0", "false", "no", "off"},
        "require_gui": os.environ.get("DRONE_MCP_SIM_REQUIRE_GUI", "").strip().lower() in {"1", "true", "yes", "on"},
        "require_camera": os.environ.get("DRONE_MCP_SIM_REQUIRE_CAMERA", "1").strip().lower()
        not in {"0", "false", "no", "off"},
        "network_host": os.environ.get("DRONE_MCP_SIM_NETWORK_HOST", "").strip().lower() in {"1", "true", "yes", "on"},
        "ports": _simulation_ports(),
        "environment": {},
    }
    if not defaults["ports"]:
        defaults["ports"] = ["14540:14540/udp", "14550:14550/udp", "8888:8888/udp"]
    visual_environment = {
        "DRONE_MCP_REQUIRED_MODEL": "x500_mono_cam_0",
        "DRONE_MCP_MODEL_WAIT_SECONDS": "180",
        "VNC_GEOMETRY": "1920x1080",
    }
    return [
        {
            "template_id": "default",
            "name": "Balanced Single-Drone",
            "description": "Server-friendly default preset with one active drone and the current simulator image.",
            "recommended": True,
            "tags": ["single-drone", "general-purpose"],
            "launch_notes": "Good default for everyday operator work with telemetry, camera capture, and map missions.",
            "mission_defaults": {"altitude": 10.0, "yaw": 0.0},
            "default_geofence": {
                "max_altitude_m": 120.0,
                "max_distance_from_home_m": 500.0,
                "min_battery_percent_for_rtl": 20.0,
            },
            **defaults,
        },
        {
            "template_id": "fast",
            "name": "Fast Headless",
            "description": "Lower-overhead preset for rapid iteration and server-side execution.",
            "recommended": False,
            "tags": ["single-drone", "headless", "fast"],
            "launch_notes": "Drops camera and GUI pressure so reset cycles stay quick on remote servers.",
            "mission_defaults": {"altitude": 8.0, "yaw": 0.0},
            "default_geofence": {
                "max_altitude_m": 80.0,
                "max_distance_from_home_m": 250.0,
                "min_battery_percent_for_rtl": 25.0,
            },
            **{
                **defaults,
                "headless": True,
                "require_gui": False,
                "require_camera": False,
                "network_host": False,
            },
        },
        {
            "template_id": "visual",
            "name": "Visual Debug",
            "description": "Keeps the GUI and camera path enabled for inspection-heavy workflows.",
            "recommended": False,
            "tags": ["single-drone", "gui", "camera"],
            "launch_notes": "Uses the visual image and waits longer for the GUI model path so inspection sessions are stable.",
            "mission_defaults": {"altitude": 10.0, "yaw": 0.0},
            "default_geofence": {
                "max_altitude_m": 120.0,
                "max_distance_from_home_m": 400.0,
                "min_battery_percent_for_rtl": 20.0,
            },
            **{
                **defaults,
                "image": visual_image,
                "dockerfile": visual_dockerfile,
                "headless": False,
                "require_gui": True,
                "require_camera": True,
                "network_host": True,
                "environment": visual_environment,
            },
        },
        {
            "template_id": "vision-follow",
            "name": "Visual Follow",
            "description": "Camera-first preset for target-follow tests with conservative autonomy defaults.",
            "recommended": False,
            "tags": ["tracking", "camera", "autonomy"],
            "launch_notes": "Best starting point for person-follow and perception-assisted control loops.",
            "mission_defaults": {"altitude": 12.0, "yaw": 0.0},
            "default_geofence": {
                "max_altitude_m": 60.0,
                "max_distance_from_home_m": 250.0,
                "min_battery_percent_for_rtl": 30.0,
            },
            "tracking_defaults": {
                "target_class": "person",
                "confidence_threshold": 0.4,
                "loop_interval_s": 0.35,
                "max_forward_speed_m_s": 1.2,
                "max_right_speed_m_s": 0.8,
                "scan_yaw_rate_deg_s": 20.0,
            },
            **{
                **defaults,
                "container_name": f"{defaults['container_name']}-follow",
                "require_camera": True,
                "headless": True,
                "require_gui": False,
                "network_host": False,
            },
        },
        {
            "template_id": "survey",
            "name": "Survey Precision",
            "description": "Balanced preset for waypoint missions, camera passes, and inspection recording.",
            "recommended": False,
            "tags": ["survey", "camera", "mapping"],
            "launch_notes": "Pairs well with the waypoint map and recorder for repeatable survey drills.",
            "mission_defaults": {"altitude": 20.0, "yaw": 0.0},
            "default_geofence": {
                "max_altitude_m": 120.0,
                "max_distance_from_home_m": 350.0,
                "min_battery_percent_for_rtl": 25.0,
            },
            **{
                **defaults,
                "container_name": f"{defaults['container_name']}-survey",
                "require_camera": True,
                "headless": True,
                "require_gui": False,
                "network_host": False,
            },
        },
    ]


def _build_status_snapshot(selected_drone_id: str = "") -> dict[str, object]:
    drones = tool_service.list_drones_data()
    primary = _primary_drone_entry()
    selected = selected_drone_id or str(primary.get("drone_id") or DEFAULT_DRONE_ID)
    try:
        runtime = tool_service.get_runtime_health_data()
        runtime_text = tool_service.get_runtime_health()
        runtime_profile = tool_service.get_runtime_profile_data()
    except Exception as exc:
        runtime = {"ready": False, "running": False, "status_text": str(exc)}
        runtime_text = f"Connection error: {exc}"
        runtime_profile = {}
    started = time.perf_counter()
    try:
        selected_status = tool_service.get_drone_status_data(selected)
    except Exception as exc:
        selected_status = {
            "connected": False,
            "drone_id": selected,
            "flight_mode": "UNKNOWN",
            "error": str(exc),
        }
    latency_ms = (time.perf_counter() - started) * 1000.0 if selected_status.get("connected") else None
    try:
        recordings = tool_service.list_recordings_data()
    except Exception:
        recordings = []
    active_drone = selected_status
    try:
        geofence = tool_service.get_geofence_data()
    except Exception:
        geofence = {}
    try:
        tracking = tool_service.get_visual_tracking_status_data(selected)
    except Exception:
        tracking = {
            "active": False,
            "drone_id": selected,
            "authorized": False,
            "detector_backend": "",
            "target_class": "",
            "step_count": 0,
            "last_error": "",
            "updated_at": 0.0,
            "last_command": {
                "forward_m_s": 0.0,
                "right_m_s": 0.0,
                "down_m_s": 0.0,
                "yaw_rate_deg_s": 0.0,
                "mode": "idle",
            },
            "last_observation": {
                "detected": False,
                "target_class": "",
                "confidence": 0.0,
                "center_x_norm": 0.5,
                "center_y_norm": 0.5,
                "area_norm": 0.0,
                "bbox": [],
                "track_id": None,
                "frame_width": 0,
                "frame_height": 0,
                "source": "none",
            },
        }
    return {
        "server_mode": "single-drone",
        "drone_id": selected,
        "drone": active_drone,
        "active_drone": active_drone,
        "runtime": runtime,
        "runtime_profile": runtime_profile,
        "runtime_text": runtime_text,
        "available_drones": drones,
        "drones": drones,
        "selected_drone_id": selected,
        "fleet_status": {selected: active_drone},
        "selected_status": selected_status,
        "telemetry": active_drone,
        "status": active_drone,
        "geofence": geofence,
        "tracking": tracking,
        "autonomy": tracking,
        "drone_count": len(drones) if drones else 1,
        "recordings": recordings,
        "connection": {
            "drone_id": selected,
            "latency_ms": latency_ms,
            "quality": _connection_quality(latency_ms, bool(selected_status.get("connected"))),
        },
    }


app = FastAPI(title="Drone MCP Operator")
app.mount("/static", StaticFiles(directory=str(UI)), name="static")
tool_service = RuntimeToolService()


@app.get("/health")
def health() -> dict[str, object]:
    return {
        "ok": True,
        "chat_ready": bool(_read_openrouter_key()),
    }


@app.get("/api/config")
def config() -> dict[str, object]:
    primary = _primary_drone_entry()
    drone_id = str(primary.get("drone_id") or DEFAULT_DRONE_ID)
    try:
        tracking = tool_service.get_visual_tracking_status_data(drone_id)
    except Exception:
        tracking = {"active": False, "drone_id": drone_id}
    try:
        runtime_profile = tool_service.get_runtime_profile_data()
    except Exception:
        runtime_profile = {}
    return {
        "server_mode": "single-drone",
        "vnc_url": os.environ.get(
            "OPERATOR_VNC_URL",
            "http://127.0.0.1:6080/vnc.html?autoconnect=true&resize=scale&quality=9&compression=0&show_dot=true&path=websockify",
        ),
        "status_ws_url": os.environ.get("OPERATOR_STATUS_WS_URL", "/ws/status"),
        "model": _read_openrouter_model(),
        "chat_ready": bool(_read_openrouter_key()),
        "drone_id": drone_id,
        "drone": primary,
        "active_drone": primary,
        "drones": tool_service.list_drones_data(),
        "runtime_profile": runtime_profile,
        "geofence": tool_service.get_geofence_data(),
        "tracking": tracking,
        "template_catalog_url": "/api/templates",
        "simulation_templates": _simulation_template_catalog(),
    }


@app.get("/api/runtime-health")
def runtime_health() -> dict[str, str]:
    return {"text": tool_service.get_runtime_health()}


@app.get("/api/status")
def status(drone_id: str = Query(default="")) -> dict[str, object]:
    return _build_status_snapshot(drone_id)


@app.get("/api/drone/status")
def drone_status(drone_id: str = Query(default="")) -> dict[str, object]:
    return tool_service.get_drone_status_data(drone_id)


@app.get("/api/geofence")
def geofence() -> dict[str, float]:
    return tool_service.get_geofence_data()


@app.get("/api/templates")
def templates() -> dict[str, object]:
    return {
        "server_mode": "single-drone",
        "drone_id": _primary_drone_entry().get("drone_id", DEFAULT_DRONE_ID),
        "template_catalog": _simulation_template_catalog(),
    }


@app.get("/api/tracking/status")
def tracking_status(drone_id: str = Query(default="")) -> dict[str, object]:
    return tool_service.get_visual_tracking_status_data(drone_id or _primary_drone_entry().get("drone_id", DEFAULT_DRONE_ID))


@app.post("/api/geofence")
def set_geofence(payload: GeofenceRequest) -> dict[str, object]:
    result = tool_service.set_geofence(
        max_altitude="" if payload.max_altitude is None else str(payload.max_altitude),
        max_distance="" if payload.max_distance is None else str(payload.max_distance),
        min_battery="" if payload.min_battery is None else str(payload.min_battery),
    )
    if result.startswith("❌"):
        raise HTTPException(status_code=400, detail=result)
    return {
        "text": result,
        "geofence": tool_service.get_geofence_data(),
    }


@app.get("/api/camera-frame")
def camera_frame(
    topic: str = Query(default=""),
    container_name: str = Query(default=""),
) -> dict[str, object]:
    try:
        return tool_service.get_camera_frame_data(container_name=container_name, topic=topic)
    except (RuntimeCommandError, ValueError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/recordings")
def recordings() -> list[dict[str, object]]:
    return tool_service.list_recordings_data()


@app.get("/api/recordings/{recording_id}")
def recording(recording_id: str) -> dict[str, object]:
    try:
        return tool_service.get_recording_data(recording_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.websocket("/ws/status")
async def status_ws(websocket: WebSocket) -> None:
    await websocket.accept()
    selected_drone_id = websocket.query_params.get("drone_id", "")
    try:
        while True:
            await websocket.send_json(_build_status_snapshot(selected_drone_id))
            try:
                message = await asyncio.wait_for(websocket.receive_text(), timeout=2.0)
                if message:
                    try:
                        payload = json.loads(message)
                    except json.JSONDecodeError:
                        payload = {}
                    if isinstance(payload, dict) and isinstance(payload.get("drone_id"), str):
                        selected_drone_id = payload["drone_id"]
            except asyncio.TimeoutError:
                continue
    except WebSocketDisconnect:
        return


@app.post("/api/tool")
def call_tool(payload: ToolRequest) -> dict[str, str]:
    try:
        result = tool_service.call_tool(payload.name, _normalize_tool_arguments(payload.arguments))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"text": result}


@app.post("/api/chat")
def chat(payload: ChatRequest) -> dict[str, object]:
    api_key = _read_openrouter_key()
    if not api_key:
        raise HTTPException(status_code=400, detail="OpenRouter key is not configured.")
    engine = OperatorChatEngine(
        OpenRouterClient(
            api_key=api_key,
            model=_read_openrouter_model(),
        ),
        tool_service,
    )
    return engine.run_turn(history=payload.history, user_message=payload.message)


@app.get("/")
def index() -> FileResponse:
    return FileResponse(UI / "index.html")


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080)
