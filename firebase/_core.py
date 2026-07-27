"""Firebase-side core for the web build (plan steps 6-7, docs/FIREBASE_WEB_PLAN.md):
the Firestore job store, the per-field expansion cache, the per-IP throttles, and the
Cloud Run Job bridge — everything ``main.py`` (the Functions wrappers) and
``worker.py`` (the Cloud Run Job entrypoint) share.

This module deliberately imports NO google packages at module level: every
``google.cloud.*`` import is lazy (inside the function that needs it) so the module
loads in ANY environment — the test suite stubs ``sys.modules`` instead of installing
the SDKs, and the Functions/Run images get the real ones from ``requirements.txt``.

Semantics mirror ``supervisorly.jobs`` / ``supervisorly.webapi`` one-for-one — same
lifecycle (``queued → running → done | failed | cancelled``), same idempotency key,
same stack-free errors; only the backing pieces change (Firestore instead of JSON
files, a Cloud Run Job instead of a thread, signed URLs instead of file paths).
"""

from __future__ import annotations

import hashlib
import importlib
import os
import re
from datetime import datetime, timedelta, timezone

from supervisorly import jobs, webapi

#: §5.2 fixed-window per-IP throttles (Firestore counters, one doc per ip+bucket+hour).
EXPAND_LIMIT_PER_HOUR = 10
MAP_LIMIT_PER_HOUR = 30
SCAN_LIMIT_PER_HOUR = 5

#: The per-job endpoints were unthrottled entirely (audit W8-F2), so a cancel→resume
#: loop re-invoked the Cloud Run Job without any limit — bypassing the 5/h scan cap
#: that exists to protect the shared source budget (§5.2). Sized by real cost:
#: a resume launches a worker execution, so it gets its own scan-sized bucket (its
#: own, not the scan one, so a resume is never blocked by unrelated scan starts);
#: cancel and result are cheap but not free; status is a single Firestore read that
#: the page polls every ``POLL_MS`` (4 s ≈ 900/h for ONE open tab), so its cap is only
#: a runaway-bill backstop and is deliberately far above normal use.
RESUME_LIMIT_PER_HOUR = 5
CANCEL_LIMIT_PER_HOUR = 60
RESULT_LIMIT_PER_HOUR = 120
STATUS_LIMIT_PER_HOUR = 3000

#: §5 — expansion results are cached per normalized field for 30 days.
CACHE_TTL_DAYS = 30

#: progress events are capped server-side so a long job doc stays small (§3.1).
MAX_PROGRESS_EVENTS = 200

#: collection names (see firestore.rules — clients can write NONE of these).
JOBS_COLLECTION = "scan_jobs"
CACHE_COLLECTION = "expand_cache"
THROTTLE_COLLECTION = "throttle"

#: environment variables (deploy config — see README.md).
SCAN_JOB_NAME_ENV = "SCAN_WORKER_JOB"
RESULTS_BUCKET_ENV = "RESULTS_BUCKET"
WEBAPP_API_BASE_ENV = "WEBAPP_API_BASE"
#: Which Firestore database to talk to. Unset = ``(default)``, the historical single
#: database. Newer Firebase projects can hand you a NAMED database instead, in which case
#: this must carry that name or every call 404s (see ``_firestore_client``).
FIRESTORE_DATABASE_ENV = "FIRESTORE_DATABASE"
#: Optional override for the account used to mint signed URLs. Normally resolved from the
#: runtime credentials; set it only when signing as a different service account.
SIGNING_SA_ENV = "SIGNING_SERVICE_ACCOUNT"

#: the Cloud Run Job that executes scans (§3.6).
WORKER_JOB_NAME = "supervisorly-scan-worker"

_SAFE_DOC_ID = re.compile(r"[A-Za-z0-9_.:+-]+")


def _error(status: int, message: str) -> tuple[int, dict]:
    return status, {"error": message}


# ── lazy google clients (the ONLY google imports in this module) ─────────────

