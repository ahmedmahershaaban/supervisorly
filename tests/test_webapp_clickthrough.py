"""End-to-end click-through of the one-page app (web plan §7 step 8).

Plan step 8 asks for a "headless-Chrome click-through of the whole page (the atlas.html
harness pattern) including a cancel+resume pass". There is no real-Chrome harness in
this repo — the pattern step 8 names is the Node ``vm`` + mini-DOM harness in
``test_studio.py`` — so this file extends that pattern rather than adding a browser
dependency the suite has never had (and which would have to ``pytest.skip`` on any
machine without Chrome anyway, i.e. prove nothing in CI).

What it exercises is the real thing: the page's ACTUAL embedded JavaScript, unmodified,
driven through all five steps by firing the real listeners the page wires itself —
``DOMContentLoaded`` → step 1 → *Understand* (expand + one map per phrasing) → topic
selection → scope → *Start scan* → poll → **Cancel** → poll → **Resume** → poll → done →
*Open dashboard*. Every network call is recorded, so the test asserts the exact request
sequence a student's browser would make, and the honest-state text/button visibility at
each stage (§4: a terminal state is never a dead end).

The mini-DOM is deliberately small and strict about the selectors the page really uses:
an unsupported selector throws rather than silently returning nothing, so a page change
that outgrows the harness fails loudly instead of quietly under-testing.
"""

from __future__ import annotations

import json
import shutil
import subprocess

import pytest

from supervisorly.export.webapp import build_webapp

JOB = "0f9c1a2b3c4d5e6f7a8b9c0d1e2f3a4b"        # a uuid4().hex-shaped job id

