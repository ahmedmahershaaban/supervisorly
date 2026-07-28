"""HTTP wrapper for the subject-map stage (D-066) + the async scan job (§3/§5 of
docs/FIREBASE_WEB_PLAN.md) — framework-agnostic.

This is the seam between the deterministic engine and any HTTP host: Firebase
Functions (see ``firebase/main.py``), a local dev server (``python -m
supervisorly.webapi --port 8765``), or any other framework. It owns request
validation and error shape only — the mapping logic lives in
``discover/subjects.py`` and stays LLM-free (D-009); the job lifecycle lives in
``jobs.py`` (local parity for Firestore + Cloud Run).

Endpoints (all CORS, JSON, stack-free errors):

- ``GET/POST /api/map`` (alias ``/subject_map``) — the read-only subject map; the only
  credential is the contact email for the OpenAlex polite pool (D-019/023), taken from
  the ``email`` param or the ``SUPERVISORLY_CONTACT_EMAIL`` environment variable.
- ``GET/POST /api/expand`` — optional LLM query expansion (D-068, fail-closed).
- ``POST /api/scan`` — start a scan job (idempotent, one active job per email).
- ``GET /api/scan/<id>`` — status + rich progress (the watchdog flip lives here, §3.2).
- ``POST /api/scan/<id>/cancel`` | ``POST /api/scan/<id>/resume`` — §3.4 safe exit/resume.
- ``GET /api/result/<id>`` — result paths (local dev; Firebase swaps in signed URLs).

Job ids are unguessable uuid4 and are the access token: status is readable only by id
and jobs are never listable (D-069).
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

from . import cli, jobs, preflight
from .discover import expand, subjects
from .discover.countries import to_country_code
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
    # `queries` (a list) maps MANY phrasings in ONE request and merges them server-side;
    # `field` (a string) is the original single-phrasing form and still works unchanged.
    #
    # This is the B-001 migration, taken at the trigger B-001 named. The page used to call
    # this once per phrasing to keep per-variant failure survivable — with the step-2 slider
    # asking for up to 50 phrasings per field, that is 50 units of a 30/hour budget for one
    # click, i.e. the feature would 429 the moment a student used it. `subject_map_multi` now
    # reports `failed_queries` per variant, so the honesty that kept the merge in the browser
    # is preserved on the server and the whole click costs one unit.
    raw_queries = params.get("queries")
    queries = [q.strip() for q in raw_queries
               if isinstance(q, str) and q.strip()] if isinstance(raw_queries, list) else []
    field = str(params.get("field") or "").strip()
    if not queries and not field:
        return _error(400, "missing required parameter 'field' "
                           "(a free-text research field, e.g. ?field=NLP) or 'queries' "
                           "(a list of phrasings to map and merge)")
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
        if queries:
            smap = subjects.subject_map_multi(queries, transport, email=email,
                                              max_results=max_results)
        else:
            smap = subjects.subject_map(field, transport, email=email,
                                        max_results=max_results)
    except Exception as exc:                             # never leak a stack over HTTP
        return _error(500, f"subject-map failed: {type(exc).__name__}")
    return 200, smap


#: Hard caps on a client report. The browser is untrusted input like any other, and this
#: endpoint writes to OUR logs — so it must never become a way to flood them or to smuggle
#: personal data into a place the privacy rules do not reach.
CLIENTLOG_MAX_BYTES = 4 * 1024
CLIENTLOG_MAX_MESSAGE = 500
CLIENTLOG_KINDS = ("js_error", "unhandled_rejection", "api_error", "diagnostics")

_EMAILISH = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")


def _scrub(text: str, limit: int) -> str:
    """Trim, cap, strip control characters, and REDACT anything email-shaped.

    The page is written not to send an address, but this is the last line before a value
    reaches a log we keep — and "the client promised not to" is not a control. A student's
    email is the one piece of personal data the browser holds, so it is redacted here even
    though it should never arrive (D-005)."""
    s = _EMAILISH.sub("[email-redacted]", str(text or ""))
    s = "".join(ch for ch in s if ch == "\n" or ch == "\t" or ch >= " ")
    return s.strip()[:limit]


def handle_client_log(params: dict, *, environ=None, now=None) -> tuple[int, dict]:
    """Accept ONE browser-side error report and write it to the server log (D-071).

    This exists because the two worst bugs found in production — a finished scan claiming
    the user was offline, and an "Open dashboard" button that failed every time — happened
    entirely in the browser and produced NO server log line at all. The CORS failure never
    even sent a request. The backend logged a healthy day while the page was broken.

    Deliberately narrow, so it cannot drift into tracking (D-069 ships no tracking):

    * **errors only** — the `kind` must be one of a fixed set; there is no page-view, no
      session id, no user id, no timing beacon, and nothing is sent on a healthy run;
    * **no identity** — no email, no plan, no professor data; anything email-shaped is
      redacted server-side regardless of what was sent;
    * **capped** — 4 KB per report, 500 chars per message, and throttled per IP in the
      Firebase wrapper, so it cannot be used to flood the logs;
    * **answers 204 always** — a logging endpoint must never tell a caller anything, and a
      failure here must never surface to the student mid-scan.
    """
    kind = str(params.get("kind") or "").strip()
    if kind not in CLIENTLOG_KINDS:
        return 204, {}                       # unknown kind: accept and drop, never explain
    if len(json.dumps(params, ensure_ascii=False).encode("utf-8")) > CLIENTLOG_MAX_BYTES:
        return 204, {}

    job = str(params.get("job_id") or "")[:64]
    entry = {
        "severity": "WARNING",
        "source": "client",
        "kind": kind,
        "job": job if jobs._SAFE_ID.fullmatch(job) else None,
        "message": _scrub(params.get("message"), CLIENTLOG_MAX_MESSAGE),
        "where": _scrub(params.get("where"), 200),
        "phase": _scrub(params.get("phase"), 80),
        "status": params.get("status") if isinstance(params.get("status"), int) else None,
        "ua": _scrub(params.get("ua"), 180),
    }
    print(json.dumps({k: v for k, v in entry.items() if v not in (None, "")},
                     ensure_ascii=True), flush=True)
    return 204, {}


def handle_expand(params: dict, *, environ=None, transport=None) -> tuple[int, dict]:
    """Expand a free-text field into search-string variants (D-068).

    The API key, endpoint and model all come from server config
    (``SUPERVISORLY_EXPAND_KEY`` / ``_BASE_URL`` / ``_MODEL``) ONLY — never a request
    param, so a caller cannot redirect the call or pick the model. NOTE: the 30-day
    per-field expansion cache (§5) lives in the Firebase wrapper (Firestore), NOT here —
    this handler always asks the engine, which itself fails closed (no key / any error →
    the raw field proceeds, ``expanded: False``).
    """
    field = str(params.get("field") or "").strip()
    if not field:
        return _error(400, "missing required parameter 'field' "
                           "(a free-text research field, e.g. ?field=NLP)")
    environ = os.environ if environ is None else environ
    key = (environ.get(expand.ENV_KEY) or "").strip() or None
    # How many phrasings to ask for (step 2's slider). Clamped, never rejected: a slider
    # position is a preference, and 400-ing a scan over one would be absurd.
    count = expand.clamp_count(params.get("count", expand.DEFAULT_VARIANTS))
    try:
        return 200, expand.expand_query(field, api_key=key, transport=transport,
                                        environ=environ, count=count)
    except Exception as exc:                             # never leak a stack over HTTP
        return _error(500, f"expand failed: {type(exc).__name__}")


# ── POST /api/scan: validation + server-side cost guards (§3.5) ──────────────

PLAN_MAX_BYTES = 64 * 1024        # plan JSON ≤ 64 KB serialized
MAX_TOPICS = 25                   # resolved_topic_ids per plan
MAX_UNIVERSITIES = 50             # universities per plan
MAX_TARGETS = 100                 # named targets per plan
SHORTLIST_MIN, SHORTLIST_MAX = 1, 200
MAX_INSTITUTIONS_MIN, MAX_INSTITUTIONS_MAX = 1, 300
FIELD_MAX_CHARS = 200

#: Local dev default for job working dirs + the JSON store (output/ is git-ignored, D-005).
DEFAULT_WORK_ROOT = Path("output/jobs")


def _plan_cap_errors(plan: dict) -> list[str]:
    """The §3.5 collection caps — key-named, honest messages for a 400."""
    errors: list[str] = []
    field = plan.get("field")
    if isinstance(field, str) and len(field) > FIELD_MAX_CHARS:
        errors.append(f"'field' must be at most {FIELD_MAX_CHARS} characters "
                      f"(got {len(field)})")
    topics = plan.get("resolved_topic_ids")
    if isinstance(topics, list) and len(topics) > MAX_TOPICS:
        errors.append(f"'resolved_topic_ids' must hold at most {MAX_TOPICS} topics "
                      f"(got {len(topics)})")
    unis = plan.get("universities")
    if isinstance(unis, list) and len(unis) > MAX_UNIVERSITIES:
        errors.append(f"'universities' must hold at most {MAX_UNIVERSITIES} entries "
                      f"(got {len(unis)})")
    targets = plan.get("targets")
    if isinstance(targets, list) and len(targets) > MAX_TARGETS:
        errors.append(f"'targets' must hold at most {MAX_TARGETS} entries "
                      f"(got {len(targets)})")
    return errors


def _int_param(params: dict, key: str, *, default, lo: int, hi: int):
    """An optional integer scope param within [lo, hi]; returns ``(value, error)``."""
    raw = params.get(key)
    if raw is None:
        return default, None
    if isinstance(raw, bool):
        return None, f"'{key}' must be an integer"
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None, f"'{key}' must be an integer"
    if not lo <= value <= hi:
        return None, f"'{key}' must be between {lo} and {hi}"
    return value, None


def _job_paths(work_root, job_id: str) -> dict:
    """Per-job working paths: the SQLite DB + snapshots (kept for resume, §3.1) and the
    result files ``run_scan_job`` writes before the status flips."""
    root = Path(work_root) if work_root else DEFAULT_WORK_ROOT
    d = root / job_id
    return {"db_path": d / "supervisorly.sqlite",
            "snap_root": d / ".cache" / "snaps",
            "out_html": d / "dashboard.html",
            "out_json": d / "dashboard.json"}


def handle_scan_start(params: dict, *, store, worker=None, transport=None,
                      work_root=None, environ=None) -> tuple[int, dict]:
    """Start a scan job (§3.3 idempotent, §3.5 caps): ``{"email", "plan",
    "shortlist"?, "max_institutions"?}`` → 202 ``{"job_id"}``.

    Plan validation reuses the CLI's own rules (``cli.PLAN_REQUIRED_KEYS`` +
    ``cli._plan_value_errors``, D-002) plus the server caps; a double-submit with the
    same email+plan returns 200 with the EXISTING job id; a different plan while one is
    active gets a 429."""
    environ = os.environ if environ is None else environ
    email = str(params.get("email") or "").strip()
    if not preflight._EMAIL_RE.match(email):
        return _error(400, "a valid contact email is required (param 'email') — it joins "
                           "the OpenAlex polite pool (D-019)")
    plan = params.get("plan")
    if not isinstance(plan, dict):
        return _error(400, "missing required parameter 'plan' (a Scan Studio plan JSON "
                           f"object with keys: {', '.join(cli.PLAN_REQUIRED_KEYS)})")
    if len(json.dumps(plan, ensure_ascii=False).encode("utf-8")) > PLAN_MAX_BYTES:
        return _error(400, f"'plan' must serialize to at most "
                           f"{PLAN_MAX_BYTES // 1024} KB")
    missing = [k for k in cli.PLAN_REQUIRED_KEYS if k not in plan]
    if missing:
        return _error(400, f"'plan' is missing required key(s): {', '.join(missing)}")
    errors = cli._plan_value_errors(plan) + _plan_cap_errors(plan)
    shortlist, err = _int_param(params, "shortlist", default=40,
                                lo=SHORTLIST_MIN, hi=SHORTLIST_MAX)
    if err:
        errors.append(err)
    max_inst, err = _int_param(params, "max_institutions", default=None,
                               lo=MAX_INSTITUTIONS_MIN, hi=MAX_INSTITUTIONS_MAX)
    if err:
        errors.append(err)
    if errors:
        return _error(400, "; ".join(errors))

    # The wizard sends a country NAME ("Egypt") because that is what a person types. ROR's
    # filter needs ISO 3166-1 alpha-2. `cli.cmd_scan` resolves this where it builds the plan
    # and fails loud on anything unrecognised — the hosted path never did, so every web scan
    # queried ROR with `country.country_code:EGYPT`, matched nothing, and finished "done"
    # with zero results, reported as an honest-looking coverage gap for a country that has
    # 285 institutions in ROR. Normalise here, before the job key is derived, so the stored
    # plan and the idempotency key both carry the resolved code.
    raw_country = plan.get("country")
    if not isinstance(raw_country, str) or not raw_country.strip():
        # A BLANK country used to slip through this check entirely: `country` is in
        # PLAN_REQUIRED_KEYS so the key had to exist, but "" satisfied that and then skipped
        # the branch below. ROR was searched for no country, matched no institutions, and the
        # student was told "Done — your dashboard is ready." over an empty table — a scan
        # accepted, a worker launched and a result that explained nothing. Found by a browser
        # driver that filled the field on the wrong wizard step, which is exactly the mistake
        # a distracted person makes. Unrecognised already failed loud (D-002); missing must too.
        return _error(400, "a country is required (plan key 'country') — pass an ISO 3166-1 "
                           "alpha-2 code (e.g. EG) or an English country name (e.g. Egypt)")
    code = to_country_code(raw_country)
    if not code:
        return _error(400, f"unrecognized country {raw_country.strip()!r} — pass an "
                           "ISO 3166-1 alpha-2 code (e.g. EG) or an English country "
                           "name (e.g. Egypt)")
    plan = {**plan, "country": code}

    job_key = jobs.new_job_key(email, plan)
    active = store.active_job_for(email)
    if active is not None:
        if active.get("job_key") == job_key:
            # idempotent start (§3.3): a double-click/refresh gets the EXISTING job id
            return 200, {"job_id": active["job_id"], "existing": True}
        return _error(429, f"you already have an active scan job ({active['job_id']}) — "
                           "wait for it to finish, or cancel it and start again")
    job_id = uuid4().hex
    try:
        store.create(email, plan, job_id, job_key)
    except jobs.JobExists as exc:      # the race backstop (§3.3)
        return 200, {"job_id": exc.job_id, "existing": True}

    worker = worker if worker is not None else jobs.Worker()
    worker.submit(store, job_id, plan=plan, email=email, transport=transport,
                  openalex_key=preflight.openalex_key(environ),
                  shortlist=shortlist, max_institutions=max_inst,
                  **_job_paths(work_root, job_id))
    return 202, {"job_id": job_id}


def _counts_from(progress: list[dict]) -> dict:
    """Latest known counts, folded from the event stream (newest wins per key)."""
    counts: dict = {}
    for e in progress:
        phase, data = e.get("phase"), e.get("data") or []
        if phase == "enumerated" and len(data) >= 2:
            counts["targets"], counts["institutions"] = data[0], data[1]
        elif phase == "deep_dive_start" and data:
            counts["deep_dive_total"] = data[0]
        elif phase == "deep_dive_progress" and len(data) >= 2:
            counts["deep_dive_done"], counts["deep_dive_total"] = data[0], data[1]
    return counts


def _age_s(iso) -> float | None:
    if not iso:
        return None
    try:
        ref = datetime.fromisoformat(iso)
    except (TypeError, ValueError):
        return None
    return round((datetime.now(timezone.utc) - ref).total_seconds(), 3)


def handle_scan_status(job_id: str, *, store) -> tuple[int, dict]:
    """Job status + rich progress (§4.1/§5). The stuck-job watchdog lives HERE (§3.2):
    a stale heartbeat flips the job to ``failed`` ("worker stalled; safe to resume")."""
    job = store.get(job_id)
    if job is None:
        return _error(404, "unknown job id — a job id is its access token and jobs are "
                           "never listable (D-069)")
    if store.is_stalled(job_id):
        job = store.set_status(job_id, "failed", error=jobs.STALL_MESSAGE)
    progress = list(job.get("progress") or [])
    return 200, {
        "job_id": job_id,
        "status": job["status"],
        "phase": progress[-1]["phase"] if progress else None,
        "counts": _counts_from(progress),
        "progress": progress[-20:],
        "heartbeat_age_s": _age_s(job.get("heartbeat_at")),
        "warnings": [e["data"][0] for e in progress
                     if e.get("phase") == "partial_warning" and e.get("data")],
        "error": job.get("error"),
        "result": job.get("result"),
    }


def handle_scan_cancel(job_id: str, *, store) -> tuple[int, dict]:
    """Cooperative cancel (§3.4): idempotent — the worker stops at the next target
    checkpoint and exports the partial results honestly."""
    job = store.get(job_id)
    if job is None:
        return _error(404, "unknown job id")
    if job.get("status") in jobs.TERMINAL_STATUSES:
        return _error(409, f"job is already {job['status']} — nothing left to cancel")
    store.request_cancel(job_id)
    return 202, {"job_id": job_id, "status": "cancelling"}


def handle_scan_resume(job_id: str, *, store, worker=None, transport=None,
                       work_root=None, environ=None) -> tuple[int, dict]:
    """Resume from ``failed``/``cancelled`` (§3.4): the status resets to ``queued`` (the
    progress history + SQLite DB are KEPT) and the worker re-runs the same job doc — the
    engine's checkpoint state skips completed targets from the persisted DB."""
    environ = os.environ if environ is None else environ
    job = store.get(job_id)
    if job is None:
        return _error(404, "unknown job id")
    if job.get("status") not in ("failed", "cancelled"):
        return _error(409, f"only a failed or cancelled job can be resumed "
                           f"(current status: {job['status']})")
    store.set_status(job_id, "queued", cancel_requested=False, error=None)
    run_params = job.get("run_params") or {}
    worker = worker if worker is not None else jobs.Worker()
    worker.submit(store, job_id, plan=job["plan"], email=job["email"],
                  transport=transport,
                  openalex_key=preflight.openalex_key(environ),
                  shortlist=run_params.get("shortlist", 40),
                  max_institutions=run_params.get("max_institutions"),
                  resume=True, **_job_paths(work_root, job_id))
    return 202, {"job_id": job_id, "status": "queued"}


