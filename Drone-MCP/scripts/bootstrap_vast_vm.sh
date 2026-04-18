#!/bin/sh
set -eu

export DEBIAN_FRONTEND=noninteractive
DOCKER_API_VERSION="${DOCKER_API_VERSION:-1.43}"

# Vast.ai instances come with Docker pre-installed.  Only install if
# truly missing (e.g. a bare-metal test VM).
if ! command -v docker >/dev/null 2>&1; then
  apt-get update
  apt-get install -y --no-install-recommends docker.io
fi

# Vast.ai uses a non-systemd init.  Try systemctl first (works on full
# VMs), fall back to the service command, then just verify Docker is
# reachable via the socket.
if command -v systemctl >/dev/null 2>&1; then
  systemctl enable --now docker 2>/dev/null || true
elif command -v service >/dev/null 2>&1; then
  service docker start 2>/dev/null || true
fi

# Wait briefly for the daemon socket to appear.
for _wait in 1 2 3 4 5; do
  if DOCKER_API_VERSION="$DOCKER_API_VERSION" docker version >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

DOCKER_API_VERSION="$DOCKER_API_VERSION" docker version >/dev/null

