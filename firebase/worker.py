"""Cloud Run Job entrypoint — the long-running scan worker (plan §3.6).

Runs ONE scan job end to end: reads ``JOB_ID`` from the environment (injected by the
Functions wrapper via a ``run_job`` override), loads the job doc from Firestore, runs
``jobs.run_scan_job`` against the ephemeral disk, uploads the results to the private
results bucket BEFORE flipping the status (§3.1 result-before-status), and honors
``cancel_requested`` between targets (§3.4). Every progress event is appended to the
job doc (which stamps the §3.2 heartbeat) and echoed as ONE ASCII status line to
stdout for Cloud Logging.

The worker's own env carries the secrets/config: ``SUPERVISORLY_CONTACT_EMAIL``,
``SUPERVISORLY_OPENALEX_KEY`` (optional), ``RESULTS_BUCKET``, and optionally
``SUPERVISORLY_WORK_ROOT`` (defaults to /tmp). A mid-run crash costs time, never
correctness: a retry re-invokes with the same ``JOB_ID`` and the engine's checkpoint
state skips completed work.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from supervisorly import jobs, phases, preflight
from supervisorly.fetch.transport import httpx_transport

import _core

#: where the SQLite DB + snapshots live during the run (the worker's ephemeral disk).
DEFAULT_WORK_ROOT = "/tmp/supervisorly-jobs"


def upload_results(bucket_name: str, job_id: str, paths: dict, *,
                   storage_client=None) -> dict:
    """Upload whatever result artifacts exist — called BEFORE the status flips (§3.1),
    so a done/cancelled job can never lack its files. On failure only the partial DB
    may exist; it is still uploaded so a resume continues instead of starting over."""
    client = storage_client if storage_client is not None else _core._storage_client()
    bucket = client.bucket(bucket_name)
    uploaded: dict = {}
    for key, path in (("html", paths.get("out_html")),
                      ("json", paths.get("out_json")),
                      ("db", paths.get("db_path"))):
        p = Path(path) if path else None
        if p is not None and p.is_file():
            name = f"{job_id}/{p.name}"
            bucket.blob(name).upload_from_filename(str(p))
            uploaded[key] = f"gs://{bucket_name}/{name}"
    return uploaded


class _FirestoreHooks:
    """The run_scan_job ↔ FirestoreJobStore adapter (twin of jobs._StoreHooks):
    events append + heartbeat, ``should_stop`` polls the cancel flag, and done/failed
    upload results FIRST and flip the status SECOND (§3.1)."""

    def __init__(self, store: _core.FirestoreJobStore, job_id: str, *, bucket: str,
                 paths: dict, storage_client=None) -> None:
        self._store = store
        self._job_id = job_id
        self._bucket = bucket
        self._paths = paths
        self._storage_client = storage_client

    def on_event(self, event: dict) -> None:
        self._store.append_event(self._job_id, event)
        # one ASCII status line per event → Cloud Logging
        print(json.dumps({"job": self._job_id, "ts": event.get("ts"),
                          "phase": event.get("phase"), "data": event.get("data")},
                         ensure_ascii=True), flush=True)

    def should_stop(self) -> bool:
        job = self._store.get(self._job_id)
        return bool(job and job.get("cancel_requested"))

    def on_done(self, result: dict) -> None:
        # results to the bucket FIRST (§3.1) — then the status flips
        uploaded = upload_results(self._bucket, self._job_id, self._paths,
                                  storage_client=self._storage_client)
        cancelled = bool((result.get("stats") or {}).get("cancelled"))
        self._store.set_status(self._job_id, "cancelled" if cancelled else "done",
                               result=uploaded)

    def on_failed(self, message: str) -> None:
        # Log the reason at ERROR before touching anything else: an upload that also fails
        # must not be what swallows the explanation. `severity` is the field Cloud Logging
        # reads, so this surfaces in `logs.py errors` rather than hiding at INFO.
        print(json.dumps({"severity": "ERROR", "job": self._job_id, "phase": "failed",
                          "error": str(message)[:800]}, ensure_ascii=True), flush=True)
        try:                                  # keep the partial DB for resume (§3.1)
            upload_results(self._bucket, self._job_id, self._paths,
                           storage_client=self._storage_client)
        except Exception as exc:
            print(json.dumps({"severity": "WARNING", "job": self._job_id,
                              "phase": "upload_failed_after_failure",
                              "error": f"{type(exc).__name__}: {exc}"[:400]},
                             ensure_ascii=True), flush=True)
        self._store.set_status(self._job_id, "failed", error=message)


def main(environ=None, *, store=None, transport=None, storage_client=None,
         work_root=None) -> int:
    """Run the job named by ``JOB_ID``; returns a process exit code (0 = the job ran,
    1 = nothing/broken — the job doc already carries the honest status)."""
    environ = os.environ if environ is None else environ
    job_id = str(environ.get("JOB_ID") or "").strip()
    if not job_id:
        print("JOB_ID is not set — nothing to do", flush=True)
        return 1
    store = store if store is not None else _core.FirestoreJobStore()
    job = store.get(job_id)
    if job is None:
        print(f"unknown job {job_id} — nothing to do", flush=True)
        return 1
    if job.get("cancel_requested"):
        # cancelled while queued (§3.4): just flip, nothing to export
        store.set_status(job_id, "cancelled")
        print(f"job {job_id} cancelled before start", flush=True)
        return 0
    run_params = job.get("run_params") or {}
    # FLAG-1/FLAG-3: the phase flags come from the WORKER'S environment and are read once,
    # before any work starts. `run_params` and `plan` are request-derived and deliberately
    # not consulted — a phase that is off because it is not ready must not be switchable
    # from a browser (D-068).
    _phase_flags = phases.PhaseFlags.from_env(environ)
    store.set_status(job_id, "running")
    # What this scan was actually asked to do. Without it the event stream starts at
    # "enumerated" and a zero-result run gives no way to tell a thin country from a wrong
    # one — which is exactly how the country-code bug stayed invisible.
    # D-005: the plan carries the student's email; it is NEVER logged. Country, field,
    # counts and scope are not personal data. Professor names never appear here either.
    _plan = job.get("plan") or {}
    print(json.dumps({"job": job_id, "phase": "start",
                      "country": _plan.get("country"),
                      "field": str(_plan.get("field") or "")[:120],
                      "topics": len(_plan.get("resolved_topic_ids") or []),
                      "named_targets": len(_plan.get("targets") or []),
                      "university_mode": _plan.get("university_mode"),
                      "universities": len(_plan.get("universities") or []),
                      "shortlist": run_params.get("shortlist", 40),
                      "max_institutions": run_params.get("max_institutions"),
                      # FLAG-1: read ONCE, here, from the worker's own environment — never
                      # from the job doc, so a request can neither enable a phase nor read
                      # which are on. Logged because a deploy whose PHASES did not take
                      # effect is otherwise indistinguishable from a phase that did nothing.
                      "phases": _phase_flags.summary(),
                      "resuming": bool(job.get("progress"))},
                     ensure_ascii=True), flush=True)
    root = Path(work_root or environ.get("SUPERVISORLY_WORK_ROOT")
                or DEFAULT_WORK_ROOT) / job_id
    paths = {"db_path": root / "supervisorly.sqlite",
             "snap_root": root / ".cache" / "snaps",
             "out_html": root / "dashboard.html",
             "out_json": root / "dashboard.json"}
    bucket = environ.get(_core.RESULTS_BUCKET_ENV) or "<RESULTS_BUCKET>"
    hooks = _FirestoreHooks(store, job_id, bucket=bucket, paths=paths,
                            storage_client=storage_client)
    tp = transport or httpx_transport(
        user_agent=f"SupervisorlyBot/0.1 (mailto:{job['email']})")
    result = jobs.run_scan_job(
        job["plan"], hooks, transport=tp, email=job["email"],
        openalex_key=preflight.openalex_key(environ),
        shortlist=run_params.get("shortlist", 40),
        max_institutions=run_params.get("max_institutions"),
        resume=bool(job.get("progress")),   # a re-invoked job resumes its checkpoints
        phase_flags=_phase_flags,           # the same object the start line logged
        **paths)
    final = store.get(job_id) or {}
    status = final.get("status")
    # Fold the event stream into the numbers that answer "did this scan find anything?" —
    # the question a container log could not previously answer without replaying Firestore.
    counts: dict = {}
    for e in final.get("progress") or []:
        d = e.get("data") or []
        if e.get("phase") == "enumerated" and len(d) >= 2:
            counts["targets"], counts["institutions"] = d[0], d[1]
        elif e.get("phase") == "deep_dive_progress" and len(d) >= 2:
            counts["deep_dive_done"], counts["deep_dive_total"] = d[0], d[1]
    warnings = [e["data"][0] for e in (final.get("progress") or [])
                if e.get("phase") == "partial_warning" and e.get("data")]
    print(json.dumps({"job": job_id, "phase": "finished", "status": status,
                      "counts": counts, "warnings": warnings[:5],
                      "error": final.get("error"),
                      "severity": "ERROR" if status == "failed" else "INFO"},
                     ensure_ascii=True), flush=True)
    print(f"job {job_id} finished with status {status}", flush=True)
    return 0 if result is not None else 1


if __name__ == "__main__":
    raise SystemExit(main())