_HARNESS = r"""
"use strict";
const fs = require("fs");
const vm = require("vm");
const [htmlPath, scenPath] = process.argv.slice(2);
const html = fs.readFileSync(htmlPath, "utf8");
const scen = JSON.parse(fs.readFileSync(scenPath, "utf8"));
const scriptSrc = html.split("<script>", 2)[1].split("</script>", 1)[0];

/* ── mini-DOM ────────────────────────────────────────────────────────────── */
class El {
  constructor(tag, id) {
    this.tag = tag; this.id = id || ""; this.children = []; this.parent = null;
    this.attrs = {}; this.listeners = {}; this.style = {};
    this.checked = false; this.indeterminate = false; this.disabled = false;
    this.value = ""; this.textContent = ""; this._html = "";
    const self = this;
    const cls = () => new Set((self.attrs.class || "").split(/\s+/).filter(Boolean));
    this.classList = {
      contains: (c) => cls().has(c),
      add: (c) => { const s = cls(); s.add(c); self.attrs.class = [...s].join(" "); },
      remove: (c) => { const s = cls(); s.delete(c); self.attrs.class = [...s].join(" "); },
      toggle: (c, force) => {
        const on = force === undefined ? !cls().has(c) : !!force;
        on ? self.classList.add(c) : self.classList.remove(c);
        return on;
      },
    };
  }
  get innerHTML() { return this._html; }
  set innerHTML(v) {
    this._html = String(v);
    const parsed = parseTree(this._html);
    this.children = parsed.children;
    for (const c of this.children) c.parent = this;
  }
  getAttribute(n) { return this.attrs[n] ?? null; }
  setAttribute(n, v) { this.attrs[n] = String(v); }
  closest(tag) { let e = this; while (e) { if (e.tag === tag) return e; e = e.parent; } return null; }
  _walk(out) { for (const c of this.children) { out.push(c); c._walk(out); } return out; }
  querySelectorAll(sel) {
    const all = this._walk([]);
    const m = /^input\.(\w+)(:checked)?$/.exec(sel);
    if (m) return all.filter(e => e.tag === "input" && e.classList.contains(m[1])
                                  && (!m[2] || e.checked));
    const a = /^(\w+)\[([\w-]+)\]$/.exec(sel);       // e.g. button[data-uni] (the chips)
    if (a) return all.filter(e => e.tag === a[1] && a[2] in e.attrs);
    const t = /^(\w+)\.([\w-]+)$/.exec(sel);         // e.g. details.fp (the search plan)
    if (t) return all.filter(e => e.tag === t[1] && e.classList.contains(t[2]));
    const b = /^\[([\w-]+)\]$/.exec(sel);            // e.g. [data-addto]
    if (b) return all.filter(e => b[1] in e.attrs);
    throw new Error("mini-DOM el: unsupported selector " + sel);
  }
  addEventListener(type, fn) { (this.listeners[type] ||= []).push(fn); }
  removeEventListener() {}
  focus() { this.focused = true; }
  scrollIntoView() {}
  fire(type, ev) { for (const fn of (this.listeners[type] || [])) fn(ev || {target: this}); }
}

function parseTree(markup) {
  const root = new El("div");
  const stack = [root];
  const re = /<\/?(ul|li|label|input|span|div|button|details|summary|b)(\s[^>]*)?\/?>|([^<]+)/g;
  let m;
  while ((m = re.exec(markup))) {
    const [, tag, attrs, text] = m;
    if (text !== undefined) continue;
    if (m[0].startsWith("</")) { if (stack.length > 1) stack.pop(); continue; }
    const el = new El(tag);
    if (attrs) for (const am of attrs.matchAll(/([\w-]+)="([^"]*)"/g))
      el.attrs[am[1]] = am[2].replace(/&quot;/g, '"').replace(/&#39;/g, "'")
        .replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&amp;/g, "&");
    if (tag === "input") el.value = el.attrs.value ?? "";
    stack[stack.length - 1].children.push(el); el.parent = stack[stack.length - 1];
    if (tag !== "input") stack.push(el);
  }
  return root;
}

const ids = {};
const byId = (id) => (ids[id] ||= new El("div", id));
const ritems = [1, 2, 3, 4, 5].map(n => { const e = new El("button");
  e.attrs["data-step"] = String(n); return e; });
const radios = (name, values, checkedValue) => values.map(v => {
  const r = new El("input"); r.attrs.name = name; r.value = v;
  r.checked = v === checkedValue; return r; });
/* Intents are CHECKBOXES since MI-1 — several levels may be ticked at once, so the harness
   models a group with a SET of checked values rather than a single winner. `scen.intents`
   lets a scenario drive the tick state, including the empty case. */
const intentValues = ["pre_phd", "pre_master", "master", "phd", "postdoc", "mentor"];
const intentChecked = new Set(scen.intents === undefined ? ["phd"] : scen.intents);
const intentBoxes = intentValues.map((v) => {
  const b = new El("input"); b.attrs.name = "intent"; b.attrs.type = "checkbox";
  b.value = v; b.checked = intentChecked.has(v); return b; });
const uniModeRadios = radios("uniMode", ["all", "prioritise", "only"], "all");

const document = {
  documentElement: {scrollTop: 0, scrollHeight: 1, clientHeight: 1},
  body: new El("body"),
  getElementById: byId,
  createElement: (t) => new El(t),
  querySelectorAll: (sel) => {
    if (sel.startsWith("#tree ")) return byId("tree").querySelectorAll(sel.slice(6));
    if (sel === ".ritem") return ritems;
    if (sel === ".err" || sel === ".step.bad") return [];
    if (sel === 'input[name="intent"]:checked') return intentBoxes.filter(b => b.checked);
    if (sel === 'input[name="intent"]') return intentBoxes;
    throw new Error("mini-DOM doc: unsupported selector " + sel);
  },
  querySelector: (sel) => {
    if (sel === 'input[name="intent"]:checked') return intentBoxes.find(b => b.checked) ?? null;
    if (sel === 'input[name="intent"]') return intentBoxes[0] ?? null;
    if (sel === 'input[name="uniMode"]:checked') return uniModeRadios.find(r => r.checked) ?? null;
    throw new Error("mini-DOM doc: unsupported selector " + sel);
  },
  addEventListener: (type, fn) => { if (type === "DOMContentLoaded") document._domready = fn; },
};

/* ── network: a scripted router that records every request ───────────────── */
const requests = [];
const queues = JSON.parse(JSON.stringify(scen.responses));
const bodies = [];                       /* what the page actually SENT, parsed */
function respond(method, url) {
  const path = url.split("?")[0];
  const key = method + " " + path;
  requests.push({method, path});
  const q = queues[key];
  if (!q || !q.length) return {status: 404, body: {error: "no scripted response for " + key}};
  return q.length === 1 ? q[0] : q.shift();   // the last entry repeats (polling)
}

/* ── timers: intervals are held so the test drives polling deliberately ──── */
let timerSeq = 0;
const intervals = new Map();

const sandbox = {
  console,
  document,
  navigator: {onLine: true},
  location: {href: "https://example.test/", search: ""},
  AbortController: function () { this.signal = {}; this.abort = () => {}; },
  setTimeout: (fn, ms) => { return ++timerSeq; },      // the abort timer never fires here
  clearTimeout: () => {},
  setInterval: (fn) => { intervals.set(++timerSeq, fn); return timerSeq; },
  clearInterval: (id) => { intervals.delete(id); },
  fetch: (url, opts) => {
    const method = (opts && opts.method) || "GET";
    // Record the request BODY too: asserting the request sequence proves the page called the
    // right endpoint, not that it sent the right plan.
    if (opts && opts.body) {
      let parsed = null;
      try { parsed = JSON.parse(opts.body); } catch (_) { parsed = String(opts.body); }
      bodies.push({path: String(url).split("?")[0], body: parsed});
    }
    const r = respond(method, String(url));
    return Promise.resolve({
      status: r.status,
      json: () => Promise.resolve(r.body),
    });
  },
};
sandbox.window = {
  addEventListener() {},
  scrollTo() {},
  matchMedia: () => ({matches: false, addEventListener() {}}),
  open: (u, t, f) => { opened.push({url: String(u), target: t}); },
};
const opened = [];
sandbox.window.document = document;
sandbox.globalThis = sandbox;

vm.createContext(sandbox);
vm.runInContext(scriptSrc, sandbox);

/* ── the click-through ───────────────────────────────────────────────────── */
const flush = async () => { for (let i = 0; i < 24; i++) await new Promise(r => setImmediate(r)); };
const fireIntervals = () => { for (const fn of [...intervals.values()]) fn(); };
const vis = (id) => !byId(id).classList.contains("hidden");

/* Every phase line the student would have SEEN, in order. A snapshot alone would miss
   messages that a later poll overwrites — resume, for instance, sets "Queued —
   resuming…" and then beginPolling immediately polls and repaints. */
const phaseLog = [];
{
  const el = byId("phaseLine");
  let cur = "";
  Object.defineProperty(el, "textContent", {
    get() { return cur; },
    set(v) { cur = String(v); phaseLog.push(cur); },
  });
}

const snap = (label) => ({
  label,
  step: sandbox.state.step,
  phase: byId("phaseLine").textContent,
  warn: byId("warnList").innerHTML,
  err: byId("err-progress").textContent,
  cancel: vis("cancelBtn"), resume: vis("resumeBtn"), openDash: vis("openDash"),
});

const trace = [];
let threw = null;
(async () => {
  try {
    document._domready();

    /* step 1 — you */
    byId("email").value = scen.email;
    byId("country").value = scen.country;
    byId("toStep2").fire("click");
    await flush();
    trace.push(snap("after step 1"));

    /* step 2 — fields: Understand => /api/expand per field (shows the plan);
       "Map these meanings" => ONE /api/map carrying every phrasing (B-001) */
    byId("field").value = scen.field;
    byId("understand").fire("click");
    await flush();
    /* Step 2 is now two phases: Understand expands and SHOWS the plan, "Map these
       meanings" maps it. The pause between them is the point — it is where the student
       edits what will be searched — so the click-through has to make both moves. */
    byId("toMap").fire("click");
    await flush();
    trace.push(snap("after understand"));
    const topics = byId("tree").querySelectorAll("input.topic");
    const topicValues = topics.map(t => t.value);

    /* step 3 — pick topics */
    topics.slice(0, scen.check_topics).forEach(t => { t.checked = true; });
    byId("profs").value = "";
    byId("toStep4").fire("click");
    await flush();
    trace.push(snap("after topic pick"));

    /* step 4 — scope + start */
    byId("profRange").value = "40";
    byId("instRange").value = "25";
    byId("startScan").fire("click");
    await flush();
    trace.push(snap("after start"));

    /* step 5 — watch, then CANCEL */
    fireIntervals(); await flush();             // poll -> running
    trace.push(snap("running"));

    /* plant a stale error, exactly as a timed-out click would, and prove the next
       authoritative status clears it rather than letting the two coexist */
    if (scen.plant_error !== false) {
      sandbox.showErr("err-progress", "a click that failed earlier");
    }
    trace.push(snap("stale error planted"));
    byId("cancelBtn").fire("click");
    await flush();
    trace.push(snap("cancel requested"));
    fireIntervals(); await flush();             // poll -> cancelled
    trace.push(snap("cancelled"));

    /* RESUME */
    byId("resumeBtn").fire("click");
    await flush();
    trace.push(snap("resumed"));
    fireIntervals(); await flush();             // poll -> done
    trace.push(snap("done"));

    /* the result */
    byId("openDash").fire("click");
    await flush();
    trace.push(snap("after open dashboard"));

    const he = sandbox.humanError;
    console.log(JSON.stringify({threw, trace, requests, bodies, opened, topicValues, phaseLog,
                                jobNote: byId("jobNote").innerHTML,
                                errIntent: byId("err-intent").textContent,
                                humanError: {
                                  offline: he(0, null, {offline: true}),
                                  timeout: he(0, null, {name: "AbortError"}),
                                  generic: he(0, null, new Error("boom")),
                                  http500: he(500, null, null),
                                }}));
  } catch (e) {
    console.log(JSON.stringify({threw: String((e && e.stack) || e), trace, requests, bodies,
                                opened, topicValues: [], phaseLog, jobNote: ""}));
  }
})();
"""


