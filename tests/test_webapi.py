"""tests for the HTTP subject-map wrapper (webapi.py) — cassettes only, no network."""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from supervisorly import jobs, preflight, webapi
from supervisorly.discover import expand, openalex, ror
from supervisorly.fetch.transport import CassetteTransport

EMAIL = "test@example.com"


def _topic(n, name, works=100, field="Computer Science", subfield="AI"):
    return {"id": f"https://openalex.org/T{n}", "display_name": name,
            "works_count": works,
            "domain": {"id": "d", "display_name": "Physical Sciences"},
            "field": {"id": "f", "display_name": field},
            "subfield": {"id": "s", "display_name": subfield}}


def _page(topics, count=None):
    return json.dumps({"meta": {"count": count if count is not None else len(topics)},
                       "results": topics})


def test_missing_field_is_a_400():
    status, body = webapi.handle_subject_map({"email": EMAIL})
    assert status == 400 and "field" in body["error"]


def test_invalid_email_is_a_400():
    tp = CassetteTransport()
    status, body = webapi.handle_subject_map({"field": "causal ML", "email": "not-an-email"},
                                             transport=tp)
    assert status == 400 and "email" in body["error"]


def test_email_falls_back_to_the_environment():
    tp = CassetteTransport()
    tp.record(openalex.topics_url("causal ml", EMAIL), 200, _page([_topic(1, "Causal inference")]))
    status, body = webapi.handle_subject_map(
        {"field": "causal ml"}, transport=tp,
        environ={preflight.CONTACT_EMAIL_ENV: EMAIL})
    assert status == 200 and body["groups"], body


def test_valid_field_returns_the_map_shape():
    tp = CassetteTransport()
    tp.record(openalex.topics_url("causal ml", EMAIL), 200,
              _page([_topic(1, "Causal inference", 900), _topic(2, "Machine learning", 5000)]))
    status, body = webapi.handle_subject_map({"field": "causal ml", "email": EMAIL},
                                             transport=tp)
    assert status == 200
    assert body["query"] == "causal ml"
    assert body["groups"][0]["topics"][0]["name"] == "Machine learning"  # works_count sort
    assert body["truncated"] is False


def test_relaxation_flows_through_the_endpoint():
    tp = CassetteTransport()
    tp.record(openalex.topics_url("causal ml", EMAIL), 200, _page([], count=0))
    tp.record(openalex.topics_url("causal", EMAIL), 200,
              _page([_topic(1, "Causal inference")], count=27))
    status, body = webapi.handle_subject_map({"field": "causal ml", "email": EMAIL},
                                             transport=tp)
    assert status == 200 and body["relaxed_from"] == "causal ml"


def test_bad_max_results_is_a_400():
    assert webapi.handle_subject_map({"field": "x", "email": EMAIL, "max_results": "abc"})[0] == 400
    assert webapi.handle_subject_map({"field": "x", "email": EMAIL, "max_results": 0})[0] == 400


