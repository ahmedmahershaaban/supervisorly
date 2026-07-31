"""tests for the async scan job (jobs.py, web build plan step 4): the JSON job store
(lifecycle, idempotent key, heartbeat/stall, cancel flag, atomic writes), the
storage-agnostic runner (ts-stamped events, result-before-status, stack-free failure),
and the threaded Worker (done / cancelled-with-partials / queued-cancel) — cassettes
only, no network (D-035).
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from supervisorly import jobs
from supervisorly.discover import openalex, ror
from supervisorly.fetch.transport import CassetteTransport

EMAIL = "me@uni.edu"
ALLOW = "User-agent: *\nAllow: /\n"

ROR_CA = json.dumps({"number_of_results": 2, "items": [   # ROR v2 record shape
    {"id": "https://ror.org/00abc11",
     "names": [{"value": "Maple University", "types": ["ror_display", "label"], "lang": "en"}],
     "locations": [{"geonames_details": {"country_code": "CA"}}],
     "links": [{"type": "website", "value": "https://maple.example/"}], "types": ["education"]},
    {"id": "https://ror.org/00abc22",
     "names": [{"value": "Northern Institute", "types": ["ror_display", "label"], "lang": "en"}],
     "locations": [{"geonames_details": {"country_code": "CA"}}],
     "links": [{"type": "website", "value": "https://northern.example/"}], "types": ["education"]},
]})


def _oa_inst(oid):
    return json.dumps({"results": [{"id": f"https://openalex.org/{oid}"}]})


def _author(aid, name, home):
    return {"id": f"https://openalex.org/{aid}", "display_name": name, "works_count": 30,
            "cited_by_count": 300, "topics": [{"id": "https://openalex.org/T10001"}],
            "last_known_institutions": [], "homepage_url": home}


ADA_PAGE = ("<html><body><main><h1>Dr. Ada Maple</h1>"
            "<p>I am recruiting two PhD students for Fall 2027.</p>"
            "<p>Applications close on 1 December 2026.</p></main></body></html>")
CARA_PAGE = ("<html><body><main><h1>A/Prof. Cara Cedar</h1>"
             "<p>I am accepting a new PhD student for 2027.</p></main></body></html>")

PLAN = {"intent_kind": "pre_phd", "country": "CA", "field": "causal ml",
        "resolved_topic_ids": ["T10001"], "university_mode": "all", "universities": []}


def _transport():
    tp = CassetteTransport()
    tp.record(ror.country_url("CA"), 200, ROR_CA)
    tp.record(openalex.institutions_url("https://ror.org/00abc11", EMAIL), 200, _oa_inst("I100"))
    tp.record(openalex.institutions_url("https://ror.org/00abc22", EMAIL), 200, _oa_inst("I200"))
    tp.record(openalex.authors_url("I100", EMAIL, topic_ids=["T10001"]), 200, json.dumps({"results": [
        _author("A200", "Dr. Ada Maple", "https://maple.example/~ada"),
        _author("A201", "Prof. Ben Birch", None),           # no homepage → open gap
    ]}))
    tp.record(openalex.authors_url("I200", EMAIL, topic_ids=["T10001"]), 200, json.dumps({"results": [
        _author("A202", "A/Prof. Cara Cedar", "https://northern.example/~cara"),
    ]}))
    tp.record("https://maple.example/robots.txt", 200, ALLOW)
    tp.record("https://maple.example/~ada", 200, ADA_PAGE)
    tp.record("https://northern.example/robots.txt", 200, ALLOW)
    tp.record("https://northern.example/~cara", 200, CARA_PAGE)
    return tp


def _iso(seconds_ago=0):
    return (datetime.now(timezone.utc) - timedelta(seconds=seconds_ago)).isoformat()


def _create(store, job_id="j1", email=EMAIL, plan=None, key=None):
    plan = PLAN if plan is None else plan
    return store.create(email, plan, job_id, key if key is not None else jobs.new_job_key(email, plan))


# ── the idempotency key ───────────────────────────────────────────────────────

def test_job_key_is_canonical_and_email_scoped():
    a = jobs.new_job_key("Me@Uni.edu ", {"b": 1, "a": {"y": [1], "x": 2}})
    b = jobs.new_job_key("me@uni.edu", {"a": {"x": 2, "y": [1]}, "b": 1})
    assert a == b                                   # key order + email case/whitespace-insensitive
    assert a != jobs.new_job_key("me@uni.edu", {"a": {"x": 3, "y": [1]}, "b": 1})
    assert a != jobs.new_job_key("other@uni.edu", {"b": 1, "a": {"y": [1], "x": 2}})


# ── JsonJobStore ──────────────────────────────────────────────────────────────

def test_create_get_roundtrip_with_all_fields(tmp_path):
    store = jobs.JsonJobStore(tmp_path / "store")
    job = _create(store)
    got = store.get("j1")
    assert got == job
    assert got["status"] == "queued" and got["progress"] == [] and got["result"] is None
    assert got["cancel_requested"] is False and got["heartbeat_at"] is None
    assert got["created_at"] and got["updated_at"] and got["job_key"]
    assert store.get("nope") is None


def test_append_event_stamps_heartbeat_and_updated(tmp_path):
    store = jobs.JsonJobStore(tmp_path / "store")
    _create(store)
    store.append_event("j1", {"ts": _iso(), "phase": "enumerated", "data": [3, 2]})
    store.append_event("j1", {"ts": _iso(), "phase": "scoring", "data": []})
    job = store.get("j1")
    assert [e["phase"] for e in job["progress"]] == ["enumerated", "scoring"]
    assert job["heartbeat_at"] == job["progress"][-1]["ts"]


def test_create_raises_jobexists_until_the_prior_key_is_terminal(tmp_path):
    store = jobs.JsonJobStore(tmp_path / "store")
    _create(store, job_id="j1", key="K")
    with pytest.raises(jobs.JobExists) as ei:
        _create(store, job_id="j2", key="K")
    assert ei.value.job_id == "j1"
    for status in jobs.TERMINAL_STATUSES:
        store.set_status("j1", status)
        fresh = _create(store, job_id=f"j-{status}", key="K")   # terminal key starts fresh
        assert fresh["status"] == "queued"
        store.set_status(f"j-{status}", status)


def test_request_cancel_sets_flag_and_status_and_is_a_noop_on_terminal(tmp_path):
    store = jobs.JsonJobStore(tmp_path / "store")
    _create(store)
    job = store.request_cancel("j1")
    assert job["cancel_requested"] is True and job["status"] == "cancelling"
    store.set_status("j1", "done")
    job = store.request_cancel("j1")                # terminal → untouched
    assert job["status"] == "done"
    assert store.request_cancel("nope") is None


def test_is_stalled_only_for_a_nonterminal_job_with_an_old_heartbeat(tmp_path):
    store = jobs.JsonJobStore(tmp_path / "store")
    _create(store)
    assert store.is_stalled("j1") is False                       # fresh
    store.set_status("j1", "running", heartbeat_at=_iso(700))
    assert store.is_stalled("j1") is True                        # heartbeat > 600 s old
    assert store.is_stalled("j1", max_age_s=800) is False        # caller-set window
    store.set_status("j1", "failed")
    assert store.is_stalled("j1") is False                       # terminal never stalls
    assert store.is_stalled("nope") is False
    # a queued job with no heartbeat yet is measured from updated_at (worker died pre-start)
    _create(store, job_id="j2")
    p = tmp_path / "store" / "j2.json"
    doc = json.loads(p.read_text(encoding="utf-8"))
    doc["updated_at"] = _iso(700)
    p.write_text(json.dumps(doc), encoding="utf-8")
    assert store.is_stalled("j2") is True


def test_active_job_for_matches_only_nonterminal_jobs_of_that_email(tmp_path):
    store = jobs.JsonJobStore(tmp_path / "store")
    _create(store, job_id="j1", email="A@Uni.edu")
    _create(store, job_id="j2", email="b@uni.edu")
    assert store.active_job_for("a@uni.EDU")["job_id"] == "j1"   # case-insensitive
    store.set_status("j1", "cancelled")
    assert store.active_job_for("a@uni.edu") is None             # terminal frees the slot
    assert store.active_job_for("b@uni.edu")["job_id"] == "j2"
    assert store.active_job_for("nobody@uni.edu") is None


def test_writes_are_atomic_and_leave_no_temp_litter(tmp_path):
    store = jobs.JsonJobStore(tmp_path / "store")
    _create(store)
    store.append_event("j1", {"ts": _iso(), "phase": "scoring", "data": []})
    store.set_status("j1", "done", result={"html": "x", "json": "y"})
    names = [p.name for p in (tmp_path / "store").iterdir()]
    assert names == ["j1.json"]                                  # no *.tmp litter


def test_malformed_job_ids_are_unknown_never_a_path_traversal(tmp_path):
    store = jobs.JsonJobStore(tmp_path / "store")
    assert store.get("../outside") is None
    assert store.get("a/b") is None
    assert store.request_cancel("../outside") is None
    with pytest.raises(ValueError):
        store.create(EMAIL, PLAN, "../evil", "K")


# ── run_scan_job (storage-agnostic runner) ────────────────────────────────────

class _Hooks:
    def __init__(self, stop_after=None, out_files=()):
        self.events = []
        self.done = None
        self.failed = None
        self.files_existed_at_done = None
        self._stop_after = stop_after
        self._stop_calls = 0
        self._out_files = out_files

    def on_event(self, event):
        self.events.append(event)

    def on_done(self, result):
        # result-before-status (§3.1): the files must already exist when on_done fires
        self.files_existed_at_done = all(Path(p).is_file() for p in self._out_files)
        self.done = result

    def on_failed(self, message):
        self.failed = message

    def should_stop(self):
        if self._stop_after is None:
            return False
        self._stop_calls += 1
        return self._stop_calls >= self._stop_after


def _run(hooks, tp, tmp_path, **kw):
    args = dict(transport=tp, db_path=tmp_path / "run.sqlite",
                snap_root=tmp_path / "snaps", out_html=tmp_path / "dashboard.html",
                out_json=tmp_path / "dashboard.json", email=EMAIL,
                rate_limit=0, backoff_sleep=lambda _s: None)
    args.update(kw)
    return jobs.run_scan_job(PLAN, hooks, **args)


def test_run_scan_job_stamps_ts_and_maps_every_engine_event(tmp_path):
    hooks = _Hooks(out_files=[tmp_path / "dashboard.html", tmp_path / "dashboard.json"])
    result = _run(hooks, _transport(), tmp_path)
    assert result is not None and hooks.failed is None
    assert [(e["phase"], tuple(e["data"])) for e in hooks.events] == [
        ("enumerated", (3, 2)),
        ("deep_dive_start", (3,)),
        ("deep_dive_progress", (1, 3)),
        ("deep_dive_progress", (2, 3)),
        ("deep_dive_progress", (3, 3)),
        ("scoring", ()),
        ("exported", ()),
    ]
    for e in hooks.events:
        assert datetime.fromisoformat(e["ts"]) is not None       # every event carries ts
    # result files written BEFORE on_done, and on_done got the engine result
    assert hooks.files_existed_at_done is True
    assert hooks.done["html"] and hooks.done["export"]["professors"]
    assert json.loads((tmp_path / "dashboard.json").read_text(encoding="utf-8"))["professors"]


def test_run_scan_job_failure_is_honest_and_stack_free(tmp_path):
    hooks = _Hooks()
    # an empty email fails preflight loud (D-019) before any fetching
    result = _run(hooks, _transport(), tmp_path, email="")
    assert result is None and hooks.done is None
    assert hooks.failed.startswith("MissingCredentials")
    assert "Traceback" not in hooks.failed and "  File " not in hooks.failed
    assert not (tmp_path / "dashboard.html").exists()            # no fake result


def test_run_scan_job_cancel_still_writes_the_partial_results(tmp_path):
    hooks = _Hooks(stop_after=1,
                   out_files=[tmp_path / "dashboard.html", tmp_path / "dashboard.json"])
    result = _run(hooks, _transport(), tmp_path)
    assert result["stats"]["cancelled"] is True
    assert hooks.files_existed_at_done is True                   # partials exported honestly
    assert [e for e in hooks.events if e["phase"] == "deep_dive_progress"] == [
        {"ts": hooks.events[2]["ts"], "phase": "deep_dive_progress", "data": [1, 3]}]


# ── Worker (threaded, store-backed) ───────────────────────────────────────────

def _worker():
    return jobs.Worker(rate_limit=0, backoff_sleep=lambda _s: None)


def _submit(store, job_id, tp, tmp_path, **kw):
    args = dict(plan=PLAN, email=EMAIL, transport=tp,
                db_path=tmp_path / job_id / "run.sqlite",
                snap_root=tmp_path / job_id / "snaps",
                out_html=tmp_path / job_id / "dashboard.html",
                out_json=tmp_path / job_id / "dashboard.json")
    args.update(kw)
    return _worker().submit(store, job_id, **args)


def test_worker_runs_a_job_to_done_with_events_and_result_paths(tmp_path):
    store = jobs.JsonJobStore(tmp_path / "store")
    _create(store)
    t = _submit(store, "j1", _transport(), tmp_path)
    t.join(timeout=60)
    job = store.get("j1")
    assert job["status"] == "done" and job["error"] is None
    assert Path(job["result"]["html"]).is_file() and Path(job["result"]["json"]).is_file()
    assert [e["phase"] for e in job["progress"]][:2] == ["enumerated", "deep_dive_start"]
    assert all(e["ts"] for e in job["progress"])
    assert job["heartbeat_at"] == job["progress"][-1]["ts"]
    # The depth controls are recorded for the same reason the scope is: a resume must repeat
    # the scan that was asked for, not a shallower one that happens to share its plan.
    assert job["run_params"] == {"shortlist": 40, "max_institutions": None,
                                 "render_all": False, "crawl": False,
                                 "concurrency": None, "use_archive": False,
                                 "obey_robots": True}


def test_worker_cancel_mid_run_marks_cancelled_and_keeps_the_partials(tmp_path):
    store = jobs.JsonJobStore(tmp_path / "store")
    _create(store)

    class _CancelOnFirstPage:                      # the HTTP handler's role, mid-run
        def __init__(self, inner):
            self._inner = inner

        def get(self, url):
            if url == "https://maple.example/~ada":
                store.request_cancel("j1")
            return self._inner.get(url)

    t = _submit(store, "j1", _CancelOnFirstPage(_transport()), tmp_path)
    t.join(timeout=60)
    job = store.get("j1")
    assert job["status"] == "cancelled"                        # never "done"
    assert Path(job["result"]["html"]).is_file()               # partial results kept
    assert [e for e in job["progress"] if e["phase"] == "deep_dive_progress"] == [
        {"ts": job["progress"][2]["ts"], "phase": "deep_dive_progress", "data": [1, 3]}]


def test_worker_a_job_cancelled_while_queued_just_flips_to_cancelled(tmp_path):
    store = jobs.JsonJobStore(tmp_path / "store")
    _create(store)
    store.request_cancel("j1")
    assert _submit(store, "j1", _transport(), tmp_path) is None
    job = store.get("j1")
    assert job["status"] == "cancelled" and job["progress"] == [] and job["result"] is None


def test_worker_failure_marks_failed_with_a_stack_free_message(tmp_path):
    store = jobs.JsonJobStore(tmp_path / "store")
    _create(store)
    t = _submit(store, "j1", _transport(), tmp_path, email="")   # preflight fails loud
    t.join(timeout=60)
    job = store.get("j1")
    assert job["status"] == "failed"
    assert job["error"].startswith("MissingCredentials") and "Traceback" not in job["error"]
    assert job["result"] is None                               # nothing faked


def test_worker_submit_on_an_unknown_job_raises(tmp_path):
    store = jobs.JsonJobStore(tmp_path / "store")
    with pytest.raises(KeyError):
        _submit(store, "nope", _transport(), tmp_path)
