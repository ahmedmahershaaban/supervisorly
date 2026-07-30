"""Phase B4 (D-067) — the Scan Studio: a self-contained, offline, Atlas-language plan wizard
over a ``map-field`` subject map. Tests cover self-containment (no external requests),
injection-safety (hostile API strings), the tri-state checkbox tree + plan builder (structurally,
plus a node syntax check when node is on PATH), the honest truncation banner (D-037), the
``studio`` CLI (fail-loud map loading, D-005 --out guard), and the ``scan --plan`` wiring that
honours a Studio plan's own email + named-professor targets. No live network — cassettes only."""

import json
import re
import shutil
import subprocess

import pytest

from supervisorly import cli
from supervisorly.discover import openalex
from supervisorly.export.studio import build_studio
from supervisorly.fetch import transport as transport_mod
from supervisorly.fetch.transport import CassetteTransport

EMAIL = "me@uni.edu"


def _map(**over):
    smap = {"query": "causal ml", "truncated": False, "groups": [
        {"domain": "Physical Sciences", "field": "Computer Science",
         "subfield": "Artificial Intelligence", "topics": [
             {"topic_id": "T10001", "name": "Causal Machine Learning", "works_count": 12400},
             {"topic_id": "T10002", "name": "Graph Neural Networks", "works_count": 960}]},
        {"domain": "Physical Sciences", "field": "Physics",
         "subfield": "Statistical Physics", "topics": [
             {"topic_id": "T10003", "name": "Causal Inference", "works_count": 1100000}]},
    ]}
    smap.update(over)
    return smap


# ── self-containment (D-033/D-048) ───────────────────────────────────────────

def test_studio_is_self_contained_no_external_resources():
    html = build_studio(_map())
    assert "<!doctype html>" in html.lower()
    for bad in ("<link", "<script src", "@import", "url(", "fetch(",
                "XMLHttpRequest", "<img", "<iframe"):
        assert bad not in html, f"external-request vector present: {bad}"
    low = html.lower()
    assert "googleapis" not in low and "cdn" not in low
    # the Blob download is the one allowed "write" — and no alert() popups anywhere
    assert "Blob(" in html and "alert(" not in html


def test_atlas_tokens_and_type_present():
    html = build_studio(_map())
    assert "#05070c" in html                                   # base void
    assert "#e8b24a" in html                                   # amber accent
    for kind in ("#43c9d6", "#79d06a", "#f0839a", "#b58cf0", "#7d828e"):  # tissue palette
        assert kind in html
    assert "'Space Grotesk'" in html and "'Space Mono'" in html  # named with fallbacks, never imported
    assert "eyebrow" in html and "letter-spacing:.24em" in html  # Atlas eyebrow convention
    assert "SCAN STUDIO" in html.upper()


# ── injection safety ──────────────────────────────────────────────────────────

def test_hostile_map_strings_cannot_break_the_data_block():
    hostile = _map(
        query='closing </script><img src=x onerror=alert(1)>',
        groups=[{"domain": 'dom</script>', "field": 'field\u2028break',
                 "subfield": 'javascript:alert(1)',
                 "topics": [{"topic_id": 'T1</script><script>alert(2)</script>',
                             "name": '<img onerror=alert(3)>', "works_count": 5}]}])
    html = build_studio(hostile)
    assert html.count("</script>") == 1          # only the one closing data-block tag
    assert " " not in html and " " not in html   # no raw JS line separators U+2028/U+2029
    assert "</script><img" not in html           # the hostile sequence never survives raw
    assert "\\u003c" in html                     # every '<' neutralised instead
    # the escaped header copy may carry the hostile words as inert TEXT, but no raw tag
    # ever survives — only the \u003c-escaped (data) and &lt;-escaped (markup) forms
    assert "<img" not in html


def test_query_interpolated_into_the_header_is_escaped():
    html = build_studio(_map(query='x"><script>alert(1)</script>'))
    assert 'x"><script>' not in html
    assert "x&quot;&gt;" in html                 # html-escaped in the hero paragraph