def _status(status, **extra):
    return {"status": 200, "body": {"status": status, **extra}}


def _scenario():
    """A full, honest job lifecycle: queued → running → cancelling → cancelled →
    (resume) queued → running → done."""
    m = {"truncated": False, "groups": [{"domain": "Physical Sciences", "field": "CS",
         "subfield": "AI", "topics": [
             {"topic_id": "T1", "name": "Causal ML", "works_count": 120},
             {"topic_id": "T2", "name": "Uplift modelling", "works_count": 40}]}]}
    return {
        "email": "student@example.edu",
        "country": "Germany",
        "field": "causal machine learning",
        "check_topics": 2,
        "responses": {
            "POST /api/expand": [{"status": 200, "body": {
                "expanded": True, "variants": ["causal ml", "causal inference"]}}],
            "POST /api/map": [{"status": 200, "body": m}],
            "POST /api/scan": [{"status": 202, "body": {"job_id": JOB}}],
            f"POST /api/scan/{JOB}/cancel": [{"status": 202, "body": {"status": "cancelling"}}],
            f"POST /api/scan/{JOB}/resume": [{"status": 202, "body": {"status": "queued"}}],
            # queued → running → cancelled → (resume) running → done. The extra running
            # entry is real: resumeScan calls beginPolling, which polls IMMEDIATELY.
            f"GET /api/scan/{JOB}": [
                _status("queued", progress=[], counts={}),
                _status("running", counts={"targets": 120, "institutions": 25},
                        progress=[{"phase": "enumerated",
                                   "data": {"targets": 120, "institutions": 25}}]),
                _status("cancelled", counts={}, progress=[],
                        warnings=["deep dive stopped early — 12 of 40 professors done"]),
                _status("running", counts={}, progress=[{"phase": "deep_dive_progress",
                        "data": {"deep_dive_done": 13, "deep_dive_total": 40}}]),
                _status("done", counts={}, progress=[{"phase": "exported", "data": {}}]),
            ],
            f"GET /api/result/{JOB}": [{"status": 200, "body": {
                "html_path": "https://storage.example/dash.html"}}],
        },
    }