def _firestore_module():
    """Lazy import — the module must load with NO google packages installed (the test
    suite stubs ``sys.modules['google.cloud.firestore']`` instead)."""
    return importlib.import_module("google.cloud.firestore")


_client_factory = None    # test hook; production builds a real Client


def set_client_factory(factory) -> None:
    """Test hook: install a callable returning a (fake) Firestore client, or None to
    restore the real ``firestore.Client()`` construction."""
    global _client_factory
    _client_factory = factory


def _firestore_client():
    """The Firestore client, honouring ``FIRESTORE_DATABASE`` when set.

    ``firestore.Client()`` with no argument targets the database literally named
    ``(default)``. That used to be the only possibility, but a Firebase project created
    today can get a NAMED database instead — this project's is called ``default``, with
    no parentheses — and against such a project every call fails with a NOT_FOUND that
    names a database you never asked for. Deploy-time config, not a code constant, is the
    right place to say which database to use, so the id comes from the environment and
    falls back to the historical default when unset.
    """
    if _client_factory is not None:
        return _client_factory()
    fs = _firestore_module()
    database = (os.environ.get(FIRESTORE_DATABASE_ENV) or "").strip()
    return fs.Client(database=database) if database else fs.Client()


def _storage_client():
    return importlib.import_module("google.cloud.storage").Client()


def _jobs_client():
    return importlib.import_module("google.cloud.run_v2").JobsClient()


# ── FirestoreJobStore: the Firestore twin of jobs.JsonJobStore ───────────────

def _touch(job: dict) -> None:
    """Every write refreshes ``updated_at`` (ISO string, local parity) and ``updatedAt``
    (a real timestamp — the Firestore TTL field for the 7-day auto-delete, D-069(c))."""
    job["updated_at"] = jobs._now_iso()
    job["updatedAt"] = datetime.now(timezone.utc)


