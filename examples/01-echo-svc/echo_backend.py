"""Tiny stdlib HTTP echo backend (no FastAPI / uvicorn dep).

Listens on 127.0.0.1:$ECHO_PORT (default 7100). Echoes the POST body back as
JSON, exposes /health for `anet svc health`, /meta for `anet svc meta`.
"""

import http.server
import json
import os
import sys

PORT = int(os.environ.get("ECHO_PORT", "7100"))


class H(http.server.BaseHTTPRequestHandler):
    def _send(self, status, payload):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):  # noqa: N802
        if self.path.startswith("/meta"):
            self._send(200, json.dumps({
                "name": "echo-l1", "version": "1.0.0",
                "endpoints": [{"method": "POST", "path": "/echo"}],
            }).encode())
        else:
            self._send(200, b'{"ok":true}')

    def do_POST(self):  # noqa: N802
        n = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(n) if n else b"{}"
        did = self.headers.get("X-Agent-DID", "<missing>")
        sys.stderr.write(f"[echo] {self.path} did={did} body={body[:120]!r}\n")
        try:
            decoded = json.loads(body)
        except Exception:  # noqa: BLE001
            decoded = body.decode("utf-8", "replace")
        self._send(200, json.dumps({"echo": decoded, "caller_did": did}).encode())

    def log_message(self, *_):
        return


if __name__ == "__main__":
    print(f"[echo] listening on 127.0.0.1:{PORT}", flush=True)
    http.server.HTTPServer(("127.0.0.1", PORT), H).serve_forever()
