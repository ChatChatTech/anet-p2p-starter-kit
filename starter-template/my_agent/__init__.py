"""my_agent — p2p starter scaffold.

Three modules:
  * backend.py  — your business logic (FastAPI). Replace with whatever your
                  agent actually does.
  * service.py  — registers `backend` with the local anet daemon and runs a
                  resilient register-loop (re-register if daemon restarts).
  * client.py   — discovers a peer that exposes the target skill and calls it.

Run order during development:

    bash scripts/two-node.sh           # term-1 (or once, leaves daemons up)
    uvicorn my_agent.backend:app --port 8000  # term-2
    python -m my_agent.service         # term-3 — registers backend with gateway
    python -m my_agent.client          # term-4 — discovers and calls
"""
__version__ = "0.1.0"
