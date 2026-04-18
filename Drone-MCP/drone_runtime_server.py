#!/usr/bin/env python3

"""Deterministic MCP server for simulator runtime control."""

import logging
import sys
from pathlib import Path

from mcp.server.fastmcp import FastMCP


ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from drone_mcp.runtime_tool_service import RuntimeToolService


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("drone-runtime-mcp")

mcp = FastMCP("drone-runtime")
service = RuntimeToolService()


@mcp.tool()
def start_simulation(
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
    """Start the simulator image and wait until runtime health is ready."""
    logger.info("start_simulation called for image=%s container=%s", image, container_name)
    return service.start_simulation(
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
        timeout=timeout,
    )


@mcp.tool()
def stop_simulation(container_name: str = "") -> str:
    """Stop the active simulator container and report the resulting state."""
    logger.info("stop_simulation called for container=%s", container_name)
    return service.stop_simulation(container_name=container_name)


@mcp.tool()
def reset_simulation(
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
    """Reset the simulator container and wait until it is healthy again."""
    logger.info("reset_simulation called for image=%s container=%s", image, container_name)
    return service.reset_simulation(
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
        timeout=timeout,
    )


@mcp.tool()
def get_runtime_health(image: str = "", container_name: str = "", model: str = "", environment: str = "") -> str:
    """Return image presence, runtime state, readiness, and camera topic health."""
    logger.info("get_runtime_health called for image=%s container=%s", image, container_name)
    return service.get_runtime_health(image=image, container_name=container_name, model=model, environment=environment)


@mcp.tool()
def get_simulation_logs(container_name: str = "", lines: str = "") -> str:
    """Return recent simulator logs from the selected container."""
    logger.info("get_simulation_logs called for container=%s lines=%s", container_name, lines)
    return service.get_simulation_logs(container_name=container_name, lines=lines)


# ------------------------------------------------------------------
# Flight control tools
# ------------------------------------------------------------------


@mcp.tool()
def connect_drone(address: str = "", drone_id: str = "") -> str:
    """Connect to the PX4 autopilot via MAVSDK. Must be called before any flight command."""
    logger.info("connect_drone called drone_id=%s address=%s", drone_id, address)
    return service.connect_drone(address=address, drone_id=drone_id)


@mcp.tool()
def list_drones() -> str:
    """List known drone ids for the current operator session."""
    logger.info("list_drones called")
    return service.list_drones()


@mcp.tool()
def arm_drone(drone_id: str = "") -> str:
    """Arm the drone's motors. Requires a GPS fix."""
    logger.info("arm_drone called drone_id=%s", drone_id)
    return service.arm_drone(drone_id=drone_id)


@mcp.tool()
def takeoff(altitude: str = "", drone_id: str = "") -> str:
    """Arm the drone and take off to a specified altitude in metres."""
    logger.info("takeoff called drone_id=%s altitude=%s", drone_id, altitude)
    return service.takeoff(altitude=altitude, drone_id=drone_id)


@mcp.tool()
def land(drone_id: str = "") -> str:
    """Land the drone at its current position."""
    logger.info("land called drone_id=%s", drone_id)
    return service.land_drone(drone_id=drone_id)


@mcp.tool()
def go_to_location(
    latitude: str = "", longitude: str = "", altitude: str = "", yaw: str = "", drone_id: str = "",
) -> str:
    """Fly the drone to a GPS coordinate at a given altitude."""
    logger.info(
        "go_to_location called drone_id=%s lat=%s lon=%s alt=%s yaw=%s",
        drone_id, latitude, longitude, altitude, yaw,
    )
    return service.go_to_location(
        latitude=latitude,
        longitude=longitude,
        altitude=altitude,
        yaw=yaw,
        drone_id=drone_id,
    )


@mcp.tool()
def get_drone_status(drone_id: str = "") -> str:
    """Get the drone's current telemetry: position, altitude, battery, flight mode, armed state."""
    logger.info("get_drone_status called drone_id=%s", drone_id)
    return service.get_drone_status(drone_id=drone_id)


@mcp.tool()
def hold_position(drone_id: str = "") -> str:
    """Switch to HOLD mode — the drone hovers in place."""
    logger.info("hold_position called drone_id=%s", drone_id)
    return service.hold_position(drone_id=drone_id)


@mcp.tool()
def return_to_launch(drone_id: str = "") -> str:
    """Trigger Return-to-Launch — the drone flies back to its home position and lands."""
    logger.info("return_to_launch called drone_id=%s", drone_id)
    return service.return_to_launch(drone_id=drone_id)


@mcp.tool()
def send_body_velocity(
    forward_m_s: str = "",
    right_m_s: str = "",
    down_m_s: str = "",
    yaw_rate_deg_s: str = "",
    drone_id: str = "",
) -> str:
    """Send a body-frame velocity command for precision/offboard control."""
    logger.info(
        "send_body_velocity called drone_id=%s forward=%s right=%s down=%s yaw_rate=%s",
        drone_id, forward_m_s, right_m_s, down_m_s, yaw_rate_deg_s,
    )
    return service.send_body_velocity(
        forward_m_s=forward_m_s,
        right_m_s=right_m_s,
        down_m_s=down_m_s,
        yaw_rate_deg_s=yaw_rate_deg_s,
        drone_id=drone_id,
    )


@mcp.tool()
def stop_body_velocity_control(drone_id: str = "") -> str:
    """Stop active offboard body-velocity control."""
    logger.info("stop_body_velocity_control called drone_id=%s", drone_id)
    return service.stop_body_velocity_control(drone_id=drone_id)


@mcp.tool()
def set_geofence(max_altitude: str = "", max_distance: str = "", min_battery: str = "") -> str:
    """Set altitude, distance, and battery reserve safety limits."""
    logger.info(
        "set_geofence called max_altitude=%s max_distance=%s min_battery=%s",
        max_altitude, max_distance, min_battery,
    )
    return service.set_geofence(
        max_altitude=max_altitude,
        max_distance=max_distance,
        min_battery=min_battery,
    )


@mcp.tool()
def get_camera_frame(container_name: str = "", topic: str = "") -> str:
    """Capture one camera frame from the Gazebo topic and return a JSON payload."""
    logger.info("get_camera_frame called container=%s topic=%s", container_name, topic)
    return service.get_camera_frame(container_name=container_name, topic=topic)


@mcp.tool()
def start_visual_tracking(
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
    """Start a server-side visual tracking loop."""
    logger.info("start_visual_tracking called drone_id=%s target_class=%s", drone_id, target_class)
    return service.start_visual_tracking(
        drone_id=drone_id,
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


@mcp.tool()
def run_visual_tracking_step(
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
    """Run one visual-tracking/autonomy cycle for debugging."""
    logger.info("run_visual_tracking_step called drone_id=%s target_class=%s", drone_id, target_class)
    return service.run_visual_tracking_step(
        drone_id=drone_id,
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


@mcp.tool()
def stop_visual_tracking(drone_id: str = "") -> str:
    """Stop the active visual tracking loop."""
    logger.info("stop_visual_tracking called drone_id=%s", drone_id)
    return service.stop_visual_tracking(drone_id=drone_id)


@mcp.tool()
def get_visual_tracking_status(drone_id: str = "") -> str:
    """Return current visual tracking state."""
    logger.info("get_visual_tracking_status called drone_id=%s", drone_id)
    return service.get_visual_tracking_status(drone_id=drone_id)


@mcp.tool()
def start_recording(drone_id: str = "", interval: str = "") -> str:
    """Start recording telemetry samples for a drone."""
    logger.info("start_recording called drone_id=%s interval=%s", drone_id, interval)
    return service.start_recording(drone_id=drone_id, interval=interval)


@mcp.tool()
def stop_recording(drone_id: str = "", recording_id: str = "") -> str:
    """Stop an active telemetry recording."""
    logger.info("stop_recording called drone_id=%s recording_id=%s", drone_id, recording_id)
    return service.stop_recording(drone_id=drone_id, recording_id=recording_id)


@mcp.tool()
def list_recordings() -> str:
    """List saved telemetry recordings."""
    logger.info("list_recordings called")
    return service.list_recordings()


@mcp.tool()
def get_recording(recording_id: str) -> str:
    """Return the full JSON payload for a saved telemetry recording."""
    logger.info("get_recording called recording_id=%s", recording_id)
    return service.get_recording(recording_id=recording_id)


@mcp.tool()
def inspect_area(
    polygon_json: str,
    altitude: str = "",
    strip_spacing: str = "",
    waypoint_spacing: str = "",
    camera_topic: str = "",
    drone_id: str = "",
) -> str:
    """Run a lawnmower inspection mission over a polygon and capture frames at each waypoint."""
    logger.info(
        "inspect_area called drone_id=%s altitude=%s strip_spacing=%s waypoint_spacing=%s",
        drone_id, altitude, strip_spacing, waypoint_spacing,
    )
    return service.inspect_area(
        polygon_json=polygon_json,
        altitude=altitude,
        strip_spacing=strip_spacing,
        waypoint_spacing=waypoint_spacing,
        camera_topic=camera_topic,
        drone_id=drone_id,
    )


if __name__ == "__main__":
    logger.info("Starting drone runtime MCP server...")
    try:
        mcp.run(transport="stdio")
    except Exception as exc:
        logger.error("Server error: %s", exc, exc_info=True)
        sys.exit(1)
