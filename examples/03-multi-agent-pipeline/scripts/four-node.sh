#!/usr/bin/env bash
# Bring up four independent anet daemons on the same laptop, all bootstrapped
# off daemon-1 so they form a single mesh.
#
# Layout:
#   /tmp/anet-p2p-u1   API=:13921  P2P=:14021    (Agent A — translate)
#   /tmp/anet-p2p-u2   API=:13922  P2P=:14022    (Agent B — summarise)
#   /tmp/anet-p2p-u3   API=:13923  P2P=:14023    (Agent C — sentiment)
#   /tmp/anet-p2p-u4   API=:13924  P2P=:14024    (Client D — kicks off pipeline)

set -euo pipefail
ANET="${ANET:-anet}"

API=(13921 13922 13923 13924)
P2P=(14021 14022 14023 14024)
HOMES=(/tmp/anet-p2p-u1 /tmp/anet-p2p-u2 /tmp/anet-p2p-u3 /tmp/anet-p2p-u4)

green() { printf "\033[32m✓\033[0m %s\n" "$*"; }
red()   { printf "\033[31m✗\033[0m %s\n" "$*"; }

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

api_alive() { curl -sf --noproxy '*' -m 1 "http://127.0.0.1:$1/api/status" >/dev/null 2>&1; }
wait_alive() {
  for _ in $(seq 1 60); do api_alive "$1" && return 0; sleep 1; done; return 1
}

cmd_start() {
  command -v "$ANET" >/dev/null || { red "anet not on PATH (set ANET=…)"; exit 1; }

  for d in "${HOMES[@]}"; do rm -rf "$d"; mkdir -p "$d"; done
  for p in "${API[@]}" "${P2P[@]}"; do
    lsof -ti tcp:"$p" 2>/dev/null | xargs -r kill -9 2>/dev/null || true
  done

  write_config "${HOMES[0]}" "${API[0]}" "${P2P[0]}" ""
  HOME="${HOMES[0]}" "$ANET" daemon > "${HOMES[0]}/daemon.log" 2>&1 &
  wait_alive "${API[0]}" || { red "daemon-1 failed"; tail "${HOMES[0]}/daemon.log"; exit 1; }
  PEER1=$(curl -sf --noproxy '*' "http://127.0.0.1:${API[0]}/api/status" \
    | python3 -c "import sys,json;print(json.load(sys.stdin)['peer_id'])")
  green "u1 alive  PEER=$PEER1"

  for i in 1 2 3; do
    BOOT="\"/ip4/127.0.0.1/tcp/${P2P[0]}/p2p/$PEER1\""
    write_config "${HOMES[$i]}" "${API[$i]}" "${P2P[$i]}" "$BOOT"
    HOME="${HOMES[$i]}" "$ANET" daemon > "${HOMES[$i]}/daemon.log" 2>&1 &
    wait_alive "${API[$i]}" || { red "u$((i+1)) failed"; tail "${HOMES[$i]}/daemon.log"; exit 1; }
    green "u$((i+1)) alive on :${API[$i]}"
  done

  # ── Seed cross-node ledgers ──────────────────────────────────────────────
  # Provider's local ledger doesn't know about callers' DIDs. Seed a small
  # mutual transfer between every (i,j) pair so any node can charge any other.
  # 1000 shells each direction is plenty for a event weekend's worth of
  # priced calls. Without this, cross-node priced calls fail with 402.
  DIDS=()
  TOKS=()
  for i in 0 1 2 3; do
    DIDS+=("$(curl -sf --noproxy '*' "http://127.0.0.1:${API[$i]}/api/status" \
              | python3 -c "import sys,json;print(json.load(sys.stdin)['did'])" 2>/dev/null)")
    TOKS+=("$(tr -d '[:space:]' < "${HOMES[$i]}/.anet/api_token")")
  done
  # Wait for mesh to converge so gossip lands.
  for _ in $(seq 1 15); do
    p=$(curl -sf --noproxy '*' "http://127.0.0.1:${API[0]}/api/status" \
        | python3 -c "import sys,json;print(json.load(sys.stdin).get('peers',0))" 2>/dev/null || echo 0)
    [ "${p:-0}" -ge 3 ] && break
    sleep 1
  done
  fail=0
  for i in 0 1 2 3; do
    for j in 0 1 2 3; do
      [ "$i" = "$j" ] && continue
      r=$(curl -sf --noproxy '*' \
              -H "Authorization: Bearer ${TOKS[$i]}" \
              -H "Content-Type: application/json" \
              -X POST "http://127.0.0.1:${API[$i]}/api/credits/transfer" \
              -d "{\"from\":\"${DIDS[$i]}\",\"to\":\"${DIDS[$j]}\",\"amount\":500,\"reason\":\"p2p-seed\"}" \
              2>/dev/null || echo "")
      echo "$r" | grep -q sender_event || fail=$((fail+1))
    done
  done
  if [ "$fail" = 0 ]; then
    green "seed transfers ok (12 cross-pairs × 500 shells, ledgers cross-linked)"
  else
    red "seed transfer: $fail / 12 failed; some priced calls may 402"
  fi

  cat <<EOF

  Daemon URLs:
    u1: http://127.0.0.1:${API[0]}   HOME=${HOMES[0]}
    u2: http://127.0.0.1:${API[1]}   HOME=${HOMES[1]}
    u3: http://127.0.0.1:${API[2]}   HOME=${HOMES[2]}
    u4: http://127.0.0.1:${API[3]}   HOME=${HOMES[3]}

  Now run (in separate terminals):
    bash run.sh agent-a       # daemon-1
    bash run.sh agent-b       # daemon-2
    bash run.sh agent-c       # daemon-3
    bash run.sh client "上海明天天气怎么样？给我用一句话总结。"
EOF
}

cmd_stop() {
  for p in "${API[@]}" "${P2P[@]}" 7301 7302 7303; do
    lsof -ti tcp:"$p" 2>/dev/null | xargs -r kill -9 2>/dev/null || true
  done
  green "killed everything"
}

cmd_status() {
  for i in 0 1 2 3; do
    api_alive "${API[$i]}" \
      && green "u$((i+1)) alive on :${API[$i]}" \
      || red   "u$((i+1)) DOWN  on :${API[$i]}"
  done
}

case "${1:-start}" in
  start) cmd_start ;;
  stop)  cmd_stop ;;
  status) cmd_status ;;
  *) echo "usage: $0 {start|stop|status}"; exit 2 ;;
esac
