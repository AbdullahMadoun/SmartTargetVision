# Natural Language Drone Agent — Coding Agent Implementation Plan

> **Project:** MCP-based autonomous drone agent with onboard vision, simulated in PX4/Gazebo on a remote Vast.ai GPU instance, viewable from a weak laptop.

***

## Overview

This document is a step-by-step implementation plan for a coding agent to build an end-to-end autonomous drone system. The agent receives natural language commands, decomposes them into structured missions via MCP tool calls, runs onboard vision to identify and track a target, and executes mission behaviors inside a PX4 + Gazebo simulation hosted on a remote Vast.ai Docker instance.

**Phases:**
1. Remote Infrastructure (Vast.ai Docker + VNC)
2. Simulation Environment (PX4 SITL + Gazebo + ROS 2)
3. Vision Pipeline (YOLOE onboard camera detection + tracking)
4. Mission Behavior Layer (state machine, action primitives)
5. LLM + MCP Agent Layer (natural language to tool calls to mission)

***

## Phase 1 — Remote Infrastructure

### Goal
Provision a reproducible remote development and simulation environment on Vast.ai, accessible via SSH and viewable via VNC from a weak laptop.

### Directory Structure

```
drone-agent/
├── docker/
│   ├── Dockerfile
│   ├── docker-compose.yml
│   └── entrypoint.sh
├── sim/                     # Phase 2
├── vision/                  # Phase 3
├── behaviors/               # Phase 4
├── agent/                   # Phase 5
└── README.md
```

### 1.1 Dockerfile

```dockerfile
FROM nvidia/cuda:12.1.0-devel-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV ROS_DISTRO=humble

RUN apt-get update && apt-get install -y \
    git curl wget python3-pip python3-dev \
    lsb-release gnupg2 sudo \
    x11vnc xvfb tigervnc-standalone-server \
    dbus-x11 xfce4 xfce4-terminal \
    mesa-utils libgl1-mesa-glx \
    && rm -rf /var/lib/apt/lists/*

# ROS 2 Humble
RUN curl -sSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.key \
    -o /usr/share/keyrings/ros-archive-keyring.gpg && \
    echo 'deb [arch=amd64 signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] http://packages.ros.org/ros2/ubuntu jammy main' \
    > /etc/apt/sources.list.d/ros2.list && \
    apt-get update && apt-get install -y \
    ros-humble-desktop \
    ros-humble-ros-gz-bridge \
    ros-humble-cv-bridge \
    ros-humble-image-transport \
    python3-colcon-common-extensions \
    && rm -rf /var/lib/apt/lists/*

# PX4 Autopilot (SITL)
RUN git clone https://github.com/PX4/PX4-Autopilot.git --recursive /px4 && \
    cd /px4 && bash ./Tools/setup/ubuntu.sh --no-nuttx

# Gazebo Harmonic
RUN curl -sSL https://packages.osrfoundation.org/gazebo.gpg \
    -o /usr/share/keyrings/pkgs-osrf-archive-keyring.gpg && \
    echo 'deb [arch=amd64 signed-by=/usr/share/keyrings/pkgs-osrf-archive-keyring.gpg] http://packages.osrfoundation.org/gazebo/ubuntu-stable jammy main' \
    > /etc/apt/sources.list.d/gazebo-stable.list && \
    apt-get update && apt-get install -y gz-harmonic && \
    rm -rf /var/lib/apt/lists/*

# Python AI stack
RUN pip3 install --no-cache-dir \
    ultralytics mavsdk openai mcp \
    numpy opencv-python-headless supervision \
    torch torchvision --index-url https://download.pytorch.org/whl/cu121

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
EXPOSE 5900 14550 8888
ENTRYPOINT ["/entrypoint.sh"]
```

### 1.2 entrypoint.sh

```bash
#!/bin/bash
export DISPLAY=:1
Xvfb :1 -screen 0 1920x1080x24 -ac +extension GLX +render -noreset &
sleep 2
startxfce4 &
x11vnc -display :1 -nopw -listen 0.0.0.0 -xkb -forever &
source /opt/ros/humble/setup.bash
exec "$@"
```

### 1.3 docker-compose.yml

```yaml
version: '3.8'
services:
  drone-sim:
    build: ./docker
    runtime: nvidia
    environment:
      - NVIDIA_VISIBLE_DEVICES=all
      - DISPLAY=:1
    ports:
      - '5900:5900'
      - '14550:14550/udp'
      - '8888:8888'
    volumes:
      - ./sim:/workspace/sim
      - ./vision:/workspace/vision
      - ./behaviors:/workspace/behaviors
      - ./agent:/workspace/agent
    stdin_open: true
    tty: true
    command: bash
```

### 1.4 Laptop Access

