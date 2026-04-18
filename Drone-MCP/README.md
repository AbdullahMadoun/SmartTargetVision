# Drone-MCP

This repository is being built in small verified slices.

## Current Slice

The current slice adds a deterministic MCP layer over the verified simulator runtime:

- derive a reproducible PX4 Gazebo image for the monocular-camera model
- provide a Python runtime layer for build, start, stop, reset, status, and logs
- expose only 5 runtime MCP tools over FastMCP stdio
- prove the simulator starts cleanly
- prove the camera path exists before adding mission logic

## What Is Verified In This Slice

- the base PX4 Gazebo container can start PX4 and Gazebo
- the `gz_x500_mono_cam` path needs extra runtime libraries on top of the official image
- a local smoke test can build, run, inspect, and fail fast on simulator startup issues

## Smoke Test

```powershell
python scripts/smoke_test_monocam.py
python scripts/smoke_test_runtime_mcp.py
```

## Visual Smoke Test

```powershell
python scripts/smoke_test_visual_sim.py
python scripts/smoke_test_operator_web.py
```

The visual smoke path now fails unless all of these are true:

- the noVNC page is reachable
- the raw VNC port responds with an RFB banner
- the websockify websocket upgrade succeeds
- a Gazebo GUI window exists with sane geometry
- no blocking `xmessage` popup is present
- an X-display frame capture shows real rendered signal instead of a flat or blank frame

## Runtime Control

```powershell
python scripts/manage_simulator.py build
python scripts/manage_simulator.py start
python scripts/manage_simulator.py wait-ready
python scripts/manage_simulator.py status
python scripts/manage_simulator.py stop
```

## MCP Server

```powershell
docker build -f docker/mcp-server.Dockerfile -t drone-mcp/runtime-mcp:local .
docker run --rm -i -v /var/run/docker.sock:/var/run/docker.sock drone-mcp/runtime-mcp:local
```

The MCP server exposes:

- `start_simulation`
- `stop_simulation`
- `reset_simulation`
- `get_runtime_health`
- `get_simulation_logs`

## Unit Tests

```powershell
python -m unittest discover -s tests -p "test_*.py" -v
```

## Compose Run

```powershell
docker compose -f docker/compose.sim.yml up --build
```

## Vast VM Deploy

The repo now includes a repeatable Vast VM deployment path for the visual operator stack.

Deploy to the active VM:

```powershell
python scripts/deploy_vast_vm.py --host 85.218.235.6 --port 39506 --ssh-key $HOME\.ssh\vast_key --openrouter-env-file D:\downloads\Yolo\.env
```

Open tunnels from another terminal:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/open_vast_vm_tunnel.ps1 -Host 85.218.235.6 -Port 39506 -KeyPath $HOME\.ssh\vast_key
```

Then open:

```text
http://127.0.0.1:8080
```
