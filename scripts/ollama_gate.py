#!/usr/bin/env python3
"""Token gate in front of Ollama (stdlib only). Ollama has NO login of its own: never expose port 11434 to the internet.
Run this gate and point the Cloudflare tunnel at the GATE port instead:

    set OLLAMA_GATE_TOKEN=<long random secret>            (PowerShell: $env:OLLAMA_GATE_TOKEN="...")
    python scripts/ollama_gate.py                         (listens on 127.0.0.1:11435, forwards to 127.0.0.1:11434)
    cloudflared tunnel --url http://localhost:11435

It only forwards POST /api/chat, POST /api/embed and GET /api/tags, and only when the request carries
`Authorization: Bearer <token>`. Responses are streamed through immediately (keeps the tunnel from timing out on slow generations).
Generate a token:  python -c "import secrets; print(secrets.token_urlsafe(32))"
"""
import argparse
import hmac
import http.client
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ALLOWED = {("POST", "/api/chat"), ("POST", "/api/embed"), ("GET", "/api/tags")}
MAX_BODY = 8 * 1024 * 1024


def make_server(listen_port: int, upstream_host: str, upstream_port: int, token: str) -> ThreadingHTTPServer:
    class Gate(BaseHTTPRequestHandler):
        # close-delimited body: lets us stream without Content-Length
        protocol_version = "HTTP/1.0"

        def log_message(self, fmt, *args):
            sys.stderr.write("gate: %s %s -> %s\n" % (self.command,
                             self.path.split("?")[0], args[1] if len(args) > 1 else ""))

        def _deny(self, code: int, msg: str):
            body = msg.encode()
            self.send_response(code)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _handle(self):
            supplied = self.headers.get("Authorization", "")
            if not hmac.compare_digest(supplied.encode(), f"Bearer {token}".encode()):
                return self._deny(401, "unauthorized")
            path = self.path.split("?")[0]
            if (self.command, path) not in ALLOWED:
                return self._deny(403, "path not allowed")
            n = int(self.headers.get("Content-Length") or 0)
            if n > MAX_BODY:
                return self._deny(413, "too large")
            body = self.rfile.read(n) if n else None
            try:
                conn = http.client.HTTPConnection(
                    upstream_host, upstream_port, timeout=900)
                conn.request(self.command, path, body=body, headers={
                             "Content-Type": "application/json"})
                resp = conn.getresponse()
            except OSError:
                return self._deny(502, "Ollama is not running on this computer")
            self.send_response(resp.status)
            self.send_header(
                "Content-Type", resp.getheader("Content-Type", "application/json"))
            self.end_headers()
            while True:
                chunk = resp.read1(8192) if hasattr(
                    resp, "read1") else resp.read(8192)
                if not chunk:
                    break
                self.wfile.write(chunk)
                self.wfile.flush()
            conn.close()

        do_GET = do_POST = _handle

    return ThreadingHTTPServer(("127.0.0.1", listen_port), Gate)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--listen", type=int, default=11435)
    ap.add_argument("--ollama-port", type=int, default=11434)
    a = ap.parse_args()
    tok = os.getenv("OLLAMA_GATE_TOKEN", "")
    if len(tok) < 16:
        sys.exit(
            "Set OLLAMA_GATE_TOKEN to a long random secret (16+ characters) first. See the docstring.")
    srv = make_server(a.listen, "127.0.0.1", a.ollama_port, tok)
    print(
        f"Gate listening on 127.0.0.1:{a.listen} -> Ollama 127.0.0.1:{a.ollama_port}. Point the tunnel at http://localhost:{a.listen}", flush=True)
    srv.serve_forever()
