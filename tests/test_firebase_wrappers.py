"""tests for the Firebase wrappers (web build plan steps 6-7): the FirestoreJobStore
(full interface incl. the idempotent create race), the §5.2 throttles, the per-field
expansion cache, the Cloud Run Job bridge, the signed-URL result redirect, and the
worker entrypoint end-to-end on cassettes.

All google clients are FAKES: an in-memory dict-backed Firestore with transaction
support (MVCC-lite: a conflicting commit forces a retry, like the real thing), a fake
Storage client recording uploads + signed-url calls, and a fake run_v2 JobsClient.
The google packages are NOT installed here — the tests stub ``sys.modules`` leaves,
which is exactly what _core's lazy imports are designed for. No network (D-035).
"""

from __future__ import annotations

import copy
import importlib.util
import json
import re
import subprocess
import sys
import threading
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIREBASE_DIR = ROOT / "firebase"
sys.path.insert(0, str(FIREBASE_DIR))          # main.py/_core.py/worker.py live flat

import _core                                   # noqa: E402
import worker as fb_worker                     # noqa: E402
from supervisorly import jobs, webapi          # noqa: E402
from supervisorly.discover import openalex, ror  # noqa: E402
from supervisorly.export.webapp import build_webapp  # noqa: E402
from supervisorly.fetch.transport import CassetteTransport  # noqa: E402

EMAIL = "me@uni.edu"
PLAN = {"intent_kind": "pre_phd", "country": "CA", "field": "causal ml",
        "resolved_topic_ids": ["T10001"], "university_mode": "all", "universities": []}


# ══ fakes: Firestore (dict-backed, transactions with contention retry) ═══════

class _Contention(Exception):
    """A transaction's reads were invalidated by a concurrent commit → retry."""


class _FakeSnapshot:
    def __init__(self, doc_id, data):
        self.id = doc_id
        self._data = data

    @property
    def exists(self):
        return self._data is not None

    def to_dict(self):
        return copy.deepcopy(self._data) if self._data is not None else None


class _FakeDocRef:
    def __init__(self, client, col, doc_id):
        self._client, self._col, self.id = client, col, doc_id

    def get(self, transaction=None):
        if transaction is not None:
            transaction._mark_read()
        data = self._client._data.get(self._col, {}).get(self.id)
        return _FakeSnapshot(self.id, data)

    def set(self, data, merge=False):
        if merge:
            cur = self._client._data.get(self._col, {}).get(self.id, {})
            data = {**cur, **copy.deepcopy(data)}
        self._client._apply(self._col, self.id, data)


class _FakeQuery:
    def __init__(self, client, col, filters):
        self._client, self._col, self._filters = client, col, filters

    def stream(self, transaction=None):
        if transaction is not None:
            transaction._mark_read()
        if self._client.on_stream is not None:
            self._client.on_stream()
        out = []
        for doc_id, data in list(self._client._data.get(self._col, {}).items()):
            if all(data.get(f) == v for f, _op, v in self._filters):
                out.append(_FakeSnapshot(doc_id, data))
        return out


class _FakeCollection:
    def __init__(self, client, name):
        self._client, self._name = client, name

    def document(self, doc_id):
        return _FakeDocRef(self._client, self._name, str(doc_id))

    def where(self, field, op, value):
        assert op == "==", f"the fake only supports == (got {op!r})"
        return _FakeQuery(self._client, self._name, [(field, op, value)])


class _FakeTransaction:
    def __init__(self, client):
        self._client = client
        self._reset()

    def _reset(self):
        self._base = self._client._version
        self._read = False
        self._ops = []

    def _mark_read(self):
        self._read = True

    def set(self, ref, data):
        self._ops.append(("set", ref, data))

    def update(self, ref, data):
        self._ops.append(("update", ref, data))

    def _commit(self):
        with self._client._lock:
            if self._read and self._client._version != self._base:
                raise _Contention
            for op, ref, data in self._ops:
                docs = self._client._data.setdefault(ref._col, {})
                if op == "set":
                    docs[ref.id] = copy.deepcopy(data)
                else:
                    docs[ref.id] = {**docs.get(ref.id, {}), **copy.deepcopy(data)}
                self._client._version += 1


def _transactional(fn):
    """The fake twin of firestore.transactional: run fn(tx), commit, retry on
    contention (real Firestore retries conflicting transactions the same way)."""
    def wrapper(tx, *args, **kwargs):
        for _ in range(10):
            tx._reset()
            try:
                result = fn(tx, *args, **kwargs)
                tx._commit()
                return result
            except _Contention:
                continue
        raise RuntimeError("fake transaction could not commit")
    return wrapper


class _FakeFirestoreClient:
    def __init__(self):
        self._data = {}                       # collection -> {doc_id: dict}
        self._lock = threading.Lock()
        self._version = 0
        self.on_stream = None                 # test hook, called inside query.stream

    def collection(self, name):
        return _FakeCollection(self, name)

    def transaction(self):
        return _FakeTransaction(self)

    def _apply(self, col, doc_id, value):
        with self._lock:
            self._data.setdefault(col, {})[doc_id] = copy.deepcopy(value)
            self._version += 1


# ══ fakes: Storage + run_v2 ═══════════════════════════════════════════════════

class _FakeBlob:
    def __init__(self, bucket, name):
        self._bucket, self.name = bucket, name

    def upload_from_filename(self, path):
        content = Path(path).read_bytes()
        full = f"{self._bucket.name}/{self.name}"
        self._bucket._client.uploads.append(("upload", full, content))

    def generate_signed_url(self, **kw):
        self._bucket._client.signed_calls.append(
            {"bucket": self._bucket.name, "name": self.name, **kw})
        return f"https://signed.example/{self._bucket.name}/{self.name}?sig=fake"


class _FakeBucket:
    def __init__(self, client, name):
        self._client, self.name = client, name

    def blob(self, name):
        return _FakeBlob(self, name)


class _FakeStorageClient:
    """``uploads`` may be a shared order log (entries are ("upload", name, bytes))."""

    def __init__(self, log=None):
        self.uploads = log if log is not None else []
        self.signed_calls = []

    def bucket(self, name):
        return _FakeBucket(self, name)