def test_defaults_are_embedded_safely():
    html = build_studio(_map(), defaults={"country": "Canada", "email": EMAIL,
                                          "universities": ["McGill"], "intent_kind": "phd"})
    assert '"defaults"' in html and "Canada" in html and "McGill" in html
    hostile = build_studio(_map(), defaults={"country": '</script>x'})
    assert hostile.count("</script>") == 1


# ── tree, tri-state, plan builder (structural + node syntax) ─────────────────

def test_reduced_motion_and_keyboard_support_present():
    html = build_studio(_map())
    assert "prefers-reduced-motion:reduce" in html
    assert ":focus-visible" in html                      # visible focus ring
    assert 'type="checkbox"' in html and 'type="radio"' in html   # real form controls
    assert 'e.key==="Escape"' in html                    # Escape closes transient UI


def test_tri_state_checkbox_logic_present():
    html = build_studio(_map())
    assert "indeterminate" in html
    assert "refreshTree" in html
    # checking a parent cascades to every descendant topic checkbox
    assert 'querySelectorAll("input.topic")' in html


def test_plan_builder_exists_with_the_full_plan_shape():
    html = build_studio(_map())
    assert "function buildPlan()" in html
    for key in ("intent_kind", "country", "field", "resolved_topic_ids",
                "university_mode", "universities", "targets", "email"):
        assert key in html, f"plan key missing: {key}"
    # the download + the exact next command
    assert "supervisorly_plan.json" in html
    assert "supervisorly scan --plan supervisorly_plan.json --out output/live.html" in html


def test_embedded_js_parses_under_node_when_available(tmp_path):
    node = shutil.which("node")
    if node is None:
        pytest.skip("node not on PATH")
    html = build_studio(_map())
    js = html.split("<script>", 1)[1].rsplit("</script>", 1)[0]
    f = tmp_path / "studio.js"
    f.write_text(js, encoding="utf-8")
    r = subprocess.run([node, "--check", str(f)], capture_output=True)
    assert r.returncode == 0, r.stderr.decode("utf-8", "replace")


# ── honesty: truncation banner (D-037) ────────────────────────────────────────

def test_truncation_banner_rendered_only_when_partial():
    partial = build_studio(_map(truncated=True))
    assert "PARTIAL MAP" in partial and "more topics than shown" in partial
    complete = build_studio(_map(truncated=False))
    assert "PARTIAL MAP" not in complete


def test_empty_map_is_an_honest_empty_tree_not_a_crash():
    html = build_studio({"query": "nothing", "groups": [], "truncated": False})
    assert "subject map is empty" in html
    assert build_studio({}).count("</script>") == 1      # even a malformed map degrades honestly


# ── CLI: studio ───────────────────────────────────────────────────────────────

def _write_map(tmp_path, smap=None):
    p = tmp_path / "subject_map.json"
    p.write_text(json.dumps(smap if smap is not None else _map()), encoding="utf-8")
    return p


def test_studio_cli_missing_map_fails_loud(tmp_path, capsys):
    rc = cli.main(["studio", "--map", str(tmp_path / "nope.json"),
                   "--out", str(tmp_path / "s.html")])
    assert rc == 2
    assert "subject map not found" in capsys.readouterr().out


def test_studio_cli_invalid_json_and_wrong_shape_fail_loud(tmp_path, capsys):
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    rc = cli.main(["studio", "--map", str(bad), "--out", str(tmp_path / "s.html")])
    assert rc == 2 and "invalid subject-map JSON" in capsys.readouterr().out

    wrong = tmp_path / "wrong.json"
    wrong.write_text(json.dumps({"topics": []}), encoding="utf-8")
    rc = cli.main(["studio", "--map", str(wrong), "--out", str(tmp_path / "s.html")])
    assert rc == 2 and "not a subject map" in capsys.readouterr().out


