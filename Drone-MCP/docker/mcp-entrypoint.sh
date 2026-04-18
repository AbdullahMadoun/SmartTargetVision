#!/bin/sh
set -eu

if [ -S /var/run/docker.sock ]; then
  SOCKET_GID="$(stat -c '%g' /var/run/docker.sock)"
  GROUP_NAME="$(getent group "$SOCKET_GID" | cut -d: -f1 || true)"
  if [ -z "$GROUP_NAME" ]; then
    GROUP_NAME="dockersock"
    groupadd -g "$SOCKET_GID" "$GROUP_NAME"
  fi
  usermod -aG "$GROUP_NAME" mcpuser
fi

exec gosu mcpuser "$@"
