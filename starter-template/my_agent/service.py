"""my_agent.service — register backend.py with the local anet daemon.

Behaviour:
  1. Reads .env (or environment) for MY_SVC_* and ANET_* config.
  2. Waits until the local backend (FastAPI on $MY_BACKEND_HOST:$MY_BACKEND_PORT)
     answers GET /health, then registers it with the gateway.
  3. Sleeps in a heartbeat loop, re-registering every 60s in case the daemon
     restarted (registrations are NOT persisted across daemon restarts in v1.1).
  4. On SIGINT / SIGTERM, unregisters cleanly so the entry disappears from
     other peers' `anet svc discover`.

Run:

    python -m my_agent.service
"""

from __future__ import annotations

import os
import signal
import socket
import sys
import time
from typing import Any

import httpx
from dotenv import load_dotenv

from anet.svc import AuthMissingError, SvcAPIError, SvcClient

# Load .env (if present) before reading config.
load_dotenv()


def _csv(name: str, default: str = "") -> list[str]:
    raw = os.getenv(name, default)
    return [x.strip() for x in raw.split(",") if x.strip()]


def _int_or_none(name: str) -> int | None:
    v = os.getenv(name)
    if not v:
        return None
    try:
        return int(v)
    except ValueError:
        return None


def _short_host_hash() -> str:
    """4-byte deterministic suffix so two laptops don't collide on MY_SVC_NAME."""
    import hashlib
    h = hashlib.sha256(socket.gethostname().encode()).hexdigest()[:6]
    return h


def _wait_for_backend(host: str, port: int, *, timeout: float = 30.0) -> None:
    deadline = time.time() + timeout
    last_err: Any = None
    while time.time() < deadline:
        try:
            r = httpx.get(f"http://{host}:{port}/health", timeout=2.0)
            if r.status_code == 200:
                return
        except httpx.HTTPError as e:
            last_err = e
        time.sleep(1)
    raise RuntimeError(f"backend at {host}:{port} not reachable: {last_err}")


def main() -> int:
    base_url = os.getenv("ANET_BASE_URL", "http://127.0.0.1:3998")
    name = os.getenv("MY_SVC_NAME", "my-agent")
    if not name.endswith(_short_host_hash()):
        # Avoid same-name collisions across laptops on the same network.
        name = f"{name}-{_short_host_hash()}"
    backend_host = os.getenv("MY_BACKEND_HOST", "127.0.0.1")
    backend_port = int(os.getenv("MY_BACKEND_PORT", "8000"))
    paths = _csv("MY_SVC_PATHS", "/echo,/health,/meta")
    modes = _csv("MY_SVC_MODES", "rr")
    tags = _csv("MY_SVC_TAGS", "p2p")
    description = os.getenv("MY_SVC_DESC", "p2p starter agent")

    free = os.getenv("MY_SVC_FREE", "true").lower() == "true"
    per_call = _int_or_none("MY_SVC_PER_CALL")
    per_kb = _int_or_none("MY_SVC_PER_KB")
    deposit = _int_or_none("MY_SVC_DEPOSIT")
    if per_call or per_kb or deposit:
        free = False  # explicit cost beats default free flag

    print(f"[service] waiting for backend on {backend_host}:{backend_port} …", flush=True)
    _wait_for_backend(backend_host, backend_port)
    print("[service] backend healthy", flush=True)

    try:
        svc = SvcClient(base_url=base_url)
    except AuthMissingError as e:
        print(f"[service] {e}", file=sys.stderr)
        return 1

    def register_once() -> None:
        try:
            resp = svc.register(
                name=name,
                endpoint=f"http://{backend_host}:{backend_port}",
                paths=paths,
                modes=modes,
                tags=tags,
                description=description,
                health_check="/health",
                meta_path="/meta",
                free=free,
                per_call=per_call,
                per_kb=per_kb,
                deposit=deposit,
            )
            ans = resp.get("ans") or {}
            print(
                f"[service] ✓ registered name={name} ans.published={ans.get('published')} "
                f"uri={ans.get('uri')}",
                flush=True,
            )
        except SvcAPIError as e:
            print(f"[service] register failed: {e}", file=sys.stderr)

    def shutdown(*_args) -> None:
        print("[service] unregistering …", flush=True)
        try:
            svc.unregister(name)
        except Exception as e:  # noqa: BLE001
            print(f"[service] unregister failed (non-fatal): {e}", file=sys.stderr)
        svc.close()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    register_once()
    while True:
        time.sleep(60)
        register_once()


if __name__ == "__main__":
    raise SystemExit(main())