```bash
# SSH tunnel VNC port to laptop
ssh -L 5900:localhost:5900 user@VAST_IP -p VAST_SSH_PORT
# Then connect any VNC viewer to localhost:5900
# Use VS Code Remote-SSH for code editing
```

***

## Phase 2 — Simulation Environment

### Goal
Spawn a camera-equipped quadcopter in Gazebo, connected to PX4 SITL and ROS 2, with named target objects in the scene.

### 2.1 PX4 + Gazebo Launch Script

Create `sim/launch_sim.sh`:

```bash
#!/bin/bash
source /opt/ros/humble/setup.bash
cd /px4
HEADLESS=0 make px4_sitl gz_x500_mono_cam &
sleep 10
ros2 run ros_gz_bridge parameter_bridge \
  /camera@sensor_msgs/msg/Image@gz.msgs.Image &
ros2 run ros_gz_bridge parameter_bridge \
  /camera_info@sensor_msgs/msg/CameraInfo@gz.msgs.CameraInfo &
echo '[SIM] Ready'
```

### 2.2 World File

Create `sim/worlds/drone_arena.world` as a standard Gazebo SDF file with:
- Flat ground plane with good ambient lighting.
- 3 named target models: `orange_cone`, `person_in_vest`, `red_backpack` using colored SDF primitives.
- Drone spawn point at origin with clear open space for search behavior.

### 2.3 Camera Bridge Node

Create `sim/ros2_ws/src/drone_sim/drone_sim/camera_bridge_node.py`:

```python
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image

class CameraBridgeNode(Node):
    def __init__(self):
        super().__init__('camera_bridge_node')
        self.sub = self.create_subscription(
            Image, '/camera', self.cb, 10)
        self.pub = self.create_publisher(
            Image, '/drone/frame', 10)
    def cb(self, msg):
        self.pub.publish(msg)

def main():
    rclpy.init()
    rclpy.spin(CameraBridgeNode())
```

***

## Phase 3 — Vision Pipeline

### Goal
A ROS 2 node that reads the simulated camera, runs YOLOE open-vocabulary detection, tracks detections, and publishes structured target observations every frame.

### 3.1 File Layout

```
vision/ros2_ws/src/drone_vision/drone_vision/
├── vision_node.py
├── detector.py
└── tracker.py
```

### 3.2 detector.py

```python
from ultralytics import YOLOE
import numpy as np

class DroneDetector:
    def __init__(self, model_size='yoloe-11s-seg.pt'):
        self.model = YOLOE(model_size)
        self.prompts_set = False

    def set_target_prompt(self, text_prompts: list):
        self.model.set_classes(text_prompts, self.model.get_text_pe(text_prompts))
        self.prompts_set = True

    def detect(self, frame: np.ndarray) -> list:
        if not self.prompts_set:
            return []
        results = self.model.predict(frame, verbose=False)
        detections = []
        for r in results:
            for box in r.boxes:
                detections.append({
                    'bbox': box.xyxy[0].tolist(),
                    'conf': float(box.conf[0]),
                    'class': self.model.names[int(box.cls[0])]
                })
        return detections
```

### 3.3 tracker.py

```python
import supervision as sv
import numpy as np

class DroneTracker:
    def __init__(self):
        self.tracker = sv.ByteTrack()

    def update(self, detections: list, frame_shape: tuple) -> list:
        if not detections:
            return []
        xyxy = np.array([d['bbox'] for d in detections])
        confs = np.array([d['conf'] for d in detections])
        sv_dets = sv.Detections(xyxy=xyxy, confidence=confs)
        tracked = self.tracker.update_with_detections(sv_dets)
        results = []
        for i, (box, conf) in enumerate(zip(tracked.xyxy, tracked.confidence)):
            results.append({
                'bbox': box.tolist(), 'conf': float(conf),
                'track_id': int(tracked.tracker_id[i]),
                'class': detections[i]['class'] if i < len(detections) else 'unknown'
            })
        return results
```

### 3.4 vision_node.py

