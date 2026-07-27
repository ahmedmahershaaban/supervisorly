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
  const re = /<\/?(ul|li|label|input|span|div|button)(\s[^>]*)?\/?>|([^<]+)/g;
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
const intentRadios = radios("intent", ["pre_phd", "pre_master", "master", "phd",
                                       "postdoc", "mentor"], "phd");
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
    throw new Error("mini-DOM doc: unsupported selector " + sel);
  },
  querySelector: (sel) => {
    if (sel === 'input[name="intent"]:checked') return intentRadios.find(r => r.checked) ?? null;
    if (sel === 'input[name="uniMode"]:checked') return uniModeRadios.find(r => r.checked) ?? null;
    throw new Error("mini-DOM doc: unsupported selector " + sel);
  },
  addEventListener: (type, fn) => { if (type === "DOMContentLoaded") document._domready = fn; },
};

/* ── network: a scripted router that records every request ───────────────── */
const requests = [];
const queues = JSON.parse(JSON.stringify(scen.responses));
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

    /* step 2 — field: Understand => /api/expand then one /api/map per phrasing */
    byId("field").value = scen.field;
    byId("understand").fire("click");
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

    console.log(JSON.stringify({threw, trace, requests, opened, topicValues, phaseLog,
                                jobNote: byId("jobNote").innerHTML}));
  } catch (e) {
    console.log(JSON.stringify({threw: String((e && e.stack) || e), trace, requests,
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
            "GET /api/map": [{"status": 200, "body": m}],
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


def _run(tmp_path, scenario):
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


def _at(rep, label):
    return next(s for s in rep["trace"] if s["label"] == label)


def test_the_wizard_walks_all_five_steps(run):
    """The five steps advance only via the page's own listeners — no state poking."""
    assert _at(run, "after step 1")["step"] == 2
    assert _at(run, "after understand")["step"] == 3
    assert _at(run, "after topic pick")["step"] == 4
    assert _at(run, "after start")["step"] == 5


def test_understand_expands_once_then_maps_every_phrasing(run):
    """D-068: one /api/expand, then one /api/map per returned variant — the multi-query
    merge is client-side, so two phrasings must produce two map calls."""
    assert run["requests"][0] == {"method": "POST", "path": "/api/expand"}
    maps = [r for r in run["requests"] if r["path"] == "/api/map"]
    assert len(maps) == 2 and all(r["method"] == "GET" for r in maps)
    assert run["topicValues"] == ["T1", "T2"]     # merged, deduped by topic_id


def test_the_full_request_sequence_is_exactly_what_the_flow_implies(run):
    """The click-through's real assertion: the exact calls a student's browser makes,
    in order, with no surprise extras (a stray call here would be a privacy question)."""
    assert [f"{r['method']} {r['path']}" for r in run["requests"]] == [
        "POST /api/expand",
        "GET /api/map", "GET /api/map",
        "POST /api/scan",
        f"GET /api/scan/{JOB}",                      # first poll, from beginWatching
        f"GET /api/scan/{JOB}",                      # interval poll -> running
        f"POST /api/scan/{JOB}/cancel",
        f"GET /api/scan/{JOB}",                      # poll -> cancelled (polling stops)
        f"POST /api/scan/{JOB}/resume",
        f"GET /api/scan/{JOB}",                      # beginPolling polls immediately
        f"GET /api/scan/{JOB}",                      # interval poll -> done
        f"GET /api/result/{JOB}",
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


def test_a_partial_warning_is_surfaced_not_swallowed(run):
    """D-037 honesty: the cancelled poll carried a partial_warning; it must reach the
    page as a visible amber note, escaped, at the moment it applies."""
    assert "PARTIAL — deep dive stopped early" in _at(run, "cancelled")["warn"]


def test_done_offers_the_dashboard_and_opens_it_in_a_new_tab(run):
    done = _at(run, "done")
    assert done["phase"] == "Done — your dashboard is ready."
    assert done["openDash"] and not done["cancel"]
    assert run["opened"] == [{"url": "https://storage.example/dash.html",
                              "target": "_blank"}]


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
    scen["responses"]["GET /api/map"] = [{"status": 200, "body": {
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


def test_the_client_side_merge_is_the_documented_choice(run):
    """D-070 / BLOCKERS B-001: the merge lives in the page, and subject_map_multi is its
    unwired server-side counterpart. Pin BOTH halves so the divergence cannot quietly
    flip: if someone wires the server-side merge, this test makes them update the
    decision rather than leaving the record wrong."""
    from supervisorly.discover import subjects

    assert callable(subjects.subject_map_multi)
    assert "NOT CURRENTLY WIRED IN (D-070)" in subjects.subject_map_multi.__doc__

    # the page's behaviour is the load-bearing half: one map call per phrasing
    maps = [r for r in run["requests"] if r["path"] == "/api/map"]
    assert len(maps) == 2, "the page stopped merging client-side — D-070 needs revisiting"


def test_an_expansion_outage_still_maps_the_students_own_words(tmp_path):
    """D-068 fail-closed: if /api/expand is down the wizard must not stall — it falls
    back to the student's literal words and maps those (one call, not zero)."""
    scen = _scenario()
    scen["responses"]["POST /api/expand"] = [{"status": 503, "body": {"error": "down"}}]
    rep = _run(tmp_path, scen)
    maps = [r for r in rep["requests"] if r["path"] == "/api/map"]
    assert len(maps) == 1                     # the field itself, not a variant list
    assert _at(rep, "after understand")["step"] == 3     # the student is not blocked
