"""Round AL — the wizard can do what `scan` can do, and says so honestly.

The web tier ran the same engine as the CLI but through a narrower door: `handle_scan_start`
accepted two scope numbers, `run_scan_job` forwarded those two, and the depth controls added
for the client-side crawl (`--render-all`, `--crawl`, `--concurrency`) stopped at the CLI. A
page could offer a browser reader all it liked; nothing downstream would have listened.

The load-bearing test here is the parity table: every `scan` flag must be *classified*. Adding
a flag without deciding whether it is a request value, an operator-only control or server
configuration turns this file red, which is the only reliable way to stop the two surfaces
drifting again.
"""

from __future__ import annotations

import argparse
import json

import pytest

from supervisorly import cli, jobs, webapi
from supervisorly.fetch import render as render_mod

EMAIL = "student@example.edu"
PLAN = {"intent_kind": "pre_phd", "country": "CA", "field": "causal ml",
        "resolved_topic_ids": ["T10001"], "university_mode": "all", "universities": []}


class _FakeWorker:
    def __init__(self):
        self.submitted = []

    def submit(self, store, job_id, **kw):
        self.submitted.append({"job_id": job_id, **kw})
        store.set_status(job_id, "running")
        return None


def _store(tmp_path):
    return jobs.JsonJobStore(tmp_path / "store")


def _start(store, params, worker=None, *, local=False, environ=None):
    return webapi.handle_scan_start(params, store=store,
                                    worker=worker if worker is not None else _FakeWorker(),
                                    environ=environ if environ is not None else {},
                                    local=local)


def _browserless(monkeypatch):
    monkeypatch.setattr(render_mod, "browser_status",
                        lambda **kw: {"available": False, "version": None,
                                      "reason": "the playwright package is not installed "
                                                "in this environment",
                                      "fix": render_mod.FIX_PACKAGE})


def _browser_ready(monkeypatch):
    monkeypatch.setattr(render_mod, "browser_status",
                        lambda **kw: {"available": True, "version": "1.49.1",
                                      "reason": None, "fix": None})


# ── 1. the parity table ──────────────────────────────────────────────────────
#: Where each `scan` flag lives on the web tier. Four honest answers, no fifth.
#:
#:   request     the page may set it — it scopes the caller's own search
#:   operator    only a LOCAL server accepts it; it spends the address the scan runs from
#:   server      configuration the worker reads from its own environment (keys, D-068/P7)
#:   n/a         the web tier owns this itself (paths, the plan, the progress view)
FLAG_HOME = {
    "--country": "request", "--field": "request", "--intent": "request",
    "--universities": "request", "--university-mode": "request", "--targets": "request",
    "--shortlist": "request", "--max-institutions": "request",
    "--institution-types": "request", "--all-institution-types": "request",
    "--render-all": "request", "--crawl": "request", "--concurrency": "request",
    "--archive": "request",
    "--compare-to": "request", "--email": "request", "--resume": "request",
    "--ignore-robots": "operator",
    "--openalex-key": "server", "--optout": "server",
    "--out": "n/a", "--plan": "n/a", "--progress": "n/a", "--demo": "n/a",
}


def _scan_flags() -> set[str]:
    parser = cli.build_parser()
    subs = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
    scan = subs.choices["scan"]
    return {opt for act in scan._actions for opt in act.option_strings
            if opt.startswith("--") and opt != "--help"}


def test_every_scan_flag_has_a_decided_home():
    """A new flag with no entry here is a flag the wizard silently cannot offer."""
    flags = _scan_flags()
    undecided = sorted(flags - set(FLAG_HOME))
    stale = sorted(set(FLAG_HOME) - flags)
    assert not undecided, f"these scan flags have no web-tier decision: {undecided}"
    assert not stale, f"FLAG_HOME names flags that no longer exist: {stale}"


def test_every_request_flag_is_reachable_over_http():
    """Classifying a flag 'request' and then not accepting it is the gap this round closed."""
    accepted = set(webapi.REQUEST_CONTROLS) | {
        # carried inside the plan rather than as a sibling parameter
        "country", "field", "intent", "universities", "university_mode", "targets", "email",
        # the resume ENDPOINT, not a parameter
        "resume",
        # two spellings of one control
        "all_institution_types", "compare_to", "archive",
    }
    for flag, home in FLAG_HOME.items():
        if home != "request":
            continue
        key = flag.lstrip("-").replace("-", "_")
        assert key in accepted, f"{flag} is classified 'request' but nothing accepts it"


