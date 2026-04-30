#!/usr/bin/env bash
# scripts/two-node.sh — bring up two isolated anet daemons on this laptop so
# you can test register/discover/call locally without needing a teammate.
#
# Layout:
#   /tmp/anet-p2p-u1    HOME for daemon-1 (will hold .anet/{api_token,config.json,db})
#   /tmp/anet-p2p-u2    HOME for daemon-2
#
# Daemon-1 listens on REST :13921, P2P :14021
# Daemon-2 listens on REST :13922, P2P :14022
# Daemon-2 is wired to dial Daemon-1 via explicit bootstrap_peers (so this
# works even when mDNS is disabled by the campus network).
#
# Usage:
#   bash scripts/two-node.sh start    # default
#   bash scripts/two-node.sh stop
#   bash scripts/two-node.sh status

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ANET="${ANET:-anet}"
HOME1="${HOME1:-/tmp/anet-p2p-u1}"
HOME2="${HOME2:-/tmp/anet-p2p-u2}"
API1=13921; P2P1=14021
API2=13922; P2P2=14022

green()  { printf "\033[32m✓\033[0m %s\n" "$*"; }
red()    { printf "\033[31m✗\033[0m %s\n" "$*"; }
header() { printf "\n\033[1;36m═══ %s ═══\033[0m\n" "$*"; }

write_config() {
  local dir="$1" api="$2" p2p="$3" boot_csv="$4"
  mkdir -p "$dir/.anet"
  cat > "$dir/.anet/config.json" <<EOF
{
  "listen_addrs": ["/ip4/127.0.0.1/tcp/$p2p"],
  "bootstrap_peers": [$boot_csv],
  "api_port": $api,
  "relay_enabled": false,
  "topics_auto_join": ["/anet/ans", "/anet/credits"],
  "bt_dht": {"enabled": false},
  "overlay": {"enabled": false}
}
EOF
}

api_alive() {
  local port="$1"
  curl -sf --noproxy '*' -m 2 "http://127.0.0.1:${port}/api/status" >/dev/null 2>&1
}

wait_for_api() {
  local port="$1" name="$2"
  printf "  waiting for %s on :%s …" "$name" "$port"
  for _ in $(seq 1 60); do
    if api_alive "$port"; then echo " ready"; return 0; fi
    sleep 1
  done
  echo " TIMEOUT"; return 1
}

