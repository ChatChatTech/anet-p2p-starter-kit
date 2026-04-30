"""LLM-as-a-Service FastAPI backend.

Two endpoints:
  POST /v1/chat        rr mode → returns the full completion as JSON
  POST /v1/chat/stream server-stream → emits one chunk per token (text/plain)

Provider is selected by $LLM_PROVIDER:
  - ollama (default): hits http://127.0.0.1:11434/api/generate, expects $OLLAMA_MODEL
  - fake             : deterministic 5-word echo so this demo runs even
                       when no model server is around (great for CI / first-touch)

The X-Agent-DID header injected by the gateway is logged so you can see who
is calling. Wire it into your real per-DID rate-limiter or quota check.
"""

import os
import time
from typing import Optional

import httpx
from fastapi import FastAPI, Header, Request
from fastapi.responses import JSONResponse, StreamingResponse

LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "ollama")
OLLAMA_BASE = os.environ.get("OLLAMA_BASE", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2:1b")

app = FastAPI(title="llm-svc")


def _fake_tokens(prompt: str):
    words = ["hi,", "this", "is", "a", "fake", "completion", "for:", prompt.strip()[:40]]
    for w in words:
        time.sleep(0.15)
        yield w + " "


def _ollama_tokens(prompt: str):
    """Minimal Ollama streaming consumer — yields the partial tokens.

    Falls back to fake tokens on any HTTP error so the demo keeps working.
    """
    payload = {"model": OLLAMA_MODEL, "prompt": prompt, "stream": True}
    try:
        with httpx.stream("POST", f"{OLLAMA_BASE}/api/generate",
                          json=payload, timeout=60.0) as r:
            r.raise_for_status()
            import json
            for line in r.iter_lines():
                if not line:
                    continue
                try:
                    chunk = json.loads(line)
                except json.JSONDecodeError:
                    continue
                tok = chunk.get("response", "")
                if tok:
                    yield tok
                if chunk.get("done"):
                    return
    except Exception as e:  # noqa: BLE001
        yield f"[ollama unavailable, falling back to fake: {e}]\n"
        yield from _fake_tokens(prompt)


def _emit(prompt: str):
    if LLM_PROVIDER == "fake":
        yield from _fake_tokens(prompt)
    else:
        yield from _ollama_tokens(prompt)


@app.get("/health")
def health():
    return {"ok": True, "provider": LLM_PROVIDER}


@app.get("/meta")
def meta():
    return {
        "name": "llm-svc",
        "version": "0.1.0",
        "description": "Streaming LLM proxy (Ollama / fake fallback) — billed per call",
        "provider": LLM_PROVIDER,
        "model": OLLAMA_MODEL if LLM_PROVIDER == "ollama" else "fake-deterministic",
        "endpoints": [
            {"method": "POST", "path": "/v1/chat",
             "in": {"prompt": "string"}, "out": {"completion": "string"}},
            {"method": "POST", "path": "/v1/chat/stream",
             "in": {"prompt": "string"}, "out": "text/plain stream of tokens"},
        ],
    }


@app.post("/v1/chat")
async def chat(req: Request,
               x_agent_did: Optional[str] = Header(default=None, convert_underscores=True)):
    body = await req.json()
    prompt = (body or {}).get("prompt") or "say hi"
    completion = "".join(_emit(prompt))
    return JSONResponse({"completion": completion, "caller_did": x_agent_did})


@app.post("/v1/chat/stream")
async def chat_stream(req: Request,
                      x_agent_did: Optional[str] = Header(default=None, convert_underscores=True)):
    body = await req.json()
    prompt = (body or {}).get("prompt") or "say hi"

    def gen():
        for tok in _emit(prompt):
            yield tok
        yield ""  # sentinel flush

    print(f"[llm] stream request from did={x_agent_did} prompt={prompt[:60]!r}", flush=True)
    return StreamingResponse(gen(), media_type="text/plain")
