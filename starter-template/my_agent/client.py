"""my_agent.client — discover a peer by skill and call it.

Usage:

    python -m my_agent.client                 # uses .env defaults
    python -m my_agent.client --skill llm     # search a different skill
    python -m my_agent.client --skill llm --stream    # consume server-stream

Pattern this is teaching you:
  1. Look up peers by capability with `svc.discover(skill=...)`.
  2. Pick one (round-robin / lowest cost / highest reputation — your call).
  3. Make the call with retry-on-transient-failure.
  4. Print the audit row with `svc.audit(limit=1)` so you can see the gateway
     wrote the call into svc_call_log.
"""

from __future__ import annotations

import argparse
import os
import sys
import time

from dotenv import load_dotenv

from anet.svc import AuthMissingError, SvcAPIError, SvcClient

load_dotenv()


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="anet svc client demo")
    p.add_argument("--skill", default=os.getenv("TARGET_SKILL", "p2p"))
    p.add_argument("--path", default="/echo")
    p.add_argument("--method", default="POST")
    p.add_argument("--stream", action="store_true")
    p.add_argument("--retry", type=int, default=2,
                   help="how many times to retry on transient errors")
    return p.parse_args()


def pick_peer(svc: SvcClient, skill: str) -> tuple[str, str]:
    peers = svc.discover(skill=skill)
    if not peers:
        raise SystemExit(f"no peers expose skill={skill!r}")
    print(f"[client] found {len(peers)} peer(s) for skill={skill}")
    for p in peers:
        services = ", ".join(s["name"] for s in p["services"])
        print(f"  - {p['peer_id'][:18]}…  services=[{services}]")
    target = peers[0]
    return target["peer_id"], target["services"][0]["name"]


def call_with_retry(svc: SvcClient, peer_id: str, name: str,
                    *, path: str, method: str, retry: int) -> dict:
    for attempt in range(retry + 1):
        try:
            return svc.call(peer_id, name, path, method=method,
                            body={"msg": f"hi from client (attempt {attempt + 1})"})
        except SvcAPIError as e:
            print(f"[client] attempt {attempt + 1} failed: {e}", file=sys.stderr)
            if attempt == retry:
                raise
            time.sleep(0.5 * (attempt + 1))
    raise RuntimeError("unreachable")


def main() -> int:
    args = parse_args()
    base_url = os.getenv("ANET_BASE_URL", "http://127.0.0.1:3998")
    try:
        svc = SvcClient(base_url=base_url)
    except AuthMissingError as e:
        print(f"[client] {e}", file=sys.stderr)
        return 1

    peer_id, svc_name = pick_peer(svc, args.skill)

    if args.stream:
        print(f"\n[client] streaming {svc_name} on {peer_id[:18]}…{args.path}")
        for ev in svc.stream(peer_id, svc_name, args.path,
                             method=args.method, mode="server-stream",
                             body={"prompt": "give me 5 ticks"}):
            print(f"  [{ev.event}] {ev.data}")
            if ev.is_terminal:
                break
    else:
        print(f"\n[client] calling {svc_name} on {peer_id[:18]}…{args.path}")
        resp = call_with_retry(svc, peer_id, svc_name,
                               path=args.path, method=args.method, retry=args.retry)
        print(f"  HTTP {resp.get('status')}  body={resp.get('body')}")

    print("\n[client] last audit row on this daemon:")
    rows = svc.audit(limit=1)
    if rows:
        r = rows[0]
        print(f"  {r['service']}  {r['method']} {r['path']}  status={r['status']}  "
              f"cost={r['cost']}  duration={r['duration_ms']}ms")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
