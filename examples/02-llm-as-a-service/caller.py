"""L2 caller: discover llm-svc, call it both rr and streaming, compare audit cost."""

import argparse
import os
import sys
import time

from anet.svc import SvcClient


def find_peer(svc: SvcClient, skill: str = "llm"):
    for _ in range(15):
        peers = svc.discover(skill=skill)
        if peers:
            return peers[0]
        time.sleep(1)
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["rr", "stream", "both"], default="both")
    ap.add_argument("--prompt", default="why is the sky blue?")
    args = ap.parse_args()

    with SvcClient(base_url=os.environ.get("ANET_BASE_URL", "http://127.0.0.1:13922")) as svc:
        peer = find_peer(svc)
        if peer is None:
            print("[caller] no llm peers found", file=sys.stderr)
            return 1
        peer_id = peer["peer_id"]
        name = peer["services"][0]["name"]
        print(f"[caller] target {name} on {peer_id[:18]}…", file=sys.stderr)

        if args.mode in ("rr", "both"):
            print("\n=== rr mode ===")
            t0 = time.time()
            resp = svc.call(peer_id, name, "/v1/chat", method="POST",
                            body={"prompt": args.prompt})
            dt = (time.time() - t0) * 1000
            print(f"HTTP {resp.get('status')}  ({dt:.0f}ms)")
            body = resp.get("body") or {}
            if isinstance(body, dict):
                print("completion:", (body.get("completion") or "")[:200])

        if args.mode in ("stream", "both"):
            print("\n=== server-stream mode ===")
            t0 = time.time()
            n = 0
            for ev in svc.stream(peer_id, name, "/v1/chat/stream", method="POST",
                                 body={"prompt": args.prompt}, mode="server-stream"):
                if ev.event == "message" and ev.data:
                    sys.stdout.write(ev.data)
                    sys.stdout.flush()
                    n += 1
                if ev.is_terminal:
                    break
            print(f"\n[stream done in {(time.time() - t0) * 1000:.0f}ms, {n} chunks]")

    # Audit lives on the *provider* daemon (the one that owns the service +
    # actually proxies the call). Querying caller-side audit returns 0 rows.
    provider_url = os.environ.get("ANET_PROVIDER_URL", "http://127.0.0.1:13921")
    provider_token = os.environ.get("ANET_PROVIDER_TOKEN")
    if provider_token:
        with SvcClient(base_url=provider_url, token=provider_token) as psvc:
            rows = psvc.audit(name=name, limit=5)
        print("\n=== audit on provider (last 5 calls) ===")
        for r in rows:
            print(f"  {r['method']:5s} {r['path']:25s} mode={r['mode']:13s} "
                  f"status={r['status']:3d}  cost={r['cost']:4d}  {r['duration_ms']:5d}ms")
        print("note: rr cost = per_call (10).  server-stream cost = per_kb × KB "
              "(deposit refunded on the rest).")
    else:
        print("\n[caller] set ANET_PROVIDER_TOKEN to also dump provider audit", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