def test_internal_failure_is_a_500_without_a_stack(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("secret internals")
    monkeypatch.setattr(webapi.subjects, "subject_map", boom)
    status, body = webapi.handle_subject_map({"field": "x", "email": EMAIL},
                                             transport=CassetteTransport())
    assert status == 500 and "RuntimeError" in body["error"] and "secret internals" not in body["error"]


# ══ /api/expand (D-068) ═══════════════════════════════════════════════════════

def test_expand_requires_a_field():
    status, body = webapi.handle_expand({}, environ={})
    assert status == 400 and "field" in body["error"]


def test_expand_fails_closed_without_a_server_key(monkeypatch):
    monkeypatch.delenv(expand.ENV_KEY, raising=False)
    status, body = webapi.handle_expand({"field": "nlp"}, environ={})
    assert status == 200
    assert body == {"variants": ["nlp"], "expanded": False, "note": "no api key"}


def test_expand_never_takes_a_key_from_the_request(monkeypatch):
    monkeypatch.delenv(expand.ENV_KEY, raising=False)
    params = {"field": "nlp", "api_key": "smuggled", "key": "smuggled"}
    status, body = webapi.handle_expand(params, environ={})
    assert status == 200 and body["expanded"] is False      # server config ONLY (D-068)


def test_expand_returns_the_engine_dict_with_a_server_key():
    def poster(url, payload, headers, *, timeout):
        assert headers["Authorization"] == "Bearer server-key"
        content = json.dumps({"variants": ["natural language processing", "NLP"]})
        return 200, json.dumps({"choices": [{"message": {"content": content}}]})
    status, body = webapi.handle_expand({"field": "nlp"},
                                        environ={expand.ENV_KEY: "server-key"},
                                        transport=poster)
    assert status == 200 and body["expanded"] is True
    assert body["variants"] == ["nlp", "natural language processing"]
    assert "server-key" not in json.dumps(body)             # the key is never returned


# ══ POST /api/scan ════════════════════════════════════════════════════════════

PLAN = {"intent_kind": "pre_phd", "country": "CA", "field": "causal ml",
        "resolved_topic_ids": ["T10001"], "university_mode": "all", "universities": []}


class _FakeWorker:
    """Stands in for jobs.Worker: records the submission and marks the job running."""
    def __init__(self):
        self.submitted = []

    def submit(self, store, job_id, **kw):
        self.submitted.append({"job_id": job_id, **kw})
        store.set_status(job_id, "running")
        return None


def _store(tmp_path):
    return jobs.JsonJobStore(tmp_path / "store")


def _make_job(store, job_id="j1", email=EMAIL, plan=None):
    plan = PLAN if plan is None else plan
    return store.create(email, plan, job_id, jobs.new_job_key(email, plan))


def _start(store, params, worker=None):
    return webapi.handle_scan_start(params, store=store,
                                    worker=worker or _FakeWorker(), environ={})


def test_scan_start_requires_a_valid_email(tmp_path):
    store = _store(tmp_path)
    assert _start(store, {"plan": PLAN})[0] == 400
    status, body = _start(store, {"email": "nope", "plan": PLAN})
    assert status == 400 and "email" in body["error"]


def test_scan_start_requires_a_plan_dict_with_the_cli_keys(tmp_path):
    store = _store(tmp_path)
    assert _start(store, {"email": EMAIL})[0] == 400
    assert _start(store, {"email": EMAIL, "plan": ["not", "a", "dict"]})[0] == 400
    status, body = _start(store, {"email": EMAIL, "plan": {"field": "x"}})
    assert status == 400 and "missing required key" in body["error"]


def test_scan_start_reuses_the_cli_value_validation(tmp_path):
    store = _store(tmp_path)
    status, body = _start(store, {"email": EMAIL, "plan": dict(PLAN, university_mode="onyl")})
    assert status == 400 and "'university_mode'" in body["error"]
    status, body = _start(store, {"email": EMAIL, "plan": dict(PLAN, resolved_topic_ids="T1")})
    assert status == 400 and "'resolved_topic_ids'" in body["error"]
    status, body = _start(store, {"email": EMAIL, "plan": dict(PLAN, targets=[{"name": 42}])})
    assert status == 400 and "'targets'" in body["error"]


def test_scan_start_enforces_the_server_caps(tmp_path):
    store = _store(tmp_path)
    too_big = dict(PLAN, padding="x" * webapi.PLAN_MAX_BYTES)
    status, body = _start(store, {"email": EMAIL, "plan": too_big})
    assert status == 400 and "'plan'" in body["error"]
    cases = [
        (dict(PLAN, field="x" * 201), "'field'"),
        (dict(PLAN, resolved_topic_ids=[f"T{i}" for i in range(26)]), "'resolved_topic_ids'"),
        (dict(PLAN, universities=[f"U{i}" for i in range(51)]), "'universities'"),
        (dict(PLAN, targets=[f"https://openalex.org/A{i}" for i in range(101)]), "'targets'"),
    ]
    for plan, key in cases:
        status, body = _start(store, {"email": EMAIL, "plan": plan})
        assert status == 400 and key in body["error"], (key, body)


def test_scan_start_enforces_the_scope_param_ranges(tmp_path):
    store = _store(tmp_path)
    for key, bad in [("shortlist", 0), ("shortlist", 201), ("shortlist", "abc"),
                     ("max_institutions", 0), ("max_institutions", 301),
                     ("max_institutions", "many")]:
        status, body = _start(store, {"email": EMAIL, "plan": PLAN, key: bad})
        assert status == 400 and f"'{key}'" in body["error"], (key, bad, body)
    worker = _FakeWorker()                                   # the valid bounds flow through
    status, body = _start(store, {"email": EMAIL, "plan": PLAN,
                                  "shortlist": 1, "max_institutions": 300}, worker=worker)
    assert status == 202
    assert worker.submitted[0]["shortlist"] == 1
    assert worker.submitted[0]["max_institutions"] == 300


def test_scan_start_is_idempotent_and_allows_one_active_job_per_email(tmp_path):
    store = _store(tmp_path)
    worker = _FakeWorker()
    params = {"email": EMAIL, "plan": PLAN}
    status, body = _start(store, params, worker=worker)
    assert status == 202 and body["job_id"]
    job_id = body["job_id"]
    # double-click / refresh: same email + same plan → the EXISTING id, no resubmit
    status, body = _start(store, dict(params), worker=worker)
    assert status == 200 and body == {"job_id": job_id, "existing": True}
    assert len(worker.submitted) == 1
    # same email, DIFFERENT plan → an honest 429
    status, body = _start(store, {"email": EMAIL, "plan": dict(PLAN, field="robotics")},
                          worker=worker)
    assert status == 429 and job_id in body["error"]
    # a different email is unaffected
    assert _start(store, {"email": "other@uni.edu", "plan": PLAN}, worker=worker)[0] == 202
    # a terminal job frees the key: the same plan starts FRESH with a new id
    store.set_status(job_id, "failed")
    status, body = _start(store, dict(params), worker=worker)
    assert status == 202 and body["job_id"] != job_id


# ══ GET /api/scan/<id> ════════════════════════════════════════════════════════

def test_scan_status_is_404_for_an_unknown_id(tmp_path):
    status, body = webapi.handle_scan_status("no-such-job", store=_store(tmp_path))
    assert status == 404 and "never listable" in body["error"]


def test_scan_status_flips_a_stalled_job_to_failed(tmp_path):
    store = _store(tmp_path)
    _make_job(store)
    old = (datetime.now(timezone.utc) - timedelta(seconds=700)).isoformat()
    store.set_status("j1", "running", heartbeat_at=old)
    status, body = webapi.handle_scan_status("j1", store=store)
    assert status == 200 and body["status"] == "failed"
    assert body["error"] == jobs.STALL_MESSAGE
    assert store.get("j1")["status"] == "failed"             # the flip is persisted


def test_scan_status_reports_phase_counts_warnings_and_heartbeat(tmp_path):
    store = _store(tmp_path)
    _make_job(store)
    now = datetime.now(timezone.utc).isoformat()
    store.append_event("j1", {"ts": now, "phase": "enumerated", "data": [3, 2]})
    store.append_event("j1", {"ts": now, "phase": "deep_dive_start", "data": [3]})
    store.append_event("j1", {"ts": now, "phase": "partial_warning", "data": ["PARTIAL - x"]})
    store.append_event("j1", {"ts": now, "phase": "deep_dive_progress", "data": [1, 3]})
    status, body = webapi.handle_scan_status("j1", store=store)
    assert status == 200 and body["status"] == "queued"
    assert body["phase"] == "deep_dive_progress"
    assert body["counts"] == {"targets": 3, "institutions": 2,
                              "deep_dive_total": 3, "deep_dive_done": 1}
    assert body["warnings"] == ["PARTIAL - x"]
    assert body["heartbeat_age_s"] >= 0 and len(body["progress"]) == 4


def test_scan_status_caps_progress_at_the_last_20_events(tmp_path):
    store = _store(tmp_path)
    _make_job(store)
    for i in range(25):
        store.append_event("j1", {"ts": datetime.now(timezone.utc).isoformat(),
                                  "phase": "deep_dive_progress", "data": [i, 25]})
    status, body = webapi.handle_scan_status("j1", store=store)
    assert len(body["progress"]) == 20
    assert body["progress"][0]["data"] == [5, 25]            # the oldest kept is #5


# ══ cancel / resume / result ══════════════════════════════════════════════════

def test_scan_cancel_is_idempotent_and_409_on_terminal(tmp_path):
    store = _store(tmp_path)
    _make_job(store)
    store.set_status("j1", "running")
    status, body = webapi.handle_scan_cancel("j1", store=store)
    assert status == 202 and body["status"] == "cancelling"
    assert store.get("j1")["cancel_requested"] is True
    assert webapi.handle_scan_cancel("j1", store=store)[0] == 202     # idempotent
    store.set_status("j1", "done")
    status, body = webapi.handle_scan_cancel("j1", store=store)
    assert status == 409 and "done" in body["error"]
    assert webapi.handle_scan_cancel("nope", store=store)[0] == 404


def test_scan_resume_requeues_failed_and_cancelled_jobs_with_the_same_scope(tmp_path):
    store = _store(tmp_path)
    worker = _FakeWorker()
    for status0 in ("failed", "cancelled"):
        job_id = f"j-{status0}"
        _make_job(store, job_id=job_id, email=f"{status0}@uni.edu")
        store.append_event(job_id, {"ts": datetime.now(timezone.utc).isoformat(),
                                    "phase": "enumerated", "data": [3, 2]})
        store.set_status(job_id, "running",
                         run_params={"shortlist": 5, "max_institutions": 2})
        store.set_status(job_id, status0, error="boom", cancel_requested=True)
        status, body = webapi.handle_scan_resume(job_id, store=store, worker=worker,
                                                 environ={})
        assert status == 202 and body["status"] == "queued"
        job = store.get(job_id)
        # reset to queued (the fake worker then flips it running, like the real one)
        assert job["status"] in ("queued", "running") and job["cancel_requested"] is False
        assert job["error"] is None
        assert [e["phase"] for e in job["progress"]] == ["enumerated"]   # history KEPT
        submitted = worker.submitted[-1]
        assert submitted["resume"] is True                    # the engine skips done work
        assert submitted["shortlist"] == 5 and submitted["max_institutions"] == 2


def test_scan_resume_is_409_unless_failed_or_cancelled(tmp_path):
    store = _store(tmp_path)
    _make_job(store)
    for status0 in ("queued", "running", "cancelling", "done"):
        store.set_status("j1", status0)
        status, body = webapi.handle_scan_resume("j1", store=store, worker=_FakeWorker(),
                                                 environ={})
        assert status == 409 and status0 in body["error"]
    assert webapi.handle_scan_resume("nope", store=store, worker=_FakeWorker(),
                                     environ={})[0] == 404


def test_scan_result_is_409_until_done_then_returns_the_paths(tmp_path):
    store = _store(tmp_path)
    _make_job(store)
    status, body = webapi.handle_scan_result("j1", store=store)
    assert status == 409 and body["status"] == "queued"
    store.set_status("j1", "done", result={"html": "/x/dashboard.html",
                                           "json": "/x/dashboard.json"})
    status, body = webapi.handle_scan_result("j1", store=store)
    assert status == 200
    assert body == {"html_path": "/x/dashboard.html", "json_path": "/x/dashboard.json"}
    assert webapi.handle_scan_result("nope", store=store)[0] == 404


# ══ routing (the dev-server seam, tested without a socket) ════════════════════

def test_subject_map_old_path_still_routes_as_an_alias():
    tp = CassetteTransport()
    tp.record(openalex.topics_url("causal ml", EMAIL), 200, _page([_topic(1, "Causal inference")]))
    for path in ("/subject_map", "/api/map"):
        status, body = webapi.route_request("GET", path,
                                            {"field": "causal ml", "email": EMAIL},
                                            transport=tp)
        assert status == 200 and body["groups"], path


def test_route_request_dispatches_the_scan_routes(tmp_path):
    store = _store(tmp_path)
    worker = _FakeWorker()
    status, body = webapi.route_request("POST", "/api/scan", {"email": EMAIL, "plan": PLAN},
                                        store=store, worker=worker, environ={})
    assert status == 202
    job_id = body["job_id"]
    assert webapi.route_request("GET", f"/api/scan/{job_id}", {}, store=store)[0] == 200
    assert webapi.route_request("POST", f"/api/scan/{job_id}/cancel", {}, store=store)[0] == 202
    assert webapi.route_request("GET", f"/api/result/{job_id}", {}, store=store)[0] == 409
    # jobs are never listable; unknown paths are 404; a storeless server is honest
    assert webapi.route_request("GET", "/api/scan", {}, store=store)[0] == 404
    assert webapi.route_request("GET", "/nope", {}, store=store)[0] == 404
    assert webapi.route_request("POST", "/api/scan", {}, store=None)[0] == 503


# ══ full round-trip on cassettes (real Worker + store) ════════════════════════

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


def _author(aid, name, home):
    return {"id": f"https://openalex.org/{aid}", "display_name": name, "works_count": 30,
            "cited_by_count": 300, "topics": [{"id": "https://openalex.org/T10001"}],
            "last_known_institutions": [], "homepage_url": home}


def _scan_transport():
    tp = CassetteTransport()
    tp.record(ror.country_url("CA"), 200, ROR_CA)
    for ror_id, oid in (("00abc11", "I100"), ("00abc22", "I200")):
        tp.record(openalex.institutions_url(f"https://ror.org/{ror_id}", EMAIL), 200,
                  json.dumps({"results": [{"id": f"https://openalex.org/{oid}"}]}))
    tp.record(openalex.authors_url("I100", EMAIL, topic_ids=["T10001"]), 200,
              json.dumps({"results": [_author("A200", "Dr. Ada Maple",
                                              "https://maple.example/~ada")]}))
    tp.record(openalex.authors_url("I200", EMAIL, topic_ids=["T10001"]), 200,
              json.dumps({"results": [_author("A202", "A/Prof. Cara Cedar",
                                              "https://northern.example/~cara")]}))
    allow = "User-agent: *\nAllow: /\n"
    tp.record("https://maple.example/robots.txt", 200, allow)
    tp.record("https://maple.example/~ada", 200,
              "<html><body><main><h1>Dr. Ada Maple</h1>"
              "<p>I am recruiting two PhD students for Fall 2027.</p></main></body></html>")
    tp.record("https://northern.example/robots.txt", 200, allow)
    tp.record("https://northern.example/~cara", 200,
              "<html><body><main><h1>A/Prof. Cara Cedar</h1>"
              "<p>I am accepting a new PhD student for 2027.</p></main></body></html>")
    return tp


def _wait_terminal(store, job_id, timeout=60):
    deadline = time.time() + timeout
    while time.time() < deadline:
        status = store.get(job_id)["status"]
        if status in jobs.TERMINAL_STATUSES:
            return status
        time.sleep(0.05)
    raise AssertionError(f"job {job_id} never reached a terminal status")


def test_scan_start_to_status_to_result_round_trip_on_cassettes(tmp_path):
    store = _store(tmp_path)
    worker = jobs.Worker(rate_limit=0, backoff_sleep=lambda _s: None)
    status, body = webapi.handle_scan_start(
        {"email": EMAIL, "plan": PLAN}, store=store, worker=worker,
        transport=_scan_transport(), work_root=tmp_path / "jobs", environ={})
    assert status == 202 and body["job_id"]
    job_id = body["job_id"]
    assert _wait_terminal(store, job_id) == "done"

    status, body = webapi.handle_scan_status(job_id, store=store)
    assert status == 200 and body["status"] == "done"
    assert body["phase"] == "exported"
    assert body["counts"] == {"targets": 2, "institutions": 2,
                              "deep_dive_total": 2, "deep_dive_done": 2}
    assert body["heartbeat_age_s"] >= 0
    assert body["error"] is None and body["result"]["html"]

    status, body = webapi.handle_scan_result(job_id, store=store)
    assert status == 200
    assert Path(body["html_path"]).is_file() and Path(body["json_path"]).is_file()

    # a terminal job can neither be cancelled nor resumed (honest 409s)
    assert webapi.handle_scan_cancel(job_id, store=store)[0] == 409
    assert webapi.handle_scan_resume(job_id, store=store, worker=worker,
                                     work_root=tmp_path / "jobs", environ={})[0] == 409


# ── D-071: browser error reports ─────────────────────────────────────────────

def _clientlog(params, capsys):
    status, body = webapi.handle_client_log(params)
    return status, capsys.readouterr().out.strip()


def test_a_client_report_is_written_to_the_log(capsys):
    status, out = _clientlog({"kind": "api_error", "message": "boom",
                              "job_id": "abc123", "phase": "deep_dive",
                              "status": 500, "where": "err-progress"}, capsys)
    assert status == 204
    rec = json.loads(out)
    assert rec["source"] == "client" and rec["kind"] == "api_error"
    assert rec["message"] == "boom" and rec["job"] == "abc123"
    assert rec["severity"] == "WARNING"


def test_an_email_is_redacted_even_though_the_page_never_sends_one(capsys):
    """The page is written not to send an address — but "the client promised not to" is
    not a control, and this is the last point before a value lands in a log we keep."""
    status, out = _clientlog({"kind": "js_error",
                              "message": "failed for student@university.edu mid-scan",
                              "where": "mail a.b+c@d.co.uk"}, capsys)
    assert status == 204
    assert "@university.edu" not in out and "@d.co.uk" not in out
    assert out.count("[email-redacted]") == 2


def test_a_malformed_job_id_is_dropped_not_logged(capsys):
    _, out = _clientlog({"kind": "js_error", "message": "x",
                         "job_id": "../../etc/passwd"}, capsys)
    assert "passwd" not in out and '"job"' not in out


def test_only_known_kinds_are_logged(capsys):
    """D-071 is errors-only. A page view is analytics; it must not be loggable through
    this endpoint just because someone posts one."""
    for kind in ("pageview", "timing", "", "click", None):
        status, out = _clientlog({"kind": kind, "message": "should not appear"}, capsys)
        assert status == 204 and out == "", kind


def test_an_oversized_report_is_dropped(capsys):
    status, out = _clientlog({"kind": "api_error", "message": "x" * 9000}, capsys)
    assert status == 204 and out == ""


def test_a_long_message_is_capped_rather_than_refused(capsys):
    _, out = _clientlog({"kind": "api_error", "message": "y" * 900}, capsys)
    assert len(json.loads(out)["message"]) == webapi.CLIENTLOG_MAX_MESSAGE


def test_control_characters_cannot_forge_log_lines(capsys):
    """A newline in a message would otherwise let a caller inject a second, fake entry."""
    _, out = _clientlog({"kind": "js_error",
                         "message": 'a\r\n{"severity":"ERROR","fake":true}'}, capsys)
    assert len(out.splitlines()) == 1
    assert json.loads(out)["message"].count("\n") <= 1


def test_clientlog_is_post_only_and_routed(capsys):
    assert webapi.route_request("POST", "/api/clientlog", {"kind": "js_error",
                                                           "message": "m"})[0] == 204
    capsys.readouterr()
    assert webapi.route_request("GET", "/api/clientlog", {})[0] == 404


def test_a_country_name_is_resolved_to_iso_alpha2_before_the_scan_starts(tmp_path):
    """The bug Ahmed's first real scan hit: the wizard sends a country NAME, ROR's filter
    needs alpha-2, and the hosted path never translated. Every web scan queried ROR with
    `country.country_code:EGYPT`, matched none of Egypt's 285 institutions, and finished
    "done" with zero results — dressed up as an honest coverage gap.

    The CLI already did this (cli.cmd_scan). This pins that the web path does too, and that
    the STORED plan carries the code — the worker reads the plan, not the request."""
    store = _store(tmp_path)
    status, body = _start(store, {"email": EMAIL, "plan": dict(PLAN, country="Egypt")})
    assert status == 202, body
    stored = store.get(body["job_id"])
    assert stored["plan"]["country"] == "EG", \
        f"the worker would scan {stored['plan']['country']!r}, which ROR cannot match"


def test_a_country_name_with_odd_casing_or_accents_still_resolves(tmp_path):
    cases = [("EGYPT", "EG"), ("  egypt ", "EG"), ("Türkiye", "TR"),
             ("Cote d'Ivoire", "CI"), ("eg", "EG")]
    # a fresh store per case, indexed — NOT named after the country: Windows paths are
    # case-insensitive, so "EGYPT" and "egypt" would share a store and the second start
    # would (correctly) come back as the idempotent duplicate of the first
    for i, (typed, expect) in enumerate(cases):
        store = _store(tmp_path / f"case{i}")
        status, body = _start(store, {"email": EMAIL, "plan": dict(PLAN, country=typed)})
        assert status == 202, (typed, body)
        assert store.get(body["job_id"])["plan"]["country"] == expect, typed


def test_an_unrecognised_country_fails_loudly_instead_of_scanning_nothing(tmp_path):
    """Silently scanning a country that matches nothing is the failure mode this whole fix
    is about — a wrong country must be a 400, not a cheerful empty dashboard."""
    status, body = _start(_store(tmp_path),
                          {"email": EMAIL, "plan": dict(PLAN, country="Freedonia")})
    assert status == 400
    assert "unrecognized country" in body["error"] and "Freedonia" in body["error"]
    assert "alpha-2" in body["error"]


def test_map_route_checks_its_method_like_every_other_route():
    """Audit W8-F7: the /api/map branch matched on PATH ALONE, so DELETE/PUT/PATCH all
    reached the subject-map handler. Every neighbouring route already checked."""
    for method in ("DELETE", "PUT", "PATCH"):
        for path in ("/api/map", "/subject_map"):
            status, body = webapi.route_request(method, path, {"field": "x"})
            assert status == 404, f"{method} {path} reached a handler"
            assert "unknown path" in body["error"]
    # …and the methods it does serve still work
    for method in ("GET", "POST"):
        assert webapi.route_request(method, "/api/map", {})[0] == 400   # missing field