def test_operator_controls_are_not_request_controls():
    """The split is the whole safety argument; an overlap would quietly void it."""
    assert not set(webapi.REQUEST_CONTROLS) & set(webapi.OPERATOR_CONTROLS)


# ── 2. capabilities: booleans and names, never a key ─────────────────────────
def test_capabilities_reports_what_is_configured(monkeypatch):
    _browser_ready(monkeypatch)
    env = {"SUPERVISORLY_SEARCH_KEY": "sk-secret-value",
           "SUPERVISORLY_SEARCH_PROVIDER": "tavily",
           "SUPERVISORLY_EXTRACT_KEY": "ek-another-secret"}
    status, body = webapi.handle_capabilities(environ=env, local=True)
    assert status == 200
    assert body["search"] == {"configured": True, "provider": "tavily"}
    assert body["model_extract"]["configured"] is True
    assert body["browser"]["available"] is True
    assert body["operator_controls"] == ["ignore_robots"]


def test_capabilities_never_echoes_a_key(monkeypatch):
    """P7: the key lives in the operator's environment. A status panel that could return it
    would have defeated the rule it exists to display."""
    _browser_ready(monkeypatch)
    env = {"SUPERVISORLY_SEARCH_KEY": "sk-secret-value",
           "SUPERVISORLY_EXTRACT_KEY": "ek-another-secret",
           "SUPERVISORLY_EXPAND_KEY": "xk-third-secret"}
    _, body = webapi.handle_capabilities(environ=env, local=True)
    blob = json.dumps(body)
    for secret in ("sk-secret-value", "ek-another-secret", "xk-third-secret"):
        assert secret not in blob


def test_a_hosted_server_offers_no_operator_controls(monkeypatch):
    _browser_ready(monkeypatch)
    _, body = webapi.handle_capabilities(environ={}, local=False)
    assert body["operator_controls"] == []
    assert body["local"] is False


def test_capabilities_names_the_fix_when_there_is_no_browser(monkeypatch):
    _browserless(monkeypatch)
    _, body = webapi.handle_capabilities(environ={}, local=True)
    assert body["browser"]["available"] is False
    assert body["browser"]["fix"] == render_mod.FIX_PACKAGE


# ── 3. the depth controls actually reach the engine ──────────────────────────
def test_depth_controls_are_forwarded_to_the_worker(tmp_path, monkeypatch):
    _browser_ready(monkeypatch)
    worker = _FakeWorker()
    status, body = _start(_store(tmp_path),
                          {"email": EMAIL, "plan": PLAN, "render_all": True,
                           "crawl": True, "concurrency": 6}, worker)
    assert status == 202, body
    sub = worker.submitted[0]
    assert sub["render_all"] is True and sub["crawl"] is True and sub["concurrency"] == 6


def test_run_scan_job_hands_them_to_the_engine(tmp_path, monkeypatch):
    """The gap that made the page powerless: `run_scan_job` called `run_live` without them."""
    seen = {}

    def _fake_run_live(plan, transport, snap_root, **kw):
        seen.update(kw)
        return {"run_id": "r1", "export": {"professors": []}, "html": "<html></html>",
                "stats": {}}

    from supervisorly import pipeline
    monkeypatch.setattr(pipeline, "run_live", _fake_run_live)

    class _Hooks:
        def on_event(self, e): pass
        def on_done(self, r): pass
        def on_failed(self, m): raise AssertionError(m)
        def should_stop(self): return False

    jobs.run_scan_job(PLAN, _Hooks(), transport=object(),
                      db_path=tmp_path / "d.sqlite", snap_root=tmp_path / "s",
                      out_html=tmp_path / "d.html", out_json=tmp_path / "d.json",
                      email=EMAIL, render_all=True, crawl=True, concurrency=5,
                      obey_robots=False)
    assert seen["render_all"] is True
    assert seen["crawl"] is True
    assert seen["concurrency"] == 5
    assert seen["obey_robots"] is False


def test_concurrency_none_leaves_the_engine_default_alone(tmp_path, monkeypatch):
    seen = {}

    def _fake_run_live(plan, transport, snap_root, **kw):
        seen.update(kw)
        return {"run_id": "r", "export": {"professors": []}, "html": "", "stats": {}}

    from supervisorly import pipeline
    monkeypatch.setattr(pipeline, "run_live", _fake_run_live)

    class _Hooks:
        def on_event(self, e): pass
        def on_done(self, r): pass
        def on_failed(self, m): raise AssertionError(m)
        def should_stop(self): return False

    jobs.run_scan_job(PLAN, _Hooks(), transport=object(),
                      db_path=tmp_path / "d.sqlite", snap_root=tmp_path / "s",
                      out_html=tmp_path / "d.html", out_json=tmp_path / "d.json",
                      email=EMAIL)
    assert "concurrency" not in seen


