"""Shared register helper used by all three agents in L3."""

import os
import sys
import time
from typing import Optional

import httpx

from anet.svc import SvcAPIError, SvcClient


def register_until_ready(name: str, port: int, *, paths, tags, description,
                         per_call: int = 0, base_url: Optional[str] = None) -> None:
    base_url = base_url or os.environ.get("ANET_BASE_URL", "http://127.0.0.1:13921")
    # Wait for backend
    for _ in range(30):
        try:
            r = httpx.get(f"http://127.0.0.1:{port}/health", timeout=1.0)
            if r.status_code == 200:
                break
        except httpx.HTTPError:
            pass
        time.sleep(0.5)
    else:
        print(f"[{name}] backend on :{port} never came up", file=sys.stderr)
        raise SystemExit(1)

    with SvcClient(base_url=base_url) as svc:
        try:
            svc.unregister(name)
        except Exception:  # noqa: BLE001
            pass
        try:
            resp = svc.register(
                name=name,
                endpoint=f"http://127.0.0.1:{port}",
                paths=paths,
                modes=["rr"],
                per_call=per_call if per_call > 0 else None,
                free=per_call <= 0,
                tags=tags,
                description=description,
                health_check="/health",
                meta_path="/meta",
            )
        except SvcAPIError as e:
            print(f"[{name}] register failed: {e}", file=sys.stderr)
            raise

    ans = (resp.get("ans") or {})
    print(f"[{name}] ✓ registered (per_call={per_call}, ans.published={ans.get('published')})",
          file=sys.stderr)