class _FakeJobsClient:
    def __init__(self):
        self.run_calls = []

    def run_job(self, request=None, **kwargs):
        req = request if request is not None else kwargs
        self.run_calls.append(req)
        return {"name": req["name"] + "/executions/exec-1", "done": False}


@pytest.fixture
def google(monkeypatch):
    """Stub the google.cloud.* leaf modules _core lazily imports; return the fakes."""
    fs_client = _FakeFirestoreClient()
    fs_mod = types.ModuleType("google.cloud.firestore")
    fs_mod.Client = lambda **kw: fs_client
    fs_mod.transactional = _transactional
    st_client = _FakeStorageClient()
    st_mod = types.ModuleType("google.cloud.storage")
    st_mod.Client = lambda **kw: st_client
    run_client = _FakeJobsClient()
    rv_mod = types.ModuleType("google.cloud.run_v2")
    rv_mod.JobsClient = lambda **kw: run_client
    monkeypatch.setitem(sys.modules, "google.cloud.firestore", fs_mod)
    monkeypatch.setitem(sys.modules, "google.cloud.storage", st_mod)
    monkeypatch.setitem(sys.modules, "google.cloud.run_v2", rv_mod)
    return SimpleNamespace(firestore=fs_client, storage=st_client, run=run_client)


def _create_job(store, job_id="j1", email=EMAIL, plan=None, key=None):
    plan = PLAN if plan is None else plan
    return store.create(email, plan, job_id,
                        key if key is not None else jobs.new_job_key(email, plan))


def _iso(seconds_ago=0):
    return (datetime.now(timezone.utc) - timedelta(seconds=seconds_ago)).isoformat()


# ══ import discipline: NO google packages / firebase_functions needed ═════════

def test_core_imports_with_no_google_packages():
    code = ("import sys; sys.path.insert(0, 'src'); sys.path.insert(0, 'firebase'); "
            "import _core; "
            "assert 'google.cloud.firestore' not in sys.modules; "
            "assert 'google.cloud.storage' not in sys.modules; "
            "assert 'google.cloud.run_v2' not in sys.modules; print('ok')")
    r = subprocess.run([sys.executable, "-c", code], cwd=ROOT,
                       capture_output=True, text=True)
    assert r.returncode == 0 and "ok" in r.stdout, r.stderr


