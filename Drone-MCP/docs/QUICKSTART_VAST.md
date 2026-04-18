# Drone-MCP on Vast.ai — Quickstart

Get a PX4 drone simulation running on a remote GPU in **3 steps**.

---

## Prerequisites

- **Windows** with PowerShell and `ssh` (OpenSSH is built-in on Windows 10/11)
- **Python 3.12+** installed locally
- **SSH key for Vast.ai** — your private key (e.g. `~/.ssh/vast_key`)
- **OpenRouter API key** — for the LLM chat operator ([openrouter.ai](https://openrouter.ai))

---

## Step 1: Rent a GPU Instance

1. Go to [vast.ai/console/create](https://cloud.vast.ai/console/create)
2. Pick any instance with:
   - **GPU**: NVIDIA with ≥8 GB VRAM (e.g. RTX 3090, A4000, A5000)
   - **Docker**: enabled (default)
   - **Image**: `ubuntu:22.04` or any base image
   - **Disk**: ≥30 GB
3. Note the **SSH command** from the instance page (e.g. `ssh -p 38092 root@74.x.x.x`)

---

## Step 2: Deploy (one-time)

From the `Drone-MCP` directory, run:

```powershell
python scripts/deploy_vast_vm.py `
  --host 74.x.x.x `
  --port 38092 `
  --ssh-key ~/.ssh/vast_key `
  --openrouter-env-file path/to/your/.env
```

> The `.env` file should contain: `OPENROUTER_KEY=sk-or-...`

This will:
1. Upload the codebase to the VM
2. Install Docker if needed
3. Build the sim and operator Docker images
4. Start the operator web server
5. **Auto-start the Gazebo simulation**
6. Save your connection info for next time

☕ First deploy takes ~10 minutes (Docker image builds). Subsequent deploys are faster.

---

## Step 3: Connect

After deploy, or any time you want to reconnect:

```powershell
.\scripts\vast_connect.ps1
```

That's it. This will:
- Open an SSH tunnel to your Vast.ai instance
- Launch your browser to the operator UI
- Keep the tunnel alive until you press `Ctrl+C`

---

## What You'll See

### Operator UI (`http://127.0.0.1:8080`)

The main interface with:
- **Live Gazebo viewport** — 3D simulation streamed via VNC
- **Chat panel** — talk to the LLM to control the drone

### Example Chat Commands

| You say | What happens |
|---------|-------------|
| "Connect to the drone" | MAVSDK connects to PX4 |
| "Take off to 10 meters" | Arms → takeoff → confirms altitude |
| "Fly to latitude 47.40, longitude 8.55" | GPS waypoint navigation |
| "What's the drone status?" | Position, battery, flight mode |
| "Hold position" | Hovers in place |
| "Return to launch" | Flies home and lands |
| "Land" | Lands at current position |
| "Start the simulation" | (Re)starts the Gazebo sim |
| "Stop the simulation" | Stops the sim container |

---

## Reconnecting After a Break

Your Vast.ai instance stays running. Just re-run:

```powershell
.\scripts\vast_connect.ps1
```

The simulation will still be running from last time.

---

## Switching to a New Vast.ai Instance

If you destroy and create a new instance, just re-run Step 2 with the new IP and port. The deploy script updates `.vast-connection.json` automatically.

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Tunnel won't connect | Check the instance is running on Vast.ai. Run `ssh -p PORT root@HOST` manually to test. |
| Gazebo viewport is black | Wait 20-30 seconds — the GPU renderer takes time to initialize. |
| Chat says "OpenRouter key not configured" | Re-deploy with `--openrouter-env-file`. |
| "Port already in use" warning | Another tunnel is running. Close it first (`Ctrl+C` in its terminal). |
| Slow/jerky Gazebo | Normal over WAN. For better quality, install [TurboVNC Viewer](https://turbovnc.org) and connect to `localhost::5900`. |

---

## File Layout Reference

```
Drone-MCP/
├── scripts/
│   ├── deploy_vast_vm.py        # One-time deploy to Vast.ai
│   ├── vast_connect.ps1         # One-click connect (after deploy)
│   └── open_vast_vm_tunnel.ps1  # Manual tunnel (legacy)
├── docker/
│   ├── sim-visual.Dockerfile    # Gazebo + VirtualGL + TurboVNC
│   └── operator-web.Dockerfile  # FastAPI operator + chat
├── src/drone_mcp/
│   ├── flight_control.py        # MAVSDK drone controller
│   ├── runtime_tool_service.py  # MCP tool definitions
│   └── operator_chat.py         # LLM chat engine
├── ui/                          # Operator web frontend
└── .vast-connection.json        # Auto-generated (gitignored)
```
