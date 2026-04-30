"""Agent A — zh-en translator (rule-based, no model deps).

Exposes POST /v1/translate {text:"…"} → {translated:"…"}.

The "translation" is a tiny synonym-table lookup so the demo runs offline; in
your real submission, swap in any model — the surface stays the same.
"""

import os
import sys
import threading
import time
from typing import Optional

import uvicorn
from fastapi import FastAPI, Header, Request
from fastapi.responses import JSONResponse

# Allow `python agent_a_translate.py` directly out of the repo by adding the
# SDK on the path before importing register.py.
sys.path.insert(0, os.path.dirname(__file__))
from register import register_until_ready  # noqa: E402

NAME = "translate-a"
PORT = int(os.environ.get("AGENT_A_PORT", "7301"))
PER_CALL = int(os.environ.get("AGENT_A_PER_CALL", "5"))

# Tiny zh→en mapping; just enough to make the demo readable.
TABLE = {
    "上海": "shanghai", "北京": "beijing", "天气": "weather",
    "明天": "tomorrow", "今天": "today", "怎么样": "how is",
    "给我": "give me", "用一句话": "in one sentence", "总结": "summarise",
    "好": "good", "不好": "bad", "热": "hot", "冷": "cold",
    "你好": "hello", "世界": "world", "？": " ", "。": ".", "，": ", ",
}

app = FastAPI(title=NAME)


def translate(text: str) -> str:
    """Naive longest-match substitution; returns ascii-only output."""
    out = []
    i = 0
    while i < len(text):
        matched = False
        for span in (3, 2, 1):
            chunk = text[i : i + span]
            if chunk in TABLE:
                out.append(TABLE[chunk])
                i += span
                matched = True
                break
        if not matched:
            ch = text[i]
            out.append(ch if ch.isascii() else "")
            i += 1
    cleaned = " ".join(s for s in " ".join(out).split() if s)
    return cleaned or "(empty translation)"


@app.get("/health")
def health(): return {"ok": True, "agent": NAME}


@app.get("/meta")
def meta():
    return {"name": NAME, "version": "0.1.0", "skill": "translate", "lang": "zh→en"}


@app.post("/v1/translate")
async def do_translate(req: Request,
                       x_agent_did: Optional[str] = Header(default=None, convert_underscores=True)):
    body = await req.json()
    text = (body or {}).get("text") or ""
    print(f"[A] caller={x_agent_did} text={text!r}", flush=True)
    return JSONResponse({"translated": translate(text), "agent": NAME})


def main() -> None:
    base_url = os.environ.get("ANET_BASE_URL", "http://127.0.0.1:13921")
    threading.Thread(
        target=lambda: register_until_ready(
            NAME, PORT, paths=["/v1/translate", "/health", "/meta"],
            tags=["translate", "zh-en", "l3-demo"], description="zh→en translator",
            per_call=PER_CALL, base_url=base_url,
        ), daemon=True,
    ).start()
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")


if __name__ == "__main__":
    main()
