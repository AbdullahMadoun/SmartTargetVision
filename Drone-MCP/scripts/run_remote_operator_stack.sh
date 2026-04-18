#!/bin/sh
set -eu

REPO_ROOT="${REPO_ROOT:-/opt/drone-mcp}"
OPERATOR_IMAGE="${OPERATOR_IMAGE:-drone-mcp/operator-web:remote}"
OPERATOR_CONTAINER="${OPERATOR_CONTAINER:-drone-mcp-operator-web}"
SIM_CONTAINER="${DRONE_MCP_SIM_CONTAINER:-drone-mcp-sim-visual}"
SIM_IMAGE="${DRONE_MCP_SIM_IMAGE:-drone-mcp/sim-visual:remote}"
SIM_DOCKERFILE="${DRONE_MCP_SIM_DOCKERFILE:-docker/sim-visual.Dockerfile}"
SIM_HEADLESS="${DRONE_MCP_SIM_HEADLESS:-0}"
SIM_REQUIRE_GUI="${DRONE_MCP_SIM_REQUIRE_GUI:-1}"
SIM_REQUIRE_CAMERA="${DRONE_MCP_SIM_REQUIRE_CAMERA:-0}"
SIM_PORTS="${DRONE_MCP_SIM_PORTS:-5900:5900,6080:6080,14540:14540/udp}"
SIM_NETWORK_HOST="${DRONE_MCP_SIM_NETWORK_HOST:-1}"
DOCKER_API_VERSION="${DOCKER_API_VERSION:-1.43}"

cd "$REPO_ROOT"

# ── Clean up any previous containers ──────────────────────────────────
DOCKER_API_VERSION="$DOCKER_API_VERSION" docker rm -f "$OPERATOR_CONTAINER" >/dev/null 2>&1 || true
DOCKER_API_VERSION="$DOCKER_API_VERSION" docker rm -f "$SIM_CONTAINER" >/dev/null 2>&1 || true

# ── Pre-build both images so first "Start" click is instant ───────────
echo "[build] Building sim image: $SIM_IMAGE ..."
DOCKER_API_VERSION="$DOCKER_API_VERSION" docker build -f "$SIM_DOCKERFILE" -t "$SIM_IMAGE" .

echo "[build] Building operator image: $OPERATOR_IMAGE ..."
DOCKER_API_VERSION="$DOCKER_API_VERSION" docker build -f docker/operator-web.Dockerfile -t "$OPERATOR_IMAGE" .

# ── Launch the operator container ─────────────────────────────────────
# --network host: required so MAVSDK in this container can reach PX4 in
# the sim container via localhost (both share the host network namespace).
set -- \
  docker run -d --restart unless-stopped \
  --name "$OPERATOR_CONTAINER" \
  --network host \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -e "DRONE_MCP_SIM_IMAGE=$SIM_IMAGE" \
  -e "DRONE_MCP_SIM_CONTAINER=$SIM_CONTAINER" \
  -e "DRONE_MCP_SIM_DOCKERFILE=$SIM_DOCKERFILE" \
  -e "DRONE_MCP_SIM_HEADLESS=$SIM_HEADLESS" \
  -e "DRONE_MCP_SIM_REQUIRE_GUI=$SIM_REQUIRE_GUI" \
  -e "DRONE_MCP_SIM_REQUIRE_CAMERA=$SIM_REQUIRE_CAMERA" \
  -e "DRONE_MCP_SIM_PORTS=$SIM_PORTS" \
  -e "DRONE_MCP_SIM_NETWORK_HOST=$SIM_NETWORK_HOST" \
  -e "DOCKER_API_VERSION=$DOCKER_API_VERSION"

if [ -n "${OPENROUTER_KEY:-}" ]; then
  set -- "$@" -e "OPENROUTER_KEY=$OPENROUTER_KEY"
fi

if [ -n "${OPENROUTER_MODEL:-}" ]; then
  set -- "$@" -e "OPENROUTER_MODEL=$OPENROUTER_MODEL"
fi

set -- "$@" "$OPERATOR_IMAGE"
DOCKER_API_VERSION="$DOCKER_API_VERSION" "$@"

# ── Wait for the operator web to become healthy ──────────────────────
python3 - <<'PY'
import json
import time
import urllib.request

deadline = time.time() + 120
last_error = ""
while time.time() < deadline:
    try:
        with urllib.request.urlopen("http://127.0.0.1:8080/health", timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if payload.get("ok"):
            print(json.dumps(payload))
            raise SystemExit(0)
    except Exception as exc:  # pragma: no cover - shell-side health poll
        last_error = str(exc)
        time.sleep(2)

raise SystemExit(f"Operator web did not become healthy: {last_error}")
PY

