"""Agent B — summariser. Internally calls Agent A (translate) when input is zh.

Exposes POST /v1/summarise {text:"…"} → {summary:"…", source_lang:"zh|en"}.

The "summariser" is a first-sentence + length-cap heuristic; the interesting
part is the *intra-handler* call to A via the SDK.
"""

import os
import sys
import threading
import time
from typing import Optional

import uvicorn
from fastapi import FastAPI, Header, Request
from fastapi.responses import JSONResponse

sys.path.insert(0, os.path.dirname(__file__))
from register import register_until_ready  # noqa: E402

from anet.svc import SvcClient  # noqa: E402

NAME = "summarise-b"
PORT = int(os.environ.get("AGENT_B_PORT", "7302"))
PER_CALL = int(os.environ.get("AGENT_B_PER_CALL", "10"))
ANET_BASE_URL = os.environ.get("ANET_BASE_URL", "http://127.0.0.1:13922")

app = FastAPI(title=NAME)


def looks_chinese(text: str) -> bool:
    return any("\u4e00" <= ch <= "\u9fff" for ch in text)


def summarise(text: str) -> str:
    """First sentence, capped to 120 chars."""
    for sep in (".", "。", "!", "?", "\n"):
        if sep in text:
            text = text.split(sep, 1)[0]
            break
    text = text.strip()
    return (text[:117] + "…") if len(text) > 120 else text


def call_translate(text: str) -> str:
    """Hop B→A through the gateway. ANS gossip means we don't need A's peer_id."""
    with SvcClient(base_url=ANET_BASE_URL) as svc:
        peers = svc.discover(skill="translate")
        if not peers:
            return text  # graceful degrade
        target = peers[0]
        resp = svc.call(target["peer_id"], target["services"][0]["name"],
                        "/v1/translate", method="POST", body={"text": text})
        body = resp.get("body") or {}
        return body.get("translated", text) if isinstance(body, dict) else text


@app.get("/health")
def health(): return {"ok": True, "agent": NAME}


@app.get("/meta")
def meta():
    return {"name": NAME, "version": "0.1.0", "skill": "summarise",
            "calls_into": ["translate"]}


@app.post("/v1/summarise")
async def do_summarise(req: Request,
                       x_agent_did: Optional[str] = Header(default=None, convert_underscores=True)):
    body = await req.json()
    text = (body or {}).get("text") or ""
    src = "zh" if looks_chinese(text) else "en"
    print(f"[B] caller={x_agent_did} src={src} text={text[:60]!r}", flush=True)
    if src == "zh":
        text = call_translate(text)
        print(f"[B]   ↳ translated to en: {text[:60]!r}", flush=True)
    return JSONResponse({"summary": summarise(text), "source_lang": src, "agent": NAME})


def main() -> None:
    threading.Thread(
        target=lambda: register_until_ready(
            NAME, PORT, paths=["/v1/summarise", "/health", "/meta"],
            tags=["summarise", "l3-demo"], description="english summariser",
            per_call=PER_CALL, base_url=ANET_BASE_URL,
        ), daemon=True,
    ).start()
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")


if __name__ == "__main__":
    main()