class FirestoreJobStore:
    """Same interface + semantics as ``jobs.JsonJobStore``, backed by Firestore.

    One document per job in ``scan_jobs``; the document id IS the unguessable access
    token (D-069(b)). ``create`` runs the §3.3 idempotent-key check in a transaction;
    ``append_event`` updates the progress log (capped at the last
    ``MAX_PROGRESS_EVENTS`` events) and the §3.2 heartbeat atomically in a transaction.
    """

    def __init__(self, client=None) -> None:
        self._client = client if client is not None else _firestore_client()

    @property
    def _col(self):
        return self._client.collection(JOBS_COLLECTION)

    @staticmethod
    def _safe(job_id) -> bool:
        return bool(jobs._SAFE_ID.fullmatch(str(job_id)))

    def create(self, email: str, plan: dict, job_id: str, job_key: str) -> dict:
        """Insert a queued job; raise ``JobExists`` when a NON-TERMINAL job already holds
        this key (the idempotency backstop, §3.3) — checked inside a transaction so a
        create race yields exactly one winner."""
        if not self._safe(job_id):
            raise ValueError(f"unsafe job id: {job_id!r}")
        fs = _firestore_module()
        ref = self._col.document(str(job_id))
        query = self._col.where("job_key", "==", job_key)
        holder: dict = {}

        @fs.transactional
        def _attempt(tx):
            for snap in query.stream(transaction=tx):
                other = snap.to_dict()
                if other.get("status") not in jobs.TERMINAL_STATUSES:
                    raise jobs.JobExists(other["job_id"])
            now = jobs._now_iso()
            job = {"job_id": str(job_id), "job_key": job_key, "status": "queued",
                   "plan": plan, "email": email,
                   "email_ci": (email or "").strip().casefold(),
                   "progress": [], "heartbeat_at": None, "cancel_requested": False,
                   "error": None, "result": None,
                   "created_at": now, "updated_at": now,
                   "updatedAt": datetime.now(timezone.utc)}
            tx.set(ref, job)
            holder["job"] = job

        _attempt(self._client.transaction())
        return holder["job"]

    def get(self, job_id: str) -> dict | None:
        if not self._safe(job_id):
            return None   # a malformed id is simply unknown
        snap = self._col.document(str(job_id)).get()
        return snap.to_dict() if snap.exists else None

    def append_event(self, job_id: str, event: dict) -> None:
        """Append one progress event (capped at the last ``MAX_PROGRESS_EVENTS``); every
        event also stamps ``heartbeat_at`` (§3.2) — all atomically in a transaction."""
        if not self._safe(job_id):
            return
        fs = _firestore_module()
        ref = self._col.document(str(job_id))

        @fs.transactional
        def _attempt(tx):
            snap = ref.get(transaction=tx)
            if not snap.exists:
                return
            job = snap.to_dict()
            job["progress"] = (list(job.get("progress") or [])
                               + [event])[-MAX_PROGRESS_EVENTS:]
            job["heartbeat_at"] = event.get("ts") or jobs._now_iso()
            _touch(job)
            tx.set(ref, job)

        _attempt(self._client.transaction())

    def set_status(self, job_id: str, status: str, **fields) -> dict | None:
        """Apply a status (+ fields) to the job — inside a transaction (audit W8-F4).

        This used to read the document, mutate the copy, and write the WHOLE thing back
        outside any transaction. Every write that landed in between was silently lost,
        and two of them matter: ``request_cancel``'s ``cancel_requested``/``cancelling``
        (so the user's cancel was dropped and the worker ran on) and ``append_event``'s
        ``progress`` (so events vanished from the page mid-scan). Re-reading INSIDE the
        transaction means the concurrent writer's fields are carried forward and
        Firestore retries the loser on contention. ``jobs.JsonJobStore`` was always safe
        this way — it holds ``self._lock`` across its read/write — so this restores the
        one-for-one semantics the module docstring promises.
        """
        if not self._safe(job_id):
            return None
        fs = _firestore_module()
        ref = self._col.document(str(job_id))
        holder: dict = {}

        @fs.transactional
        def _attempt(tx):
            snap = ref.get(transaction=tx)
            if not snap.exists:
                holder["job"] = None
                return
            job = snap.to_dict()
            job["status"] = status
            job.update(fields)
            _touch(job)
            tx.set(ref, job)
            holder["job"] = job

        _attempt(self._client.transaction())
        return holder.get("job")

    def request_cancel(self, job_id: str) -> dict | None:
        """Set the cooperative-cancel flag + ``cancelling`` (§3.4); a no-op on terminal."""
        if not self._safe(job_id):
            return None
        fs = _firestore_module()
        ref = self._col.document(str(job_id))
        holder: dict = {}

        @fs.transactional
        def _attempt(tx):
            snap = ref.get(transaction=tx)
            if not snap.exists:
                holder["job"] = None
                return
            job = snap.to_dict()
            if job.get("status") not in jobs.TERMINAL_STATUSES:
                job["cancel_requested"] = True
                job["status"] = "cancelling"
                _touch(job)
                tx.set(ref, job)
            holder["job"] = job

        _attempt(self._client.transaction())
        return holder["job"]

    def is_stalled(self, job_id: str, max_age_s: float = jobs.DEFAULT_STALL_AGE_S) -> bool:
        """True when a non-terminal job's heartbeat is older than ``max_age_s`` (§3.2).
        A queued job that never got a first heartbeat is measured from ``updated_at``."""
        job = self.get(job_id)
        if job is None or job.get("status") in jobs.TERMINAL_STATUSES:
            return False
        ref = jobs._parse_iso(job.get("heartbeat_at") or job.get("updated_at"))
        if ref is None:
            return False
        return (datetime.now(timezone.utc) - ref).total_seconds() > max_age_s

    def active_job_for(self, email: str) -> dict | None:
        """The one non-terminal job owned by ``email`` (§3.5: one active job per email)."""
        wanted = (email or "").strip().casefold()
        for snap in self._col.where("email_ci", "==", wanted).stream():
            job = snap.to_dict()
            if job.get("status") not in jobs.TERMINAL_STATUSES:
                return job
        return None


# ── per-IP throttle (§5.2) ───────────────────────────────────────────────────

