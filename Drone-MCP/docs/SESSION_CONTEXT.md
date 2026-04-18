# Drone-MCP Session Context

This is the working handoff for resuming the project without relying on chat history.

## 1. Mission

- Build a deterministic MCP-based drone control system.
- Use Vast.ai for heavy compute and remote simulation.
- Keep the system fully simulated until the simulator, runtime, and visual control path are proven.
- Do not hand back visual or runtime behavior unless it has been verified with tests or a live smoke run.
- Avoid assumptions. Ask before guessing when the answer is not obvious from the repo.

## 2. What The User Wants

- A drone simulation that can be controlled through MCP tools.
- A visual path, not just backend health.
- A scalable design that can later grow into broader drone control.
- Heavy compute on Vast.ai rather than local resources.
- Bite-sized work with tests before each new step.
- No destructive cleanup of machines the assistant did not create.

## 3. Operating Rules

- Never destroy a Vast instance unless it was created in this session or the user explicitly approves that exact machine.
- Prefer the smallest valid slice that can be tested end to end.
- Treat simulator readiness as stricter than “container is up”.
- If the GUI is black, missing, or blocked by a popup, do not report the stack as visually ready.
- Keep the MCP surface deterministic and simple.
- When something fails, fix the acceptance test boundary before claiming success.

## 4. Current Repository Shape

The repo already contains the runtime, visual, operator, and Vast deployment pieces.

### Runtime and MCP-related code

- `src/drone_mcp/sim_runtime.py`
- `src/drone_mcp/runtime_tool_service.py`
- `src/drone_mcp/operator_chat.py`
- `drone_runtime_server.py`
- `visual_operator_server.py`

### Vast deployment support

- `src/drone_mcp/vast_vm.py`
- `scripts/deploy_vast_vm.py`
- `scripts/bootstrap_vast_vm.sh`
- `scripts/run_remote_operator_stack.sh`
- `scripts/open_vast_vm_tunnel.ps1`

### Simulator and operator images

- `docker/sim-monocam.Dockerfile`
- `docker/sim-visual.Dockerfile`
- `docker/operator-web.Dockerfile`
- `docker/mcp-server.Dockerfile`
- `docker/visual-entrypoint.sh`

### Smoke tests

- `scripts/smoke_test_monocam.py`
- `scripts/smoke_test_runtime_mcp.py`
- `scripts/smoke_test_visual_sim.py`
- `scripts/smoke_test_operator_web.py`

### Tests

- `tests/test_sim_runtime.py`
- `tests/test_runtime_tool_service.py`
- `tests/test_vast_vm.py`
- `tests/test_operator_chat.py`

### UI

- `ui/index.html`
- `ui/app.js`
- `ui/styles.css`

## 5. What Has Already Been Proven

### Local simulator proof

- The monocam simulator image was smoke-tested locally earlier in the session.
- PX4/Gazebo camera topics were verified.
- The local runtime layer passed unit tests.

### Local MCP proof

- The runtime MCP server was implemented and smoke-tested.
- The deterministic tool surface exposes runtime-only tools.

### Remote Vast proof

- A Vast VM was successfully leased and used for remote deployment work.
- Docker was installed and used on the VM.
- The operator stack was deployed remotely.
- Remote health endpoints were reachable through a local tunnel.

## 6. Current Remote Machine

At the last verified state, the active machine was:

- VM id: `34614727`
- Label: `drone-mcp-vm-visual`
- SSH host: `85.218.235.6`
- SSH port: `39506`

This was the only active remote machine when the work stopped.

## 7. Remote Topology

The remote machine is a Vast VM, not a plain container host.

What is running conceptually:

- a Dockerized operator web container
- a Dockerized visual simulator container
- a local tunnel back to `127.0.0.1:8080` on the workstation
- noVNC on port `6080`
- raw VNC on port `5900`

Important detail:

- The remote stack should not publish unnecessary UDP simulator ports unless a slice explicitly needs them.
- Earlier port conflicts came from publishing `14550` unnecessarily.

## 8. Main Failure History

### Black screen

The user reported that the UI was only showing a black screen.

Root cause discovered:

- The simulator container was running the PX4/Gazebo server path.
- The Gazebo GUI client was not actually being started initially.
- A black screen was therefore expected.

### Blocking popup