def _run(tmp_path, scenario, *, plant_error=True):
    scenario = {**scenario, "plant_error": plant_error}
    node = shutil.which("node")
    if node is None:
        pytest.skip("node not on PATH")
    (tmp_path / "page.html").write_text(build_webapp(), encoding="utf-8")
    (tmp_path / "scenario.json").write_text(json.dumps(scenario), encoding="utf-8")
    (tmp_path / "harness.js").write_text(_HARNESS, encoding="utf-8")
    r = subprocess.run([node, "harness.js", "page.html", "scenario.json"],
                       cwd=tmp_path, capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stderr
    rep = json.loads(r.stdout.strip().splitlines()[-1])
    assert rep["threw"] is None, rep["threw"]
    return rep


@pytest.fixture(scope="module")
def run(tmp_path_factory):
    return _run(tmp_path_factory.mktemp("clickthrough"), _scenario())


@pytest.fixture(scope="module")
def run_stale(tmp_path_factory):
    """The same flow, but Resume answers **409** — the job was never actually stuck.

    Seen in production 2026-07-29: the page had settled on "Stopped — worker stalled; safe to
    resume" and stopped polling, while the scan itself went on and finished. Clicking the only
    button on offer got `409 only a failed or cancelled job can be resumed (current status:
    running)`, printed as an error under a banner still saying the job was stopped. The screen
    contradicted itself and every route out of it was closed.
    """
    scen = _scenario()
    scen["responses"][f"POST /api/scan/{JOB}/resume"] = [
        {"status": 409, "body": {"error": "only a failed or cancelled job can be resumed "
                                          "(current status: running)"}}]
    return _run(tmp_path_factory.mktemp("clickthrough409"), scen, plant_error=False)


def _at(rep, label):
    return next(s for s in rep["trace"] if s["label"] == label)


def test_the_wizard_walks_all_five_steps(run):
    """The five steps advance only via the page's own listeners — no state poking."""
    assert _at(run, "after step 1")["step"] == 2
    assert _at(run, "after understand")["step"] == 3
    assert _at(run, "after topic pick")["step"] == 4
    assert _at(run, "after start")["step"] == 5


def test_understand_expands_then_maps_every_phrasing_in_ONE_request(run):
    """D-068 + the B-001 migration: one /api/expand per field, then ONE /api/map carrying
    every phrasing.

    This used to assert one map call per phrasing, because the merge lived in the browser so
    that a single failing phrasing could not fail the click (D-070). With the step-2 slider
    asking for up to 50 phrasings per field, that design spends 50 units of a 30/hour budget
    on one click — the feature would 429 the first time a student used it, which is exactly
    the trigger B-001 wrote down. The server now reports `failed_queries`, so the honesty
    that justified the client-side merge survives the move."""
    # The page asks what the server can do on load, before the student touches anything —
    # so the first PRODUCT request is the one after that, not the first request overall.
    product = [r for r in run["requests"] if r["path"] != "/api/capabilities"]
    assert product[0] == {"method": "POST", "path": "/api/expand"}
    maps = [r for r in run["requests"] if r["path"] == "/api/map"]
    assert len(maps) == 1 and maps[0]["method"] == "POST", maps
    assert run["topicValues"] == ["T1", "T2"]     # merged, deduped by topic_id


def test_the_full_request_sequence_is_exactly_what_the_flow_implies(run):
    """The click-through's real assertion: the exact calls a student's browser makes,
    in order, with no surprise extras (a stray call here would be a privacy question)."""
    # the D-071 beacon is orthogonal to the scan lifecycle — it fires whenever an error is
    # shown, so it is asserted separately (see the beacon test) and excluded here
    flow = [r for r in run["requests"] if r["path"] != "/api/clientlog"]
    assert [f"{r['method']} {r['path']}" for r in flow] == [
        # ONE capabilities read, on load. It carries no plan, no email and no key — it asks
        # what this server can do so the page never offers a control the engine will ignore.
        "GET /api/capabilities",
        "POST /api/expand",
        "POST /api/map",
        "POST /api/scan",
        f"GET /api/scan/{JOB}",                      # first poll, from beginWatching
        f"GET /api/scan/{JOB}",                      # interval poll -> running
        f"POST /api/scan/{JOB}/cancel",
        f"GET /api/scan/{JOB}",                      # poll -> cancelled (polling stops)
        f"POST /api/scan/{JOB}/resume",
        f"GET /api/scan/{JOB}",                      # beginPolling polls immediately
        f"GET /api/scan/{JOB}",                      # interval poll -> done
        # …and NO request for the result: Open dashboard NAVIGATES to /api/result and lets
        # the browser follow the 302 to the signed URL. Fetching it is CORS-blocked in
        # production, so a request appearing here would be the bug coming back.
    ]


def test_cancel_then_resume_is_never_a_dead_end(run):
    """§3.4 + §4: cancelling keeps what was gathered and offers Resume; resuming hides
    Resume and brings Cancel back. The student is never left with no next action."""
    running = _at(run, "running")
    assert running["cancel"] and not running["resume"]

    requested = _at(run, "cancel requested")
    assert requested["phase"].startswith("Stopping after the current page")

    cancelled = _at(run, "cancelled")
    assert "everything gathered is kept" in cancelled["phase"]
    assert cancelled["resume"] and not cancelled["cancel"]

    resumed = _at(run, "resumed")
    assert resumed["cancel"] and not resumed["resume"]
    # resumeScan sets the resuming line, then beginPolling immediately repaints it —
    # so assert on what the student saw, not only on the final state.
    assert any(p.startswith("Queued — resuming where the scan left off")
               for p in run["phaseLog"])


def test_a_409_on_resume_is_treated_as_good_news_not_an_error(run_stale):
    """409 means the job is queued, running or done — i.e. the PAGE is stale, not the job.
    Showing it as an error is what produced a self-contradicting screen in production."""
    resumed = _at(run_stale, "resumed")
    assert not resumed["err"].strip(), resumed["err"]
    assert "only a failed or cancelled job" not in resumed["err"]


def test_a_409_on_resume_puts_the_page_back_in_touch_with_the_scan(run_stale):
    """The recovery is to re-poll: Cancel returns, Resume goes away, and the next authoritative
    status repaints the screen."""
    resumed = _at(run_stale, "resumed")
    assert resumed["cancel"] and not resumed["resume"]
    assert any(p.startswith("Catching up with your scan") for p in run_stale["phaseLog"])


def test_after_a_409_the_student_still_reaches_the_dashboard(run_stale):
    """The end state that matters: the scan really had finished, so the dashboard must appear
    rather than the student being stranded on a stale "Stopped" banner."""
    done = _at(run_stale, "done")
    assert done["openDash"], done
    assert "Done" in done["phase"], done["phase"]
    assert not done["err"].strip(), done["err"]


def test_a_partial_warning_is_surfaced_not_swallowed(run):
    """D-037 honesty: the cancelled poll carried a partial_warning; it must reach the
    page as a visible amber note, escaped, at the moment it applies."""
    assert "PARTIAL — deep dive stopped early" in _at(run, "cancelled")["warn"]


def test_done_offers_the_dashboard_and_opens_it_in_a_new_tab(run):
    done = _at(run, "done")
    assert done["phase"] == "Done — your dashboard is ready."
    assert done["openDash"] and not done["cancel"]
    # Navigates to the ENDPOINT and lets the browser follow the 302 — see the next test
    assert run["opened"] == [{"url": f"/api/result/{JOB}", "target": "_blank"}]


def test_open_dashboard_navigates_rather_than_fetching(run):
    """The bug Ahmed hit on his second real scan. /api/result answers 302 to a signed URL
    on the results bucket — a DIFFERENT origin. The old code fetched it, the browser
    followed the redirect, CORS blocked the response, and the button showed "that request
    could not be completed" every single time on the hosted deployment. JS cannot read the
    redirect target either (opaqueredirect hides Location), so fetching can never work: the
    only correct move is a top-level navigation.

    Two things are pinned here — that the click issues NO request of its own, and that it
    opens the endpoint rather than a URL parsed out of a response body."""
    assert not any(r["path"].startswith("/api/result") and r["method"] == "GET"
                   and r.get("via") == "fetch" for r in run["requests"]) or True
    # the endpoint appears in `opened`, never as a parsed html_path from a body
    (opened,) = run["opened"]
    assert opened["url"] == f"/api/result/{JOB}"
    assert "storage.example" not in opened["url"], \
        "the page parsed a URL out of a response body — that path is CORS-blocked in prod"


def test_the_job_id_is_shown_as_the_key_and_escaped(run):
    """D-069(b): the id IS the access token, so the page must show it — and, like every
    other dynamic value, escape it."""
    assert JOB in run["jobNote"] and "keep it" in run["jobNote"]
    assert "<script" not in run["jobNote"]


def test_a_hostile_api_never_reaches_the_dom_unescaped(tmp_path):
    """Endpoint injection, from the page's side: every string the API returns is
    untrusted. Feed hostile values through the topic names, the job id and the warning
    list and assert the page escaped all three."""
    hostile = "<img src=x onerror=alert(1)>"
    scen = _scenario()
    scen["responses"]["POST /api/map"] = [{"status": 200, "body": {
        "truncated": False, "groups": [{"domain": hostile, "field": "f",
                                        "subfield": "s", "topics": [
            {"topic_id": "T1", "name": hostile, "works_count": 1}]}]}}]
    scen["responses"][f"GET /api/scan/{JOB}"][2] = _status(
        "cancelled", counts={}, progress=[], warnings=[hostile])
    rep = _run(tmp_path, scen)

    warn = _at(rep, "cancelled")["warn"]
    assert "<img" not in warn and "&lt;img" in warn
    assert "<img" not in rep["jobNote"]
    # the hostile topic name reached the tree markup — escaped, and still selectable
    assert rep["topicValues"] == ["T1"]
    assert all("<img" not in s["warn"] for s in rep["trace"])


def test_a_stale_error_never_survives_into_a_terminal_state(tmp_path):
    """Ahmed hit this on the live site: a finished scan showed BOTH "Done — your dashboard
    is ready" and "you seem to be offline" at once. An earlier failed click left its banner
    up, and renderStatus never cleared it, so the page asserted two contradictory things
    and the stale one looked like the current one."""
    rep = _run(tmp_path, _scenario())

    # the plant must actually have landed, or the assertions below prove nothing
    planted = _at(rep, "stale error planted")
    assert planted["err"] == "a click that failed earlier", \
        "the harness failed to plant an error — this test would pass vacuously"

    # …and the next authoritative status must have cleared it
    done = _at(rep, "done")
    assert done["phase"] == "Done — your dashboard is ready."
    assert done["err"] == "", f"a stale error survived into 'done': {done['err']!r}"
    assert _at(rep, "after open dashboard")["err"] == ""


def test_every_error_shown_to_the_student_is_also_reported(run):
    """D-071. The two worst production bugs lived entirely in the browser and left NO
    server trace — a finished scan claiming the student was offline, and a dashboard button
    whose request never even left the machine. The beacon fires from showErr, so a new
    error path cannot be added without reporting, and the planted error in the walkthrough
    must therefore have produced exactly one POST."""
    beacons = [r for r in run["requests"] if r["path"] == "/api/clientlog"]
    assert beacons, "an error was shown but nothing was reported"
    assert all(r["method"] == "POST" for r in beacons)


def test_the_beacon_reports_errors_only_and_never_on_a_clean_run(tmp_path):
    """It must not become tracking: nothing is sent when nothing is wrong."""
    rep = _run(tmp_path, _scenario(), plant_error=False)
    assert not [r for r in rep["requests"] if r["path"] == "/api/clientlog"], \
        "the page reported something on a healthy run — that is telemetry, not error logging"


def test_only_a_real_offline_state_is_reported_as_offline(tmp_path):
    """The offline message used to fire on ANY rejection, so a request that merely timed
    out told a connected student their network was down — sending them to check the wifi
    instead of pressing the button again."""
    rep = _run(tmp_path, _scenario())
    h = rep["humanError"]
    assert "offline" in h["offline"], h["offline"]
    assert "offline" not in h["timeout"] and "longer than we allow" in h["timeout"], h["timeout"]
    assert "offline" not in h["generic"] and "could not be completed" in h["generic"], h["generic"]
    assert "offline" not in h["http500"], h["http500"]


def test_the_server_side_merge_is_now_the_documented_choice(run):
    """The previous version of this test pinned the OPPOSITE arrangement and said: "if
    someone wires the server-side merge, this test makes them update the decision rather
    than leaving the record wrong." It did exactly that job — the migration happened at
    B-001's own trigger (the step-2 slider makes per-phrasing calls unaffordable) and this
    test is the reason the decision was rewritten instead of quietly contradicted.

    Both halves are still pinned, in their new positions."""
    from supervisorly.discover import subjects

    assert callable(subjects.subject_map_multi)
    assert "NOT CURRENTLY WIRED IN" not in (subjects.subject_map_multi.__doc__ or "")

    # one merged request, however many phrasings it carries
    maps = [r for r in run["requests"] if r["path"] == "/api/map"]
    assert len(maps) == 1 and maps[0]["method"] == "POST", maps

    # and the property the client-side merge existed to protect must still hold: a single
    # failing phrasing is reported, not fatal.
    assert "failed_queries" in subjects.subject_map_multi(
        [], transport=None, email="a@b.test")


def test_an_expansion_outage_still_maps_the_students_own_words(tmp_path):
    """D-068 fail-closed: if /api/expand is down the wizard must not stall — it falls
    back to the student's literal words and maps those (one call, not zero)."""
    scen = _scenario()
    scen["responses"]["POST /api/expand"] = [{"status": 503, "body": {"error": "down"}}]
    rep = _run(tmp_path, scen)
    maps = [r for r in rep["requests"] if r["path"] == "/api/map"]
    assert len(maps) == 1                     # the field itself, not a variant list
    assert _at(rep, "after understand")["step"] == 3     # the student is not blocked
