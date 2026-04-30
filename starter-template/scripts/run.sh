#!/usr/bin/env bash
# scripts/run.sh — start your agent backend + register loop in one shot,
# pinned to whichever daemon you choose. Reads .env automatically.
#
# Usage:
#   bash scripts/run.sh              # daemon-1 (default)
#   bash scripts/run.sh u2           # daemon-2 (uses HOME=/tmp/anet-p2p-u2)
#
# Requires: scripts/two-node.sh start has been run beforehand.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

NODE="${1:-u1}"
case "$NODE" in
  u1) export ANET_BASE_URL="http://127.0.0.1:13921"; H="/tmp/anet-p2p-u1"; PORT=8001 ;;
  u2) export ANET_BASE_URL="http://127.0.0.1:13922"; H="/tmp/anet-p2p-u2"; PORT=8002 ;;
  *)  echo "usage: $0 [u1|u2]"; exit 2 ;;
esac

if [ ! -f "$H/.anet/api_token" ]; then
  echo "✗ daemon HOME=$H has no api_token; run scripts/two-node.sh start first" >&2
  exit 1
fi
export ANET_TOKEN
ANET_TOKEN="$(tr -d '[:space:]' < "$H/.anet/api_token")"
export MY_BACKEND_PORT="${PORT}"

echo "── ANET_BASE_URL=$ANET_BASE_URL  MY_BACKEND_PORT=$PORT ──"

# Backend in background
( uvicorn my_agent.backend:app --host 127.0.0.1 --port "$PORT" --log-level warning ) &
BACKEND_PID=$!
trap 'kill $BACKEND_PID 2>/dev/null || true' EXIT

# Service register loop in foreground (Ctrl-C unregisters cleanly)
python -m my_agent.service