def test_studio_cli_writes_the_html_and_an_ascii_line(tmp_path, capsys):
    out = tmp_path / "out" / "studio.html"
    rc = cli.main(["studio", "--map", str(_write_map(tmp_path)), "--out", str(out)])
    assert rc == 0
    printed = capsys.readouterr().out
    assert "studio wrote 3 topics in 2 groups" in printed and printed.isascii()
    html = out.read_text(encoding="utf-8")
    assert "<!doctype html>" in html.lower() and "SCAN STUDIO" in html.upper()


def test_studio_out_inside_repo_and_not_ignored_warns(tmp_path, capsys):
    """The D-005 guard applies to `studio --out` exactly like `scan --out` (mirrors test_cli)."""
    if shutil.which("git") is None:
        pytest.skip("git binary not available")
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True, capture_output=True)
    (repo / ".gitignore").write_text("/output/\n", encoding="utf-8")
    out = repo / "results" / "studio.html"
    rc = cli.main(["studio", "--map", str(_write_map(tmp_path)), "--out", str(out)])
    assert rc == 0 and out.exists()                      # warns, never refuses
    err = capsys.readouterr().err
    assert "D-005" in err and "git-ignored" in err


# ── scan --plan honours a Studio plan's email + targets ──────────────────────

def _targets_cassette():
    tp = CassetteTransport()
    tp.record(openalex.author_search_url("Ada Maple", EMAIL), 200, json.dumps({"results": [
        {"id": "https://openalex.org/A100", "display_name": "Dr. Ada Maple", "works_count": 30,
         "cited_by_count": 500, "topics": [],
         "last_known_institutions": [{"id": "https://openalex.org/I100",
                                      "display_name": "Maple University"}],
         "homepage_url": "https://maple.example/~ada"}]}))
    tp.record("https://maple.example/robots.txt", 200, "User-agent: *\nAllow: /\n")
    tp.record("https://maple.example/~ada", 200,
              "<html><body><main><p>I am recruiting a PhD student for 2027.</p></main></body></html>")
    return tp


def _studio_plan(tmp_path, **over):
    plan = {"intent_kind": "phd", "country": "", "field": "", "resolved_topic_ids": [],
            "university_mode": "all", "universities": [], "email": EMAIL,
            "targets": [{"name": "Ada Maple", "affiliation": "Maple University"}]}
    plan.update(over)
    p = tmp_path / "supervisorly_plan.json"
    p.write_text(json.dumps(plan), encoding="utf-8")
    return p


def test_scan_plan_uses_the_plans_email_and_targets(tmp_path, monkeypatch, capsys):
    # a Studio-exported plan is self-sufficient: no --email, no --targets, no country needed
    monkeypatch.setattr(transport_mod, "httpx_transport", lambda **kw: _targets_cassette())
    out = tmp_path / "out" / "live.html"
    rc = cli.main(["scan", "--plan", str(_studio_plan(tmp_path)), "--out", str(out)])
    assert rc == 0
    printed = capsys.readouterr().out
    assert "scanned 1 professors (live)" in printed and printed.isascii()
    export = json.loads(out.with_suffix(".json").read_text(encoding="utf-8"))
    assert export["professors"][0]["name"] == "Dr. Ada Maple"


def test_scan_plan_invalid_targets_entry_fails_loud(tmp_path, capsys):
    rc = cli.main(["scan", "--plan", str(_studio_plan(tmp_path, targets={"name": "x"})),
                   "--out", str(tmp_path / "d.html")])
    assert rc == 2
    assert "invalid 'targets'" in capsys.readouterr().out


# ── B6 audit (Wave C) regression tests ───────────────────────────────────────

def _embedded_data(html):
    """The plan-wizard DATA block, decoded back to a dict."""
    m = re.search(r"const DATA = (\{.*?\});\r?\n", html, re.S)
    assert m, "DATA block not found"
    return json.loads(m.group(1))


def test_scroll_into_view_honours_reduced_motion():              # U1
    html = build_studio(_map())
    assert 'matchMedia("(prefers-reduced-motion:reduce)")' in html
    assert 'behavior:_rm?"auto":"smooth"' in html       # gated, never unconditional
    assert '{behavior:"smooth"' not in html


