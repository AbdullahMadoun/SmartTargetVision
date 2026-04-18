from __future__ import annotations

import json
import os
from pathlib import Path

from .flight_control import DEFAULT_DRONE_ID, DEFAULT_SYSTEM_ADDRESS, DroneController
from .navigation import GeoPoint, generate_lawnmower_pattern
from .recording import FlightRecordingManager
from .sim_runtime import DockerSimulatorRuntime, RuntimeCommandError, SimulatorNotReadyError
from .vision_tracking import TrackingConfig, TrackingStatus, VisualTrackingService


def _repo_root() -> Path:
    configured = os.environ.get("DRONE_MCP_REPO_ROOT", "").strip()
    return Path(configured) if configured else Path.cwd()


def _default_image() -> str:
    return os.environ.get("DRONE_MCP_SIM_IMAGE", "drone-mcp/sim-monocam:local").strip()


def _default_container_name() -> str:
    return os.environ.get("DRONE_MCP_SIM_CONTAINER", "drone-mcp-sim-monocam").strip()


def _default_dockerfile() -> str:
    return os.environ.get("DRONE_MCP_SIM_DOCKERFILE", "docker/sim-monocam.Dockerfile").strip()


def _default_model() -> str:
    return os.environ.get("DRONE_MCP_SIM_MODEL", "gz_x500_mono_cam").strip()


def _parse_int(raw_value: str, *, default: int, minimum: int, field_name: str) -> int:
    candidate = raw_value.strip()
    if not candidate:
        return default
    value = int(candidate)
    if value < minimum:
        raise ValueError(f"{field_name} must be at least {minimum}.")
    return value


def _parse_float(raw_value: str, *, default: float, minimum: float | None = None, field_name: str) -> float:
    candidate = raw_value.strip()
    if not candidate:
        return default
    value = float(candidate)
    if minimum is not None and value < minimum:
        raise ValueError(f"{field_name} must be at least {minimum}.")
    return value


def _parse_bool(raw_value: str, *, default: bool, field_name: str) -> bool:
    candidate = raw_value.strip().lower()
    if not candidate:
        return default
    if candidate in {"1", "true", "yes", "on"}:
        return True
    if candidate in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{field_name} must be a boolean value.")


def _parse_ports(raw_value: str) -> tuple[str, ...]:
    candidate = raw_value.strip()
    if not candidate:
        return ()
    if candidate.startswith("["):
        parsed = json.loads(candidate)
        if not isinstance(parsed, list):
            raise ValueError("ports JSON must decode to a list.")
        return tuple(str(item).strip() for item in parsed if str(item).strip())
    return tuple(part.strip() for part in candidate.split(",") if part.strip())


def _default_instance_count() -> int:
    raw = os.environ.get("DRONE_MCP_SIM_INSTANCE_COUNT", "1").strip()
    return _parse_int(raw, default=1, minimum=1, field_name="instance_count")


def _default_ports() -> tuple[str, ...]:
    raw = os.environ.get("DRONE_MCP_SIM_PORTS", "").strip()
    if raw:
        return tuple(part.strip() for part in raw.split(",") if part.strip())

    instance_count = _default_instance_count()
    ports = [f"{14540 + offset}:{14540 + offset}/udp" for offset in range(instance_count)]
    ports.extend(["14550:14550/udp", "8888:8888/udp"])
    return tuple(ports)


