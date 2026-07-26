"""HTTP wrapper for the subject-map stage (D-066) — framework-agnostic.

This is the seam between the deterministic engine and any HTTP host: Firebase
Functions (see ``firebase/main.py``), a local dev server (``python -m
supervisorly.webapi --port 8765``), or any other framework. It owns request
validation and error shape only — the mapping logic lives in
``discover/subjects.py`` and stays LLM-free (D-009).

The endpoint is read-only and polite: the only credential is the contact email
for the OpenAlex polite pool (D-019/023), taken from the ``email`` param or the
``SUPERVISORLY_CONTACT_EMAIL`` environment variable.
"""

from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

from . import preflight
from .discover import subjects
from .fetch.transport import httpx_transport

_CONTENT_JSON = "application/json; charset=utf-8"
CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
}


def _error(status: int, message: str) -> tuple[int, dict]:
    return status, {"error": message}


def handle_subject_map(params: dict, *, transport=None, environ=None) -> tuple[int, dict]:
    """Map a free-text field to the hierarchical subject map.

    ``params``: ``{"field": str, "email": str (optional), "max_results": int (optional)}``.
    Returns ``(http_status, jsonable_dict)``. ``transport``/``environ`` are injectable
    for tests; production uses httpx and os.environ.
    """
    field = str(params.get("field") or "").strip()
    if not field:
        return _error(400, "missing required parameter 'field' "
                           "(a free-text research field, e.g. ?field=NLP)")
    environ = os.environ if environ is None else environ
    email = str(params.get("email") or environ.get(preflight.CONTACT_EMAIL_ENV) or "").strip()
    if not preflight._EMAIL_RE.match(email):
        return _error(400, "a valid contact email is required (param 'email' or the "
                           f"{preflight.CONTACT_EMAIL_ENV} env var) — it joins the OpenAlex "
                           "polite pool (D-019)")
    raw_max = params.get("max_results")
    try:
        max_results = int(raw_max) if raw_max is not None else 25
    except (TypeError, ValueError):
        return _error(400, "'max_results' must be an integer")
    if not 1 <= max_results <= 100:
        return _error(400, "'max_results' must be between 1 and 100")

    if transport is None:
        transport = httpx_transport(
            user_agent=f"SupervisorlyBot/0.1 (mailto:{email})")
    try:
        smap = subjects.subject_map(field, transport, email=email, max_results=max_results)
    except Exception as exc:                             # never leak a stack over HTTP
        return _error(500, f"subject-map failed: {type(exc).__name__}")
    return 200, smap


# ── local dev server: python -m supervisorly.webapi [--port 8765] ─────────────


class _Handler(BaseHTTPRequestHandler):
    def _send(self, status: int, body: dict) -> None:
        payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", _CONTENT_JSON)
        self.send_header("Content-Length", str(len(payload)))
        for k, v in CORS_HEADERS.items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(payload)

    def do_OPTIONS(self):                                # CORS preflight
        self._send(204, {})

    def do_GET(self):
        qs = {k: v[0] for k, v in parse_qs(urlparse(self.path).query).items()}
        if urlparse(self.path).path.rstrip("/") == "/subject_map":
            status, body = handle_subject_map(qs)
        else:
            status, body = _error(404, "unknown path — try /subject_map?field=...")
        self._send(status, body)

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        try:
            params = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            params = {}
        if urlparse(self.path).path.rstrip("/") == "/subject_map":
            status, body = handle_subject_map(params)
        else:
            status, body = _error(404, "unknown path — try /subject_map?field=...")
        self._send(status, body)

    def log_message(self, *args):                        # keep the console quiet
        pass


def main(argv: list[str] | None = None) -> int:
    import argparse
    p = argparse.ArgumentParser(prog="python -m supervisorly.webapi",
                                description="local subject-map dev server")
    p.add_argument("--port", type=int, default=8765)
    args = p.parse_args(argv)
    print(f"subject-map server on http://127.0.0.1:{args.port}/subject_map?field=...")
    HTTPServer(("127.0.0.1", args.port), _Handler).serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