def test_focus_ring_painted_on_intent_card_not_hidden_input():   # U2
    html = build_studio(_map())
    # the intent radios are opacity:0 — the :focus-visible indicator must land on the card
    assert ".rcard:has(input:focus-visible){outline:2px solid var(--focus)" in html


def test_malformed_topics_sanitized_python_side():               # U3a + U6
    html = build_studio(_map(groups=[
        {"domain": "d", "field": "f", "subfield": "s", "topics": "nope"},
        {"domain": "d", "field": "f", "subfield": "s", "topics": [
            None, {"name": "no id"}, {"topic_id": "", "name": "empty id"},
            {"topic_id": "T1", "name": "ok", "works_count": 3}]},
    ]))
    assert html.count("</script>") == 1                            # page still generated
    groups = _embedded_data(html)["groups"]
    assert groups[0]["topics"] == []                               # non-list coerced away
    assert [t["topic_id"] for t in groups[1]["topics"]] == ["T1"]  # malformed entries skipped


def test_hostile_intent_kind_default_falls_back_python_side():   # U4
    html = build_studio(_map(), defaults={"intent_kind": 'x"]'})
    assert _embedded_data(html)["defaults"]["intent_kind"] == "pre_phd"
    ok = build_studio(_map(), defaults={"intent_kind": "phd"})
    assert _embedded_data(ok)["defaults"]["intent_kind"] == "phd"  # valid values untouched


