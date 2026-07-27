"""Plan step 5 (D-069) — the Supervisorly web app: ONE dynamic Atlas page, the Scan
Studio's dynamic sibling. Tests cover self-containment EXCEPT the api_base fetches (the
only fetch() targets are the endpoint paths), api_base injection ("" default, deploy
placeholder passes through), injection-safety (the esc() discipline over every API
string), all five wizard steps with the plan's §4.1 phase text verbatim, the bar-math
constants, sliders + defaults + caps + cost preview, cancel/resume, the §4.2 slow state,
the 4 s poll + lost-contact job-id recovery, and the error states (OpenAlex 429 ->
midnight UTC, offline, expansion-off). The embedded JS gets a node --check plus a small
vm harness asserting the client-side merge dedupes by topic_id and the bar percent math.
No live network."""

import json
import re
import shutil
import subprocess

import pytest

from supervisorly.export.webapp import INTENTS, build_webapp


def _norm(html):
    """Collapse whitespace so multi-line HTML copy can be asserted as one string."""
    return re.sub(r"\s+", " ", html)


def _js(html):
    return html.split("<script>", 1)[1].rsplit("</script>", 1)[0]


# ── document shape + api_base injection ──────────────────────────────────────

def test_build_webapp_returns_one_html_document():
    html = build_webapp()
    assert html.lower().startswith("<!doctype html>")
    assert "<title>Supervisorly" in html
    assert html.count("</script>") == 1 and html.count("<style>") == 1
    assert 'const API_BASE = "";' in html              # "" = same-origin (local dev / rewrite)


def test_api_base_injection_default_and_placeholder():
    assert 'const API_BASE = "";' in build_webapp()
    hosted = build_webapp(api_base="<API_BASE_URL>")
    assert 'const API_BASE = "<API_BASE_URL>";' in hosted     # placeholder passes through
    real = build_webapp(api_base="https://example.functions.app")
    assert 'const API_BASE = "https://example.functions.app";' in real


# ── self-containment: ONLY the api_base fetches may leave the page ────────────

def test_self_contained_except_api_fetches():
    html = build_webapp(api_base="<API_BASE_URL>")
    for bad in ("<link", "<script src", "@import", "url(", "<img", "<iframe",
                "XMLHttpRequest", "googleapis", "cdn", "alert("):
        assert bad not in html, f"external-request vector present: {bad}"
    # D-069: MAY fetch the API, but nothing is ever persisted client-side
    assert "fetch(" in html
    assert "localStorage" not in html and "sessionStorage" not in html
    assert "document.cookie" not in html


def test_only_fetch_targets_are_the_endpoint_paths():
    js = _js(build_webapp())
    # one call site, always on a variable built by api() — never a literal URL
    assert re.findall(r"fetch\((\w+)", js) == ["url"]
    paths = set(re.findall(r'api\("([^"]+)"', js))
    assert paths == {"/api/expand", "/api/map", "/api/scan", "/api/scan/", "/api/result/"}
    # dynamic ids are concatenated onto the scan/result prefixes only
    assert '"/api/scan/"+state.jobId' in js
    assert '"/api/result/"+state.jobId' in js
    assert '"/api/scan/"+state.jobId+"/cancel"' in js
    assert '"/api/scan/"+state.jobId+"/resume"' in js


# ── Atlas language + accessibility ───────────────────────────────────────────

def test_atlas_tokens_and_type_present():
    html = build_webapp()
    assert "#05070c" in html                                   # base void
    assert "#e8b24a" in html                                   # amber accent
    for kind in ("#43c9d6", "#79d06a", "#f0839a", "#b58cf0", "#7d828e"):
        assert kind in html                                    # tissue palette
    assert "'Space Grotesk'" in html and "'Space Mono'" in html  # named, never imported
    assert "eyebrow" in html and "letter-spacing:.24em" in html


def test_reduced_motion_keyboard_escape():
    html = build_webapp()
    assert "prefers-reduced-motion:reduce" in html
    assert ":focus-visible" in html                            # visible focus ring
    assert 'e.key==="Escape"' in html                          # Escape closes transient UI
    assert 'type="checkbox"' in html and 'type="radio"' in html  # real form controls
    assert "indeterminate" in html                             # tri-state parents


# ── the five steps ────────────────────────────────────────────────────────────

def test_five_steps_and_step_rail_present():
    html = _norm(build_webapp())
    for n in range(1, 6):
        assert f'id="s{n}"' in html
        assert f'data-step="{n}"' in html
    for label in ("You", "Field", "Disambiguate", "Scope &amp; scan", "Progress"):
        assert label in html
    # step 1: email, the 7 intents, country, universities + mode, max_institutions
    assert 'type="email" id="email"' in html
    assert len(INTENTS) == 7
    for key, _, _ in INTENTS:
        assert f'value="{key}"' in html
    for mode in ("all", "prioritise", "only"):
        assert f'value="{mode}"' in html
    assert 'id="maxInst" min="1" max="300"' in html


