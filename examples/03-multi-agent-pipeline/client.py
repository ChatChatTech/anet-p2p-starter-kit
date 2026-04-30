"""L3 client — kicks off the C → B → A pipeline from daemon-4 and audits all 4."""

import argparse
import os
import sys
import time

from anet.svc import SvcClient


def find(svc: SvcClient, skill: str, *, retries: int = 20):
    for _ in range(retries):
        peers = svc.discover(skill=skill)
        if peers:
            return peers[0]
        time.sleep(1)
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("text", nargs="?", default="上海明天天气怎么样？")
    args = ap.parse_args()

    base = os.environ.get("ANET_BASE_URL", "http://127.0.0.1:13924")
    with SvcClient(base_url=base) as svc:
        target = find(svc, "sentiment")
        if not target:
            print("[client] no sentiment peers", file=sys.stderr)
            return 1
        peer_id = target["peer_id"]
        name = target["services"][0]["name"]
        print(f"[client] calling sentiment={name} on {peer_id[:18]}…")
        resp = svc.call(peer_id, name, "/v1/sentiment", method="POST",
                        body={"text": args.text})
        env = resp.get("body") or {}
        if isinstance(env, dict):
            print(f"\n[client] result:")
            print(f"  text:        {args.text!r}")
            print(f"  source_lang: {env.get('source_lang')}")
            print(f"  summary:     {env.get('summary')!r}")
            print(f"  label:       {env.get('label')}")
            print(f"  score:       {env.get('score')}")

        # Now snapshot audit on every daemon for the reconciliation story
        homes = {
            "u1 (A)": ("http://127.0.0.1:13921", os.path.expanduser("/tmp/anet-p2p-u1/.anet/api_token")),
            "u2 (B)": ("http://127.0.0.1:13922", os.path.expanduser("/tmp/anet-p2p-u2/.anet/api_token")),
            "u3 (C)": ("http://127.0.0.1:13923", os.path.expanduser("/tmp/anet-p2p-u3/.anet/api_token")),
            "u4 (D)": ("http://127.0.0.1:13924", os.path.expanduser("/tmp/anet-p2p-u4/.anet/api_token")),
        }
        print("\n[client] svc_call_log per node:")
        for label, (url, tok_path) in homes.items():
            try:
                token = open(tok_path).read().strip()
            except OSError:
                print(f"  {label}: token unreadable at {tok_path}")
                continue
            try:
                with SvcClient(base_url=url, token=token) as s2:
                    rows = s2.audit(limit=5)
            except Exception as e:  # noqa: BLE001
                print(f"  {label}: audit failed ({e})")
                continue
            print(f"  {label}: {len(rows)} row(s) recent")
            for r in rows[:3]:
                print(f"    {r['service']:18s} {r['method']:5s} {r['path']:18s} "
                      f"status={r['status']:3d}  cost={r['cost']:4d}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