cmd_start() {
  command -v "$ANET" >/dev/null || { red "anet not in PATH (set ANET=/path/to/anet)"; exit 1; }

  header "Reset homes"
  rm -rf "$HOME1" "$HOME2"
  mkdir -p "$HOME1" "$HOME2"

  for port in $API1 $API2 $P2P1 $P2P2; do
    lsof -ti tcp:"$port" 2>/dev/null | xargs -r kill -9 2>/dev/null || true
  done

  header "Start daemon-1"
  write_config "$HOME1" "$API1" "$P2P1" ""
  HOME="$HOME1" "$ANET" daemon > "$HOME1/daemon.log" 2>&1 &
  echo "  pid=$!  HOME=$HOME1"
  wait_for_api "$API1" daemon-1 || { red "daemon-1 failed"; tail "$HOME1/daemon.log"; exit 1; }
  PEER1=$(curl -sf --noproxy '*' "http://127.0.0.1:${API1}/api/status" \
            | python3 -c "import sys,json;print(json.load(sys.stdin)['peer_id'])")
  green "daemon-1 PEER=$PEER1"

  header "Start daemon-2 (bootstrapped to daemon-1)"
  write_config "$HOME2" "$API2" "$P2P2" "\"/ip4/127.0.0.1/tcp/$P2P1/p2p/$PEER1\""
  HOME="$HOME2" "$ANET" daemon > "$HOME2/daemon.log" 2>&1 &
  echo "  pid=$!  HOME=$HOME2"
  wait_for_api "$API2" daemon-2 || { red "daemon-2 failed"; tail "$HOME2/daemon.log"; exit 1; }
  green "daemon-2 ready"

  header "Seed cross-node credit ledgers"
  # Each daemon's bootstrap grant is local — provider's ledger doesn't know the
  # caller's DID exists. Seed a tiny mutual transfer so both daemons hold a
  # non-zero row for each other's DID, otherwise priced cross-node calls fail
  # with "insufficient credits" even though both have local balance.
  TOK1=$(tr -d '[:space:]' < "$HOME1/.anet/api_token")
  TOK2=$(tr -d '[:space:]' < "$HOME2/.anet/api_token")
  DID1=$(curl -sf --noproxy '*' "http://127.0.0.1:${API1}/api/status" \
           | python3 -c "import sys,json;print(json.load(sys.stdin)['did'])" 2>/dev/null)
  DID2=$(curl -sf --noproxy '*' "http://127.0.0.1:${API2}/api/status" \
           | python3 -c "import sys,json;print(json.load(sys.stdin)['did'])" 2>/dev/null)
  if [ -n "$DID1" ] && [ -n "$DID2" ]; then
    # Wait for a libp2p connection (transfers don't need it but gossip does)
    for _ in $(seq 1 15); do
      peers=$(curl -sf --noproxy '*' "http://127.0.0.1:${API1}/api/status" \
                | python3 -c "import sys,json;print(json.load(sys.stdin).get('peers',0))" 2>/dev/null || echo 0)
      [ "${peers:-0}" -ge 1 ] && break
      sleep 1
    done
    # u1 -> u2 (1000 shells)
    R1=$(curl -sf --noproxy '*' -H "Authorization: Bearer $TOK1" \
              -H "Content-Type: application/json" \
              -X POST "http://127.0.0.1:${API1}/api/credits/transfer" \
              -d "{\"from\":\"$DID1\",\"to\":\"$DID2\",\"amount\":1000,\"reason\":\"p2p-seed\"}" 2>/dev/null || echo "")
    # u2 -> u1 (1000 shells)
    R2=$(curl -sf --noproxy '*' -H "Authorization: Bearer $TOK2" \
              -H "Content-Type: application/json" \
              -X POST "http://127.0.0.1:${API2}/api/credits/transfer" \
              -d "{\"from\":\"$DID2\",\"to\":\"$DID1\",\"amount\":1000,\"reason\":\"p2p-seed\"}" 2>/dev/null || echo "")
    if echo "$R1" | grep -q sender_event && echo "$R2" | grep -q sender_event; then
      green "seed transfers ok (1000⇄1000 shells, both ledgers know each other)"
    else
      red "seed transfer failed; cross-node priced calls will hit 402"
      echo "  u1->u2: $R1"
      echo "  u2->u1: $R2"
    fi
  else
    red "could not resolve DIDs for seeding (priced cross-node calls may 402)"
  fi

  header "Snapshot"
  cat <<EOF
  daemon-1   API=http://127.0.0.1:$API1   P2P=:$P2P1   HOME=$HOME1
  daemon-2   API=http://127.0.0.1:$API2   P2P=:$P2P2   HOME=$HOME2

Use either with:
  export ANET_BASE_URL=http://127.0.0.1:$API1
  export ANET_TOKEN=\$(HOME=$HOME1 $ANET auth token print)

Then:
  uvicorn my_agent.backend:app --port 8000
  python -m my_agent.service
EOF
}

cmd_stop() {
  for port in $API1 $API2 $P2P1 $P2P2; do
    lsof -ti tcp:"$port" 2>/dev/null | xargs -r kill -9 2>/dev/null || true
  done
  green "killed everything bound to $API1/$API2/$P2P1/$P2P2"
}

cmd_status() {
  api_alive "$API1" && green "daemon-1 alive on :$API1" || red "daemon-1 down"
  api_alive "$API2" && green "daemon-2 alive on :$API2" || red "daemon-2 down"
}

case "${1:-start}" in
  start)  cmd_start ;;
  stop)   cmd_stop ;;
  status) cmd_status ;;
  *) echo "usage: $0 {start|stop|status}"; exit 2 ;;
esac