def _load_main():
    """``firebase/main.py`` imported with no Functions SDK present (as in the suite)."""
    spec = importlib.util.spec_from_file_location("firebase_main_under_test",
                                                  FIREBASE_DIR / "main.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_main_imports_without_firebase_functions():
    mod = _load_main()
    assert mod.https_fn is None                 # guarded import — no SDK locally
    # This used to assert ``main`` re-exported ``handle_subject_map``, because the
    # ``subject_map`` function called it directly — which was exactly the bug in audit
    # W8-F6 (that path skipped the 30/h throttle). The import is gone on purpose; what
    # must still hold is that the module imports SDK-free and keeps the CORS contract.
    assert not hasattr(mod, "handle_subject_map")
    assert mod.CORS_HEADERS["Access-Control-Allow-Origin"] == "*"


# ══ the Functions wrappers themselves (audit W8: they were untestable before) ══
#
# Everything in main.py lives behind ``if https_fn is not None:``, so with no SDK
# installed the suite could not reach a single wrapper — which is how a CSRF-able
# method gap and an unthrottled alias both survived review. Stubbing the SDK the same
# way the google clients are stubbed makes the whole layer reachable offline.

class _FakeResponse:
    def __init__(self, body="", status=200, headers=None):
        self.body, self.status, self.headers = body, status, headers or {}


class _FakeReq:
    def __init__(self, method="GET", path="/api", args=None, json=None,
                 headers=None, remote_addr=""):
        self.method, self.path = method, path
        self.args = args or {}
        self.headers = headers or {}
        self.remote_addr = remote_addr
        self._json = json

    def get_json(self, silent=False):
        return self._json


@pytest.fixture
def main_mod(monkeypatch):
    """``firebase/main.py`` loaded with a stub Functions SDK, so the wrappers exist."""
    ff = types.ModuleType("firebase_functions")
    ff.https_fn = SimpleNamespace(Response=_FakeResponse, Request=object,
                                  on_request=lambda *a, **k: (lambda fn: fn))
    monkeypatch.setitem(sys.modules, "firebase_functions", ff)
    mod = _load_main()
    assert mod.https_fn is not None
    return mod


# ── W8-F1: the throttle key must not be caller-supplied ──────────────────────

def test_client_ip_uses_the_front_end_entry_not_the_caller_supplied_prefix(main_mod):
    """GCP APPENDS ``<client>, <lb>`` to whatever X-Forwarded-For it received, so the
    leftmost entry is attacker-controlled. Keying the §5.2 throttles on it let a caller
    mint a fresh identity per request and spend an unlimited source budget."""
    spoofed = _FakeReq(headers={"X-Forwarded-For": "1.2.3.4, 203.0.113.9, 10.0.0.1"})
    assert main_mod._ip(spoofed) == "203.0.113.9"      # the entry the GFE wrote

    # A caller rotating the prefix cannot change the identity the throttle sees.
    other = _FakeReq(headers={"X-Forwarded-For": "9.9.9.9, 203.0.113.9, 10.0.0.1"})
    assert main_mod._ip(other) == main_mod._ip(spoofed)

    # No proxy chain (emulator/direct/tests): the socket peer, which is unspoofable.
    assert main_mod._ip(_FakeReq(headers={"X-Forwarded-For": "1.2.3.4"},
                                 remote_addr="198.51.100.5")) == "198.51.100.5"
    assert main_mod._ip(_FakeReq(remote_addr="198.51.100.5")) == "198.51.100.5"
    assert main_mod._ip(_FakeReq(headers={"X-Forwarded-For": "1.2.3.4"})) == "1.2.3.4"


# ── W8-F5: a wrong method is a 405, never a state change ─────────────────────

@pytest.mark.parametrize("fn_name,handler,bad_method", [
    ("scan_cancel", "handle_scan_cancel", "GET"),
    ("scan_resume", "handle_scan_resume", "GET"),
    ("scan_start", "handle_scan_start", "GET"),
    ("scan_status", "handle_scan_status", "POST"),
    ("scan_result", "handle_scan_result", "DELETE"),
    ("map", "handle_map", "DELETE"),
    ("expand", "handle_expand", "DELETE"),
])
def test_wrappers_reject_a_wrong_method_without_acting(main_mod, monkeypatch,
                                                       fn_name, handler, bad_method):
    """``GET /scan_cancel?id=<job id>`` used to cancel the job: the wrappers ran their
    handler on ANY method, ``_params`` reads the query string on GET, and ``_job_id``
    falls back to ``params["id"]`` — so a third-party ``<img>`` tag was enough."""
    called = []
    monkeypatch.setattr(_core, handler, lambda *a, **k: called.append((a, k)) or (200, {}))
    resp = getattr(main_mod, fn_name)(_FakeReq(method=bad_method, path=f"/{fn_name}",
                                               args={"id": "j1"}))
    assert resp.status == 405
    assert called == [], "the handler ran despite the method being rejected"
    assert json.loads(resp.body)["error"].startswith("method not allowed")


def test_the_right_method_still_reaches_the_handler(main_mod, monkeypatch):
    """The guard must not break the real paths (a 405 everywhere would 'pass' too)."""
    seen = []
    monkeypatch.setattr(_core, "handle_scan_cancel",
                        lambda job_id, **k: seen.append(job_id) or (202, {"ok": True}))
    resp = main_mod.scan_cancel(_FakeReq(method="POST", path="/scan_cancel",
                                         json={"id": "j1"}))
    assert resp.status == 202 and seen == ["j1"]


# ── W8-F6: the legacy alias must cost the same budget as /api/map ────────────

def test_subject_map_alias_goes_through_the_throttled_path(main_mod, monkeypatch):
    """``subject_map`` called ``handle_subject_map`` directly — the one subject-map
    route with no throttle, so the 30/h cap was a rename away from being bypassed."""
    routed = []
    monkeypatch.setattr(_core, "handle_map",
                        lambda params, **k: routed.append(k.get("ip")) or (200, {}))
    resp = main_mod.subject_map(_FakeReq(method="GET", path="/subject_map",
                                         args={"field": "x"},
                                         headers={"X-Forwarded-For": "1.1.1.1, 203.0.113.9, 10.0.0.1"}))
    assert resp.status == 200
    assert routed == ["203.0.113.9"], "the alias must throttle on the same IP identity"


# ── W8-F4: set_status must not clobber a concurrent write ────────────────────

def test_set_status_does_not_clobber_a_concurrent_cancel(google, monkeypatch):
    """``set_status`` read the doc, mutated the copy and wrote the WHOLE thing back
    outside any transaction. A ``request_cancel`` landing in that window was reverted:
    the user saw 'cancelling', the flag went back to False, and the worker ran on.

    ``_touch`` is called between the read and the write, so patching it reproduces the
    race deterministically — the cancel commits inside ``set_status``'s window.
    """
    store = _core.FirestoreJobStore(google.firestore)
    _create_job(store)
    real_touch, fired = _core._touch, []

    def touch_then_cancel(job):
        if not fired:                       # once, and before the nested _touch calls
            fired.append(True)
            store.request_cancel("j1")      # the user hits Cancel at exactly this moment
        real_touch(job)

    monkeypatch.setattr(_core, "_touch", touch_then_cancel)
    store.set_status("j1", "running")
    assert fired == [True], "the race window was never entered — test is not proving anything"

    job = store.get("j1")
    assert job["cancel_requested"] is True, "the cancel was silently lost"
    assert job["status"] == "running"       # the flag, not the status, stops the worker


def test_set_status_does_not_clobber_concurrently_appended_progress(google, monkeypatch):
    """The same full-document overwrite also dropped progress events appended mid-write,
    so the page's live log silently lost entries."""
    store = _core.FirestoreJobStore(google.firestore)
    _create_job(store)
    real_touch, fired = _core._touch, []

    def touch_then_append(job):
        if not fired:
            fired.append(True)
            store.append_event("j1", {"phase": "fetch", "ts": _iso()})
        real_touch(job)

    monkeypatch.setattr(_core, "_touch", touch_then_append)
    store.set_status("j1", "running")
    assert [e["phase"] for e in store.get("j1")["progress"]] == ["fetch"]


def test_set_status_on_an_unknown_or_malformed_id_is_still_none(google):
    store = _core.FirestoreJobStore(google.firestore)
    assert store.set_status("nope", "running") is None
    assert store.set_status("../etc/passwd", "running") is None


# ── W8-F2: every job endpoint is throttled ───────────────────────────────────

def test_resume_is_throttled_so_a_cancel_resume_loop_cannot_relaunch_forever(google):
    """Resume launches a Cloud Run Job execution exactly like a scan start, but was
    unthrottled — so cancel→resume in a loop bought unlimited worker executions and
    walked straight around the 5/h scan cap. The cap is checked before any work."""
    kw = dict(store=_core.FirestoreJobStore(google.firestore), environ={},
              client=google.firestore, jobs_client=google.run, ip="203.0.113.7")
    seen = [_core.handle_scan_resume("nope", **kw)[0]
            for _ in range(_core.RESUME_LIMIT_PER_HOUR + 1)]
    assert seen[:-1] == [404] * _core.RESUME_LIMIT_PER_HOUR
    assert seen[-1] == 429


@pytest.mark.parametrize("bucket,limit_name", [("cancel", "CANCEL_LIMIT_PER_HOUR"),
                                               ("result", "RESULT_LIMIT_PER_HOUR"),
                                               ("status", "STATUS_LIMIT_PER_HOUR")])
def test_each_job_endpoint_has_its_own_throttle_bucket(google, bucket, limit_name):
    """Separate buckets: exhausting one must not lock a student out of the others
    (cancelling a runaway scan has to keep working when polling hit its cap)."""
    limit = getattr(_core, limit_name)
    assert limit > 0
    for _ in range(limit):
        assert _core.check_throttle(bucket, "203.0.113.7", limit,
                                    client=google.firestore) is True
    assert _core.check_throttle(bucket, "203.0.113.7", limit,
                                client=google.firestore) is False
    assert _core.check_throttle("cancel_other", "203.0.113.7", 1,
                                client=google.firestore) is True


def test_the_status_cap_cannot_bite_a_normally_polling_page():
    """The page polls every POLL_MS; a cap below that rate would 429 an honest user
    mid-scan. Tie the constant to the page's real cadence so neither drifts alone."""
    poll_ms = int(re.search(r"var POLL_MS = (\d+)", build_webapp()).group(1))
    polls_per_hour_one_tab = 3_600_000 // poll_ms
    assert _core.STATUS_LIMIT_PER_HOUR >= 3 * polls_per_hour_one_tab


# ── W8-F3: the rules must not hand out more than the endpoint does ───────────

def test_firestore_rules_deny_client_reads_of_job_documents():
    """``allow get: if true`` returned the WHOLE job doc — ``email``, ``email_ci`` and
    the full ``plan`` — to anyone holding a job id, while ``handle_scan_status`` returns
    only status/progress. The page never reads Firestore, so this costs nothing."""
    raw = (FIREBASE_DIR / "firestore.rules").read_text(encoding="utf-8")
    rules = "\n".join(ln for ln in raw.splitlines()
                      if not ln.lstrip().startswith("//"))    # the prose explains the
    body = rules.split("match /scan_jobs/{jobId}", 1)[1].split("}", 1)[0]  # old rule
    assert "allow get: if false;" in body
    assert "allow list: if false;" in body
    assert "allow write: if false;" in body
    # no collection anywhere may be client-readable
    assert "if true" not in rules


def test_the_firestore_database_id_comes_from_the_environment(monkeypatch):
    """A Firebase project created today can hand you a NAMED database (this project's is
    called "default", no parentheses) rather than the historical "(default)".
    ``Client()`` with no argument targets "(default)", so against such a project every
    call 404s. The id must therefore be deploy-time config, not a code constant."""
    seen = {}

    class _Mod:
        @staticmethod
        def Client(**kw):
            seen.clear()
            seen.update(kw)
            return "client"

    monkeypatch.setattr(_core, "_firestore_module", lambda: _Mod)
    monkeypatch.setattr(_core, "_client_factory", None)

    monkeypatch.setenv(_core.FIRESTORE_DATABASE_ENV, "default")
    assert _core._firestore_client() == "client"
    assert seen == {"database": "default"}

    # unset (or blank) keeps the historical behaviour — no argument at all
    monkeypatch.delenv(_core.FIRESTORE_DATABASE_ENV, raising=False)
    _core._firestore_client()
    assert seen == {}
    monkeypatch.setenv(_core.FIRESTORE_DATABASE_ENV, "   ")
    _core._firestore_client()
    assert seen == {}


def test_the_page_never_talks_to_firestore_directly():
    """The justification for denying client reads: every call the page makes is /api/**,
    so if this ever changes the rules above must be revisited deliberately."""
    page = build_webapp()
    for token in ("firebase.initializeApp", "firestore", "onSnapshot", "firebasejs"):
        assert token not in page


# ══ FirestoreJobStore ═════════════════════════════════════════════════════════

def test_store_create_get_roundtrip_with_all_fields(google):
    store = _core.FirestoreJobStore(google.firestore)
    job = _create_job(store)
    got = store.get("j1")
    assert got == job
    assert got["status"] == "queued" and got["progress"] == []
    assert got["cancel_requested"] is False and got["heartbeat_at"] is None
    assert got["job_key"] and got["created_at"] and got["updated_at"]
    assert isinstance(got["updatedAt"], datetime)        # the Firestore TTL field
    assert got["email_ci"] == EMAIL.casefold()
    assert store.get("nope") is None


def test_store_create_raises_jobexists_until_the_prior_key_is_terminal(google):
    store = _core.FirestoreJobStore(google.firestore)
    _create_job(store, job_id="j1", key="K")
    with pytest.raises(jobs.JobExists) as ei:
        _create_job(store, job_id="j2", key="K")
    assert ei.value.job_id == "j1"
    for status in jobs.TERMINAL_STATUSES:
        store.set_status("j1", status)
        fresh = _create_job(store, job_id=f"j-{status}", key="K")
        assert fresh["status"] == "queued"               # a terminal key starts fresh
        store.set_status(f"j-{status}", status)


def test_store_create_race_yields_one_winner_and_one_jobexists(google):
    # force both transactions to read BEFORE either commits (the fake then detects
    # the conflict and retries — real Firestore semantics) → exactly one winner
    barrier = threading.Barrier(2)
    state = {"met": False}

    def hook():
        if not state["met"]:
            barrier.wait(timeout=10)
            state["met"] = True

    google.firestore.on_stream = hook
    store = _core.FirestoreJobStore(google.firestore)
    results, errors = {}, {}

    def attempt(job_id):
        try:
            results[job_id] = _create_job(store, job_id=job_id, key="K")
        except jobs.JobExists as exc:
            errors[job_id] = exc.job_id

    threads = [threading.Thread(target=attempt, args=(f"j-{i}",)) for i in (1, 2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    assert len(results) == 1 and len(errors) == 1
    winner = next(iter(results))
    assert errors[next(iter(errors))] == winner          # loser got the winner's id
    assert store.get(winner)["status"] == "queued"


def test_store_append_event_stamps_heartbeat_and_caps_at_200(google):
    store = _core.FirestoreJobStore(google.firestore)
    _create_job(store)
    for i in range(_core.MAX_PROGRESS_EVENTS + 5):
        store.append_event("j1", {"ts": _iso(), "phase": "deep_dive_progress",
                                  "data": [i, 205]})
    job = store.get("j1")
    assert len(job["progress"]) == _core.MAX_PROGRESS_EVENTS
    assert job["progress"][0]["data"] == [5, 205]        # the oldest kept is #5
    assert job["heartbeat_at"] == job["progress"][-1]["ts"]
    store.append_event("nope", {"ts": _iso(), "phase": "x", "data": []})   # no crash


def test_store_set_status_and_request_cancel_terminal_semantics(google):
    store = _core.FirestoreJobStore(google.firestore)
    _create_job(store)
    job = store.set_status("j1", "running", run_params={"shortlist": 5})
    assert job["status"] == "running" and job["run_params"] == {"shortlist": 5}
    assert store.set_status("nope", "running") is None
    job = store.request_cancel("j1")
    assert job["cancel_requested"] is True and job["status"] == "cancelling"
    store.set_status("j1", "done")
    job = store.request_cancel("j1")                     # terminal → untouched
    assert job["status"] == "done" and job["cancel_requested"] is True
    assert store.request_cancel("nope") is None


def test_store_is_stalled_matches_the_local_semantics(google):
    store = _core.FirestoreJobStore(google.firestore)
    _create_job(store)
    assert store.is_stalled("j1") is False               # fresh
    store.set_status("j1", "running", heartbeat_at=_iso(700))
    assert store.is_stalled("j1") is True                # heartbeat > 600 s old
    assert store.is_stalled("j1", max_age_s=800) is False
    store.set_status("j1", "failed")
    assert store.is_stalled("j1") is False               # terminal never stalls
    assert store.is_stalled("nope") is False


def test_store_active_job_for_matches_only_nonterminal_jobs_of_that_email(google):
    store = _core.FirestoreJobStore(google.firestore)
    _create_job(store, job_id="j1", email="A@Uni.edu")
    _create_job(store, job_id="j2", email="b@uni.edu")
    assert store.active_job_for("a@uni.EDU")["job_id"] == "j1"   # case-insensitive
    store.set_status("j1", "cancelled")
    assert store.active_job_for("a@uni.edu") is None             # terminal frees it
    assert store.active_job_for("b@uni.edu")["job_id"] == "j2"
    assert store.active_job_for("nobody@uni.edu") is None


def test_store_malformed_job_ids_are_unknown(google):
    store = _core.FirestoreJobStore(google.firestore)
    assert store.get("../outside") is None
    assert store.request_cancel("a/b") is None
    with pytest.raises(ValueError):
        store.create(EMAIL, PLAN, "../evil", "K")


# ══ throttle (§5.2) ═══════════════════════════════════════════════════════════

def test_throttle_allows_up_to_the_limit_then_blocks(google):
    ip = "203.0.113.7"
    assert _core.check_throttle("expand", ip, 2, client=google.firestore) is True
    assert _core.check_throttle("expand", ip, 2, client=google.firestore) is True
    assert _core.check_throttle("expand", ip, 2, client=google.firestore) is False
    assert _core.check_throttle("expand", ip, 2, client=google.firestore) is False
    # the counter doc: ip#bucket#yyyymmddhh, incremented only while under the limit
    (doc_id, doc), = google.firestore._data["throttle"].items()
    expected = f"{ip}#expand#{datetime.now(timezone.utc).strftime('%Y%m%d%H')}"
    assert doc_id == expected and doc["count"] == 2
    # a different bucket / ip gets its own window
    assert _core.check_throttle("map", ip, 2, client=google.firestore) is True
    assert _core.check_throttle("expand", "198.51.100.2", 2,
                                client=google.firestore) is True


# ══ /api/expand: cache + throttle ═════════════════════════════════════════════

def _stub_engine(monkeypatch, calls, expanded=True):
    def fake_handle_expand(params, *, environ=None, transport=None):
        calls.append(str(params.get("field") or ""))
        return 200, {"variants": [calls[-1], "natural language processing"],
                     "expanded": expanded}
    monkeypatch.setattr(webapi, "handle_expand", fake_handle_expand)


def test_expand_caches_real_expansions_per_normalized_field(google, monkeypatch):
    calls = []
    _stub_engine(monkeypatch, calls)
    s1, b1 = _core.handle_expand({"field": "NLP"}, client=google.firestore,
                                 ip="9.9.9.1", environ={})
    s2, b2 = _core.handle_expand({"field": "  nlp "}, client=google.firestore,
                                 ip="9.9.9.2", environ={})
    assert s1 == 200 and "cached" not in b1
    assert s2 == 200 and b2["cached"] is True and b2["expanded"] is True
    assert calls == ["NLP"]                    # normalized-field hit — engine ran ONCE
    doc = google.firestore._data["expand_cache"]["nlp"]
    ttl = doc["expires_at"] - datetime.now(timezone.utc)
    assert timedelta(days=29) < ttl <= timedelta(days=30)


def test_expand_an_expired_cache_entry_is_a_clean_miss(google, monkeypatch):
    calls = []
    _stub_engine(monkeypatch, calls)
    _core.handle_expand({"field": "nlp"}, client=google.firestore, ip="9.9.9.3",
                        environ={})
    doc = google.firestore._data["expand_cache"]["nlp"]
    doc["expires_at"] = datetime.now(timezone.utc) - timedelta(seconds=1)  # expired
    status, body = _core.handle_expand({"field": "nlp"}, client=google.firestore,
                                       ip="9.9.9.4", environ={})
    assert status == 200 and "cached" not in body and calls == ["nlp", "nlp"]


def test_expand_fail_closed_results_are_never_cached(google):
    # no SUPERVISORLY_EXPAND_KEY → the real engine fails closed (expanded: False)
    for ip in ("9.9.9.5", "9.9.9.6"):
        status, body = _core.handle_expand({"field": "nlp"}, client=google.firestore,
                                           ip=ip, environ={})
        assert status == 200 and body["expanded"] is False and "cached" not in body
    assert "expand_cache" not in google.firestore._data


def test_expand_is_throttled_at_the_hourly_limit(google, monkeypatch):
    _stub_engine(monkeypatch, [])
    monkeypatch.setattr(_core, "EXPAND_LIMIT_PER_HOUR", 2)
    for expected in (200, 200, 429):
        status, body = _core.handle_expand({"field": "nlp"}, client=google.firestore,
                                           ip="9.9.9.7", environ={})
        assert status == expected
    assert "per hour" in body["error"]


# ══ /api/map throttle ═════════════════════════════════════════════════════════

def test_map_delegates_and_is_throttled(google, monkeypatch):
    seen = []
    monkeypatch.setattr(webapi, "handle_subject_map",
                        lambda params, **kw: seen.append(params) or (200, {"groups": []}))
    monkeypatch.setattr(_core, "MAP_LIMIT_PER_HOUR", 1)
    s1, _ = _core.handle_map({"field": "nlp", "email": EMAIL},
                             client=google.firestore, ip="9.9.9.8", environ={})
    s2, body = _core.handle_map({"field": "nlp", "email": EMAIL},
                                client=google.firestore, ip="9.9.9.8", environ={})
    assert s1 == 200 and seen == [{"field": "nlp", "email": EMAIL}]
    assert s2 == 429 and "per hour" in body["error"]


# ══ POST /api/scan ════════════════════════════════════════════════════════════

def _start(google, params, ip="10.0.0.1", environ=None):
    return _core.handle_scan_start(params, client=google.firestore, ip=ip,
                                   environ={} if environ is None else environ,
                                   jobs_client=google.run)


def test_scan_start_validation_errors_match_the_local_400s(google):
    assert _start(google, {"plan": PLAN})[0] == 400                      # no email
    status, body = _start(google, {"email": "nope", "plan": PLAN})
    assert status == 400 and "email" in body["error"]
    assert _start(google, {"email": EMAIL})[0] == 400                    # no plan
    status, body = _start(google, {"email": EMAIL, "plan": {"field": "x"}})
    assert status == 400 and "missing required key" in body["error"]
    assert google.run.run_calls == []                    # nothing invalid reaches GCP


def test_scan_start_202_invokes_the_worker_with_the_job_id_env(google):
    env = {"SCAN_WORKER_JOB": "projects/p/locations/r/jobs/w"}
    status, body = _start(google, {"email": EMAIL, "plan": PLAN, "shortlist": 7},
                          environ=env)
    assert status == 202 and body["job_id"]
    (call,) = google.run.run_calls
    assert call["name"] == "projects/p/locations/r/jobs/w"
    env_overrides = call["overrides"]["container_overrides"][0]["env"]
    assert {"name": "JOB_ID", "value": body["job_id"]} in env_overrides
    job = _core.FirestoreJobStore(google.firestore).get(body["job_id"])
    assert job["status"] == "queued"                     # the worker flips it running
    # The depth controls ride on the job doc because the Cloud Run Job receives only a
    # JOB_ID and reads everything else back from Firestore.
    assert job["run_params"] == {"shortlist": 7, "max_institutions": None,
                                 "render_all": False, "crawl": False,
                                 "concurrency": None, "use_archive": False,
                                 "obey_robots": True}


def test_scan_start_builds_the_default_worker_job_name(google):
    env = {"FIREBASE_PROJECT_ID": "demo-proj", "REGION": "europe-west1"}
    status, _ = _start(google, {"email": EMAIL, "plan": PLAN}, environ=env)
    assert status == 202
    assert google.run.run_calls[0]["name"] == (
        "projects/demo-proj/locations/europe-west1/jobs/supervisorly-scan-worker")


def test_scan_start_is_idempotent_and_allows_one_active_job_per_email(google):
    params = {"email": EMAIL, "plan": PLAN}
    status, body = _start(google, params)
    assert status == 202
    job_id = body["job_id"]
    status, body = _start(google, dict(params))          # double-click → existing id
    assert status == 200 and body == {"job_id": job_id, "existing": True}
    assert len(google.run.run_calls) == 1                # no second execution
    status, body = _start(google, {"email": EMAIL, "plan": dict(PLAN, field="robotics")})
    assert status == 429 and job_id in body["error"]     # one active job per email
    store = _core.FirestoreJobStore(google.firestore)
    store.set_status(job_id, "failed")                   # a terminal job frees the key
    status, body = _start(google, dict(params))
    assert status == 202 and body["job_id"] != job_id


def test_scan_start_is_throttled_at_5_per_hour(google):
    for i in range(5):
        status, _ = _start(google, {"email": f"user{i}@uni.edu", "plan": PLAN})
        assert status == 202
    status, body = _start(google, {"email": "user6@uni.edu", "plan": PLAN})
    assert status == 429 and "per hour" in body["error"]


# ══ status / cancel / resume ══════════════════════════════════════════════════

def test_scan_status_watchdog_flips_a_stalled_job(google):
    store = _core.FirestoreJobStore(google.firestore)
    _create_job(store)
    store.set_status("j1", "running", heartbeat_at=_iso(700))
    status, body = _core.handle_scan_status("j1", store=store)
    assert status == 200 and body["status"] == "failed"
    assert body["error"] == jobs.STALL_MESSAGE
    assert store.get("j1")["status"] == "failed"         # the flip is persisted
    assert _core.handle_scan_status("nope", store=store)[0] == 404


def test_scan_cancel_semantics(google):
    store = _core.FirestoreJobStore(google.firestore)
    _create_job(store)
    store.set_status("j1", "running")
    status, body = _core.handle_scan_cancel("j1", store=store)
    assert status == 202 and body["status"] == "cancelling"
    assert store.get("j1")["cancel_requested"] is True
    assert _core.handle_scan_cancel("j1", store=store)[0] == 202     # idempotent
    store.set_status("j1", "done")
    status, body = _core.handle_scan_cancel("j1", store=store)
    assert status == 409 and "done" in body["error"]
    assert _core.handle_scan_cancel("nope", store=store)[0] == 404


def test_scan_resume_reinvokes_the_worker_with_the_same_job_id(google):
    store = _core.FirestoreJobStore(google.firestore)
    _create_job(store)
    store.append_event("j1", {"ts": _iso(), "phase": "enumerated", "data": [3, 2]})
    store.set_status("j1", "running",
                     run_params={"shortlist": 5, "max_institutions": 2})
    store.set_status("j1", "failed", error="boom", cancel_requested=True)
    status, body = _core.handle_scan_resume(
        "j1", store=store, environ={"SCAN_WORKER_JOB": "projects/p/locations/r/jobs/w"},
        jobs_client=google.run)
    assert status == 202 and body["status"] == "queued"
    (call,) = google.run.run_calls
    env = call["overrides"]["container_overrides"][0]["env"]
    assert {"name": "JOB_ID", "value": "j1"} in env      # SAME job doc (§3.4)
    job = store.get("j1")
    assert job["status"] == "queued" and job["cancel_requested"] is False
    assert job["error"] is None
    assert [e["phase"] for e in job["progress"]] == ["enumerated"]     # history KEPT


def test_scan_resume_is_409_unless_failed_or_cancelled(google):
    store = _core.FirestoreJobStore(google.firestore)
    _create_job(store)
    status, body = _core.handle_scan_resume("j1", store=store, environ={},
                                            jobs_client=google.run)
    assert status == 409 and "queued" in body["error"]
    assert google.run.run_calls == []
    assert _core.handle_scan_resume("nope", store=store, environ={},
                                    jobs_client=google.run)[0] == 404


# ══ GET /api/result/<id> ══════════════════════════════════════════════════════

def test_result_is_a_302_with_a_fresh_signed_url_when_done(google):
    store = _core.FirestoreJobStore(google.firestore)
    _create_job(store)
    store.set_status("j1", "done",
                     result={"html": "gs://results-b/j1/dashboard.html"})
    status, body = _core.handle_scan_result(
        "j1", store=store, environ={"RESULTS_BUCKET": "results-b"},
        storage_client=google.storage)
    assert status == 302
    assert body["url"] == "https://signed.example/results-b/j1/dashboard.html?sig=fake"
    (call,) = google.storage.signed_calls
    assert call["bucket"] == "results-b" and call["name"] == "j1/dashboard.html"
    assert call["version"] == "v4" and call["expiration"] == 900
    assert call["method"] == "GET"


def _stub_google_auth(monkeypatch, creds):
    """Stub ``google.auth`` (+ its transport) for the signing path.

    sys.modules alone is not enough: ``import google.auth`` then ``google.auth.default()``
    resolves ``auth`` as an ATTRIBUTE of the parent ``google`` package, which the real
    import system sets and a bare sys.modules insert does not.
    """
    auth = types.ModuleType("google.auth")
    auth.default = lambda: (creds, "supervisorly")
    transport = types.ModuleType("google.auth.transport")
    req_mod = types.ModuleType("google.auth.transport.requests")
    req_mod.Request = lambda: object()
    transport.requests = req_mod
    auth.transport = transport

    pkg = sys.modules.get("google") or types.ModuleType("google")
    monkeypatch.setitem(sys.modules, "google", pkg)
    monkeypatch.setattr(pkg, "auth", auth, raising=False)
    for name, mod in (("google.auth", auth), ("google.auth.transport", transport),
                      ("google.auth.transport.requests", req_mod)):
        monkeypatch.setitem(sys.modules, name, mod)


def test_signing_routes_through_iam_when_the_runtime_has_no_private_key(google, monkeypatch):
    """Cloud Run/Functions credentials are a bearer token with NO private key, so v4
    signing raises "you need a private key to sign credentials" — which is exactly how
    /api/result/<id> failed in production on the first real deploy. Granting
    roles/iam.serviceAccountTokenCreator is necessary but NOT sufficient: the library only
    signs via the IAM signBlob API when handed an email + access token."""
    class _KeylessCreds:                       # what compute_engine.Credentials looks like
        signer = None
        token = None
        service_account_email = "1040155948868-compute@developer.gserviceaccount.com"

        def refresh(self, _request):
            self.token = "ya29.fake-token"

    _stub_google_auth(monkeypatch, _KeylessCreds())
    _core.signed_result_url("results-b", "j1", storage_client=google.storage, environ={})
    (call,) = google.storage.signed_calls
    assert call["service_account_email"].endswith("-compute@developer.gserviceaccount.com")
    assert call["access_token"] == "ya29.fake-token"


def test_signing_stays_unaided_when_the_credentials_hold_a_real_key(google, monkeypatch):
    """A key file can sign directly — don't route those through IAM."""
    class _KeyedCreds:
        signer = object()                      # a real private key

    _stub_google_auth(monkeypatch, _KeyedCreds())
    _core.signed_result_url("results-b", "j1", storage_client=google.storage, environ={})
    (call,) = google.storage.signed_calls
    assert "access_token" not in call and "service_account_email" not in call


def test_result_is_409_until_done_and_404_for_an_unknown_id(google):
    store = _core.FirestoreJobStore(google.firestore)
    _create_job(store)
    store.set_status("j1", "running")
    status, body = _core.handle_scan_result("j1", store=store, environ={},
                                            storage_client=google.storage)
    assert status == 409 and body["status"] == "running"
    assert google.storage.signed_calls == []             # no URL before done
    assert _core.handle_scan_result("nope", store=store, environ={},
                                    storage_client=google.storage)[0] == 404


# ══ the one-page app + the /api/** router ═════════════════════════════════════

def test_webapp_html_is_built_once_and_injects_the_api_base(google):
    _core._WEBAPP_CACHE.clear()
    html = _core.webapp_html(environ={"WEBAPP_API_BASE": "https://api.example"})
    assert "<html" in html and "https://api.example" in html
    assert _core.webapp_html(environ={"WEBAPP_API_BASE": "https://api.example"}) is html
    same_origin = _core.webapp_html(environ={})
    assert "<html" in same_origin
    _core._WEBAPP_CACHE.clear()


def test_route_api_smoke(google):
    store_create = _core.FirestoreJobStore(google.firestore)
    _create_job(store_create)
    store_create.set_status("j1", "done", result={"html": "gs://b/j1/dashboard.html"})
    status, body = _core.route_api("GET", "/api/result/j1", {},
                                   client=google.firestore,
                                   environ={"RESULTS_BUCKET": "b"},
                                   storage_client=google.storage)
    assert status == 302 and "j1/dashboard.html" in body["url"]
    status, body = _core.route_api("GET", "/api/scan/j1", {},
                                   client=google.firestore, environ={})
    assert status == 200 and body["status"] == "done"
    assert _core.route_api("GET", "/nope", {}, client=google.firestore,
                           environ={})[0] == 404


# ══ the worker, end-to-end on cassettes ═══════════════════════════════════════

ROR_CA = json.dumps({"number_of_results": 2, "items": [
    {"id": "https://ror.org/00abc11",
     "names": [{"value": "Maple University", "types": ["ror_display", "label"], "lang": "en"}],
     "locations": [{"geonames_details": {"country_code": "CA"}}],
     "links": [{"type": "website", "value": "https://maple.example/"}], "types": ["education"]},
    {"id": "https://ror.org/00abc22",
     "names": [{"value": "Northern Institute", "types": ["ror_display", "label"], "lang": "en"}],
     "locations": [{"geonames_details": {"country_code": "CA"}}],
     "links": [{"type": "website", "value": "https://northern.example/"}], "types": ["education"]},
]})

ALLOW = "User-agent: *\nAllow: /\n"
ADA_PAGE = ("<html><body><main><h1>Dr. Ada Maple</h1>"
            "<p>I am recruiting two PhD students for Fall 2027.</p>"
            "<p>Applications close on 1 December 2026.</p></main></body></html>")
CARA_PAGE = ("<html><body><main><h1>A/Prof. Cara Cedar</h1>"
             "<p>I am accepting a new PhD student for 2027.</p></main></body></html>")


def _author(aid, name, home):
    return {"id": f"https://openalex.org/{aid}", "display_name": name, "works_count": 30,
            "cited_by_count": 300, "topics": [{"id": "https://openalex.org/T10001"}],
            "last_known_institutions": [], "homepage_url": home}


def _transport():
    tp = CassetteTransport()
    tp.record(ror.country_url("CA"), 200, ROR_CA)
    tp.record(openalex.institutions_url("https://ror.org/00abc11", EMAIL), 200,
              json.dumps({"results": [{"id": "https://openalex.org/I100"}]}))
    tp.record(openalex.institutions_url("https://ror.org/00abc22", EMAIL), 200,
              json.dumps({"results": [{"id": "https://openalex.org/I200"}]}))
    tp.record(openalex.authors_url("I100", EMAIL, topic_ids=["T10001"]), 200,
              json.dumps({"results": [_author("A200", "Dr. Ada Maple",
                                              "https://maple.example/~ada"),
                                      _author("A201", "Prof. Ben Birch", None)]}))
    tp.record(openalex.authors_url("I200", EMAIL, topic_ids=["T10001"]), 200,
              json.dumps({"results": [_author("A202", "A/Prof. Cara Cedar",
                                              "https://northern.example/~cara")]}))
    tp.record("https://maple.example/robots.txt", 200, ALLOW)
    tp.record("https://maple.example/~ada", 200, ADA_PAGE)
    tp.record("https://northern.example/robots.txt", 200, ALLOW)
    tp.record("https://northern.example/~cara", 200, CARA_PAGE)
    return tp


class _RecordingStore:
    """FirestoreJobStore proxy that logs every set_status into a shared order log."""

    def __init__(self, inner, log):
        self._inner = inner
        self._log = log

    def __getattr__(self, name):
        return getattr(self._inner, name)

    def set_status(self, job_id, status, **fields):
        self._log.append(("status", status))
        return self._inner.set_status(job_id, status, **fields)


def _run_worker(google, store, tmp_path, transport=None, environ=None):
    env = {"JOB_ID": "j1", "RESULTS_BUCKET": "results-b"}
    env.update(environ or {})
    return fb_worker.main(env, store=store, transport=transport or _transport(),
                          storage_client=google.storage, work_root=tmp_path)


def test_worker_done_uploads_the_results_before_flipping_status(google, tmp_path,
                                                                capsys):
    store = _core.FirestoreJobStore(google.firestore)
    _create_job(store)
    log = []
    google.storage.uploads = log                         # one shared order log
    rc = _run_worker(google, _RecordingStore(store, log), tmp_path)
    assert rc == 0
    job = store.get("j1")
    assert job["status"] == "done" and job["error"] is None
    names = [e[1] for e in log if e[0] == "upload"]
    assert names == ["results-b/j1/dashboard.html",
                     "results-b/j1/dashboard.json",
                     "results-b/j1/supervisorly.sqlite"]
    done_at = log.index(("status", "done"))
    assert all(i < done_at for i, e in enumerate(log) if e[0] == "upload")  # §3.1
    assert job["result"]["html"] == "gs://results-b/j1/dashboard.html"
    assert job["heartbeat_at"] and job["progress"]       # heartbeat on every event
    out = capsys.readouterr().out
    assert '"phase": "exported"' in out                  # one status line per event
    assert all(line.isascii() for line in out.splitlines())


def test_worker_failure_marks_failed_stack_free_and_keeps_the_db(google, tmp_path):
    store = _core.FirestoreJobStore(google.firestore)
    _create_job(store, email="")                         # preflight fails loud
    rc = _run_worker(google, store, tmp_path)
    assert rc == 1
    job = store.get("j1")
    assert job["status"] == "failed"
    assert job["error"].startswith("MissingCredentials")
    assert "Traceback" not in job["error"] and "  File " not in job["error"]
    assert job["result"] is None                         # nothing faked
    assert all("dashboard" not in e[1] for e in google.storage.uploads)


def test_worker_cancel_mid_run_marks_cancelled_and_uploads_the_partials(
        google, tmp_path):
    store = _core.FirestoreJobStore(google.firestore)
    _create_job(store)

    class _CancelOnFirstPage:                # the Functions wrapper's role, mid-run
        def __init__(self, inner):
            self._inner = inner

        def get(self, url):
            if url == "https://maple.example/~ada":
                store.request_cancel("j1")
            return self._inner.get(url)

    rc = _run_worker(google, store, tmp_path, transport=_CancelOnFirstPage(_transport()))
    assert rc == 0
    job = store.get("j1")
    assert job["status"] == "cancelled"                  # never "done"
    names = [e[1] for e in google.storage.uploads]
    assert "results-b/j1/dashboard.html" in names        # partials kept honestly
    progress = [e for e in job["progress"] if e["phase"] == "deep_dive_progress"]
    assert [e["data"] for e in progress] == [[1, 3]]     # stopped between targets


def test_worker_a_job_cancelled_while_queued_just_flips_to_cancelled(google, tmp_path):
    store = _core.FirestoreJobStore(google.firestore)
    _create_job(store)
    store.request_cancel("j1")
    rc = _run_worker(google, store, tmp_path)
    assert rc == 0
    job = store.get("j1")
    assert job["status"] == "cancelled"
    assert job["progress"] == [] and google.storage.uploads == []


def test_worker_requires_a_job_id_and_a_known_job(google, tmp_path):
    store = _core.FirestoreJobStore(google.firestore)
    assert fb_worker.main({}, store=store, transport=_transport(),
                          storage_client=google.storage, work_root=tmp_path) == 1
    assert _run_worker(google, store, tmp_path) == 1     # "j1" was never created
