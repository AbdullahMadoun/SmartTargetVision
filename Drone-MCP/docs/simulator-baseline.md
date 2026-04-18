# Simulator Baseline Findings

## Why This Exists

The simulator is the first hard dependency for the rest of the project. We do not add MCP orchestration, mission logic, or detector integration until the simulator path is proven.

## Verified Findings

### Baseline Container

The official PX4 Gazebo image starts PX4 and Gazebo successfully for the plain x500 model.

### Monocular Camera Failure

The `gz_x500_mono_cam` model does not work cleanly on the official `px4io/px4-sitl-gazebo:latest` image as pulled on `2026-04-11`.

Observed failure pattern:

- Gazebo starts
- the world becomes ready
- the monocam model is selected
- camera-related plugins fail to load because runtime libraries are missing

The missing library chain observed during probing included:

- `libopencv_imgproc.so.406`
- `libgstreamer-1.0.so.0`
- `libopencv_video.so.406`
- `libgstapp-1.0.so.0`

## Design Decision

The first custom image in this repository derives from the official PX4 Gazebo image and installs the missing runtime packages needed by the monocam stack.

This keeps the slice narrow:

- we do not replace PX4 packaging yet
- we do not compile PX4 from source yet
- we do not add ROS 2 or MCP into this slice yet

## Acceptance Criteria For This Slice

The slice is considered valid only if all of the following are true:

1. The derived image builds locally.
2. A container launched with `PX4_SIM_MODEL=gz_x500_mono_cam` reaches a running state.
3. Logs do not contain Gazebo plugin load failures.
4. Gazebo topics include a camera sensor topic, not just `camera_imu`.

## Current Runtime Layer

The repository now includes a deterministic runtime layer that can:

- build the verified simulator image
- start the simulator container
- stop the simulator container
- reset the simulator container
- report runtime health
- tail simulator logs

This runtime is implemented in Python so later MCP tools can call stable internal operations rather than shell scripts.

## Current MCP Layer

The repository now also includes a runtime-only FastMCP server that exposes exactly five verified operations:

- `start_simulation`
- `stop_simulation`
- `reset_simulation`
- `get_runtime_health`
- `get_simulation_logs`

This MCP layer does not introduce new simulator behavior. It only wraps the runtime module and returns formatted text results over `stdio`.

## Consequence For The Next Slice

Now that simulator lifecycle, readiness, and MCP transport are real, the next slice can add either:

1. ROS 2 and telemetry exposure under the same deterministic runtime boundary, or
2. mission-level MCP tools that build on this runtime surface without leaking raw control details too early