def test_phase_text_strings_verbatim():
    js = _js(build_webapp())
    assert '"Understanding your field…"' in js
    assert '"Reading professor pages — "' in js
    assert '"Finding universities and researchers in "' in js
    assert '"Ranking researchers and universities…"' in js
    assert '"Building your dashboard…"' in js
    assert '" topic areas for you to pick from."' in js
    assert '" institutions — picking the best matches."' in js
    assert '" pages need the slower path — filling what we can…"' in js
    assert '"Reading the pages of the top "' in js


def test_bar_math_constants():
    js = _js(build_webapp())
    assert "discovery 0–30%, deep-dive 30–90%" in js and "90–100%" in js
    assert "Math.min(90, Math.round(30 + 60*i/c.deep_dive_total))" in js
    assert 'if(c.targets!=null) return 30;' in js
    assert 'if(status==="done") return 100;' in js
    assert "return null;" in js          # indeterminate pulse before the first count


def test_sliders_defaults_caps_and_cost_preview():
    html = build_webapp()
    assert 'id="instRange" min="1" max="300" value="25"' in html
    assert 'id="profRange" min="1" max="200" value="40"' in html
    assert "≈ 25 institutions + 40 professors ≈ 8–11 minutes" in _norm(html)
    js = _js(html)
    assert '"≈ "+i+" institutions + "+s+" professors ≈ "' in js
    # §4.3 estimate: discovery 2–5 min + 1.5 min per 10 professors, a range
    assert "Math.round(2 + 1.5*shortlist/10)" in js
    assert "Math.round(5 + 1.5*shortlist/10)" in js


def test_review_card_and_start_scan():
    html = _norm(build_webapp())
    assert 'id="review"' in html and 'id="startScan"' in html
    js = _js(build_webapp())
    for row in ("email", "intent", "country", "universities", "topics",
                "named professors", "institutions to scan", "professors to deep-dive"):
        assert f'["{row}"' in js
    # double-click safe: the button disables instantly; 200 existing:true -> progress
    assert "btn.disabled = true;" in js
    assert '(r.status===202 || r.status===200) && r.body && r.body.job_id' in js
    # 429 -> the one-active-job message, button re-enabled
    assert "you already have an active scan job" in js


def test_cancel_resume_open_dashboard():
    html = _norm(build_webapp())
    assert 'id="cancelBtn"' in html and 'id="resumeBtn"' in html and 'id="openDash"' in html
    assert ("cancel stops after the current page and keeps everything gathered"
            in html)
    js = _js(build_webapp())
    assert '"/cancel"' in js and '"/resume"' in js
    assert 'window.open(String(target), "_blank", "noopener")' in js   # NEW TAB
    assert "only a failed or cancelled job can be resumed" not in js   # server-side copy
    assert "Resume continues where it left off." in js


def test_slow_state_thresholds_and_notice():
    html = _norm(build_webapp())
    assert ("This is taking longer than usual — the source sites are slow today. "
            "You can keep waiting, or pause and resume later, or cancel and keep "
            "what we have.") in html
    assert 'id="slowWait"' in html and 'id="slowPause"' in html and 'id="slowCancel"' in html
    js = _js(build_webapp())
    assert "var SLOW_DISCOVERY_S = 300;" in js       # discovery ~5 min soft expectation
    assert "var SLOW_PER10_S = 90;" in js            # 1.5 min per 10 professors
    assert "var SLOW_FACTOR = 1.5;" in js            # past 1.5x soft -> calm notice
    assert "state.phaseEnter" in js                  # phase-enter tracked client-side


def test_polling_interval_and_lost_contact_recovery():
    html = _norm(build_webapp())
    js = _js(html)
    assert "var POLL_MS = 4000;" in js               # poll every 4 s
    assert "var LOST_AFTER_MS = 120000;" in js       # >2 min of consecutive poll errors
    assert "setInterval(poll, POLL_MS)" in js
    assert "stopPolling()" in js                     # terminal status stops polling
    assert ("Your job id is <span class=\"jobid\" id=\"lostJobId\"></span>; "
            "paste it later to resume watching.") in html
    assert 'id="resumeId"' in html and 'id="resumeIdBtn"' in html   # resume-by-id input


