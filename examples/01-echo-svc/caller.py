"""L1 caller: discover echo by skill, call it, print the audit row.

Run from daemon-2 (export ANET_BASE_URL=http://127.0.0.1:13922 first).
"""

import os
import sys
import time

from anet.svc import SvcClient


def main() -> int:
    with SvcClient(base_url=os.environ.get("ANET_BASE_URL", "http://127.0.0.1:13922")) as svc:
        # ANS gossip is async; give it a beat to converge after register.py
        # ran on the other daemon.
        for attempt in range(15):
            peers = svc.discover(skill="echo")
            if peers:
                break
            time.sleep(1)
        else:
            print("[caller] no peers expose skill=echo (mesh not converged?)", file=sys.stderr)
            return 1

        target = peers[0]
        svc_name = target["services"][0]["name"]
        print(f"[caller] picked {svc_name} on {target['peer_id'][:18]}…")

        resp = svc.call(target["peer_id"], svc_name, "/echo",
                        method="POST", body={"msg": "hi from L1 caller"})
        print(f"[caller] HTTP {resp.get('status')} → {resp.get('body')}")

        rows = svc.audit(limit=1)
        if rows:
            r = rows[0]
            print(f"[caller] audit on caller side: {r['service']}  {r['method']} {r['path']}  "
                  f"status={r['status']}  cost={r['cost']}")

        if resp.get("status") == 200 and isinstance(resp.get("body"), dict) \
                and resp["body"].get("echo") == {"msg": "hi from L1 caller"}:
            print("✓ L1 demo PASSED")
            return 0
        print("✗ unexpected envelope", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
