#!/bin/sh
set -eu

export DISPLAY="${DISPLAY:-:0}"
export HEADLESS="${HEADLESS:-0}"
REQUIRED_MODEL="${DRONE_MCP_REQUIRED_MODEL:-x500_mono_cam_0}"
MODEL_WAIT_SECONDS="${DRONE_MCP_MODEL_WAIT_SECONDS:-120}"

case "$MODEL_WAIT_SECONDS" in
  ''|*[!0-9]*)
    MODEL_WAIT_SECONDS=120
    ;;
esac

# ── Virtual Desktop ───────────────────────────────────────────────────
# Default 1920x1080 for a crisp viewport (override via VNC_GEOMETRY).
VNC_GEOMETRY="${VNC_GEOMETRY:-1920x1080}"
rm -rf /tmp/.X11-unix/X* /tmp/.X*-lock
/opt/TurboVNC/bin/vncserver "$DISPLAY" \
  -geometry "$VNC_GEOMETRY" -depth 24 \
  -securitytypes none \
  -noxdamage \
  -jpeg yes -quality 90 \
  -alr 1 -alrqual 80 \
  >/tmp/vncserver.log 2>&1

sleep 2
fluxbox >/tmp/fluxbox.log 2>&1 &
FLUXBOX_PID=$!

# Give the virtual desktop a clean background and kill popups.
sleep 1
xsetroot -display "$DISPLAY" -solid "#11161c" >/tmp/xsetroot.log 2>&1 || true
pkill xmessage 2>/dev/null || true

# ── WebSocket bridge for noVNC ────────────────────────────────────────
websockify --web=/usr/share/novnc/ 6080 localhost:5900 >/tmp/websockify.log 2>&1 &
WEBSOCKIFY_PID=$!

# ── PX4 / Gazebo headless server ─────────────────────────────────────
/opt/px4-gazebo/bin/px4-entrypoint.sh "$@" &
PX4_PID=$!
GZ_GUI_PID=""

cleanup() {
  kill "$GZ_GUI_PID" "$PX4_PID" "$WEBSOCKIFY_PID" "$FLUXBOX_PID" 2>/dev/null || true
  /opt/TurboVNC/bin/vncserver -kill "$DISPLAY" 2>/dev/null || true
}

trap cleanup EXIT INT TERM

wait_for_model() {
  model_name="$1"
  state_service="/world/default/state"
  i=0
  while [ "$i" -lt "$MODEL_WAIT_SECONDS" ]; do
    state_output="$(gz service -s "$state_service" --reqtype gz.msgs.Empty --reptype gz.msgs.SerializedStepMap --timeout 5000 --req '' 2>/dev/null || true)"
    if printf '%s\n' "$state_output" | grep -Fq "$model_name"; then
      return 0
    fi

    if gz topic -l 2>/dev/null | grep -Fq "/model/$model_name/"; then
      return 0
    fi

    sleep 1
    i=$((i + 1))
  done

  return 1
}

if [ "$HEADLESS" = "0" ]; then
  if ! wait_for_model "$REQUIRED_MODEL"; then
    echo "Timed out waiting for required model: $REQUIRED_MODEL" >&2
    exit 1
  fi

  pkill xmessage 2>/dev/null || true

  # Launch Gazebo GUI with VirtualGL for GPU-accelerated rendering.
  DISPLAY="$DISPLAY" /opt/VirtualGL/bin/vglrun gz sim -g >/tmp/gz-gui.log 2>&1 &
  GZ_GUI_PID=$!

  # Wait for the GUI window to appear, then maximize it so it fills
  # the entire VNC desktop — no wasted black borders for the viewer.
  for _mw in $(seq 1 30); do
    if DISPLAY="$DISPLAY" xdotool search --name "Gazebo" 2>/dev/null | head -1 | grep -q .; then
      sleep 1
      DISPLAY="$DISPLAY" xdotool search --name "Gazebo" windowactivate --sync windowsize --sync 100% 100% windowmove --sync 0 0 2>/dev/null || true
      break
    fi
    sleep 1
  done &
fi

wait "$PX4_PID"

