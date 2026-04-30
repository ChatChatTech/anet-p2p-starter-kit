"""my_agent.backend — your business logic, behind a thin FastAPI surface.

The anet daemon proxies HTTP requests from remote peers to this server. As far
as your code is concerned you are writing a normal FastAPI app — no P2P
plumbing, no auth header parsing. Two headers are auto-injected by the gateway:

    X-Agent-DID      did:key of the calling peer (verify identity here)
    X-Forwarded-Via  PeerID of the gateway hop (audit / observability)

Run standalone for development:

    uvicorn my_agent.backend:app --reload --port 8000

The default endpoints below mirror the .env.example MY_SVC_PATHS list:
  POST /echo    echoes the body + caller DID
  GET  /health  liveness probe used by `anet svc health`
  GET  /meta    machine-readable service description (CP7 register-time probe)

Replace these with your own routes. Keep at least /health and /meta — the
gateway uses them to surface your service in `anet svc health` /
`anet svc meta` so judges can browse it.
"""

import os
from typing import Optional

from fastapi import FastAPI, Header, Request
from fastapi.responses import JSONResponse, StreamingResponse

app = FastAPI(title=os.getenv("MY_SVC_NAME", "my-agent"))


@app.get("/health")
def health() -> dict:
    return {"ok": True, "service": os.getenv("MY_SVC_NAME", "my-agent")}


@app.get("/meta")
def meta() -> dict:
    return {
        "name": os.getenv("MY_SVC_NAME", "my-agent"),
        "version": "0.1.0",
        "description": os.getenv("MY_SVC_DESC", "starter agent"),
        "endpoints": [
            {"method": "POST", "path": "/echo",
             "in": {"msg": "string"}, "out": {"echo": "object", "caller_did": "string"}},
            {"method": "POST", "path": "/stream",
             "out": "text/event-stream of {tick,ts}"},
        ],
    }


@app.post("/echo")
async def echo(req: Request,
               x_agent_did: Optional[str] = Header(default=None, convert_underscores=True)) -> JSONResponse:
    body = await req.body()
    try:
        payload = await req.json()
    except Exception:  # noqa: BLE001 — body might not be JSON
        payload = body.decode("utf-8", "replace") if body else None
    return JSONResponse({"echo": payload, "caller_did": x_agent_did})


@app.post("/stream")
async def stream():
    """Demo of server-stream mode: emit 5 SSE-friendly chunks, then end.

    The gateway forwards each chunk back to the caller as one SSE `data:` event.
    Replace with token-by-token LLM output, file chunks, etc.
    """
    import json
    import time

    def gen():
        for i in range(5):
            time.sleep(0.2)
            yield json.dumps({"tick": i, "ts": time.time()}) + "\n"

    return StreamingResponse(gen(), media_type="text/plain")
