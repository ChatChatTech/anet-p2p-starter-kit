#!/usr/bin/env bash
# L2 driver. Sub-commands:
#   provider       — start backend on :7200 + register against daemon-1
#   caller-rr      — one-shot rr call from daemon-2
#   caller-stream  — streaming call from daemon-2
#   caller-both    — both, in sequence

set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../../.." && pwd)"
HOME1="${HOME1:-/tmp/anet-p2p-u1}"
HOME2="${HOME2:-/tmp/anet-p2p-u2}"
LLM_PORT="${LLM_PORT:-7200}"
LLM_PROVIDER="${LLM_PROVIDER:-ollama}"

export PYTHONPATH="$ROOT/sdk/python:${PYTHONPATH:-}"

case "${1:-provider}" in
  provider)
    if [ ! -f "$HOME1/.anet/api_token" ]; then
      echo "✗ daemon-1 not up; run p2p/starter-template/scripts/two-node.sh start" >&2
      exit 1
    fi
    lsof -ti tcp:"$LLM_PORT" 2>/dev/null | xargs -r kill -9 2>/dev/null || true
    LLM_PROVIDER="$LLM_PROVIDER" LLM_PORT="$LLM_PORT" \
      uvicorn llm_backend:app --host 127.0.0.1 --port "$LLM_PORT" \
      --app-dir "$HERE" --log-level warning &
    BACK_PID=$!
    trap 'kill $BACK_PID 2>/dev/null || true' EXIT
    # Wait for backend
    for _ in $(seq 1 30); do
      curl -sf -m 1 "http://127.0.0.1:$LLM_PORT/health" >/dev/null && break
      sleep 1
    done
    ANET_BASE_URL="http://127.0.0.1:13921" \
      ANET_TOKEN="$(tr -d '[:space:]' < "$HOME1/.anet/api_token")" \
      LLM_PORT="$LLM_PORT" LLM_PROVIDER="$LLM_PROVIDER" \
      python3 "$HERE/register.py"
    echo "[provider] llm-svc up on :$LLM_PORT, provider=$LLM_PROVIDER, registered with daemon-1."
    echo "[provider] Ctrl-C to stop."
    wait $BACK_PID
    ;;
  caller-rr|caller-stream|caller-both)
    mode="${1#caller-}"
    [ "$mode" = "both" ] && mode="both"
    if [ ! -f "$HOME2/.anet/api_token" ]; then
      echo "✗ daemon-2 not up" >&2; exit 1
    fi
    ANET_BASE_URL="http://127.0.0.1:13922" \
      ANET_TOKEN="$(tr -d '[:space:]' < "$HOME2/.anet/api_token")" \
      ANET_PROVIDER_URL="http://127.0.0.1:13921" \
      ANET_PROVIDER_TOKEN="$(tr -d '[:space:]' < "$HOME1/.anet/api_token")" \
      python3 "$HERE/caller.py" --mode "$mode"
    ;;
  *)
    echo "usage: $0 {provider|caller-rr|caller-stream|caller-both}" >&2
    exit 2
    ;;
esac