def test_a_resume_repeats_the_scan_that_was_asked_for(tmp_path, monkeypatch):
    """A resume that quietly dropped --render-all would finish faster and read as the same
    scan — the worst of the three possible outcomes."""
    _browser_ready(monkeypatch)
    store = _store(tmp_path)
    worker = _FakeWorker()
    _, body = _start(store, {"email": EMAIL, "plan": PLAN, "render_all": True,
                             "crawl": True, "concurrency": 7}, worker)
    job_id = body["job_id"]
    # the real worker records run_params; the fake one does not, so set them as it would
    store.set_status(job_id, "failed",
                     run_params={"shortlist": 40, "max_institutions": None,
                                 "render_all": True, "crawl": True, "concurrency": 7,
                                 "obey_robots": False})
    webapi.handle_scan_resume(job_id, store=store, worker=worker, environ={})
    sub = worker.submitted[-1]
    assert sub["render_all"] is True and sub["crawl"] is True
    assert sub["concurrency"] == 7 and sub["obey_robots"] is False


# ── 4. a browser that was asked for and is absent fails HERE ─────────────────
def test_render_all_without_a_browser_is_refused_with_the_fix(tmp_path, monkeypatch):
    """Left to the engine it degrades silently: every page falls back to plain HTML, the
    counters stay at zero, and the student is told the scan finished."""
    _browserless(monkeypatch)
    status, body = _start(_store(tmp_path),
                          {"email": EMAIL, "plan": PLAN, "render_all": True})
    assert status == 400
    assert render_mod.FIX_PACKAGE in body["error"]
    assert "playwright package is not installed" in body["error"]


def test_a_scan_without_render_all_does_not_need_a_browser(tmp_path, monkeypatch):
    _browserless(monkeypatch)
    status, _ = _start(_store(tmp_path), {"email": EMAIL, "plan": PLAN})
    assert status == 202


# ── 5. robots stays an operator decision ─────────────────────────────────────
def test_ignore_robots_is_refused_on_a_hosted_server(tmp_path):
    status, body = _start(_store(tmp_path),
                          {"email": EMAIL, "plan": PLAN, "ignore_robots": True})
    assert status == 403
    assert "locally served" in body["error"]


def test_ignore_robots_is_accepted_on_a_local_server(tmp_path):
    worker = _FakeWorker()
    status, _ = _start(_store(tmp_path),
                       {"email": EMAIL, "plan": PLAN, "ignore_robots": True},
                       worker, local=True)
    assert status == 202
    assert worker.submitted[0]["obey_robots"] is False


def test_robots_is_obeyed_when_nobody_says_otherwise(tmp_path):
    worker = _FakeWorker()
    _start(_store(tmp_path), {"email": EMAIL, "plan": PLAN}, worker, local=True)
    assert worker.submitted[0]["obey_robots"] is True


# ── 6. parameter strictness ──────────────────────────────────────────────────
@pytest.mark.parametrize("raw,expected", [(True, True), (False, False),
                                          ("true", True), ("false", False), (None, False)])
def test_bool_param_accepts_only_real_booleans(raw, expected):
    value, err = webapi._bool_param({"x": raw} if raw is not None else {}, "x")
    assert err is None and value is expected


@pytest.mark.parametrize("raw", ["yes", "1", 1, 0, "on", []])
def test_bool_param_rejects_everything_else(raw):
    """A checkbox arriving as "0" and read as truthy turns an hour-long scan on for someone
    who left it off."""
    value, err = webapi._bool_param({"x": raw}, "x")
    assert value is None and err


def test_concurrency_out_of_range_is_a_400(tmp_path, monkeypatch):
    _browser_ready(monkeypatch)
    status, body = _start(_store(tmp_path),
                          {"email": EMAIL, "plan": PLAN, "concurrency": 99})
    assert status == 400 and "concurrency" in body["error"]


def test_unknown_institution_type_is_a_400(tmp_path):
    status, body = _start(_store(tmp_path),
                          {"email": EMAIL, "plan": PLAN,
                           "institution_types": ["eductaion"]})
    assert status == 400 and "eductaion" in body["error"]