# Node-executed init, extending the probe_tree.js technique: the REAL embedded JS runs
# against a minimal DOM and reports whether the wiring survived and what the tree holds.
_NODE_HARNESS = r"""
"use strict";
const fs = require("fs");
const [htmlPath, scenPath] = process.argv.slice(2);
const html = fs.readFileSync(htmlPath, "utf8");
const scen = JSON.parse(fs.readFileSync(scenPath, "utf8"));
const scriptSrc = html.split("<script>", 2)[1].split("</script>", 1)[0];

class El {
  constructor(tag) {
    this.tag = tag; this.children = []; this.parent = null;
    this.attrs = {}; this.listeners = {};
    this.checked = false; this.indeterminate = false; this.value = "";
    this.textContent = ""; this.style = {};
    const self = this;
    this.classList = {
      contains: (c) => (self.attrs.class || "").split(/\s+/).includes(c),
      add: (c) => { const s = new Set((self.attrs.class || "").split(/\s+/).filter(Boolean));
        s.add(c); self.attrs.class = [...s].join(" "); },
      remove: (c) => { const s = new Set((self.attrs.class || "").split(/\s+/).filter(Boolean));
        s.delete(c); self.attrs.class = [...s].join(" "); },
    };
  }
  getAttribute(n) { return this.attrs[n] ?? null; }
  closest(tag) { let e = this.parent; while (e) { if (e.tag === tag) return e; e = e.parent; } return null; }
  _walk(out) { for (const c of this.children) { out.push(c); c._walk(out); } return out; }
  querySelectorAll(sel) {
    const all = this._walk([]);
    const m = sel.match(/^input\.(\w+)$/);
    if (m) return all.filter(e => e.tag === "input" && e.classList.contains(m[1]));
    const mc = sel.match(/^input\.(\w+):checked$/);
    if (mc) return all.filter(e => e.tag === "input" && e.classList.contains(mc[1]) && e.checked);
    if (sel === "button[data-uni]") return all.filter(e => e.tag === "button" && "data-uni" in e.attrs);
    throw new Error("mini-DOM: unsupported selector " + sel);
  }
  addEventListener(type, fn) { (this.listeners[type] ||= []).push(fn); }
  focus() { this.focused = true; }
}

function parseTree(markup) {
  const root = new El("div");
  const stack = [root];
  const re = /<\/?(ul|li|label|input|span|div)(\s[^>]*)?\/?>|([^<]+)/g;
  let m;
  while ((m = re.exec(markup))) {
    const [, tag, attrs, text] = m;
    if (text !== undefined) continue;
    if (m[0].startsWith("</")) { stack.pop(); continue; }
    const el = new El(tag);
    if (attrs) for (const am of attrs.matchAll(/([\w-]+)="([^"]*)"/g))
      el.attrs[am[1]] = am[2].replace(/&quot;/g, '"').replace(/&amp;/g, "&")
        .replace(/&lt;/g, "<").replace(/&gt;/g, ">");
    if (tag === "input") { el.value = el.attrs.value ?? ""; el.indeterminate = false; }
    stack[stack.length - 1].children.push(el); el.parent = stack[stack.length - 1];
    if (tag !== "input") stack.push(el);
  }
  return root;
}

const treeHost = new El("div"); treeHost.attrs.id = "tree";
let treeMarkup = "";
Object.defineProperty(treeHost, "innerHTML", {
  set(v) { treeMarkup = v; const parsed = parseTree(v); treeHost.children = parsed.children;
    for (const c of treeHost.children) c.parent = treeHost; },
  get() { return treeMarkup; },
});
const ids = {};
for (const id of ["country", "email", "uniInput", "uniAdd", "export", "copybtn",
                  "done", "toast", "progress", "nextcmd", "profs",
                  "err-country", "err-topics", "err-profs", "err-email",
                  "step-country", "step-topics", "step-profs", "step-email", "uniChips"])
  ids[id] = new El("div");
ids.country.value = ""; ids.email.value = ""; ids.profs.value = ""; ids.uniInput.value = "";
const intentRadios = ["pre_phd", "pre_master", "master", "phd", "postdoc", "mentor"]
  .map(v => { const r = new El("input"); r.attrs.name = "intent"; r.value = v;
    r.checked = v === "pre_phd"; return r; });

const document = {
  documentElement: { scrollTop: 0, scrollHeight: 1, clientHeight: 1 },
  getElementById: (id) => id === "tree" ? treeHost : (ids[id] ?? null),
  querySelectorAll: (sel) => {
    if (sel.startsWith("#tree ")) return treeHost.querySelectorAll(sel.slice(6));
    if (sel === ".err" || sel === ".step.bad") return [];
    throw new Error("mini-DOM doc: unsupported selector " + sel);
  },
  querySelector: (sel) => {
    if (sel === 'input[name="uniMode"]:checked') { const r = new El("input"); r.value = "all"; return r; }
    if (sel === 'input[name="intent"]:checked') return intentRadios.find(r => r.checked) ?? null;
    const m = sel.match(/^input\[name="intent"\]\[value="((?:[^"\\]|\\.)*)"\](.*)$/);
    if (!m || m[2] !== "") { // malformed selector — browsers throw SyntaxError
      const err = new Error(`'${sel}' is not a valid selector`);
      err.name = "SyntaxError"; throw err;
    }
    return intentRadios.find(r => r.value === m[1]) ?? null;
  },
  createElement: (t) => new El(t),
  body: new El("body"),
  addEventListener: (type, fn) => { document._domready = type === "DOMContentLoaded" ? fn : document._domready; },
};
const DATA = scen.DATA ?? JSON.parse(scriptSrc.match(/const DATA = (\{.*?\});\r?\n/s)[1]);
const sandbox = { document, DATA, window: { addEventListener() {} },
  navigator: {}, URL: { createObjectURL: () => "blob:x", revokeObjectURL() {} },
  Blob: function () {}, setTimeout: (fn) => 0, clearTimeout: () => {}, console };
sandbox.window.document = document;

const vm = require("vm");
vm.createContext(sandbox);
const js = scriptSrc.replace(/const DATA = \{.*?\};\r?\n/s, "");
vm.runInContext(js, sandbox);
let threw = null;
try { document._domready(); } catch (e) { threw = String(e && e.message || e); }
const wired = (el, t) => (el.listeners[t] || []).length > 0;
console.log(JSON.stringify({
  threw,
  exportWired: wired(ids.export, "click"),
  uniAddWired: wired(ids.uniAdd, "click"),
  copyWired: wired(ids.copybtn, "click"),
  topicValues: treeHost.querySelectorAll("input.topic").map(b => b.value),
  checkedIntent: (intentRadios.find(r => r.checked) || {}).value || null,
  parseProfs: scen.profs == null ? null : sandbox.parseProfs(scen.profs),
}));
"""