def test_error_states_offline_openalex429_expansion_off():
    html = _norm(build_webapp())
    assert "smart expansion is off — using your words directly." in html
    js = _js(html)
    assert "midnight UTC" in js                       # OpenAlex 429 -> honest 503 copy
    assert "navigator.onLine === false" in js         # offline detection
    assert "you seem to be offline — nothing was lost; your place is kept." in js
    assert 'state.expansionOff = true; return [f];' in js   # deterministic fallback
    assert "PARTIAL — " in js                         # inline amber partial_warning notes


def test_understand_flow_cold_start_timeout_retry():
    js = _js(build_webapp())
    assert "var REQ_TIMEOUT_MS = 45000;" in js        # 45 s timeout (§5.1 cold starts)
    assert "withRetry" in js                          # + one retry
    assert "warming up…" in js
    assert 'JSON.stringify({field:f})' in js          # POST /api/expand
    assert '"?field="+encodeURIComponent(v)' in js    # GET /api/map per variant
    assert "PARTIAL MAP" in _norm(build_webapp())     # truncated-variant banner


def test_topic_gate_and_counter():
    html = build_webapp()
    assert "0 of 0 topics selected" in html
    js = _js(html)
    assert '" of "+state.topicTotal+" topics selected"' in js
    assert "check at least one topic, or name at least one professor below." in js
    # named professors: last-comma affiliation format, like the Studio
    assert "function parseProfs(text)" in js and "lastIndexOf(\",\")" in js


# ── injection safety ──────────────────────────────────────────────────────────

def test_esc_discipline_covers_every_dynamic_render_path():
    js = _js(build_webapp())
    assert "function esc(" in js
    # tree rows, found_by chips, review rows, warnings, job id — all esc()'d
    for snippet in ('value="\'+esc(t.topic_id)', "'+esc(t.name)+'",
                    "'+esc(t.found_by.join(\", \"))+'", "'+esc(r[1])+'",
                    "PARTIAL — '+esc(w)+", "\"+esc(state.jobId)+\"",
                    "'+esc(u)+'"):
        assert snippet in js, f"unescaped render path: {snippet}"
    # no raw API string concatenation into HTML anywhere
    assert '"+t.name+"' not in js and '"+w+"' not in js and '"+u+"' not in js


def test_default_page_has_exactly_one_script_close_and_no_raw_tags():
    html = build_webapp()
    assert html.count("</script>") == 1
    # the merge/render path is runtime-fed; the Python side interpolates only the
    # trusted intent constants + api_base (json.dumps-escaped)
    assert "\\u003c" not in html                      # api_base is NOT _inline_json'd…
    assert 'const API_BASE = "";' in html             # …it is a plain JSON string literal


# ── embedded JS: node syntax check + merge/bar harness ───────────────────────

def test_embedded_js_parses_under_node_when_available(tmp_path):
    node = shutil.which("node")
    if node is None:
        pytest.skip("node not on PATH")
    f = tmp_path / "webapp.js"
    f.write_text(_js(build_webapp()), encoding="utf-8")
    r = subprocess.run([node, "--check", str(f)], capture_output=True)
    assert r.returncode == 0, r.stderr.decode("utf-8", "replace")


# Runs the REAL embedded JS in a vm against minimal stubs, then drives mergeMaps /
# barPercent / costEstimate / esc with scenario data — the studio probe pattern.
_NODE_HARNESS = r"""
"use strict";
const fs = require("fs");
const [jsPath, scenPath] = process.argv.slice(2);
const js = fs.readFileSync(jsPath, "utf8");
const scen = JSON.parse(fs.readFileSync(scenPath, "utf8"));
const sandbox = {
  document: { addEventListener() {}, getElementById: () => null,
              querySelectorAll: () => [], querySelector: () => null },
  window: {}, navigator: {}, console,
  setTimeout: () => 0, clearTimeout: () => {}, setInterval: () => 0,
  clearInterval: () => {},
};
const vm = require("vm");
vm.createContext(sandbox);
vm.runInContext(js, sandbox);
const out = {};
if (scen.merge) out.merged = sandbox.mergeMaps(scen.merge);
if (scen.bar) out.bar = scen.bar.map(c => sandbox.barPercent(c[0], c[1], c[2]));
if (scen.cost) out.cost = scen.cost.map(s => sandbox.costEstimate(s));
if (scen.esc) out.esc = scen.esc.map(s => sandbox.esc(s));
console.log(JSON.stringify(out));
"""


def _run_webapp_js(tmp_path, scenario):
    node = shutil.which("node")
    if node is None:
        pytest.skip("node not on PATH")
    (tmp_path / "webapp.js").write_text(_js(build_webapp()), encoding="utf-8")
    (tmp_path / "scenario.json").write_text(json.dumps(scenario), encoding="utf-8")
    (tmp_path / "harness.js").write_text(_NODE_HARNESS, encoding="utf-8")
    r = subprocess.run([node, "harness.js", "webapp.js", "scenario.json"],
                       cwd=tmp_path, capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout.strip().splitlines()[-1])


