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
  GET      /api/scan/<id>     status + rich progress (3000/h/IP — the 4 s poll)
  POST     /api/scan/<id>/cancel   §3.4 safe exit (60/h/IP)
  POST     /api/scan/<id>/resume   §3.4 resume — launches a worker (5/h/IP)
  GET      /api/result/<id>   302 → fresh 15-min signed dashboard URL (120/h/IP)
  GET      /**                the one-page app (the ``webapp`` function)

Every route enforces its method (a wrong one is a 405, never a state change) and every
route is throttled per client IP; see ``_core`` for the buckets and why each is sized
the way it is.

The Hosting rewrite sends ``/api/**`` to the single ``api`` function (see
``firebase.json``); the named functions above remain directly callable too.

Deploy: see README.md in this folder.
"""

import json

from supervisorly.webapi import CORS_HEADERS

import _core

try:
    from firebase_functions import https_fn
except ImportError:      # local tooling/tests without the SDK — _core is the logic
    https_fn = None


def _params(req) -> dict:
    if req.method == "GET":
        return dict(req.args)
    return req.get_json(silent=True) or {}


#: The D-068 expansion key, as a Secret Manager secret name. A 2nd-gen function only
#: receives the secrets it DECLARES — putting a value in Secret Manager and setting the
#: env var is not enough on its own, and the failure is silent: the key simply is not
#: there at runtime and expansion fails closed as if no key existed. Declared on the two
#: functions that can reach ``handle_expand``: ``expand`` directly, and ``api``, which
#: routes ``/api/expand`` behind the Hosting rewrite. Nothing else needs it — the scan
#: worker never expands.
EXPAND_KEY_SECRET = "SUPERVISORLY_EXPAND_KEY"


def _ip(req) -> str:
    """The client IP for the §5.2 throttles — the entry the Google front end wrote.

    This used to take the LEFTMOST ``X-Forwarded-For`` entry, which is whatever the
    caller sent (audit W8-F1). GCP *appends* ``<client-ip>, <lb-ip>`` to the header it
    received rather than replacing it, so the leftmost value is fully attacker-supplied:
    a fresh ``X-Forwarded-For: 1.2.3.4`` per request gave every quota an unlimited
    budget — defeating the protection that exists precisely because OpenAlex's daily
    limit already 429'd this project once (§5.2).

    The second-from-last entry is the one the front end appended, so it cannot be
    forged. With no proxy chain (emulator, direct call, tests) fall back to the socket
    peer, which is likewise unspoofable, and only then to a lone header value.
    """
    parts = [p.strip() for p in req.headers.get("X-Forwarded-For", "").split(",")
             if p.strip()]
    if len(parts) >= 2:
        return parts[-2]
    return getattr(req, "remote_addr", "") or (parts[0] if parts else "")


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

    def _deny_method(req, *allowed: str):
        """405 unless the method is allowed; ``None`` when it is (audit W8-F5).

        These named wrappers used to run their handler on ANY method. Since ``_params``
        reads the query string on GET and ``_job_id`` falls back to ``params["id"]``,
        that made ``GET /scan_cancel?id=<job id>`` a state change — one any third-party
        page could fire from an ``<img>`` tag, with the browser attaching nothing but
        still cancelling a stranger's scan if the id ever leaked. The regex router in
        ``_core.route_api`` always checked the method; these did not.
        """
        if req.method in allowed:
            return None
        return _json(405, {"error": "method not allowed — this endpoint accepts "
                                    + " or ".join(allowed)})

    @https_fn.on_request()
    def subject_map(req: https_fn.Request) -> https_fn.Response:
        """The original endpoint — kept as an alias for anything already deployed.

        It used to call ``handle_subject_map`` directly, which meant it was the one
        subject-map route with NO throttle: the 30/h cap on ``/api/map`` was a rename
        away from being bypassed entirely (audit W8-F6). It now shares ``_core``'s
        throttled path, so both names cost the same budget.
        """
        if req.method == "OPTIONS":                             # CORS preflight
            return _preflight()
        return (_deny_method(req, "GET", "POST")
                or _respond(*_core.handle_map(_params(req), ip=_ip(req))))

    @https_fn.on_request(secrets=[EXPAND_KEY_SECRET])
    def expand(req: https_fn.Request) -> https_fn.Response:
        if req.method == "OPTIONS":
            return _preflight()
        return (_deny_method(req, "GET", "POST")
                or _respond(*_core.handle_expand(_params(req), ip=_ip(req))))

    @https_fn.on_request()
    def map(req: https_fn.Request) -> https_fn.Response:
        if req.method == "OPTIONS":
            return _preflight()
        return (_deny_method(req, "GET", "POST")
                or _respond(*_core.handle_map(_params(req), ip=_ip(req))))

    @https_fn.on_request()
    def scan_start(req: https_fn.Request) -> https_fn.Response:
        if req.method == "OPTIONS":
            return _preflight()
        return (_deny_method(req, "POST")
                or _respond(*_core.handle_scan_start(_params(req), ip=_ip(req))))

    @https_fn.on_request()
    def scan_status(req: https_fn.Request) -> https_fn.Response:
        if req.method == "OPTIONS":
            return _preflight()
        return (_deny_method(req, "GET")
                or _respond(*_core.handle_scan_status(_job_id(req, _params(req)),
                                                      ip=_ip(req))))

    @https_fn.on_request()
    def scan_cancel(req: https_fn.Request) -> https_fn.Response:
        if req.method == "OPTIONS":
            return _preflight()
        return (_deny_method(req, "POST")
                or _respond(*_core.handle_scan_cancel(_job_id(req, _params(req)),
                                                      ip=_ip(req))))

    @https_fn.on_request()
    def scan_resume(req: https_fn.Request) -> https_fn.Response:
        if req.method == "OPTIONS":
            return _preflight()
        return (_deny_method(req, "POST")
                or _respond(*_core.handle_scan_resume(_job_id(req, _params(req)),
                                                      ip=_ip(req))))

    @https_fn.on_request()
    def scan_result(req: https_fn.Request) -> https_fn.Response:
        if req.method == "OPTIONS":
            return _preflight()
        return (_deny_method(req, "GET")
                or _respond(*_core.handle_scan_result(_job_id(req, _params(req)),
                                                      ip=_ip(req))))

    @https_fn.on_request()
    def webapp(req: https_fn.Request) -> https_fn.Response:
        if req.method == "OPTIONS":
            return _preflight()
        return https_fn.Response(
            _core.webapp_html(), status=200,
            headers={**CORS_HEADERS, "Content-Type": "text/html; charset=utf-8"})

    @https_fn.on_request(secrets=[EXPAND_KEY_SECRET])
    def api(req: https_fn.Request) -> https_fn.Response:
        """The single router behind the Hosting ``/api/**`` rewrite."""
        if req.method == "OPTIONS":
            return _preflight()
        status, body = _core.route_api(req.method, req.path, _params(req), ip=_ip(req))
        return _respond(status, body)
