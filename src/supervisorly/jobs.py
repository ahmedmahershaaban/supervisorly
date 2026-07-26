"""The async scan job: storage-agnostic runner + local JSON job store + threaded worker.

Web build, plan step 4 (docs/FIREBASE_WEB_PLAN.md §3): the Firebase deployment swaps
``JsonJobStore`` for Firestore and ``Worker`` for a Cloud Run Job, but the lifecycle is
identical — ``queued → running → done | failed | cancelled`` (plus ``cancelling`` while
the worker drains) — so the local dev server is a faithful parity environment:

- **Result before status** (§3.1): ``run_scan_job`` writes the dashboard + JSON export
  files FIRST and only then calls ``hooks.on_done`` — a done job can never lack its
  result. On exception the partial SQLite DB stays on disk so a resume continues instead
  of starting over, and the failure surfaces as an honest, stack-free message.
- **Heartbeat watchdog** (§3.2): every progress event stamps ``heartbeat_at``; the status
  endpoint (never the worker) flips a stale job to ``failed`` — no job sits at ``running``
  forever.
- **Idempotent start** (§3.3): the job key is ``sha256(email + canonical plan JSON)``;
  creating a second non-terminal job with the same key raises ``JobExists`` and the
  endpoint answers with the EXISTING job id.
- **Cooperative cancel** (§3.4): ``request_cancel`` sets a flag the worker polls between
  targets through the engine's ``should_stop``; a stopped run exports its partials
  honestly and lands in ``cancelled`` — every terminal state is resumable from the kept
  DB.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
from datetime import datetime, timezone
from pathlib import Path

from .fetch.transport import httpx_transport

#: Non-terminal statuses are the ones that still occupy a job key / an email slot.
TERMINAL_STATUSES = ("done", "failed", "cancelled")

#: §3.2 — a heartbeat older than this reads as a dead worker (the status endpoint flips).
DEFAULT_STALL_AGE_S = 600

#: The honest, stack-free message a watchdog-flipped job carries (§3.2).
STALL_MESSAGE = "worker stalled; safe to resume"

_SAFE_ID = re.compile(r"[A-Za-z0-9_-]+")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _parse_iso(s) -> datetime | None:
    try:
        return datetime.fromisoformat(s)
    except (TypeError, ValueError):
        return None


def new_job_key(email: str, plan: dict) -> str:
    """The idempotency key (§3.3): sha256 over the email + canonical plan JSON."""
    canonical = json.dumps(plan, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(
        (email.strip().casefold() + "\n" + canonical).encode("utf-8")).hexdigest()


class JobExists(Exception):
    """A non-terminal job with the same idempotency key already exists (§3.3)."""

    def __init__(self, job_id: str):
        super().__init__(f"an active job with this plan already exists: {job_id}")
        self.job_id = job_id


def run_scan_job(plan: dict, hooks, *, transport, db_path, snap_root, out_html, out_json,
                 email: str, openalex_key=None, shortlist: int = 40,
                 max_institutions=None, resume: bool = False,
                 rate_limit: float = 1.0, backoff_sleep=None) -> dict | None:
    """Run one scan job against any storage backend (§3.1, §6 item 5).

    ``hooks`` is the storage seam — an object with ``on_event(dict)``,
    ``on_done(result)``, ``on_failed(message)`` and ``should_stop() -> bool``. Every
    engine event tuple is stamped with ``ts`` (§4.1) and forwarded as
    ``{"ts", "phase", "data"}``; ``should_stop`` delegates to ``hooks.should_stop()`` so
    the backend's cancel flag drives the engine's cooperative stop.

    Result-before-status: the dashboard + JSON export files are written BEFORE
    ``hooks.on_done(result)`` is called, so a done job can never lack its result. Any
    exception becomes a stack-free ``hooks.on_failed("Type: message")`` (never a stack
    trace) and ``None`` is returned; the partial DB stays at ``db_path`` for resume.

    ``resume`` forwards to the engine's checkpoint skip (a fresh DB makes it a no-op);
    ``rate_limit``/``backoff_sleep`` mirror ``run_live``'s own politeness knobs so
    cassette runs stay fast.
    """
    from . import pipeline

    def _progress(event: tuple) -> None:
        hooks.on_event({"ts": _now_iso(), "phase": event[0], "data": list(event[1:])})

    try:
        db_parent = Path(db_path).parent
        if db_parent != Path("") and not db_parent.exists():
            db_parent.mkdir(parents=True, exist_ok=True)   # sqlite can't create parents
        result = pipeline.run_live(
            plan, transport, snap_root, email=email, openalex_key=openalex_key,
            db_path=db_path, shortlist_size=shortlist, max_institutions=max_institutions,
            resume=resume, rate_limit=rate_limit, backoff_sleep=backoff_sleep,
            progress=_progress, should_stop=hooks.should_stop)
        out_html, out_json = Path(out_html), Path(out_json)
        out_html.parent.mkdir(parents=True, exist_ok=True)
        out_html.write_text(result["html"], encoding="utf-8")
        out_json.write_text(json.dumps(result["export"], ensure_ascii=False, indent=2),
                            encoding="utf-8")
    except Exception as exc:  # honest + stack-free (§3.1); the DB stays for resume
        hooks.on_failed(f"{type(exc).__name__}: {str(exc)[:200]}")
        return None
    hooks.on_done(result)
    return result


class JsonJobStore:
    """The LOCAL job store — one JSON file per job, local parity for Firestore (§6.6).

    Every write is atomic (temp file + ``os.replace``, no litter on failure) and a lock
    serializes read-modify-write, so the threaded worker and the HTTP handlers can share
    one store safely. Job documents carry: ``job_id``, ``job_key``, ``status``, ``plan``,
    ``email``, ``progress`` (events with ``ts``), ``heartbeat_at``, ``cancel_requested``,
    ``error``, ``result`` (``{"html", "json"}`` paths), ``created_at``, ``updated_at``.
    """

    def __init__(self, dir) -> None:
        self._dir = Path(dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def _path(self, job_id: str) -> Path:
        return self._dir / f"{job_id}.json"

    def _read(self, job_id: str) -> dict | None:
        if not _SAFE_ID.fullmatch(str(job_id)):
            return None  # a malformed id is simply unknown (never a path traversal)
        try:
            return json.loads(self._path(str(job_id)).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def _write(self, job: dict) -> None:
        tmp = self._dir / f".{job['job_id']}.json.tmp"
        try:
            tmp.write_text(json.dumps(job, ensure_ascii=False, indent=2),
                           encoding="utf-8")
            os.replace(tmp, self._path(job["job_id"]))
        finally:
            try:
                tmp.unlink(missing_ok=True)   # a failed write leaves no temp litter
            except OSError:
                pass

    def _all(self) -> list[dict]:
        out = []
        for p in sorted(self._dir.glob("*.json")):
            try:
                out.append(json.loads(p.read_text(encoding="utf-8")))
            except (OSError, ValueError):
                continue   # a half-written/corrupt file is skipped, never fatal
        return out

    def create(self, email: str, plan: dict, job_id: str, job_key: str) -> dict:
        """Insert a queued job; raise ``JobExists`` when a NON-TERMINAL job already holds
        this key (the idempotency backstop, §3.3) — a terminal key starts fresh."""
        if not _SAFE_ID.fullmatch(str(job_id)):
            raise ValueError(f"unsafe job id: {job_id!r}")
        with self._lock:
            for j in self._all():
                if j.get("job_key") == job_key and j.get("status") not in TERMINAL_STATUSES:
                    raise JobExists(j["job_id"])
            now = _now_iso()
            job = {"job_id": job_id, "job_key": job_key, "status": "queued",
                   "plan": plan, "email": email, "progress": [], "heartbeat_at": None,
                   "cancel_requested": False, "error": None, "result": None,
                   "created_at": now, "updated_at": now}
            self._write(job)
            return job

    def get(self, job_id: str) -> dict | None:
        return self._read(job_id)

    def append_event(self, job_id: str, event: dict) -> None:
        """Append one progress event; every event also stamps ``heartbeat_at`` (§3.2)."""
        with self._lock:
            job = self._read(job_id)
            if job is None:
                return
            job["progress"].append(event)
            job["heartbeat_at"] = event.get("ts") or _now_iso()
            job["updated_at"] = _now_iso()
            self._write(job)

    def set_status(self, job_id: str, status: str, **fields) -> dict | None:
        with self._lock:
            job = self._read(job_id)
            if job is None:
                return None
            job["status"] = status
            job.update(fields)
            job["updated_at"] = _now_iso()
            self._write(job)
            return job

    def request_cancel(self, job_id: str) -> dict | None:
        """Set the cooperative-cancel flag + ``cancelling`` (§3.4); a no-op on terminal."""
        with self._lock:
            job = self._read(job_id)
            if job is None or job.get("status") in TERMINAL_STATUSES:
                return job
            job["cancel_requested"] = True
            job["status"] = "cancelling"
            job["updated_at"] = _now_iso()
            self._write(job)
            return job

    def is_stalled(self, job_id: str, max_age_s: float = DEFAULT_STALL_AGE_S) -> bool:
        """True when a non-terminal job's heartbeat is older than ``max_age_s`` (§3.2).
        A queued job that never got a first heartbeat is measured from ``updated_at``."""
        job = self._read(job_id)
        if job is None or job.get("status") in TERMINAL_STATUSES:
            return False
        ref = _parse_iso(job.get("heartbeat_at") or job.get("updated_at"))
        if ref is None:
            return False
        return (datetime.now(timezone.utc) - ref).total_seconds() > max_age_s

    def active_job_for(self, email: str) -> dict | None:
        """The one non-terminal job owned by ``email`` (§3.5: one active job per email)."""
        wanted = (email or "").strip().casefold()
        with self._lock:
            for j in self._all():
                if (j.get("status") not in TERMINAL_STATUSES
                        and str(j.get("email") or "").strip().casefold() == wanted):
                    return j
        return None


class _StoreHooks:
    """The run_scan_job ↔ JsonJobStore adapter: events append + heartbeat, the engine's
    ``should_stop`` polls the store's cancel flag, and done/failed flip the status — an
    engine-cancelled run lands in ``cancelled`` (partials exported), never ``done``."""

    def __init__(self, store: JsonJobStore, job_id: str, *, out_html, out_json) -> None:
        self._store = store
        self._job_id = job_id
        self._out_html = out_html
        self._out_json = out_json

    def on_event(self, event: dict) -> None:
        self._store.append_event(self._job_id, event)

    def should_stop(self) -> bool:
        job = self._store.get(self._job_id)
        return bool(job and job.get("cancel_requested"))

    def on_done(self, result: dict) -> None:
        cancelled = bool((result.get("stats") or {}).get("cancelled"))
        self._store.set_status(
            self._job_id, "cancelled" if cancelled else "done",
            result={"html": str(self._out_html), "json": str(self._out_json)})

    def on_failed(self, message: str) -> None:
        self._store.set_status(self._job_id, "failed", error=message)


class Worker:
    """Threaded local worker — local parity for the Cloud Run Job (§3.6).

    ``submit`` runs ``run_scan_job`` in a daemon thread; the engine's ``should_stop``
    polls the store's cancel flag between targets. Stall detection is NOT the worker's
    job — the status endpoint owns the watchdog flip (§3.2).
    """

    def __init__(self, *, rate_limit: float = 1.0, backoff_sleep=None) -> None:
        self._rate_limit = rate_limit
        self._backoff_sleep = backoff_sleep

    def submit(self, store: JsonJobStore, job_id: str, *, plan: dict, email: str,
               transport=None, db_path, snap_root, out_html, out_json,
               openalex_key=None, shortlist: int = 40, max_institutions=None,
               resume: bool = False):
        """Start the job in a daemon thread; returns the thread (None when the job was
        cancelled while still queued — §3.4: a queued-not-started job just flips to
        ``cancelled`` with nothing to export)."""
        job = store.get(job_id)
        if job is None:
            raise KeyError(f"unknown job {job_id}")
        if job.get("cancel_requested"):
            store.set_status(job_id, "cancelled")
            return None
        # record the attempt's run params so a later resume reuses the SAME scope
        store.set_status(job_id, "running",
                         run_params={"shortlist": shortlist,
                                     "max_institutions": max_institutions})
        hooks = _StoreHooks(store, job_id, out_html=out_html, out_json=out_json)

        def _run() -> None:
            tp = transport or httpx_transport(
                user_agent=f"SupervisorlyBot/0.1 (mailto:{email})")
            run_scan_job(plan, hooks, transport=tp, db_path=db_path, snap_root=snap_root,
                         out_html=out_html, out_json=out_json, email=email,
                         openalex_key=openalex_key, shortlist=shortlist,
                         max_institutions=max_institutions, resume=resume,
                         rate_limit=self._rate_limit, backoff_sleep=self._backoff_sleep)

        t = threading.Thread(target=_run, name=f"scan-job-{job_id}", daemon=True)
        t.start()
        return t