def test_institution_types_ride_in_the_stored_plan(tmp_path):
    worker = _FakeWorker()
    status, _ = _start(_store(tmp_path),
                       {"email": EMAIL, "plan": PLAN,
                        "institution_types": ["education", "facility"]}, worker)
    assert status == 202
    assert worker.submitted[0]["plan"]["institution_types"] == ["education", "facility"]


def test_all_is_accepted_as_a_single_word(tmp_path):
    worker = _FakeWorker()
    _start(_store(tmp_path), {"email": EMAIL, "plan": PLAN,
                              "institution_types": "all"}, worker)
    assert worker.submitted[0]["plan"]["institution_types"] == "all"


def test_a_plan_file_with_a_bad_institution_type_fails_validation():
    errors = cli._plan_value_errors({**PLAN, "institution_types": ["hospitals"]})
    assert any("institution_types" in e for e in errors)


# ── 7. compare_to_job ────────────────────────────────────────────────────────
def test_compare_to_an_unfinished_job_is_refused(tmp_path):
    store = _store(tmp_path)
    _, body = _start(store, {"email": "other@example.edu", "plan": PLAN})
    status, err = _start(store, {"email": EMAIL, "plan": PLAN,
                                 "compare_to_job": body["job_id"]})
    assert status == 400 and "compare_to_job" in err["error"]


def test_compare_to_a_finished_job_forwards_its_export(tmp_path):
    store = _store(tmp_path)
    export = {"schema_version": "1", "professors": [{"id": "a", "name": "A", "fields": {}}]}
    prev = tmp_path / "prev.json"
    prev.write_text(json.dumps(export), encoding="utf-8")
    _, body = _start(store, {"email": "other@example.edu", "plan": PLAN})
    store.set_status(body["job_id"], "done",
                     result={"html": str(tmp_path / "x.html"), "json": str(prev)})
    worker = _FakeWorker()
    status, _ = _start(store, {"email": EMAIL, "plan": PLAN,
                               "compare_to_job": body["job_id"]}, worker)
    assert status == 202
    assert worker.submitted[0]["previous_export"] == export


# ── 8. `supervisorly serve` ──────────────────────────────────────────────────
def test_serve_is_a_registered_command():
    ns = cli.build_parser().parse_args(["serve"])
    assert ns.func is cli.cmd_serve
    assert ns.port == 8765 and ns.no_open is False


def test_the_local_server_binds_loopback_and_serves_the_page(tmp_path):
    """`local=True` unlocks the operator controls and is only defensible because nothing off
    this machine can reach the socket — so the binding is asserted, not assumed."""
    server = webapi.build_server(port=0, work_root=tmp_path, local=True, page_html="<h1>hi</h1>")
    try:
        assert server.server_address[0] == "127.0.0.1"
        assert server.local is True
        assert server.page_html == "<h1>hi</h1>"
    finally:
        server.server_close()


def test_the_api_only_server_is_not_local_privileged(tmp_path):
    server = webapi.build_server(port=0, work_root=tmp_path)
    try:
        assert server.local is False and server.page_html is None
    finally:
        server.server_close()


def test_capabilities_is_routed():
    status, body = webapi.route_request("GET", "/api/capabilities", {}, environ={}, local=True)
    assert status == 200 and body["local"] is True


def test_routing_does_not_leak_local_privilege_by_default():
    _, body = webapi.route_request("GET", "/api/capabilities", {}, environ={})
    assert body["local"] is False and body["operator_controls"] == []


# ── 9. the page offers exactly what the server accepts ───────────────────────
def test_the_wizard_ships_a_control_for_every_request_flag():
    from supervisorly.export.webapp import build_webapp

    html = build_webapp(api_base="")
    for element_id in ("optRenderAll", "optCrawl", "concRange", "instTypes",
                       "compareSel", "optIgnoreRobots", "capChips"):
        assert f'id="{element_id}"' in html, f"the wizard has no {element_id} control"
    # …and actually sends them
    for key in ("render_all:", "crawl:", "concurrency:", "institution_types:"):
        assert key in html, f"the wizard never sends {key}"
    assert "compare_to_job" in html
    assert "/api/capabilities" in html


def test_the_wizard_asks_the_server_before_offering_a_browser():
    """A checkbox for a browser that is not installed is worse than no checkbox: the scan
    starts, renders nothing, and reports success."""
    from supervisorly.export.webapp import build_webapp

    html = build_webapp(api_base="")
    assert "ra.disabled = true" in html
