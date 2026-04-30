"""Register the L1 echo backend with the local anet daemon.

Run AFTER echo_backend.py is up. Uses ANET_BASE_URL + ANET_TOKEN from env.
"""

import os
import sys

from anet.svc import SvcClient

NAME = os.environ.get("ECHO_SVC_NAME", "echo-l1")


def main() -> int:
    with SvcClient(base_url=os.environ.get("ANET_BASE_URL", "http://127.0.0.1:13921")) as svc:
        try:
            svc.unregister(NAME)
        except Exception:  # noqa: BLE001 — first run will 404, ignore
            pass
        resp = svc.register(
            name=NAME,
            endpoint=f"http://127.0.0.1:{os.environ.get('ECHO_PORT', '7100')}",
            paths=["/echo", "/health", "/meta"],
            modes=["rr"],
            free=True,
            tags=["echo", "l1-demo"],
            description="L1 p2p echo service",
            health_check="/health",
            meta_path="/meta",
        )
        print(f"✓ registered {resp.get('name')} ans={resp.get('ans')}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