def handle_scan_result(job_id: str, *, store) -> tuple[int, dict]:
    """The result of a done job: local dev returns plain file paths — the Firebase
    wrapper swaps in 15-min signed URLs (§5). Result-before-status (§3.1) means a done
    job can never lack its files."""
    job = store.get(job_id)
    if job is None:
        return _error(404, "unknown job id")
    if job.get("status") != "done":
        return 409, {"error": f"results are not ready — job status: {job['status']}",
                     "status": job["status"]}
    result = job.get("result") or {}
    return 200, {"html_path": result.get("html"), "json_path": result.get("json")}


def route_request(method: str, path: str, params: dict, *, store=None, worker=None,
                  transport=None, work_root=None, environ=None) -> tuple[int, dict]:
    """Method + path → handler, shared by the dev server and the tests so the routing
    itself is covered without a socket. ``/subject_map`` stays as an alias of
    ``/api/map`` so nothing already deployed breaks."""
    path = path.rstrip("/") or "/"
    if path in ("/api/map", "/subject_map") and method in ("GET", "POST"):
        return handle_subject_map(params, transport=transport, environ=environ)
    if path == "/api/expand" and method in ("GET", "POST"):
        return handle_expand(params, environ=environ, transport=transport)
    if path == "/api/clientlog" and method == "POST":
        return handle_client_log(params, environ=environ)
    if path == "/api/scan" or path.startswith("/api/scan/") \
            or path.startswith("/api/result/"):
        if store is None:
            return _error(503, "no job store is configured on this server")
        if path == "/api/scan" and method == "POST":
            return handle_scan_start(params, store=store, worker=worker,
                                     transport=transport, work_root=work_root,
                                     environ=environ)
        m = re.fullmatch(r"/api/scan/([A-Za-z0-9_-]+)(?:/(cancel|resume))?", path)
        if m:
            job_id, action = m.group(1), m.group(2)
            if action is None and method == "GET":
                return handle_scan_status(job_id, store=store)
            if action == "cancel" and method == "POST":
                return handle_scan_cancel(job_id, store=store)
            if action == "resume" and method == "POST":
                return handle_scan_resume(job_id, store=store, worker=worker,
                                          transport=transport, work_root=work_root,
                                          environ=environ)
        m = re.fullmatch(r"/api/result/([A-Za-z0-9_-]+)", path)
        if m and method == "GET":
            return handle_scan_result(m.group(1), store=store)
    return _error(404, "unknown path — try /api/map?field=... or POST /api/scan")


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

    def _route(self, method: str, params: dict) -> None:
        server = self.server
        status, body = route_request(
            method, urlparse(self.path).path, params,
            store=getattr(server, "job_store", None),
            worker=getattr(server, "worker", None),
            work_root=getattr(server, "work_root", None))
        self._send(status, body)

    def do_GET(self):
        qs = {k: v[0] for k, v in parse_qs(urlparse(self.path).query).items()}
        self._route("GET", qs)

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        try:
            params = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            params = {}
        self._route("POST", params)

    def log_message(self, *args):                        # keep the console quiet
        pass


def main(argv: list[str] | None = None) -> int:
    import argparse
    p = argparse.ArgumentParser(prog="python -m supervisorly.webapi",
                                description="local subject-map + scan-job dev server")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--work-root", default=str(DEFAULT_WORK_ROOT),
                   help="root for job working dirs + the JSON job store "
                        f"(default: {DEFAULT_WORK_ROOT})")
    args = p.parse_args(argv)
    work_root = Path(args.work_root)
    server = HTTPServer(("127.0.0.1", args.port), _Handler)
    server.job_store = jobs.JsonJobStore(work_root / "_store")
    server.worker = jobs.Worker()
    server.work_root = work_root
    print(f"server on http://127.0.0.1:{args.port} — /api/map?field=... | POST /api/scan")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