def _throttle_doc_id(name: str, ip: str, now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    safe_ip = re.sub(r"[^A-Za-z0-9_.:-]", "_", ip or "unknown")
    return f"{safe_ip}#{name}#{now.strftime('%Y%m%d%H')}"


def check_throttle(name: str, ip: str, limit_per_hour: int, *, client=None) -> bool:
    """Fixed-window per-IP counter (§5.2): one ``throttle`` doc per ``ip#bucket#yyyymmddhh``,
    incremented in a transaction; over the limit → False (the caller answers 429)."""
    fs = _firestore_module()
    client = client if client is not None else _firestore_client()
    ref = client.collection(THROTTLE_COLLECTION).document(_throttle_doc_id(name, ip))
    holder = {"ok": False}

    @fs.transactional
    def _attempt(tx):
        snap = ref.get(transaction=tx)
        count = (snap.to_dict() or {}).get("count", 0) if snap.exists else 0
        if count >= limit_per_hour:
            return                                    # over the limit — do not increment
        tx.set(ref, {"count": count + 1, "bucket": name,
                     "updatedAt": datetime.now(timezone.utc)})
        holder["ok"] = True

    _attempt(client.transaction())
    return holder["ok"]


def _throttled(limit: int) -> tuple[int, dict]:
    return _error(429, f"too many requests from this client — this endpoint allows "
                       f"{limit} per hour; try again later (the shared source budget "
                       "is protected, plan §5.2)")


# ── per-field expansion cache (§5: Firestore, 30-day TTL) ────────────────────

def normalize_field(field: str) -> str:
    """The cache key normalization: casefold + collapsed whitespace."""
    return " ".join(str(field or "").split()).casefold()


def _cache_doc_id(field: str) -> str | None:
    norm = normalize_field(field)
    if not norm:
        return None
    if len(norm) <= 400 and _SAFE_DOC_ID.fullmatch(norm) \
            and not (norm.startswith("__") and norm.endswith("__")):
        return norm
    return "h:" + hashlib.sha256(norm.encode("utf-8")).hexdigest()


def expansion_cache_get(field: str, *, client=None) -> dict | None:
    """The cached expansion payload for a field, or None on miss/expiry — the 30-day
    TTL is compared server-side (``expires_at``), so an expired doc is a clean miss."""
    doc_id = _cache_doc_id(field)
    if doc_id is None:
        return None
    client = client if client is not None else _firestore_client()
    snap = client.collection(CACHE_COLLECTION).document(doc_id).get()
    if not snap.exists:
        return None
    doc = snap.to_dict() or {}
    expires = doc.get("expires_at")
    if isinstance(expires, datetime):
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if expires > datetime.now(timezone.utc):
            return doc.get("payload")
    return None


def expansion_cache_put(field: str, payload: dict, *, client=None,
                        ttl_days: int = CACHE_TTL_DAYS) -> None:
    doc_id = _cache_doc_id(field)
    if doc_id is None:
        return
    client = client if client is not None else _firestore_client()
    now = datetime.now(timezone.utc)
    client.collection(CACHE_COLLECTION).document(doc_id).set({
        "field": normalize_field(field), "payload": payload,
        "created_at": jobs._now_iso(), "expires_at": now + timedelta(days=ttl_days),
        "updatedAt": now})


# ── the Cloud Run Job bridge (§3.3/§3.6) ─────────────────────────────────────

def worker_job_name(environ=None) -> str:
    """The Cloud Run Job resource name: the ``SCAN_WORKER_JOB`` env override wins, else
    it is built from the project/region envs (the ``<FIREBASE_PROJECT_ID>``/``<REGION>``
    placeholders until deploy config fills them — see README.md)."""
    environ = os.environ if environ is None else environ
    name = (environ.get(SCAN_JOB_NAME_ENV) or "").strip()
    if name:
        return name
    project = environ.get("FIREBASE_PROJECT_ID") or environ.get("GCP_PROJECT") \
        or environ.get("GOOGLE_CLOUD_PROJECT") or "<FIREBASE_PROJECT_ID>"
    region = environ.get("REGION") or environ.get("FUNCTION_REGION") or "<REGION>"
    return f"projects/{project}/locations/{region}/jobs/{WORKER_JOB_NAME}"


def invoke_worker(job_id: str, *, environ=None, client=None):
    """Run ONE execution of the scan-worker Cloud Run Job with ``JOB_ID`` injected as a
    container env override (§3.3: a retry or resume reuses the SAME job doc)."""
    environ = os.environ if environ is None else environ
    client = client if client is not None else _jobs_client()
    request = {"name": worker_job_name(environ),
               "overrides": {"container_overrides": [
                   {"env": [{"name": "JOB_ID", "value": str(job_id)}]}]}}
    return client.run_job(request=request)


class CloudRunWorker:
    """The Firebase twin of ``jobs.Worker``: ``submit`` records the attempt's run params
    on the job doc (the status stays ``queued`` — the worker itself flips ``running``)
    and invokes the Cloud Run Job with ``JOB_ID``. Secrets (contact email, OpenAlex key)
    and the results bucket live on the worker's own env, never in the job doc."""

    def __init__(self, *, environ=None, client=None) -> None:
        self._environ = environ
        self._client = client

    def submit(self, store, job_id: str, *, plan: dict, email: str, transport=None,
               openalex_key=None, shortlist: int = 40, max_institutions=None,
               resume: bool = False, db_path=None, snap_root=None,
               out_html=None, out_json=None):
        # the local-only path kwargs are accepted for interface parity and ignored —
        # the worker computes its own ephemeral paths from JOB_ID (§3.6)
        job = store.get(job_id)
        if job is None:
            raise KeyError(f"unknown job {job_id}")
        if job.get("cancel_requested"):
            store.set_status(job_id, "cancelled")   # cancelled while queued (§3.4)
            return None
        store.set_status(job_id, "queued",
                         run_params={"shortlist": shortlist,
                                     "max_institutions": max_institutions})
        invoke_worker(job_id, environ=self._environ, client=self._client)
        return None


# ── the endpoint handlers (thin; validation lives in webapi) ─────────────────

def handle_expand(params: dict, *, client=None, ip: str = "", environ=None,
                  transport=None) -> tuple[int, dict]:
    """GET/POST /api/expand: throttle (§5.2, 10/h) → per-field cache (30-day TTL, hit →
    ``cached: true``) → the engine (fail-closed, D-068); only real expansions cache."""
    environ = os.environ if environ is None else environ
    if not check_throttle("expand", ip, EXPAND_LIMIT_PER_HOUR, client=client):
        return _throttled(EXPAND_LIMIT_PER_HOUR)
    field = str(params.get("field") or "").strip()
    if field:
        cached = expansion_cache_get(field, client=client)
        if cached is not None:
            return 200, {**cached, "cached": True}
    status, body = webapi.handle_expand(params, environ=environ, transport=transport)
    if status == 200 and body.get("expanded"):
        expansion_cache_put(field, body, client=client)
    return status, body


def handle_map(params: dict, *, client=None, ip: str = "", environ=None,
               transport=None) -> tuple[int, dict]:
    """GET/POST /api/map: throttle (§5.2, 30/h) → the existing subject-map handler."""
    environ = os.environ if environ is None else environ
    if not check_throttle("map", ip, MAP_LIMIT_PER_HOUR, client=client):
        return _throttled(MAP_LIMIT_PER_HOUR)
    return webapi.handle_subject_map(params, transport=transport, environ=environ)


def handle_scan_start(params: dict, *, store=None, client=None, ip: str = "",
                      environ=None, transport=None, jobs_client=None) -> tuple[int, dict]:
    """POST /api/scan: throttle (§5.2, 5/h) → the local validation/idempotency logic,
    backed by Firestore and starting a Cloud Run Job execution instead of a thread."""
    environ = os.environ if environ is None else environ
    if not check_throttle("scan", ip, SCAN_LIMIT_PER_HOUR, client=client):
        return _throttled(SCAN_LIMIT_PER_HOUR)
    store = store if store is not None else FirestoreJobStore(client)
    worker = CloudRunWorker(environ=environ, client=jobs_client)
    return webapi.handle_scan_start(params, store=store, worker=worker,
                                    transport=transport, environ=environ)


def handle_scan_status(job_id: str, *, store=None, client=None,
                       ip: str = "") -> tuple[int, dict]:
    """GET /api/scan/<id>: throttle (§5.2, the runaway-bill backstop) → status."""
    if not check_throttle("status", ip, STATUS_LIMIT_PER_HOUR, client=client):
        return _throttled(STATUS_LIMIT_PER_HOUR)
    store = store if store is not None else FirestoreJobStore(client)
    return webapi.handle_scan_status(job_id, store=store)


def handle_scan_cancel(job_id: str, *, store=None, client=None,
                       ip: str = "") -> tuple[int, dict]:
    """POST /api/scan/<id>/cancel: throttle (§5.2, 60/h) → cooperative cancel."""
    if not check_throttle("cancel", ip, CANCEL_LIMIT_PER_HOUR, client=client):
        return _throttled(CANCEL_LIMIT_PER_HOUR)
    store = store if store is not None else FirestoreJobStore(client)
    return webapi.handle_scan_cancel(job_id, store=store)


def handle_scan_resume(job_id: str, *, store=None, client=None, environ=None,
                       transport=None, jobs_client=None,
                       ip: str = "") -> tuple[int, dict]:
    """POST /api/scan/<id>/resume: throttle (§5.2, 5/h — a resume launches a worker
    execution exactly like a scan start, and this endpoint was the unthrottled half of
    the cancel→resume loop, audit W8-F2) → re-invoke the Cloud Run Job with the SAME
    ``JOB_ID`` (§3.4)."""
    environ = os.environ if environ is None else environ
    if not check_throttle("resume", ip, RESUME_LIMIT_PER_HOUR, client=client):
        return _throttled(RESUME_LIMIT_PER_HOUR)
    store = store if store is not None else FirestoreJobStore(client)
    worker = CloudRunWorker(environ=environ, client=jobs_client)
    return webapi.handle_scan_resume(job_id, store=store, worker=worker,
                                     transport=transport, environ=environ)


# ── the result redirect (D-069(c): private bucket + 15-min signed URLs) ──────

def _signing_kwargs(environ=None) -> dict:
    """Extra ``generate_signed_url`` arguments so v4 signing works on Cloud Run/Functions.

    There is no key file in a serverless runtime: the ambient credentials are
    ``compute_engine.Credentials``, a bearer token with no private key, and asking the
    storage library to sign with them raises

        AttributeError: you need a private key to sign credentials.

    Handing it the service-account email plus a live access token makes it sign through
    the IAM ``signBlob`` API instead — which is what the
    ``roles/iam.serviceAccountTokenCreator`` self-binding exists to permit. Note that the
    IAM binding alone is NOT enough; the library only takes that path when given these
    arguments.

    Returns ``{}`` whenever the credentials can already sign unaided (a real key file) or
    cannot be resolved at all (tests, local dev) — so nothing outside the cloud changes.
    """
    environ = os.environ if environ is None else environ
    try:
        import google.auth
        from google.auth.transport import requests as _grequests

        creds, _ = google.auth.default()
        if getattr(creds, "signer", None) is not None:
            return {}                       # has a private key — sign directly
        creds.refresh(_grequests.Request())  # populates token + the real SA email
        email = ((environ.get(SIGNING_SA_ENV) or "").strip()
                 or getattr(creds, "service_account_email", "") or "")
        token = getattr(creds, "token", None)
        if email and email != "default" and token:
            return {"service_account_email": email, "access_token": token}
    except Exception:
        pass                                 # fall through: let the library try unaided
    return {}


def signed_result_url(bucket_name: str, job_id: str, *, storage_client=None,
                      expiration_s: int = 900, environ=None) -> str:
    """A fresh 15-min v4 signed URL for the job's dashboard — re-issued on every
    request, so an expired URL is never a dead end."""
    client = storage_client if storage_client is not None else _storage_client()
    blob = client.bucket(bucket_name).blob(f"{job_id}/dashboard.html")
    return blob.generate_signed_url(version="v4", expiration=expiration_s, method="GET",
                                    **_signing_kwargs(environ))


def handle_scan_result(job_id: str, *, store=None, client=None, environ=None,
                       storage_client=None, ip: str = "") -> tuple[int, dict]:
    """GET /api/result/<id>: throttle (§5.2, 120/h — each call mints a signed URL) →
    302 with a fresh signed URL when done (the body carries the URL so ``main.py`` can
    set the Location header); 409 until then."""
    environ = os.environ if environ is None else environ
    if not check_throttle("result", ip, RESULT_LIMIT_PER_HOUR, client=client):
        return _throttled(RESULT_LIMIT_PER_HOUR)
    store = store if store is not None else FirestoreJobStore(client)
    job = store.get(job_id)
    if job is None:
        return _error(404, "unknown job id — a job id is its access token and jobs are "
                           "never listable (D-069)")
    if job.get("status") != "done":
        return 409, {"error": f"results are not ready — job status: {job['status']}",
                     "status": job["status"]}
    bucket = environ.get(RESULTS_BUCKET_ENV) or "<RESULTS_BUCKET>"
    return 302, {"status": "done",
                 "url": signed_result_url(bucket, job_id, storage_client=storage_client)}


# ── the one-page app ─────────────────────────────────────────────────────────

_WEBAPP_CACHE: dict[str, str] = {}


def webapp_html(environ=None) -> str:
    """The built web app, cached per process (Functions instances are reused);
    ``WEBAPP_API_BASE`` empty = same-origin — the Hosting rewrites route /api/**."""
    environ = os.environ if environ is None else environ
    api_base = environ.get(WEBAPP_API_BASE_ENV, "")
    if api_base not in _WEBAPP_CACHE:
        from supervisorly.export.webapp import build_webapp
        _WEBAPP_CACHE[api_base] = build_webapp(api_base=api_base)
    return _WEBAPP_CACHE[api_base]


# ── the single router behind the Hosting /api/** rewrite ─────────────────────

def route_api(method: str, path: str, params: dict, *, ip: str = "", environ=None,
              client=None, transport=None, jobs_client=None,
              storage_client=None) -> tuple[int, dict]:
    """Method + path → handler for the single ``api`` function — the same routes as
    ``webapi.route_request``, backed by Firestore + the Cloud Run Job."""
    path = path.rstrip("/") or "/"
    if path in ("/api/map", "/subject_map") and method in ("GET", "POST"):
        return handle_map(params, client=client, ip=ip, environ=environ,
                          transport=transport)
    if path == "/api/expand" and method in ("GET", "POST"):
        return handle_expand(params, client=client, ip=ip, environ=environ,
                             transport=transport)
    if path == "/api/scan" and method == "POST":
        return handle_scan_start(params, client=client, ip=ip, environ=environ,
                                 transport=transport, jobs_client=jobs_client)
    m = re.fullmatch(r"/api/scan/([A-Za-z0-9_-]+)(?:/(cancel|resume))?", path)
    if m:
        job_id, action = m.group(1), m.group(2)
        if action is None and method == "GET":
            return handle_scan_status(job_id, client=client, ip=ip)
        if action == "cancel" and method == "POST":
            return handle_scan_cancel(job_id, client=client, ip=ip)
        if action == "resume" and method == "POST":
            return handle_scan_resume(job_id, client=client, environ=environ,
                                      transport=transport, jobs_client=jobs_client,
                                      ip=ip)
    m = re.fullmatch(r"/api/result/([A-Za-z0-9_-]+)", path)
    if m and method == "GET":
        return handle_scan_result(m.group(1), client=client, environ=environ,
                                  storage_client=storage_client, ip=ip)
    return _error(404, "unknown path — try /api/map?field=... or POST /api/scan")
