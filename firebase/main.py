"""Firebase Functions (Python, 2nd gen) — the Supervisorly web endpoints.

Thin wrappers only: ALL logic lives in ``_core.py`` (Firestore job store, throttles,
expansion cache, Cloud Run Job bridge, signed URLs) on top of the
``supervisorly.webapi`` handlers, so the Functions and the local dev server share one
semantics. Every function handles the OPTIONS preflight, answers JSON with CORS
headers, and never leaks a stack trace.

Endpoints (mirroring the local ``supervisorly.webapi`` ones, plan §5):

  GET/POST /api/expand        LLM query expansion, per-field cache + 10/h/IP throttle
  GET/POST /api/map           subject map (30/h/IP)        [was: subject_map, kept]
  POST     /api/scan          start a scan job → Cloud Run Job execution (5/h/IP)
  GET      /api/scan/<id>     status + rich progress
  POST     /api/scan/<id>/cancel | /resume   §3.4 safe exit / resume
  GET      /api/result/<id>   302 → fresh 15-min signed dashboard URL
  GET      /**                the one-page app (the ``webapp`` function)

The Hosting rewrite sends ``/api/**`` to the single ``api`` function (see
``firebase.json``); the named functions above remain directly callable too.

Deploy: see README.md in this folder.
"""

import json

from supervisorly.webapi import CORS_HEADERS, handle_subject_map

import _core

try:
    from firebase_functions import https_fn
except ImportError:      # local tooling/tests without the SDK — _core is the logic
    https_fn = None


def _params(req) -> dict:
    if req.method == "GET":
        return dict(req.args)
    return req.get_json(silent=True) or {}


def _ip(req) -> str:
    fwd = req.headers.get("X-Forwarded-For", "")
    if fwd:
        return fwd.split(",")[0].strip()
    return getattr(req, "remote_addr", "") or ""


def _job_id(req, params: dict) -> str:
    tail = req.path.rstrip("/").rsplit("/", 1)[-1]
    own = {"expand", "map", "subject_map", "scan_start", "scan_status",
           "scan_cancel", "scan_resume", "scan_result", "api", "webapp"}
    if tail and tail not in own:
        return tail
    return str(params.get("id") or params.get("job_id") or "")


if https_fn is not None:

    def _preflight():
        return https_fn.Response("", status=204, headers=CORS_HEADERS)

    def _json(status: int, body: dict):
        return https_fn.Response(
            json.dumps(body, ensure_ascii=False),
            status=status,
            headers={**CORS_HEADERS, "Content-Type": "application/json; charset=utf-8"})

    def _respond(status: int, body: dict):
        if status == 302:                       # the signed-URL result redirect
            return https_fn.Response("", status=302,
                                     headers={**CORS_HEADERS,
                                              "Location": body["url"]})
        return _json(status, body)

    @https_fn.on_request()
    def subject_map(req: https_fn.Request) -> https_fn.Response:
        """The original endpoint — kept verbatim for anything already deployed."""
        if req.method == "OPTIONS":                             # CORS preflight
            return _preflight()
        status, body = handle_subject_map(_params(req))
        return _json(status, body)

    @https_fn.on_request()
    def expand(req: https_fn.Request) -> https_fn.Response:
        if req.method == "OPTIONS":
            return _preflight()
        return _respond(*_core.handle_expand(_params(req), ip=_ip(req)))

    @https_fn.on_request()
    def map(req: https_fn.Request) -> https_fn.Response:
        if req.method == "OPTIONS":
            return _preflight()
        return _respond(*_core.handle_map(_params(req), ip=_ip(req)))

    @https_fn.on_request()
    def scan_start(req: https_fn.Request) -> https_fn.Response:
        if req.method == "OPTIONS":
            return _preflight()
        return _respond(*_core.handle_scan_start(_params(req), ip=_ip(req)))

    @https_fn.on_request()
    def scan_status(req: https_fn.Request) -> https_fn.Response:
        if req.method == "OPTIONS":
            return _preflight()
        return _respond(*_core.handle_scan_status(_job_id(req, _params(req))))

    @https_fn.on_request()
    def scan_cancel(req: https_fn.Request) -> https_fn.Response:
        if req.method == "OPTIONS":
            return _preflight()
        return _respond(*_core.handle_scan_cancel(_job_id(req, _params(req))))

    @https_fn.on_request()
    def scan_resume(req: https_fn.Request) -> https_fn.Response:
        if req.method == "OPTIONS":
            return _preflight()
        return _respond(*_core.handle_scan_resume(_job_id(req, _params(req))))

    @https_fn.on_request()
    def scan_result(req: https_fn.Request) -> https_fn.Response:
        if req.method == "OPTIONS":
            return _preflight()
        return _respond(*_core.handle_scan_result(_job_id(req, _params(req))))

    @https_fn.on_request()
    def webapp(req: https_fn.Request) -> https_fn.Response:
        if req.method == "OPTIONS":
            return _preflight()
        return https_fn.Response(
            _core.webapp_html(), status=200,
            headers={**CORS_HEADERS, "Content-Type": "text/html; charset=utf-8"})

    @https_fn.on_request()
    def api(req: https_fn.Request) -> https_fn.Response:
        """The single router behind the Hosting ``/api/**`` rewrite."""
        if req.method == "OPTIONS":
            return _preflight()
        status, body = _core.route_api(req.method, req.path, _params(req), ip=_ip(req))
        return _respond(status, body)