def _default_headless() -> bool:
    raw = os.environ.get("DRONE_MCP_SIM_HEADLESS", "1").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def _default_require_gui() -> bool:
    raw = os.environ.get("DRONE_MCP_SIM_REQUIRE_GUI", "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _default_require_camera() -> bool:
    raw = os.environ.get("DRONE_MCP_SIM_REQUIRE_CAMERA", "1").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def _default_network_host() -> bool:
    raw = os.environ.get("DRONE_MCP_SIM_NETWORK_HOST", "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _default_recordings_dir() -> Path:
    configured = os.environ.get("DRONE_MCP_RECORDINGS_DIR", "").strip()
    if configured:
        return Path(configured)
    return _repo_root() / ".operator-recordings"


def _default_camera_topic() -> str:
    return os.environ.get("DRONE_MCP_CAMERA_TOPIC", "").strip()


def _default_environment() -> dict[str, str]:
    configured = os.environ.get("DRONE_MCP_SIM_ENVIRONMENT", "").strip()
    if not configured:
        return {}
    return _parse_environment(configured)


def _default_drone_addresses() -> dict[str, str]:
    configured = os.environ.get("DRONE_MCP_MAVSDK_ADDRESSES", "").strip()
    addresses: dict[str, str] = {}
    if configured:
        if configured.startswith("{"):
            parsed = json.loads(configured)
            if not isinstance(parsed, dict):
                raise ValueError("DRONE_MCP_MAVSDK_ADDRESSES JSON must decode to an object.")
            addresses = {
                str(key).strip(): str(value).strip()
                for key, value in parsed.items()
                if str(key).strip() and str(value).strip()
            }
        else:
            for item in configured.split(","):
                drone_id, separator, address = item.partition("=")
                if separator and drone_id.strip() and address.strip():
                    addresses[drone_id.strip()] = address.strip()

    if addresses:
        return addresses

    default_address = os.environ.get("DRONE_MCP_MAVSDK_ADDRESS", "").strip() or DEFAULT_SYSTEM_ADDRESS
    instance_count = _default_instance_count()
    generated = {DEFAULT_DRONE_ID: default_address}
    if instance_count > 1:
        for offset in range(1, instance_count):
            generated[f"drone-{offset + 1}"] = f"udp://:{14540 + offset}"
    return generated


def _drone_property() -> dict[str, object]:
    return {
        "type": "string",
        "description": f"Optional drone id (default: {DEFAULT_DRONE_ID})",
    }


def _parse_environment(raw_value: str) -> dict[str, str]:
    candidate = raw_value.strip()
    if not candidate:
        return {}
    if candidate.startswith("{"):
        parsed = json.loads(candidate)
        if not isinstance(parsed, dict):
            raise ValueError("environment JSON must decode to an object.")
        return {
            str(key).strip(): str(value).strip()
            for key, value in parsed.items()
            if str(key).strip()
        }

    environment: dict[str, str] = {}
    for item in candidate.split(","):
        key, separator, value = item.partition("=")
        if separator and key.strip():
            environment[key.strip()] = value.strip()
    if environment:
        return environment
    raise ValueError("environment must be a JSON object or comma-separated KEY=VALUE pairs.")


class RuntimeToolService:
    TOOL_DEFINITIONS = [
        {
            "type": "function",
            "function": {
                "name": "start_simulation",
                "description": "Start the simulator image and wait until runtime health is ready.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "image": {"type": "string"},
                        "container_name": {"type": "string"},
                        "dockerfile": {"type": "string"},
                        "model": {"type": "string", "description": "PX4/Gazebo simulation model (default: gz_x500_mono_cam)"},
                        "headless": {"type": "string"},
                        "require_gui": {"type": "string"},
                        "require_camera": {"type": "string"},
                        "network_host": {"type": "string"},
                        "ports": {"type": "string", "description": "Comma-separated or JSON list of port mappings."},
                        "environment": {"type": "string", "description": "JSON object or comma-separated KEY=VALUE runtime environment variables."},
                        "timeout": {"type": "string"},
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "stop_simulation",
                "description": "Stop the active simulator container and report the resulting state.",
                "parameters": {
                    "type": "object",
                    "properties": {"container_name": {"type": "string"}},
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "reset_simulation",
                "description": "Reset the simulator container and wait until it is healthy again.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "image": {"type": "string"},
                        "container_name": {"type": "string"},
                        "dockerfile": {"type": "string"},
                        "model": {"type": "string", "description": "PX4/Gazebo simulation model (default: gz_x500_mono_cam)"},
                        "headless": {"type": "string"},
                        "require_gui": {"type": "string"},
                        "require_camera": {"type": "string"},
                        "network_host": {"type": "string"},
                        "ports": {"type": "string", "description": "Comma-separated or JSON list of port mappings."},
                        "environment": {"type": "string", "description": "JSON object or comma-separated KEY=VALUE runtime environment variables."},
                        "timeout": {"type": "string"},
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_runtime_health",
                "description": "Return image presence, runtime state, readiness, and camera topic health.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "image": {"type": "string"},
                        "container_name": {"type": "string"},
                        "model": {"type": "string"},
                        "environment": {"type": "string"},
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_simulation_logs",
                "description": "Return recent simulator logs from the selected container.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "container_name": {"type": "string"},
                        "lines": {"type": "string"},
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "connect_drone",
                "description": "Connect to the PX4 autopilot via MAVSDK. Must be called before any flight command.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "drone_id": _drone_property(),
                        "address": {
                            "type": "string",
                            "description": "MAVSDK system address (default: udp://:14540 or configured mapping)",
                        },
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "list_drones",
                "description": "List known drone ids for the current operator session.",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "arm_drone",
                "description": "Arm the drone's motors. Requires a GPS fix.",
                "parameters": {
                    "type": "object",
                    "properties": {"drone_id": _drone_property()},
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "takeoff",
                "description": "Arm the drone and take off to a specified altitude in metres.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "drone_id": _drone_property(),
                        "altitude": {"type": "string", "description": "Target altitude in metres (default: 5)"},
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "land",
                "description": "Land the drone at its current position.",
                "parameters": {
                    "type": "object",
                    "properties": {"drone_id": _drone_property()},
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "go_to_location",
                "description": "Fly the drone to a GPS coordinate at a given altitude.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "drone_id": _drone_property(),
                        "latitude": {"type": "string", "description": "Target latitude in degrees"},
                        "longitude": {"type": "string", "description": "Target longitude in degrees"},
                        "altitude": {"type": "string", "description": "Target altitude above home in metres (default: 10)"},
                        "yaw": {"type": "string", "description": "Target yaw in degrees (default: 0)"},
                    },
                    "required": ["latitude", "longitude"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_drone_status",
                "description": "Get the drone's current telemetry including speed, heading, and home distance.",
                "parameters": {
                    "type": "object",
                    "properties": {"drone_id": _drone_property()},
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "hold_position",
                "description": "Switch to HOLD mode so the drone hovers in place.",
                "parameters": {
                    "type": "object",
                    "properties": {"drone_id": _drone_property()},
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "return_to_launch",
                "description": "Trigger Return-to-Launch so the drone flies back to its home position and lands.",
                "parameters": {
                    "type": "object",
                    "properties": {"drone_id": _drone_property()},
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "send_body_velocity",
                "description": "Send a body-frame velocity command for precise manual control and autonomy loops.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "drone_id": _drone_property(),
                        "forward_m_s": {"type": "string", "description": "Forward velocity in m/s"},
                        "right_m_s": {"type": "string", "description": "Rightward velocity in m/s"},
                        "down_m_s": {"type": "string", "description": "Downward velocity in m/s (negative moves up)"},
                        "yaw_rate_deg_s": {"type": "string", "description": "Yaw rate in degrees per second"},
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "stop_body_velocity_control",
                "description": "Stop active offboard body-velocity control.",
                "parameters": {
                    "type": "object",
                    "properties": {"drone_id": _drone_property()},
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "set_geofence",
                "description": "Set geofence and safety reserve limits for flight operations.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "max_altitude": {"type": "string", "description": "Maximum altitude above home in metres"},
                        "max_distance": {"type": "string", "description": "Maximum distance from home in metres"},
                        "min_battery": {"type": "string", "description": "Minimum battery percent reserved for RTL"},
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_camera_frame",
                "description": "Capture one camera frame from the Gazebo camera topic and return a JSON payload with base64 image data.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "container_name": {"type": "string"},
                        "topic": {"type": "string"},
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "start_visual_tracking",
                "description": "Start a server-side visual tracking loop that captures camera frames and steers the drone with body-frame velocity control.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "drone_id": _drone_property(),
                        "container_name": {"type": "string"},
                        "camera_topic": {"type": "string"},
                        "target_class": {"type": "string", "description": "Object class to track (default: person)"},
                        "confidence_threshold": {"type": "string"},
                        "target_area_norm": {"type": "string"},
                        "area_deadzone_norm": {"type": "string"},
                        "horizontal_deadzone_norm": {"type": "string"},
                        "vertical_deadzone_norm": {"type": "string"},
                        "forward_gain": {"type": "string"},
                        "lateral_gain": {"type": "string"},
                        "vertical_gain": {"type": "string"},
                        "yaw_gain": {"type": "string"},
                        "max_forward_speed_m_s": {"type": "string"},
                        "max_right_speed_m_s": {"type": "string"},
                        "max_down_speed_m_s": {"type": "string"},
                        "max_yaw_rate_deg_s": {"type": "string"},
                        "scan_yaw_rate_deg_s": {"type": "string"},
                        "enable_vertical_control": {"type": "string"},
                        "loop_interval_s": {"type": "string"},
                        "detector_backend": {"type": "string"},
                        "model_path": {"type": "string"},
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "run_visual_tracking_step",
                "description": "Run one deterministic visual-tracking cycle for debugging detectors and offboard control.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "drone_id": _drone_property(),
                        "container_name": {"type": "string"},
                        "camera_topic": {"type": "string"},
                        "target_class": {"type": "string"},
                        "confidence_threshold": {"type": "string"},
                        "target_area_norm": {"type": "string"},
                        "area_deadzone_norm": {"type": "string"},
                        "horizontal_deadzone_norm": {"type": "string"},
                        "vertical_deadzone_norm": {"type": "string"},
                        "forward_gain": {"type": "string"},
                        "lateral_gain": {"type": "string"},
                        "vertical_gain": {"type": "string"},
                        "yaw_gain": {"type": "string"},
                        "max_forward_speed_m_s": {"type": "string"},
                        "max_right_speed_m_s": {"type": "string"},
                        "max_down_speed_m_s": {"type": "string"},
                        "max_yaw_rate_deg_s": {"type": "string"},
                        "scan_yaw_rate_deg_s": {"type": "string"},
                        "enable_vertical_control": {"type": "string"},
                        "loop_interval_s": {"type": "string"},
                        "detector_backend": {"type": "string"},
                        "model_path": {"type": "string"},
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "stop_visual_tracking",
                "description": "Stop the active server-side visual tracking loop.",
                "parameters": {
                    "type": "object",
                    "properties": {"drone_id": _drone_property()},
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_visual_tracking_status",
                "description": "Return the current visual-tracking/autonomy status.",
                "parameters": {
                    "type": "object",
                    "properties": {"drone_id": _drone_property()},
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "start_recording",
                "description": "Start recording telemetry samples for a drone into a JSON log file.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "drone_id": _drone_property(),
                        "interval": {"type": "string", "description": "Sampling interval in seconds (default: 2)"},
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "stop_recording",
                "description": "Stop an active telemetry recording.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "drone_id": _drone_property(),
                        "recording_id": {"type": "string"},
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "list_recordings",
                "description": "List saved telemetry recordings.",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_recording",
                "description": "Return the full JSON payload for a saved telemetry recording.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "recording_id": {"type": "string", "description": "Recording id returned by list_recordings"},
                    },
                    "required": ["recording_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "inspect_area",
                "description": "Generate a lawnmower inspection mission for a polygon, fly it, capture camera frames at each waypoint, and return a JSON summary.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "drone_id": _drone_property(),
                        "polygon_json": {
                            "type": "string",
                            "description": "JSON array of polygon points with latitude/longitude fields",
                        },
                        "altitude": {"type": "string", "description": "Survey altitude above home in metres"},
                        "strip_spacing": {"type": "string", "description": "Strip spacing in metres"},
                        "waypoint_spacing": {"type": "string", "description": "Waypoint spacing along strips in metres"},
                        "camera_topic": {"type": "string"},
                    },
                    "required": ["polygon_json"],
                },
            },
        },
    ]

    def __init__(
        self,
        drone: DroneController | None = None,
        *,
        recordings: FlightRecordingManager | None = None,
        tracking: VisualTrackingService | None = None,
    ) -> None:
        self._drone: DroneController | None = drone
        self._recordings = recordings
        self._tracking = tracking
        self._runtime_profile: dict[str, object] = {}

    @property
    def drone(self) -> DroneController:
        if self._drone is None:
            addresses = _default_drone_addresses()
            self._drone = DroneController(
                address=addresses.get(DEFAULT_DRONE_ID, DEFAULT_SYSTEM_ADDRESS),
                addresses=addresses,
            )
        return self._drone

    @property
    def recordings(self) -> FlightRecordingManager:
        if self._recordings is None:
            self._recordings = FlightRecordingManager(
                _default_recordings_dir(),
                status_provider=self.drone.get_status_snapshot,
            )
        return self._recordings

    @property
    def tracking(self) -> VisualTrackingService:
        if self._tracking is None:
            self._tracking = VisualTrackingService(
                capture_provider=self._capture_tracking_frame,
                status_provider=self.drone.get_status_snapshot,
                command_sender=self.drone.send_body_velocity,
                stop_sender=self.drone.stop_body_velocity_control,
            )
        return self._tracking

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
    ) -> DockerSimulatorRuntime:
        stored = self._runtime_profile
        resolved_image = image.strip() or str(stored.get("image", "")).strip() or _default_image()
        resolved_container = container_name.strip() or str(stored.get("container_name", "")).strip() or _default_container_name()
        resolved_dockerfile = dockerfile.strip() or str(stored.get("dockerfile", "")).strip() or _default_dockerfile()
        resolved_model = model.strip() or str(stored.get("model", "")).strip() or _default_model()
        resolved_headless = _parse_bool(
            headless,
            default=bool(stored.get("headless", _default_headless())),
            field_name="headless",
        )
        resolved_require_gui = _parse_bool(
            require_gui,
            default=bool(stored.get("require_gui", _default_require_gui())),
            field_name="require_gui",
        )
        resolved_require_camera = _parse_bool(
            require_camera,
            default=bool(stored.get("require_camera", _default_require_camera())),
            field_name="require_camera",
        )
        resolved_network_host = _parse_bool(
            network_host,
            default=bool(stored.get("network_host", _default_network_host())),
            field_name="network_host",
        )
        parsed_ports = _parse_ports(ports) if ports.strip() else ()
        stored_ports = tuple(str(item).strip() for item in stored.get("ports", ()) if str(item).strip())
        resolved_ports = parsed_ports or stored_ports or _default_ports()
        resolved_environment = (
            _parse_environment(environment)
            if environment.strip()
            else {
                str(key).strip(): str(value).strip()
                for key, value in dict(stored.get("environment", _default_environment())).items()
                if str(key).strip()
            }
        )
        return DockerSimulatorRuntime(
            _repo_root(),
            image=resolved_image,
            container_name=resolved_container,
            dockerfile=resolved_dockerfile,
            model=resolved_model,
            headless=resolved_headless,
            require_gui=resolved_require_gui,
            require_camera=resolved_require_camera,
            network_host=resolved_network_host,
            ports=resolved_ports,
            environment=resolved_environment,
        )

    def _set_runtime_profile(
        self,
        *,
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
    ) -> None:
        runtime = self.runtime(
            image=image,
            container_name=container_name,
            dockerfile=dockerfile,
            model=model,
            headless=headless,
            require_gui=require_gui,
            require_camera=require_camera,
            network_host=network_host,
            ports=ports,
            environment=environment,
        )
        self._runtime_profile = {
            "image": runtime.image,
            "container_name": runtime.container_name,
            "dockerfile": runtime.dockerfile,
            "model": runtime.model,
            "headless": runtime.headless,
            "require_gui": runtime.require_gui,
            "require_camera": runtime.require_camera,
            "network_host": runtime.network_host,
            "ports": tuple(runtime.ports),
            "environment": dict(runtime.environment),
        }

    def list_tool_definitions(self) -> list[dict[str, object]]:
        return [tool.copy() for tool in self.TOOL_DEFINITIONS]

    def call_tool(self, name: str, arguments: dict[str, str] | None = None) -> str:
        args = arguments or {}
        if name == "start_simulation":
            return self.start_simulation(
                image=args.get("image", ""),
                container_name=args.get("container_name", ""),
                dockerfile=args.get("dockerfile", ""),
                model=args.get("model", ""),
                headless=args.get("headless", ""),
                require_gui=args.get("require_gui", ""),
                require_camera=args.get("require_camera", ""),
                network_host=args.get("network_host", ""),
                ports=args.get("ports", ""),
                environment=args.get("environment", ""),
                timeout=args.get("timeout", ""),
            )
        if name == "stop_simulation":
            return self.stop_simulation(container_name=args.get("container_name", ""))
        if name == "reset_simulation":
            return self.reset_simulation(
                image=args.get("image", ""),
                container_name=args.get("container_name", ""),
                dockerfile=args.get("dockerfile", ""),
                model=args.get("model", ""),
                headless=args.get("headless", ""),
                require_gui=args.get("require_gui", ""),
                require_camera=args.get("require_camera", ""),
                network_host=args.get("network_host", ""),
                ports=args.get("ports", ""),
                environment=args.get("environment", ""),
                timeout=args.get("timeout", ""),
            )
        if name == "get_runtime_health":
            return self.get_runtime_health(
                image=args.get("image", ""),
                container_name=args.get("container_name", ""),
                model=args.get("model", ""),
                environment=args.get("environment", ""),
            )
        if name == "get_simulation_logs":
            return self.get_simulation_logs(
                container_name=args.get("container_name", ""),
                lines=args.get("lines", ""),
            )
        if name == "connect_drone":
            return self.connect_drone(
                drone_id=args.get("drone_id", ""),
                address=args.get("address", ""),
            )
        if name == "list_drones":
            return self.list_drones()
        if name == "arm_drone":
            return self.arm_drone(drone_id=args.get("drone_id", ""))
        if name == "takeoff":
            return self.takeoff(
                altitude=args.get("altitude", ""),
                drone_id=args.get("drone_id", ""),
            )
        if name == "land":
            return self.land_drone(drone_id=args.get("drone_id", ""))
        if name == "go_to_location":
            return self.go_to_location(
                latitude=args.get("latitude", ""),
                longitude=args.get("longitude", ""),
                altitude=args.get("altitude", ""),
                yaw=args.get("yaw", ""),
                drone_id=args.get("drone_id", ""),
            )
        if name == "get_drone_status":
            return self.get_drone_status(drone_id=args.get("drone_id", ""))
        if name == "hold_position":
            return self.hold_position(drone_id=args.get("drone_id", ""))
        if name == "return_to_launch":
            return self.return_to_launch(drone_id=args.get("drone_id", ""))
        if name == "send_body_velocity":
            return self.send_body_velocity(
                forward_m_s=args.get("forward_m_s", ""),
                right_m_s=args.get("right_m_s", ""),
                down_m_s=args.get("down_m_s", ""),
                yaw_rate_deg_s=args.get("yaw_rate_deg_s", ""),
                drone_id=args.get("drone_id", ""),
            )
        if name == "stop_body_velocity_control":
            return self.stop_body_velocity_control(drone_id=args.get("drone_id", ""))
        if name == "set_geofence":
            return self.set_geofence(
                max_altitude=args.get("max_altitude", args.get("maxAltitudeM", "")),
                max_distance=args.get("max_distance", args.get("maxDistanceM", "")),
                min_battery=args.get("min_battery", args.get("minBatteryPercent", "")),
            )
        if name == "start_visual_tracking":
            return self.start_visual_tracking(
                drone_id=args.get("drone_id", ""),
                container_name=args.get("container_name", ""),
                camera_topic=args.get("camera_topic", ""),
                target_class=args.get("target_class", ""),
                confidence_threshold=args.get("confidence_threshold", ""),
                target_area_norm=args.get("target_area_norm", ""),
                area_deadzone_norm=args.get("area_deadzone_norm", ""),
                horizontal_deadzone_norm=args.get("horizontal_deadzone_norm", ""),
                vertical_deadzone_norm=args.get("vertical_deadzone_norm", ""),
                forward_gain=args.get("forward_gain", ""),
                lateral_gain=args.get("lateral_gain", ""),
                vertical_gain=args.get("vertical_gain", ""),
                yaw_gain=args.get("yaw_gain", ""),
                max_forward_speed_m_s=args.get("max_forward_speed_m_s", ""),
                max_right_speed_m_s=args.get("max_right_speed_m_s", ""),
                max_down_speed_m_s=args.get("max_down_speed_m_s", ""),
                max_yaw_rate_deg_s=args.get("max_yaw_rate_deg_s", ""),
                scan_yaw_rate_deg_s=args.get("scan_yaw_rate_deg_s", ""),
                enable_vertical_control=args.get("enable_vertical_control", ""),
                loop_interval_s=args.get("loop_interval_s", ""),
                detector_backend=args.get("detector_backend", ""),
                model_path=args.get("model_path", ""),
            )
        if name == "run_visual_tracking_step":
            return self.run_visual_tracking_step(
                drone_id=args.get("drone_id", ""),
                container_name=args.get("container_name", ""),
                camera_topic=args.get("camera_topic", ""),
                target_class=args.get("target_class", ""),
                confidence_threshold=args.get("confidence_threshold", ""),
                target_area_norm=args.get("target_area_norm", ""),
                area_deadzone_norm=args.get("area_deadzone_norm", ""),
                horizontal_deadzone_norm=args.get("horizontal_deadzone_norm", ""),
                vertical_deadzone_norm=args.get("vertical_deadzone_norm", ""),
                forward_gain=args.get("forward_gain", ""),
                lateral_gain=args.get("lateral_gain", ""),
                vertical_gain=args.get("vertical_gain", ""),
                yaw_gain=args.get("yaw_gain", ""),
                max_forward_speed_m_s=args.get("max_forward_speed_m_s", ""),
                max_right_speed_m_s=args.get("max_right_speed_m_s", ""),
                max_down_speed_m_s=args.get("max_down_speed_m_s", ""),
                max_yaw_rate_deg_s=args.get("max_yaw_rate_deg_s", ""),
                scan_yaw_rate_deg_s=args.get("scan_yaw_rate_deg_s", ""),
                enable_vertical_control=args.get("enable_vertical_control", ""),
                loop_interval_s=args.get("loop_interval_s", ""),
                detector_backend=args.get("detector_backend", ""),
                model_path=args.get("model_path", ""),
            )
        if name == "stop_visual_tracking":
            return self.stop_visual_tracking(drone_id=args.get("drone_id", ""))
        if name == "get_visual_tracking_status":
            return self.get_visual_tracking_status(drone_id=args.get("drone_id", ""))
        if name == "get_camera_frame":
            return self.get_camera_frame(
                container_name=args.get("container_name", ""),
                topic=args.get("topic", ""),
            )
        if name == "start_recording":
            return self.start_recording(
                drone_id=args.get("drone_id", ""),
                interval=args.get("interval", ""),
            )
        if name == "stop_recording":
            return self.stop_recording(
                drone_id=args.get("drone_id", ""),
                recording_id=args.get("recording_id", ""),
            )
        if name == "list_recordings":
            return self.list_recordings()
        if name == "get_recording":
            return self.get_recording(recording_id=args.get("recording_id", ""))
        if name == "inspect_area":
            return self.inspect_area(
                polygon_json=args.get("polygon_json", ""),
                altitude=args.get("altitude", ""),
                strip_spacing=args.get("strip_spacing", ""),
                waypoint_spacing=args.get("waypoint_spacing", ""),
                camera_topic=args.get("camera_topic", ""),
                drone_id=args.get("drone_id", ""),
            )
        raise ValueError(f"Unknown tool: {name}")

    def start_simulation(
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
        timeout: str = "",
    ) -> str:
        try:
            timeout_s = _parse_int(timeout, default=120, minimum=1, field_name="timeout")
            self._set_runtime_profile(
                image=image,
                container_name=container_name,
                dockerfile=dockerfile,
                model=model,
                headless=headless,
                require_gui=require_gui,
                require_camera=require_camera,
                network_host=network_host,
                ports=ports,
                environment=environment,
            )
            runtime = self.runtime()
            runtime.ensure_image()
            runtime.start()
            status = runtime.wait_until_ready(timeout_s=timeout_s)
            return self._format_runtime_status("✅ Simulation started and is ready.", status)
        except (RuntimeCommandError, SimulatorNotReadyError, ValueError) as exc:
            return f"❌ Error: {exc}"

    def stop_simulation(self, container_name: str = "") -> str:
        try:
            runtime = self.runtime(container_name=container_name)
            runtime.stop()
            status = runtime.status()
            return self._format_runtime_status("✅ Simulation stop command completed.", status)
        except (RuntimeCommandError, ValueError) as exc:
            return f"❌ Error: {exc}"

    def reset_simulation(
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
        timeout: str = "",
    ) -> str:
        try:
            timeout_s = _parse_int(timeout, default=120, minimum=1, field_name="timeout")
            self._set_runtime_profile(
                image=image,
                container_name=container_name,
                dockerfile=dockerfile,
                model=model,
                headless=headless,
                require_gui=require_gui,
                require_camera=require_camera,
                network_host=network_host,
                ports=ports,
                environment=environment,
            )
            runtime = self.runtime()
            runtime.ensure_image()
            runtime.reset()
            status = runtime.wait_until_ready(timeout_s=timeout_s)
            return self._format_runtime_status("✅ Simulation reset and is ready.", status)
        except (RuntimeCommandError, SimulatorNotReadyError, ValueError) as exc:
            return f"❌ Error: {exc}"

    def get_runtime_health(self, image: str = "", container_name: str = "", model: str = "", environment: str = "") -> str:
        try:
            runtime = self.runtime(image=image, container_name=container_name, model=model, environment=environment)
            status = runtime.status()
            prefix = "✅ Runtime health snapshot." if status.ready else "⚠️ Runtime health snapshot."
            return self._format_runtime_status(prefix, status)
        except (RuntimeCommandError, ValueError) as exc:
            return f"❌ Error: {exc}"

    def get_runtime_health_data(
        self,
        image: str = "",
        container_name: str = "",
        model: str = "",
        environment: str = "",
    ) -> dict[str, object]:
        runtime = self.runtime(image=image, container_name=container_name, model=model, environment=environment)
        return runtime.status().to_dict()

    def get_runtime_profile_data(self) -> dict[str, object]:
        runtime = self.runtime()
        return {
            "image": runtime.image,
            "container_name": runtime.container_name,
            "dockerfile": runtime.dockerfile,
            "model": runtime.model,
            "headless": runtime.headless,
            "require_gui": runtime.require_gui,
            "require_camera": runtime.require_camera,
            "network_host": runtime.network_host,
            "ports": list(runtime.ports),
            "environment": dict(runtime.environment),
        }

    def get_simulation_logs(self, container_name: str = "", lines: str = "") -> str:
        try:
            line_count = _parse_int(lines, default=200, minimum=1, field_name="lines")
            runtime = self.runtime(container_name=container_name)
            log_output = runtime.logs_tail(lines=line_count).strip()
            if not log_output:
                log_output = "<no logs available>"
            return f"📁 Simulation logs:\n{log_output}"
        except (RuntimeCommandError, ValueError) as exc:
            return f"❌ Error: {exc}"

    def connect_drone(self, drone_id: str = "", address: str = "") -> str:
        return self.drone.connect(address=address, drone_id=drone_id)

    def list_drones(self) -> str:
        drone_ids = self.drone.list_drones()
        if not drone_ids:
            return "No drones are configured."
        return "Known drones:\n" + "\n".join(f"- {drone_id}" for drone_id in drone_ids)

    def list_drones_data(self) -> list[dict[str, str]]:
        return [{"drone_id": drone_id} for drone_id in self.drone.list_drones()]

    def arm_drone(self, drone_id: str = "") -> str:
        return self.drone.arm(drone_id=drone_id)

    def takeoff(self, altitude: str = "", drone_id: str = "") -> str:
        try:
            alt = _parse_float(altitude, default=5.0, minimum=1.0, field_name="altitude")
        except ValueError:
            return "❌ Invalid altitude value."
        return self.drone.takeoff(altitude_m=alt, drone_id=drone_id)

    def land_drone(self, drone_id: str = "") -> str:
        return self.drone.land(drone_id=drone_id)

    def go_to_location(
        self,
        latitude: str = "",
        longitude: str = "",
        altitude: str = "",
        yaw: str = "",
        drone_id: str = "",
    ) -> str:
        try:
            lat = float(latitude)
            lon = float(longitude)
        except (ValueError, TypeError):
            return "❌ latitude and longitude are required numeric values."
        try:
            alt = _parse_float(altitude, default=10.0, minimum=0.0, field_name="altitude")
        except ValueError:
            return "❌ Invalid altitude value."
        try:
            yaw_d = float(yaw.strip()) if yaw.strip() else 0.0
        except ValueError:
            yaw_d = 0.0
        return self.drone.go_to_location(
            lat,
            lon,
            altitude_m=alt,
            yaw_deg=yaw_d,
            drone_id=drone_id,
        )

    def get_drone_status(self, drone_id: str = "") -> str:
        return self.drone.get_status(drone_id=drone_id)

    def get_drone_status_data(self, drone_id: str = "") -> dict[str, object]:
        return self.drone.get_status_snapshot(drone_id).to_dict()

    def get_fleet_status_data(self) -> dict[str, dict[str, object]]:
        return {
            drone_id: self.get_drone_status_data(drone_id)
            for drone_id in self.drone.list_drones()
        }

    def hold_position(self, drone_id: str = "") -> str:
        return self.drone.hold_position(drone_id=drone_id)

    def return_to_launch(self, drone_id: str = "") -> str:
        return self.drone.return_to_launch(drone_id=drone_id)

    def send_body_velocity(
        self,
        *,
        forward_m_s: str = "",
        right_m_s: str = "",
        down_m_s: str = "",
        yaw_rate_deg_s: str = "",
        drone_id: str = "",
    ) -> str:
        try:
            forward = _parse_float(forward_m_s, default=0.0, field_name="forward_m_s")
            right = _parse_float(right_m_s, default=0.0, field_name="right_m_s")
            down = _parse_float(down_m_s, default=0.0, field_name="down_m_s")
            yaw_rate = _parse_float(yaw_rate_deg_s, default=0.0, field_name="yaw_rate_deg_s")
        except ValueError as exc:
            return f"❌ Error: {exc}"
        return self.drone.send_body_velocity(
            forward_m_s=forward,
            right_m_s=right,
            down_m_s=down,
            yaw_rate_deg_s=yaw_rate,
            drone_id=drone_id,
        )

    def stop_body_velocity_control(self, drone_id: str = "") -> str:
        return self.drone.stop_body_velocity_control(drone_id=drone_id)

    def set_geofence(self, max_altitude: str = "", max_distance: str = "", min_battery: str = "") -> str:
        try:
            geofence = self.drone.set_geofence(
                max_altitude_m=None if not max_altitude.strip() else float(max_altitude),
                max_distance_from_home_m=None if not max_distance.strip() else float(max_distance),
                min_battery_percent_for_rtl=None if not min_battery.strip() else float(min_battery),
            )
        except ValueError as exc:
            return f"❌ Error: {exc}"
        return (
            "✅ Geofence updated.\n"
            f"Max Altitude: {geofence.max_altitude_m:.1f} m\n"
            f"Max Distance: {geofence.max_distance_from_home_m:.1f} m\n"
            f"Min Battery Reserve: {geofence.min_battery_percent_for_rtl:.0f}%"
        )

    def get_geofence_data(self) -> dict[str, float]:
        return self.drone.get_geofence().to_dict()

    def _resolve_tracking_topic(self, runtime: DockerSimulatorRuntime, camera_topic: str = "") -> str:
        resolved_topic = camera_topic.strip() or _default_camera_topic()
        if resolved_topic:
            return resolved_topic
        camera_topics = runtime.status().camera_topics
        if camera_topics:
            return camera_topics[0]
        raise ValueError("No camera topic is available. Start the simulator and provide camera_topic if needed.")

    def _capture_tracking_frame(self, container_name: str, camera_topic: str):
        runtime = self.runtime(container_name=container_name)
        resolved_topic = self._resolve_tracking_topic(runtime, camera_topic)
        return runtime.capture_camera_frame(topic=resolved_topic)

    def _build_tracking_config(
        self,
        *,
        container_name: str = "",
        camera_topic: str = "",
        target_class: str = "",
        confidence_threshold: str = "",
        target_area_norm: str = "",
        area_deadzone_norm: str = "",
        horizontal_deadzone_norm: str = "",
        vertical_deadzone_norm: str = "",
        forward_gain: str = "",
        lateral_gain: str = "",
        vertical_gain: str = "",
        yaw_gain: str = "",
        max_forward_speed_m_s: str = "",
        max_right_speed_m_s: str = "",
        max_down_speed_m_s: str = "",
        max_yaw_rate_deg_s: str = "",
        scan_yaw_rate_deg_s: str = "",
        enable_vertical_control: str = "",
        loop_interval_s: str = "",
        detector_backend: str = "",
        model_path: str = "",
    ) -> TrackingConfig:
        defaults = TrackingConfig()
        runtime = self.runtime(container_name=container_name)
        resolved_container = runtime.container_name
        resolved_topic = self._resolve_tracking_topic(runtime, camera_topic)
        return TrackingConfig(
            target_class=target_class.strip() or defaults.target_class,
            confidence_threshold=_parse_float(
                confidence_threshold,
                default=defaults.confidence_threshold,
                minimum=0.0,
                field_name="confidence_threshold",
            ),
            target_area_norm=_parse_float(
                target_area_norm,
                default=defaults.target_area_norm,
                minimum=0.0,
                field_name="target_area_norm",
            ),
            area_deadzone_norm=_parse_float(
                area_deadzone_norm,
                default=defaults.area_deadzone_norm,
                minimum=0.0,
                field_name="area_deadzone_norm",
            ),
            horizontal_deadzone_norm=_parse_float(
                horizontal_deadzone_norm,
                default=defaults.horizontal_deadzone_norm,
                minimum=0.0,
                field_name="horizontal_deadzone_norm",
            ),
            vertical_deadzone_norm=_parse_float(
                vertical_deadzone_norm,
                default=defaults.vertical_deadzone_norm,
                minimum=0.0,
                field_name="vertical_deadzone_norm",
            ),
            forward_gain=_parse_float(forward_gain, default=defaults.forward_gain, minimum=0.0, field_name="forward_gain"),
            lateral_gain=_parse_float(lateral_gain, default=defaults.lateral_gain, minimum=0.0, field_name="lateral_gain"),
            vertical_gain=_parse_float(vertical_gain, default=defaults.vertical_gain, minimum=0.0, field_name="vertical_gain"),
            yaw_gain=_parse_float(yaw_gain, default=defaults.yaw_gain, minimum=0.0, field_name="yaw_gain"),
            max_forward_speed_m_s=_parse_float(
                max_forward_speed_m_s,
                default=defaults.max_forward_speed_m_s,
                minimum=0.0,
                field_name="max_forward_speed_m_s",
            ),
            max_right_speed_m_s=_parse_float(
                max_right_speed_m_s,
                default=defaults.max_right_speed_m_s,
                minimum=0.0,
                field_name="max_right_speed_m_s",
            ),
            max_down_speed_m_s=_parse_float(
                max_down_speed_m_s,
                default=defaults.max_down_speed_m_s,
                minimum=0.0,
                field_name="max_down_speed_m_s",
            ),
            max_yaw_rate_deg_s=_parse_float(
                max_yaw_rate_deg_s,
                default=defaults.max_yaw_rate_deg_s,
                minimum=0.0,
                field_name="max_yaw_rate_deg_s",
            ),
            scan_yaw_rate_deg_s=_parse_float(
                scan_yaw_rate_deg_s,
                default=defaults.scan_yaw_rate_deg_s,
                minimum=0.0,
                field_name="scan_yaw_rate_deg_s",
            ),
            enable_vertical_control=_parse_bool(
                enable_vertical_control,
                default=defaults.enable_vertical_control,
                field_name="enable_vertical_control",
            ),
            loop_interval_s=_parse_float(
                loop_interval_s,
                default=defaults.loop_interval_s,
                minimum=0.1,
                field_name="loop_interval_s",
            ),
            camera_topic=resolved_topic,
            container_name=resolved_container,
            model_path=model_path.strip(),
            detector_backend=detector_backend.strip() or defaults.detector_backend,
        )

    def _format_tracking_status(self, status: TrackingStatus) -> str:
        observation = status.last_observation
        command = status.last_command
        observation_summary = (
            f"detected {observation.target_class} @ {observation.confidence:.2f}"
            if observation.detected
            else "not detected"
        )
        if observation.detected and observation.track_id is not None:
            observation_summary += f" (track {observation.track_id})"
        error_text = status.last_error or "<none>"
        return (
            "🎯 Visual Tracking:\n"
            f"Active: {'yes' if status.active else 'no'}\n"
            f"Drone: {status.drone_id}\n"
            f"Authorized: {'yes' if status.authorized else 'no'}\n"
            f"Backend: {status.detector_backend or '<none>'}\n"
            f"Target Class: {status.target_class or '<none>'}\n"
            f"Step Count: {status.step_count}\n"
            f"Last Error: {error_text}\n"
            f"Last Command: {command.mode} "
            f"(fwd={command.forward_m_s:.2f}, right={command.right_m_s:.2f}, "
            f"down={command.down_m_s:.2f}, yaw={command.yaw_rate_deg_s:.1f})\n"
            f"Observation: {observation_summary}"
        )

    def start_visual_tracking(
        self,
        *,
        drone_id: str = "",
        container_name: str = "",
        camera_topic: str = "",
        target_class: str = "",
        confidence_threshold: str = "",
        target_area_norm: str = "",
        area_deadzone_norm: str = "",
        horizontal_deadzone_norm: str = "",
        vertical_deadzone_norm: str = "",
        forward_gain: str = "",
        lateral_gain: str = "",
        vertical_gain: str = "",
        yaw_gain: str = "",
        max_forward_speed_m_s: str = "",
        max_right_speed_m_s: str = "",
        max_down_speed_m_s: str = "",
        max_yaw_rate_deg_s: str = "",
        scan_yaw_rate_deg_s: str = "",
        enable_vertical_control: str = "",
        loop_interval_s: str = "",
        detector_backend: str = "",
        model_path: str = "",
    ) -> str:
        try:
            config = self._build_tracking_config(
                container_name=container_name,
                camera_topic=camera_topic,
                target_class=target_class,
                confidence_threshold=confidence_threshold,
                target_area_norm=target_area_norm,
                area_deadzone_norm=area_deadzone_norm,
                horizontal_deadzone_norm=horizontal_deadzone_norm,
                vertical_deadzone_norm=vertical_deadzone_norm,
                forward_gain=forward_gain,
                lateral_gain=lateral_gain,
                vertical_gain=vertical_gain,
                yaw_gain=yaw_gain,
                max_forward_speed_m_s=max_forward_speed_m_s,
                max_right_speed_m_s=max_right_speed_m_s,
                max_down_speed_m_s=max_down_speed_m_s,
                max_yaw_rate_deg_s=max_yaw_rate_deg_s,
                scan_yaw_rate_deg_s=scan_yaw_rate_deg_s,
                enable_vertical_control=enable_vertical_control,
                loop_interval_s=loop_interval_s,
                detector_backend=detector_backend,
                model_path=model_path,
            )
            status = self.tracking.start(drone_id=drone_id.strip() or DEFAULT_DRONE_ID, config=config)
            return f"✅ Visual tracking loop started.\n{self._format_tracking_status(status)}"
        except (RuntimeCommandError, RuntimeError, ValueError) as exc:
            return f"❌ Error: {exc}"

    def run_visual_tracking_step(
        self,
        *,
        drone_id: str = "",
        container_name: str = "",
        camera_topic: str = "",
        target_class: str = "",
        confidence_threshold: str = "",
        target_area_norm: str = "",
        area_deadzone_norm: str = "",
        horizontal_deadzone_norm: str = "",
        vertical_deadzone_norm: str = "",
        forward_gain: str = "",
        lateral_gain: str = "",
        vertical_gain: str = "",
        yaw_gain: str = "",
        max_forward_speed_m_s: str = "",
        max_right_speed_m_s: str = "",
        max_down_speed_m_s: str = "",
        max_yaw_rate_deg_s: str = "",
        scan_yaw_rate_deg_s: str = "",
        enable_vertical_control: str = "",
        loop_interval_s: str = "",
        detector_backend: str = "",
        model_path: str = "",
    ) -> str:
        try:
            config = self._build_tracking_config(
                container_name=container_name,
                camera_topic=camera_topic,
                target_class=target_class,
                confidence_threshold=confidence_threshold,
                target_area_norm=target_area_norm,
                area_deadzone_norm=area_deadzone_norm,
                horizontal_deadzone_norm=horizontal_deadzone_norm,
                vertical_deadzone_norm=vertical_deadzone_norm,
                forward_gain=forward_gain,
                lateral_gain=lateral_gain,
                vertical_gain=vertical_gain,
                yaw_gain=yaw_gain,
                max_forward_speed_m_s=max_forward_speed_m_s,
                max_right_speed_m_s=max_right_speed_m_s,
                max_down_speed_m_s=max_down_speed_m_s,
                max_yaw_rate_deg_s=max_yaw_rate_deg_s,
                scan_yaw_rate_deg_s=scan_yaw_rate_deg_s,
                enable_vertical_control=enable_vertical_control,
                loop_interval_s=loop_interval_s,
                detector_backend=detector_backend,
                model_path=model_path,
            )
            status = self.tracking.run_once(drone_id=drone_id.strip() or DEFAULT_DRONE_ID, config=config)
            return f"✅ Visual tracking step completed.\n{self._format_tracking_status(status)}"
        except (RuntimeCommandError, RuntimeError, ValueError) as exc:
            return f"❌ Error: {exc}"

    def stop_visual_tracking(self, drone_id: str = "") -> str:
        status = self.tracking.stop(drone_id=drone_id.strip() or DEFAULT_DRONE_ID)
        return f"✅ Visual tracking loop stopped.\n{self._format_tracking_status(status)}"

    def get_visual_tracking_status(self, drone_id: str = "") -> str:
        return self._format_tracking_status(self.tracking.status(drone_id.strip() or DEFAULT_DRONE_ID))

    def get_visual_tracking_status_data(self, drone_id: str = "") -> dict[str, object]:
        return self.tracking.status(drone_id.strip() or DEFAULT_DRONE_ID).to_dict()

    def get_camera_frame(self, container_name: str = "", topic: str = "") -> str:
        try:
            payload = self.get_camera_frame_data(container_name=container_name, topic=topic)
            return json.dumps(payload, ensure_ascii=True)
        except (RuntimeCommandError, ValueError) as exc:
            return f"❌ Error: {exc}"

    def get_camera_frame_data(self, container_name: str = "", topic: str = "") -> dict[str, object]:
        runtime = self.runtime(container_name=container_name)
        resolved_topic = topic.strip() or _default_camera_topic()
        if not resolved_topic:
            camera_topics = runtime.status().camera_topics
            if camera_topics:
                resolved_topic = camera_topics[0]
        capture = runtime.capture_camera_frame(topic=resolved_topic)
        return capture.to_dict()

    def start_recording(self, drone_id: str = "", interval: str = "") -> str:
        try:
            drone_name = drone_id.strip() or DEFAULT_DRONE_ID
            interval_s = _parse_float(interval, default=2.0, minimum=0.2, field_name="interval")
            summary = self.recordings.start(drone_id=drone_name, interval_s=interval_s)
            return (
                f"✅ Recording started for {summary['drone_id']}.\n"
                f"Recording ID: {summary['recording_id']}\n"
                f"Interval: {summary['interval_s']:.1f}s"
            )
        except ValueError as exc:
            return f"❌ Error: {exc}"

    def stop_recording(self, drone_id: str = "", recording_id: str = "") -> str:
        try:
            summary = self.recordings.stop(
                drone_id=drone_id.strip(),
                recording_id=recording_id.strip(),
            )
            return (
                f"✅ Recording stopped.\n"
                f"Recording ID: {summary['recording_id']}\n"
                f"Samples: {summary['sample_count']}"
            )
        except ValueError as exc:
            return f"❌ Error: {exc}"

    def list_recordings(self) -> str:
        recordings = self.list_recordings_data()
        if not recordings:
            return "No recordings found."
        return json.dumps(recordings, ensure_ascii=True)

    def list_recordings_data(self) -> list[dict[str, object]]:
        combined = self.recordings.list_recordings()
        active = {item["recording_id"]: item for item in self.recordings.active_recordings()}
        for item in combined:
            if item["recording_id"] in active:
                item["active"] = True
        return combined

    def get_recording(self, recording_id: str = "") -> str:
        if not recording_id.strip():
            return "❌ Error: recording_id is required."
        try:
            payload = self.recordings.get_recording(recording_id.strip())
            return json.dumps(payload, ensure_ascii=True)
        except ValueError as exc:
            return f"❌ Error: {exc}"

    def get_recording_data(self, recording_id: str) -> dict[str, object]:
        return self.recordings.get_recording(recording_id)

    def inspect_area(
        self,
        polygon_json: str = "",
        altitude: str = "",
        strip_spacing: str = "",
        waypoint_spacing: str = "",
        camera_topic: str = "",
        drone_id: str = "",
    ) -> str:
        if not polygon_json.strip():
            return "❌ Error: polygon_json is required."
        try:
            polygon = self._parse_polygon_json(polygon_json)
            altitude_m = _parse_float(altitude, default=20.0, minimum=1.0, field_name="altitude")
            strip_spacing_m = _parse_float(strip_spacing, default=25.0, minimum=1.0, field_name="strip_spacing")
            waypoint_spacing_m = _parse_float(
                waypoint_spacing,
                default=25.0,
                minimum=1.0,
                field_name="waypoint_spacing",
            )
            waypoints = generate_lawnmower_pattern(
                polygon,
                strip_spacing_m=strip_spacing_m,
                waypoint_spacing_m=waypoint_spacing_m,
            )
            if not waypoints:
                raise ValueError("Inspection pattern did not produce any waypoints.")

            drone_name = drone_id.strip() or DEFAULT_DRONE_ID
            results: list[dict[str, object]] = []
            captures: list[dict[str, object]] = []
            for waypoint in waypoints:
                command_result = self.drone.go_to_location(
                    waypoint.latitude_deg,
                    waypoint.longitude_deg,
                    altitude_m=altitude_m,
                    drone_id=drone_name,
                )
                if command_result.startswith("❌"):
                    raise ValueError(command_result)
                arrival = self.drone.wait_until_arrival(
                    drone_id=drone_name,
                    latitude_deg=waypoint.latitude_deg,
                    longitude_deg=waypoint.longitude_deg,
                    altitude_m=altitude_m,
                )
                results.append(arrival.to_dict())
                captures.append(self.get_camera_frame_data(topic=camera_topic))

            payload = {
                "ok": True,
                "drone_id": drone_name,
                "waypoint_count": len(waypoints),
                "waypoints": [point.to_dict() for point in waypoints],
                "telemetry": results,
                "captures": captures,
            }
            return json.dumps(payload, ensure_ascii=True)
        except (RuntimeCommandError, TimeoutError, ValueError) as exc:
            return f"❌ Error: {exc}"

    def _parse_polygon_json(self, polygon_json: str) -> list[GeoPoint]:
        parsed = json.loads(polygon_json)
        if not isinstance(parsed, list):
            raise ValueError("polygon_json must decode to a list of points.")
        polygon: list[GeoPoint] = []
        for point in parsed:
            if not isinstance(point, dict):
                raise ValueError("Each polygon point must be an object.")
            latitude = point.get("latitude_deg", point.get("latitude", point.get("lat")))
            longitude = point.get("longitude_deg", point.get("longitude", point.get("lon")))
            if latitude is None or longitude is None:
                raise ValueError("Each polygon point requires latitude and longitude fields.")
            polygon.append(GeoPoint(latitude_deg=float(latitude), longitude_deg=float(longitude)))
        return polygon

    def _format_runtime_status(self, heading: str, status) -> str:
        camera_topics = "\n".join(f"- {topic}" for topic in status.camera_topics) or "- <none>"
        plugin_errors = "\n".join(f"- {error}" for error in status.plugin_errors) or "- <none>"
        gui_windows = "\n".join(f"- {window}" for window in status.gui_windows) or "- <none>"
        gui_blockers = "\n".join(f"- {window}" for window in status.gui_blockers) or "- <none>"
        return (
            f"{heading}\n"
            f"Image: {status.image}\n"
            f"Image Present: {'yes' if status.image_present else 'no'}\n"
            f"Container: {status.container_name}\n"
            f"Running: {'yes' if status.running else 'no'}\n"
            f"Ready: {'yes' if status.ready else 'no'}\n"
            f"Camera Ready: {'yes' if status.camera_ready else 'no'}\n"
            f"GUI Ready: {'yes' if status.gui_ready else 'no'}\n"
            f"Status: {status.status_text or '<not running>'}\n"
            f"Camera Topics:\n{camera_topics}\n"
            f"Plugin Errors:\n{plugin_errors}\n"
            f"GUI Windows:\n{gui_windows}\n"
            f"GUI Blockers:\n{gui_blockers}"
        )
