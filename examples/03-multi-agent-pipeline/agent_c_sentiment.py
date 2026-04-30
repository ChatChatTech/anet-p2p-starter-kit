"""Agent C — sentiment classifier. Internally calls B (which calls A).

Exposes POST /v1/sentiment {text:"…"} → {label, score, summary}.
"""

import os
import sys
import threading
from typing import Optional

import uvicorn
from fastapi import FastAPI, Header, Request
from fastapi.responses import JSONResponse

sys.path.insert(0, os.path.dirname(__file__))
from register import register_until_ready  # noqa: E402

from anet.svc import SvcClient  # noqa: E402

NAME = "sentiment-c"
PORT = int(os.environ.get("AGENT_C_PORT", "7303"))
PER_CALL = int(os.environ.get("AGENT_C_PER_CALL", "10"))
ANET_BASE_URL = os.environ.get("ANET_BASE_URL", "http://127.0.0.1:13923")

POSITIVE = {"good", "hot", "hello", "yes", "love", "great"}
NEGATIVE = {"bad", "cold", "no", "hate", "awful"}

app = FastAPI(title=NAME)


def classify(text: str) -> tuple[str, float]:
    """Token-frequency vs. tiny lexicon. Returns (label, confidence in [0,1])."""
    toks = [t.strip(".,!?;:").lower() for t in text.split()]
    pos = sum(t in POSITIVE for t in toks)
    neg = sum(t in NEGATIVE for t in toks)
    total = max(1, pos + neg)
    if pos > neg:
        return "positive", min(1.0, 0.5 + pos / (2 * total))
    if neg > pos:
        return "negative", min(1.0, 0.5 + neg / (2 * total))
    return "neutral", 0.5


def call_summarise(text: str) -> dict:
    with SvcClient(base_url=ANET_BASE_URL) as svc:
        peers = svc.discover(skill="summarise")
        if not peers:
            return {"summary": text, "source_lang": "?"}
        target = peers[0]
        resp = svc.call(target["peer_id"], target["services"][0]["name"],
                        "/v1/summarise", method="POST", body={"text": text})
        body = resp.get("body") or {}
        return body if isinstance(body, dict) else {"summary": text, "source_lang": "?"}


@app.get("/health")
def health(): return {"ok": True, "agent": NAME}


@app.get("/meta")
def meta():
    return {"name": NAME, "version": "0.1.0", "skill": "sentiment",
            "calls_into": ["summarise"]}


@app.post("/v1/sentiment")
async def do_sentiment(req: Request,
                       x_agent_did: Optional[str] = Header(default=None, convert_underscores=True)):
    body = await req.json()
    text = (body or {}).get("text") or ""
    print(f"[C] caller={x_agent_did} text={text[:60]!r}", flush=True)
    distilled = call_summarise(text)
    label, score = classify(distilled.get("summary") or "")
    return JSONResponse({
        "label": label, "score": round(score, 3),
        "summary": distilled.get("summary"),
        "source_lang": distilled.get("source_lang"),
        "agent": NAME,
    })


def main() -> None:
    threading.Thread(
        target=lambda: register_until_ready(
            NAME, PORT, paths=["/v1/sentiment", "/health", "/meta"],
            tags=["sentiment", "l3-demo"], description="sentiment classifier",
            per_call=PER_CALL, base_url=ANET_BASE_URL,
        ), daemon=True,
    ).start()
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")


if __name__ == "__main__":
    main()
