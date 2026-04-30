"""Register llm_backend with the local daemon, billed per call."""

import os
import sys

from anet.svc import SvcClient

NAME = os.environ.get("LLM_SVC_NAME", "llm-svc")
PORT = int(os.environ.get("LLM_PORT", "7200"))
PER_CALL = int(os.environ.get("LLM_PER_CALL", "10"))
# per_kb only applies to streaming modes (server-stream / chunked / bidi).
# Without it, an upfront deposit (= max(deposit, per_call)) gets fully refunded
# at end-of-stream because actual usage = 0, so the audit row shows cost=0.
# Set a small per_kb so streams are *actually* billed proportional to bytes.
PER_KB = int(os.environ.get("LLM_PER_KB", "2"))


def main() -> int:
    with SvcClient(base_url=os.environ.get("ANET_BASE_URL", "http://127.0.0.1:13921")) as svc:
        try:
            svc.unregister(NAME)
        except Exception:  # noqa: BLE001
            pass
        resp = svc.register(
            name=NAME,
            endpoint=f"http://127.0.0.1:{PORT}",
            paths=["/v1/chat", "/v1/chat/stream", "/health", "/meta"],
            modes=["rr", "server-stream"],
            per_call=PER_CALL,
            per_kb=PER_KB,
            tags=["llm", "chat", "streaming", "l2-demo"],
            description=(
                f"Streaming LLM proxy ({os.environ.get('LLM_PROVIDER', 'ollama')}) — "
                f"{PER_CALL}🔐/rr-call + {PER_KB}🔐/KB on streams"
            ),
            health_check="/health",
            meta_path="/meta",
        )
        ans = resp.get("ans") or {}
        print(
            f"✓ registered {NAME} per_call={PER_CALL} per_kb={PER_KB} "
            f"ans.published={ans.get('published')}",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