A Fluxbox wallpaper-helper message appeared in the desktop environment.

Observed behavior:

- `xmessage` warned about installing `Eterm` / `Esetroot`.
- This did not crash the simulator, but it polluted the desktop and obscured the visual experience.

### Port conflict

The user later reported a failure involving `14550` already being allocated.

Root cause discovered:

- The visual simulator container was exposing unnecessary ports.
- Repeated starts or existing containers could collide on the UDP bind.

### Incomplete readiness criteria

The old readiness definition was too weak.

It only required:

- container running
- no plugin errors
- camera topics present

That was not enough for a visual stack.

## 9. What Was Patched

The simulator readiness boundary was tightened.

### `src/drone_mcp/sim_runtime.py`

Added visual readiness tracking:

- `gui_ready`
- `gui_windows`
- `gui_blockers`

The runtime now checks:

- whether the Gazebo GUI window exists
- whether a blocking `xmessage` popup is present

The runtime only reports `ready` when:

- the container is running
- there are no plugin errors
- camera topics exist
- GUI readiness is satisfied when required

### `src/drone_mcp/runtime_tool_service.py`

The operator-facing runtime tool output now reports:

- `Ready`
- `GUI Ready`
- camera topics
- plugin errors
- GUI windows
- GUI blockers

### Visual startup and smoke test hardening

The visual smoke path now fails if:

- the Gazebo GUI window does not appear
- an `xmessage` popup remains present

### Remote stack startup

The remote startup scripts were updated to pass the stricter GUI requirement.

### Unit test coverage

The unit tests were extended to cover:

- GUI-ready status
- GUI popup blocker detection
- no GUI window detection
- the stricter readiness failure path

## 10. Last Verified Local State

The last completed local verification was:

- `python -m unittest discover -s tests -p "test_*.py" -v`

That passed after the GUI-readiness patch.

The visual smoke test was not fully completed before the interruption.

## 11. Exact Commands Used Often

### Local tests

```powershell
python -m unittest discover -s tests -p "test_*.py" -v
```

### Visual smoke test

```powershell
python scripts\smoke_test_visual_sim.py
```

### Remote deployment

```powershell
python scripts\deploy_vast_vm.py --host 85.218.235.6 --port 39506 --ssh-key "$HOME\.ssh\vast_key" --openrouter-env-file "D:\downloads\Yolo\.env"
```

### SSH to the VM

```powershell
ssh -i "$HOME\.ssh\vast_key" -p 39506 root@85.218.235.6
```

### Docker inspection on the VM

```powershell
DOCKER_API_VERSION=1.43 docker ps -a
```

## 12. Resume Strategy

1. Re-run the visual smoke test locally or on the VM.
2. Confirm the Gazebo GUI window exists in the X display tree.
3. Confirm no `xmessage` popup is present.
4. Confirm runtime health reports both camera readiness and GUI readiness.
5. Re-run remote deployment only after the visual smoke test passes.
6. Then move on to the next slice of functionality.

## 13. Good Next Slices

Choose one after the visual stack is stable:

- ROS 2 telemetry bridge and introspection
- deterministic mission tools layered on top of runtime
- noVNC/UI hardening so the view is easier to operate
- drone motion primitives exposed through MCP
- simulator observability endpoints for logs and state

## 14. Files To Inspect First On Resume

- [src/drone_mcp/sim_runtime.py](/D:/downloads/Yolo/Drone-MCP/src/drone_mcp/sim_runtime.py)
- [src/drone_mcp/runtime_tool_service.py](/D:/downloads/Yolo/Drone-MCP/src/drone_mcp/runtime_tool_service.py)
- [docker/visual-entrypoint.sh](/D:/downloads/Yolo/Drone-MCP/docker/visual-entrypoint.sh)
- [scripts/smoke_test_visual_sim.py](/D:/downloads/Yolo/Drone-MCP/scripts/smoke_test_visual_sim.py)
- [scripts/smoke_test_operator_web.py](/D:/downloads/Yolo/Drone-MCP/scripts/smoke_test_operator_web.py)
- [scripts/run_remote_operator_stack.sh](/D:/downloads/Yolo/Drone-MCP/scripts/run_remote_operator_stack.sh)
- [scripts/deploy_vast_vm.py](/D:/downloads/Yolo/Drone-MCP/scripts/deploy_vast_vm.py)