def _run_studio_js(tmp_path, html, scenario):
    """Run the embedded studio JS through the node mini-DOM; returns the report dict."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("node not on PATH")
    (tmp_path / "page.html").write_text(html, encoding="utf-8")
    (tmp_path / "scenario.json").write_text(json.dumps(scenario), encoding="utf-8")
    (tmp_path / "harness.js").write_text(_NODE_HARNESS, encoding="utf-8")
    # UTF-8, not the ANSI code page — the harness echoes page HTML back and cp1252 cannot
    # decode a typographic quote, which kills the reader thread and nulls stdout (see the
    # same note in test_multi_intent.py).
    r = subprocess.run([node, "harness.js", "page.html", "scenario.json"],
                       cwd=tmp_path, capture_output=True,
                       encoding="utf-8", errors="replace")
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout.strip().splitlines()[-1])


@pytest.mark.parametrize("topics", ["nope", [None], [{"name": "no id"}]])
def test_malformed_map_never_bricks_the_wizard(tmp_path, topics):   # U3
    groups = [{"domain": "d", "field": "f", "subfield": "s", "topics": topics}]
    # (a) through build_studio: Python sanitizes, the page generates, init wires up
    rep = _run_studio_js(tmp_path, build_studio(
        {"query": "q", "truncated": False, "groups": groups}), {})
    assert rep["threw"] is None
    assert rep["exportWired"] and rep["uniAddWired"] and rep["copyWired"]
    assert rep["topicValues"] == []                       # malformed entries skipped
    # (b) raw malformed entries straight into the JS (bypassing the Python guard)
    rep = _run_studio_js(tmp_path, build_studio(_map()), {"DATA": {
        "query": "q", "truncated": False, "defaults": {}, "groups": groups}})
    assert rep["threw"] is None
    assert rep["exportWired"] and rep["uniAddWired"] and rep["copyWired"]
    assert rep["topicValues"] == []


def test_hostile_intent_default_leaves_the_page_wired(tmp_path):    # U4
    html = build_studio(_map(), defaults={"intent_kind": 'x"]'})
    rep = _run_studio_js(tmp_path, html, {})
    assert rep["threw"] is None
    assert rep["exportWired"] and rep["copyWired"]
    assert rep["checkedIntent"] == "pre_phd"              # fell back to the CLI default


def test_parse_profs_splits_on_the_last_comma(tmp_path):            # U5
    rep = _run_studio_js(tmp_path, build_studio(_map()), {"profs":
        "Ada Maple, McGill University\nMartin Luther King, Jr., MIT\n"
        "Hopper, Grace, Yale\n  , MIT\nSolo Name"})
    assert rep["parseProfs"] == [
        {"name": "Ada Maple", "affiliation": "McGill University"},
        {"name": "Martin Luther King, Jr.", "affiliation": "MIT"},
        {"name": "Hopper, Grace", "affiliation": "Yale"},
        {"name": "Solo Name"},
    ]


def test_topic_without_id_never_renders_a_checkbox(tmp_path):       # U6
    rep = _run_studio_js(tmp_path, build_studio(_map()), {"DATA": {
        "query": "q", "truncated": False, "defaults": {}, "groups": [
            {"domain": "d", "field": "f", "subfield": "s", "topics": [
                {"name": "no id"}, {"topic_id": "", "name": "empty id"},
                {"topic_id": "T1", "name": "ok", "works_count": 3}]}]}})
    assert rep["threw"] is None
    assert rep["topicValues"] == ["T1"]                   # id-less topics never render
