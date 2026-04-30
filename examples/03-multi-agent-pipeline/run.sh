#!/usr/bin/env bash
# L3 dispatcher.
#
# Sub-commands:
#   agent-a      bring up A on daemon-1 :13921
#   agent-b      bring up B on daemon-2 :13922
#   agent-c      bring up C on daemon-3 :13923
#   client TEXT  kick off the pipeline from daemon-4 :13924

set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../../.." && pwd)"
HOMES=(/tmp/anet-p2p-u1 /tmp/anet-p2p-u2 /tmp/anet-p2p-u3 /tmp/anet-p2p-u4)
APIS=(13921 13922 13923 13924)

export PYTHONPATH="$ROOT/sdk/python:${PYTHONPATH:-}"

token_for() { tr -d '[:space:]' < "$1/.anet/api_token"; }

case "${1:-}" in
  agent-a)
    ANET_BASE_URL="http://127.0.0.1:${APIS[0]}" \
      ANET_TOKEN="$(token_for "${HOMES[0]}")" \
      python3 "$HERE/agent_a_translate.py"
    ;;
  agent-b)
    ANET_BASE_URL="http://127.0.0.1:${APIS[1]}" \
      ANET_TOKEN="$(token_for "${HOMES[1]}")" \
      python3 "$HERE/agent_b_summarise.py"
    ;;
  agent-c)
    ANET_BASE_URL="http://127.0.0.1:${APIS[2]}" \
      ANET_TOKEN="$(token_for "${HOMES[2]}")" \
      python3 "$HERE/agent_c_sentiment.py"
    ;;
  client)
    shift
    ANET_BASE_URL="http://127.0.0.1:${APIS[3]}" \
      ANET_TOKEN="$(token_for "${HOMES[3]}")" \
      python3 "$HERE/client.py" "${1:-上海明天天气怎么样？}"
    ;;
  *)
    echo "usage: $0 {agent-a|agent-b|agent-c|client TEXT}" >&2
    exit 2
    ;;
esac