def test_merge_dedupes_by_topic_id_and_tags_found_by(tmp_path):
    rep = _run_webapp_js(tmp_path, {"merge": [
        {"variant": "causal ml", "map": {"truncated": False, "groups": [
            {"domain": "Physical Sciences", "field": "CS", "subfield": "AI", "topics": [
                {"topic_id": "T1", "name": "Causal ML", "works_count": 10},
                {"topic_id": "T2", "name": "Graphs", "works_count": 3}]}]}},
        {"variant": "causal machine learning", "map": {"truncated": True, "groups": [
            {"domain": "Physical Sciences", "field": "CS", "subfield": "AI", "topics": [
                {"topic_id": "T1", "name": "Causal ML (dup)", "works_count": 10},
                {"topic_id": "T3", "name": "DAGs", "works_count": 5}]},
             {"domain": "Physical Sciences", "field": "CS", "subfield": "AI", "topics": [
                 {"topic_id": "T4", "name": "Shaped group merge", "works_count": 1}]}]}},
    ]})
    m = rep["merged"]
    # T1 appears in both variants -> ONE entry, found_by carries both phrasings;
    # the two identically-shaped groups from variant 2 merge into one cluster
    assert m["truncated"] is True                     # any variant truncated -> PARTIAL
    assert m["queries"] == ["causal ml", "causal machine learning"]
    assert len(m["groups"]) == 1
    topics = m["groups"][0]["topics"]
    assert [t["topic_id"] for t in topics] == ["T1", "T2", "T3", "T4"]
    t1 = topics[0]
    assert t1["found_by"] == ["causal ml", "causal machine learning"]
    assert t1["name"] == "Causal ML"                  # first sighting wins, never the dup


def test_merge_skips_malformed_topics_and_handles_hostile_strings(tmp_path):
    hostile = '<img src=x onerror=alert(1)> </script>'
    rep = _run_webapp_js(tmp_path, {"esc": [hostile], "merge": [
        {"variant": hostile, "map": {"truncated": False, "groups": [
            {"domain": hostile, "field": "f", "subfield": "s", "topics": [
                None, {"name": "no id"}, {"topic_id": "", "name": "empty id"},
                {"topic_id": "T1", "name": hostile, "works_count": "7"}]}]}}]})
    topics = rep["merged"]["groups"][0]["topics"]
    assert [t["topic_id"] for t in topics] == ["T1"]   # malformed entries skipped
    assert topics[0]["name"] == hostile                # stored verbatim…
    assert topics[0]["works_count"] == 7               # …counts coerced to numbers
    # …and esc() (used by every render path) neutralises it for HTML interpolation
    assert rep["esc"] == ["&lt;img src=x onerror=alert(1)&gt; &lt;/script&gt;"]


def test_esc_neutralises_the_single_quote_too(tmp_path):
    """Audit W8-F8: esc() covered & < > " but not ' — and the page mixes single- and
    double-quoted attribute markup (e.g. "<span class='jobid'>"+esc(...)), so the next
    esc()'d value landing in a single-quoted attribute would have broken straight out.
    Closed while it was still latent rather than after it was reachable."""
    rep = _run_webapp_js(tmp_path, {"esc": ["' onmouseover='alert(1)",
                                            "O'Brien & Sons <x>"]})
    assert rep["esc"] == ["&#39; onmouseover=&#39;alert(1)",
                          "O&#39;Brien &amp; Sons &lt;x&gt;"]


def test_bar_percent_math(tmp_path):
    rep = _run_webapp_js(tmp_path, {"bar": [
        ["done", "exported", {}, ],
        ["running", "discovering", {}],
        ["running", "enumerated", {"targets": 120, "institutions": 25}],
        ["queued", None, {}],
        ["running", "deep_dive_start", {"deep_dive_total": 10}],
        ["running", "deep_dive_progress", {"deep_dive_done": 3, "deep_dive_total": 10}],
        ["running", "deep_dive_progress", {"deep_dive_done": 10, "deep_dive_total": 10}],
        ["running", "scoring", {"deep_dive_done": 10, "deep_dive_total": 10}],
        ["running", "exported", {"deep_dive_done": 10, "deep_dive_total": 10}],
    ]})
    assert rep["bar"] == [100, None, 30, None, 30, 48, 90, 92, 96]


def test_cost_estimate_range(tmp_path):
    rep = _run_webapp_js(tmp_path, {"cost": [1, 40, 200]})
    # discovery 2–5 min + 1.5 min per 10 professors, rounded to a minute range
    assert rep["cost"] == ["2–5 minutes", "8–11 minutes", "32–35 minutes"]