```python
import rclpy, json
from rclpy.node import Node
from sensor_msgs.msg import Image
from std_msgs.msg import String
from cv_bridge import CvBridge
from .detector import DroneDetector
from .tracker import DroneTracker

class VisionNode(Node):
    def __init__(self):
        super().__init__('vision_node')
        self.bridge = CvBridge()
        self.detector = DroneDetector()
        self.tracker = DroneTracker()
        self.sub_frame = self.create_subscription(
            Image, '/drone/frame', self.frame_cb, 10)
        self.sub_prompt = self.create_subscription(
            String, '/drone/target_prompt', self.prompt_cb, 10)
        self.pub = self.create_publisher(
            String, '/drone/target_observation', 10)

    def prompt_cb(self, msg):
        prompts = json.loads(msg.data)
        self.detector.set_target_prompt(prompts)

    def frame_cb(self, msg):
        frame = self.bridge.imgmsg_to_cv2(msg, 'bgr8')
        dets = self.detector.detect(frame)
        tracked = self.tracker.update(dets, frame.shape)
        h, w = frame.shape[:2]
        if tracked:
            best = max(tracked, key=lambda d: d['conf'])
            cx = (best['bbox'][0] + best['bbox'][2]) / 2
            cy = (best['bbox'][1] + best['bbox'][3]) / 2
            area = (best['bbox'][2]-best['bbox'][0])*(best['bbox'][3]-best['bbox'][1])
            obs = {'detected': True, 'class': best['class'], 'conf': best['conf'],
                   'cx_norm': cx/w, 'cy_norm': cy/h, 'area_norm': area/(w*h),
                   'bbox': best['bbox']}
        else:
            obs = {'detected': False}
        self.pub.publish(String(data=json.dumps(obs)))
```

**Published topic**: `/drone/target_observation` — JSON every frame.

***

## Phase 4 — Mission Behavior Layer

### States

```
IDLE → SEARCHING → APPROACHING → ORBITING/INSPECTING → REPORTING → RETURNING
```

### 4.1 primitives.py

Create `behaviors/primitives.py`:

```python
import asyncio
from mavsdk import System
from mavsdk.offboard import VelocityBodyYawspeed

class DronePrimitives:
    def __init__(self, drone: System):
        self.drone = drone

    async def takeoff(self, altitude=3.0):
        await self.drone.action.arm()
        await self.drone.action.takeoff()
        await asyncio.sleep(5)

    async def return_home(self):
        await self.drone.action.return_to_launch()

    async def hover(self, duration=2.0):
        await self.drone.offboard.set_velocity_body(
            VelocityBodyYawspeed(0, 0, 0, 0))
        await asyncio.sleep(duration)

    async def search_spin(self, yaw_speed=15.0, duration=10.0):
        await self.drone.offboard.set_velocity_body(
            VelocityBodyYawspeed(0, 0, 0, yaw_speed))
        await asyncio.sleep(duration)

    async def approach_target(self, get_obs, target_area=0.08, kp_yaw=60.0, kp_fwd=0.4):
        # Visual servoing: center target and close distance until target_area reached
        while True:
            obs = get_obs()
            if not obs.get('detected'):
                await self.search_spin(yaw_speed=15.0, duration=0.5)
                continue
            yaw_err = (obs['cx_norm'] - 0.5) * kp_yaw
            area_err = target_area - obs['area_norm']
            forward = kp_fwd * area_err if area_err > 0 else 0.0
            await self.drone.offboard.set_velocity_body(
                VelocityBodyYawspeed(forward, 0, 0, yaw_err))
            await asyncio.sleep(0.1)
            if obs['area_norm'] >= target_area:
                break
        await self.hover(2.0)

    async def orbit_target(self, get_obs, duration=8.0, orbit_yaw=20.0):
        elapsed = 0.0
        while elapsed < duration:
            obs = get_obs()
            yaw_err = (obs['cx_norm'] - 0.5) * 50.0 if obs.get('detected') else 0.0
            await self.drone.offboard.set_velocity_body(
                VelocityBodyYawspeed(0, 1.5, 0, yaw_err + orbit_yaw))
            await asyncio.sleep(0.1)
            elapsed += 0.1

    async def capture_evidence(self, get_obs, n_frames=5) -> list:
        samples = []
        for _ in range(n_frames):
            obs = get_obs()
            if obs.get('detected'):
                samples.append({'conf': obs['conf'], 'bbox': obs['bbox']})
            await asyncio.sleep(0.5)
        return sorted(samples, key=lambda x: x['conf'], reverse=True)
```

### 4.2 mission_fsm.py

Create `behaviors/mission_fsm.py`:

```python
import asyncio, json
from enum import Enum
from mavsdk import System
from mavsdk.offboard import VelocityBodyYawspeed
from .primitives import DronePrimitives

class MissionState(Enum):
    IDLE        = 'idle'
    SEARCHING   = 'searching'
    APPROACHING = 'approaching'
    ORBITING    = 'orbiting'
    INSPECTING  = 'inspecting'
    REPORTING   = 'reporting'
    RETURNING   = 'returning'

class MissionFSM:
    def __init__(self):
        self.state = MissionState.IDLE
        self.latest_obs = {'detected': False}
        self.drone = None
        self.primitives = None

    async def connect(self, address='udp://:14540'):
        self.drone = System()
        await self.drone.connect(system_address=address)
        await self.drone.offboard.set_velocity_body(
            VelocityBodyYawspeed(0, 0, 0, 0))
        self.primitives = DronePrimitives(self.drone)

    def update_observation(self, obs_json: str):
        self.latest_obs = json.loads(obs_json)

    def get_obs(self):
        return self.latest_obs

    async def execute_mission(self, mission: dict) -> dict:
        # mission: {mission_type, target_class, safety_distance, orbit_duration}
        await self.primitives.takeoff()
        self.state = MissionState.SEARCHING
        await self.primitives.search_spin(duration=10.0)
        if not self.latest_obs.get('detected'):
            await self.primitives.return_home()
            return {'status': 'TARGET_NOT_FOUND'}
        self.state = MissionState.APPROACHING
        await self.primitives.approach_target(
            self.get_obs, target_area=mission.get('safety_distance', 0.08))
        mtype = mission.get('mission_type', 'inspect')
        evidence = []
        if mtype == 'orbit':
            self.state = MissionState.ORBITING
            await self.primitives.orbit_target(
                self.get_obs, duration=mission.get('orbit_duration', 8.0))
        if mtype in ('inspect', 'evidence', 'orbit'):
            self.state = MissionState.INSPECTING
            evidence = await self.primitives.capture_evidence(self.get_obs)
        self.state = MissionState.REPORTING
        result = {
            'status': 'TARGET_ACQUIRED',
            'class': mission['target_class'],
            'confidence': evidence[0]['conf'] if evidence else self.latest_obs.get('conf', 0.0),
            'evidence_frames': len(evidence)
        }
        print(f'[MISSION RESULT] {result}')
        self.state = MissionState.RETURNING
        await self.primitives.return_home()
        self.state = MissionState.IDLE
        return result
```

***

## Phase 5 — LLM + MCP Agent Layer

### 5.1 tools.py

Create `agent/tools.py`:

```python
TOOLS = [
    {
        'name': 'set_target_prompt',
        'description': 'Set visual search prompts. Provide 2-4 short discriminative noun phrases.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'prompts': {'type': 'array', 'items': {'type': 'string'}}
            },
            'required': ['prompts']
        }
    },
    {
        'name': 'execute_mission',
        'description': 'Command the drone to run a mission around the current target.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'mission_type': {'type': 'string', 'enum': ['approach','inspect','orbit','evidence']},
                'target_class': {'type': 'string'},
                'safety_distance': {'type': 'number'},
                'orbit_duration': {'type': 'number'}
            },
            'required': ['mission_type', 'target_class']
        }
    },
    {
        'name': 'get_mission_status',
        'description': 'Get current FSM state and latest target observation.',
        'input_schema': {'type': 'object', 'properties': {}}
    },
    {
        'name': 'abort_mission',
        'description': 'Halt mission and return drone home immediately.',
        'input_schema': {'type': 'object', 'properties': {}}
    }
]
```

### 5.2 runtime.py

Create `agent/runtime.py`:

```python
import rclpy, json
from rclpy.node import Node
from std_msgs.msg import String
from behaviors.mission_fsm import MissionFSM

class DroneRosNode(Node):
    def __init__(self, fsm: MissionFSM):
        super().__init__('drone_agent_node')
        self.fsm = fsm
        self.pub_prompt = self.create_publisher(String, '/drone/target_prompt', 10)
        self.sub_obs = self.create_subscription(
            String, '/drone/target_observation',
            lambda msg: fsm.update_observation(msg.data), 10)

fsm = MissionFSM()
ros_node = None

async def initialize():
    rclpy.init()
    global ros_node
    ros_node = DroneRosNode(fsm)
    await fsm.connect('udp://:14540')
```

### 5.3 llm_agent.py

Create `agent/llm_agent.py`:

```python
import asyncio, json
from openai import AsyncOpenAI
from .tools import TOOLS
from .runtime import fsm, ros_node

client = AsyncOpenAI()  # uses OPENAI_API_KEY env var

SYSTEM_PROMPT = '''
You are the mission commander for an autonomous drone.
Given a natural language command, always:
1. Call set_target_prompt with 2-4 short noun phrases describing the target visually.
2. Call execute_mission with appropriate parameters.
3. Call get_mission_status to confirm if needed.
4. Call abort_mission only if safety is at risk.
Mission types: approach, inspect, orbit, evidence.
'''

async def run_mission(command: str):
    messages = [
        {'role': 'system', 'content': SYSTEM_PROMPT},
        {'role': 'user', 'content': command}
    ]
    while True:
        response = await client.chat.completions.create(
            model='gpt-4o', messages=messages,
            tools=[{'type': 'function', 'function': {
                'name': t['name'], 'description': t['description'],
                'parameters': t['input_schema']}} for t in TOOLS],
            tool_choice='auto'
        )
        msg = response.choices[0]