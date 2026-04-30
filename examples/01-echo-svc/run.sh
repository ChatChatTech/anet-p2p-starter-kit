#!/usr/bin/env bash
# L1 echo-svc end-to-end driver. Assumes:
#   - `anet` is on PATH
#   - p2p/starter-template/scripts/two-node.sh start has been run
#   - the SDK is importable (pip install -e ../../sdk/python)

set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../../.." && pwd)"
HOME1="${HOME1:-/tmp/anet-p2p-u1}"
HOME2="${HOME2:-/tmp/anet-p2p-u2}"
ECHO_PORT=7100

if [ ! -f "$HOME1/.anet/api_token" ] || [ ! -f "$HOME2/.anet/api_token" ]; then
  echo "✗ daemons not running; run p2p/starter-template/scripts/two-node.sh start first" >&2
  exit 1
fi

cleanup() {
  for pid in ${PIDS_TO_KILL[@]:-}; do
    kill "$pid" 2>/dev/null || true
  done
  lsof -ti tcp:"$ECHO_PORT" 2>/dev/null | xargs -r kill -9 2>/dev/null || true
}
trap cleanup EXIT

PYTHONPATH="$ROOT/sdk/python:${PYTHONPATH:-}" \
  ECHO_PORT="$ECHO_PORT" python3 "$HERE/echo_backend.py" > /tmp/l1-echo.log 2>&1 &
PIDS_TO_KILL+=($!)
sleep 1

# Sanity probe
curl -sf -m 3 "http://127.0.0.1:$ECHO_PORT/health" >/dev/null \
  || { echo "✗ echo backend failed to start"; tail /tmp/l1-echo.log; exit 1; }

ANET_BASE_URL="http://127.0.0.1:13921" \
  ANET_TOKEN="$(tr -d '[:space:]' < "$HOME1/.anet/api_token")" \
  ECHO_PORT="$ECHO_PORT" \
  PYTHONPATH="$ROOT/sdk/python:${PYTHONPATH:-}" \
  python3 "$HERE/register.py"

ANET_BASE_URL="http://127.0.0.1:13922" \
  ANET_TOKEN="$(tr -d '[:space:]' < "$HOME2/.anet/api_token")" \
  PYTHONPATH="$ROOT/sdk/python:${PYTHONPATH:-}" \
  python3 "$HERE/caller.py"
