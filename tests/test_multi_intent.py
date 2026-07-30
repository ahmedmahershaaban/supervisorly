"""MI — several intents at once, and filtering the dashboard by supervision level.

Two halves, and the second is the one with teeth.

**The plan shape** (MI-1/MI-2) follows the rule ``fields``/``field`` already established: the
list is the truth, the scalar is derived. That rule is written down because the first
implementation of it had a bug — the page sent a list *and* a human-readable join of it, the
two were merged, and the join became a phantom extra field named after all the others. The
same merge here would invent an eighth intent. It is pinned below.

**The filter** (MI-4/MI-5) is dangerous in a way a filter usually is not: what it *hides*.
A professor with no ``supervises`` claim is ``unknown``, never "no" — we did not find a
statement, which is not the same as the person not taking students. Today that is *every*
professor, because ``supervises`` only gets populated once P5 ships, so a filter that dropped
unknowns would show an empty dashboard and look like a broken product rather than an honest
one. Those tests run the dashboard's REAL embedded JavaScript in Node against a mini-DOM,
the pattern ``test_webapp_clickthrough.py`` uses, rather than re-describing the logic in
Python where it could drift from what ships.
"""

from __future__ import annotations

import json
import shutil
import subprocess

import pytest

from supervisorly import cli, pipeline
from supervisorly.discover.ladder import plan_intents
from supervisorly.export import dashboard as dash
from supervisorly.export.webapp import INTENTS, build_webapp
from supervisorly.extract.llm_claims import SUPERVISION_LEVELS


# ── MI-2: the plan carries a list ─────────────────────────────────────────────
def test_the_two_vocabularies_are_still_the_same_seven_words():
    """The feature only works without a translation layer, and that is not an accident.

    If these ever diverge, "I want a PhD supervisor" and "this person takes PhD students"
    stop being the same word and something has to map between them — which is the synonym
    table D-038 forbids. Fail here, loudly, rather than growing one.
    """
    assert tuple(cli.PLAN_INTENT_KINDS) == tuple(SUPERVISION_LEVELS)


def test_plan_intents_reads_the_list():
    assert plan_intents({"intent_kinds": ["phd", "master"]}) == ["phd", "master"]


def test_plan_intents_reads_an_old_single_valued_plan():
    """One reader serves old plans and new — every plan written before MI carries a scalar."""
    assert plan_intents({"intent_kind": "postdoc"}) == ["postdoc"]


def test_plan_intents_never_invents_a_phantom_intent():
    """The `plan_fields` bug, pinned so it cannot happen twice.

    The scalar IS the list's first element. Merging the two shapes would be harmless today
    and would start duplicating the moment either side changed, so the list wins outright.
    """
    got = plan_intents({"intent_kinds": ["phd", "master"], "intent_kind": "phd"})
    assert got == ["phd", "master"]
    assert len(got) == len(set(got))


def test_plan_intents_dedupes_and_keeps_order():
    assert plan_intents({"intent_kinds": ["phd", "master", "phd"]}) == ["phd", "master"]


def test_plan_intents_of_an_empty_plan_is_empty_not_a_default():
    """A guessed default here would search for something the student never asked for."""
    assert plan_intents({}) == []


def test_normalize_derives_the_scalar_from_the_list():
    p = cli.normalize_plan_intents({"intent_kinds": ["master", "phd"], "intent_kind": "phd"})
    assert p["intent_kind"] == "master", "the scalar must be re-derived, never trusted"
    assert p["intent_kinds"] == ["master", "phd"]


def test_normalize_upgrades_an_old_scalar_only_plan():
    p = cli.normalize_plan_intents({"intent_kind": "phd"})
    assert p["intent_kinds"] == ["phd"] and p["intent_kind"] == "phd"


def test_normalize_leaves_an_intentless_plan_for_validation_to_report():
    """It must not invent one. An absent intent is a validation error, not a default."""
    assert "intent_kinds" not in cli.normalize_plan_intents({"country": "EG"})


@pytest.mark.parametrize("kinds", [["phd", "master"], ["postdoc"], list(SUPERVISION_LEVELS)])
def test_a_valid_list_passes_validation(kinds):
    assert cli._plan_value_errors({"intent_kinds": kinds}) == []


def test_an_unknown_level_fails_loud():
    errs = cli._plan_value_errors({"intent_kinds": ["phd", "postgrad"]})
    assert errs and "postgrad" in errs[0]


def test_an_empty_list_is_rejected_rather_than_read_as_everything():
    """MI-2.3 — a search for no level at all is a mangled intent, not a wide search."""
    errs = cli._plan_value_errors({"intent_kinds": []})
    assert errs and "must not be empty" in errs[0]


def test_a_non_list_fails_loud():
    assert cli._plan_value_errors({"intent_kinds": "phd"})


# ── MI-1: the wizard ──────────────────────────────────────────────────────────
def _page():
    return build_webapp(api_base="")


def test_step_one_offers_checkboxes_not_radios():
    html = _page()
    assert 'type="checkbox" name="intent"' in html
    assert 'type="radio" name="intent"' not in html


def test_every_enum_value_is_offered_so_the_server_can_never_reject_a_card():
    html = _page()
    for key, _title, _desc in INTENTS:
        assert f'name="intent" value="{key}"' in html, key
    assert {k for k, _, _ in INTENTS} == set(cli.PLAN_INTENT_KINDS)


def test_the_group_is_no_longer_announced_as_a_radiogroup():
    """A checkbox group announced as a radiogroup tells a screen-reader user they may pick
    exactly one — the opposite of the change."""
    html = _page()
    assert 'role="radiogroup" aria-label="intent"' not in html
    assert 'id="err-intent"' in html, "MI-1.2 needs somewhere to say what went wrong"


def test_the_plan_sent_by_the_page_carries_the_list_and_the_derived_scalar():
    html = _page()
    assert "intent_kinds: state.intents.slice()" in html
    assert "intent_kind: state.intents[0]" in html


# MI-1.5, driven through the page's OWN listeners with the click-through harness — asserting
# the source contains the right lines proves it was typed, not that it works.
def test_two_ticked_levels_both_reach_the_plan(tmp_path):
    from test_webapp_clickthrough import _at, _run, _scenario

    rep = _run(tmp_path, {**_scenario(), "intents": ["phd", "master"]})
    scan = next(b for b in rep["bodies"] if b["path"].endswith("/api/scan"))
    kinds = scan["body"]["plan"]["intent_kinds"]
    assert set(kinds) == {"phd", "master"}
    # Order is CARD order, not tick order — the DOM is the only ordering the page has, and it
    # is stable, so the derived scalar is predictable rather than dependent on which box the
    # student happened to click first.
    assert kinds == ["master", "phd"], "the list must follow the order the cards are rendered in"
    assert scan["body"]["plan"]["intent_kind"] == kinds[0]
    assert _at(rep, "after step 1")["step"] == 2


def test_no_ticked_level_stops_at_step_one_with_a_reason(tmp_path):
    """Never a silent default. Quietly searching "pre_phd" for someone who ticked nothing is
    the tool deciding their intent for them — and they would never find out.

    Asserted at the "after step 1" snapshot: the harness fires every later step's button
    unconditionally, so a step-5 reading proves nothing about whether step 1 let them past.
    """
    from test_webapp_clickthrough import _at, _run, _scenario

    rep = _run(tmp_path, {**_scenario(), "intents": []})
    assert _at(rep, "after step 1")["step"] == 1, "the wizard advanced with no intent ticked"
    assert "tick at least one" in rep["errIntent"].lower()
    assert "this step" in rep["errIntent"], "MI-1.2: the error says WHICH step"


# ── MI-4 / MI-5: the filter, running the page's real JavaScript ───────────────
_FILTER_HARNESS = r"""
"use strict";
const fs = require("fs"), vm = require("vm");
const [htmlPath, scenPath] = process.argv.slice(2);
const html = fs.readFileSync(htmlPath, "utf8");
const scen = JSON.parse(fs.readFileSync(scenPath, "utf8"));

/* The dashboard inlines DATA in one <script> and its logic in the next. Take the LAST one. */
const parts = html.split("<script>").slice(1).map(s => s.split("</script>")[0]);
const scriptSrc = parts[parts.length - 1];

class El {
  constructor(id){ this.id=id||""; this._html=""; this.textContent=""; this.value="";
    this.attrs={}; this.listeners={}; this.style={}; const self=this;
    const cls=()=>new Set((self.attrs.class||"").split(/\s+/).filter(Boolean));
    this.classList={ contains:c=>cls().has(c),
      add:c=>{const s=cls();s.add(c);self.attrs.class=[...s].join(" ");},
      remove:c=>{const s=cls();s.delete(c);self.attrs.class=[...s].join(" ");},
      toggle:(c,f)=>{const on=f===undefined?!cls().has(c):!!f; on?self.classList.add(c):self.classList.remove(c); return on;} };
  }
  get innerHTML(){ return this._html; }
  set innerHTML(v){ this._html=String(v); }
  addEventListener(t,fn){ (this.listeners[t]=this.listeners[t]||[]).push(fn); }
  querySelectorAll(){ return []; }
  scrollIntoView(){}
  getBoundingClientRect(){ return {x:0,y:0,width:100,height:20}; }
}
const els={};
const byId=(id)=>(els[id]=els[id]||new El(id));
["grid","deadlines","how","stage","ledger","levels","count","q","panel",
 "vTable","vDeadlines","vHow"].forEach(byId);

const document={ documentElement:{}, body:new El("body"), getElementById:byId,
  createElement:()=>new El(), querySelectorAll:()=>[], querySelector:()=>null,
  addEventListener:(t,fn)=>{ if(t==="DOMContentLoaded") document._ready=fn; } };
const window={ addEventListener(){}, matchMedia:()=>({matches:false}) };

const ctx={ document, window, DATA:scen.data, console,
            setTimeout, clearTimeout, requestAnimationFrame:(f)=>f(0) };
ctx.globalThis=ctx;
vm.createContext(ctx);
vm.runInContext(scriptSrc, ctx);
if(document._ready) document._ready();

/* Drive the filter exactly as a click would: flip a chip, then re-render. */
(scen.toggle||[]).forEach(k => {
  ctx.initLevelSel();
  if(ctx.levelSel.has(k)) ctx.levelSel.delete(k); else ctx.levelSel.add(k);
});
if(scen.query !== undefined) byId("q").value = scen.query;
ctx.render();

console.log(JSON.stringify({
  visible: ctx.filtered().map(p => p.id),
  counts: ctx.levelCounts(),
  selected: [...ctx.levelSel].sort(),
  chips: ctx.chipKeys(ctx.levelCounts()),
  chipHtml: byId("levels").innerHTML,
  gridHtml: byId("grid").innerHTML,
  empty: ctx.emptyStateMessage(),
  count: byId("count").textContent,
}));
"""


def _prof(pid, supervises=None, name=None):
    """One exported professor. `supervises=None` = no claim at all — the state every
    professor is in until P5 ships."""
    fields = {"recruiting_signal": {"state": "never_attempted", "value": None}}
    if supervises is not None:
        fields["supervises"] = {"state": "value", "value": supervises,
                                "source_url": "https://u.edu/p", "quote": "q"}
    return {"id": pid, "name": name or pid, "fields": fields}


def _export(professors, intents=("phd",)):
    return {"schema_version": "1", "generated_at": "2026-07-29T00:00:00+00:00",
            "run": {"run_id": "r1", "status": "finalized", "coverage": "n professors.",
                    "ledger": [], "intents": list(intents)},
            "fields": [{"id": "recruiting_signal", "label": "Recruiting signal",
                        "kind": "filter", "datatype": "string"},
                       {"id": "supervises", "label": "Supervises", "kind": "filter",
                        "datatype": "string"}],
            "professors": professors}


def _filter(tmp_path, export, *, toggle=(), query=None):
    node = shutil.which("node")
    if node is None:
        pytest.skip("node not on PATH")
    (tmp_path / "harness.js").write_text(_FILTER_HARNESS, encoding="utf-8")
    (tmp_path / "page.html").write_text(dash.build_dashboard(export), encoding="utf-8")
    scen = {"data": export, "toggle": list(toggle)}
    if query is not None:
        scen["query"] = query
    (tmp_path / "scen.json").write_text(json.dumps(scen), encoding="utf-8")
    # `text=True` alone decodes the child's output with the ANSI code page, which on a stock
    # Windows shell is cp1252 — and the harness echoes dashboard HTML back, typographic quotes
    # and all. cp1252 has no 0x9D, so the reader thread dies, `r.stdout` comes back None, and
    # four tests fail with `'NoneType' has no attribute 'strip'` for a reason that has nothing
    # to do with what they test. node writes UTF-8; say so.
    r = subprocess.run([node, "harness.js", "page.html", "scen.json"],
                       cwd=tmp_path, capture_output=True, timeout=60,
                       encoding="utf-8", errors="replace")
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout.strip().splitlines()[-1])


MIXED = [_prof("a", "phd"), _prof("b", "master"), _prof("c", "phd, master"), _prof("d")]


def test_a_professor_with_no_supervises_claim_is_unknown_not_no(tmp_path):
    """MI-5.1. Absence of a statement is not a statement of absence."""
    out = _filter(tmp_path, _export(MIXED))
    assert out["counts"]["unknown"] == 1
    assert out["counts"]["phd"] == 2 and out["counts"]["master"] == 2


def test_unknown_is_shown_by_default(tmp_path):
    """MI-5.2 — the load-bearing one. The student picked "phd"; professor `d` has no
    statement either way and must still be on the page."""
    out = _filter(tmp_path, _export(MIXED, intents=("phd",)))
    assert "unknown" in out["selected"]
    assert "d" in out["visible"], "a professor we know nothing about was silently dropped"


def test_the_students_levels_are_preselected(tmp_path):
    """MI-4.2."""
    out = _filter(tmp_path, _export(MIXED, intents=("master",)))
    assert "master" in out["selected"]
    assert set(out["visible"]) == {"b", "c", "d"}, "master + the unknowns"


def test_unknown_is_only_hidden_when_the_student_unticks_it(tmp_path):
    """MI-5.4 — the filter never removes an unknown on its own."""
    out = _filter(tmp_path, _export(MIXED, intents=("phd",)), toggle=["unknown"])
    assert "d" not in out["visible"]
    assert set(out["visible"]) == {"a", "c"}


def test_a_professor_stating_several_levels_matches_any_of_them(tmp_path):
    """`supervises` is a comma list over the enum, so `c` answers both questions."""
    out = _filter(tmp_path, _export(MIXED, intents=("master",)))
    assert "c" in out["visible"]


def test_chips_carry_counts(tmp_path):
    """MI-4.3."""
    out = _filter(tmp_path, _export(MIXED))
    assert "phd" in out["chips"] and "unknown" in out["chips"]
    assert 'data-level="phd"' in out["chipHtml"]
    assert ">2<" in out["chipHtml"], "the phd/master counts must be rendered, not just computed"


def test_ticking_every_level_is_the_same_as_no_filter(tmp_path):
    out = _filter(tmp_path, _export(MIXED, intents=tuple(SUPERVISION_LEVELS)))
    assert set(out["visible"]) == {"a", "b", "c", "d"}


def test_the_level_filter_composes_with_the_text_filter(tmp_path):
    """MI-4.5 — they narrow together; neither resets the other."""
    profs = [_prof("a", "phd", name="Ada Maple"), _prof("b", "phd", name="Ben Birch"),
             _prof("c", "master", name="Ada Cedar")]
    out = _filter(tmp_path, _export(profs, intents=("phd",)), query="ada")
    assert set(out["visible"]) == {"a"}, "text AND level, not one or the other"


def test_the_empty_state_says_which_empty_it_is(tmp_path):
    """MI-5.3 — "no results" over a hidden pile of unknowns is the failure being prevented."""
    out = _filter(tmp_path, _export([_prof("d"), _prof("e")], intents=("phd",)),
                  toggle=["unknown"])
    assert out["visible"] == []
    assert "no statement either way" in out["empty"]
    assert "2" in out["empty"], "it must say HOW MANY are being hidden"
    assert "unknown" in out["empty"], "…and how to get them back"


# ── the state everything is actually in today ────────────────────────────────
def test_before_p5_every_professor_is_unknown_and_the_page_says_so(tmp_path):
    """The plan's own edge case: with no level claims anywhere, the filter must not look
    broken. Everyone is visible, and a note explains why one chip carries every row."""
    out = _filter(tmp_path, _export([_prof("a"), _prof("b"), _prof("c")], intents=("phd",)))
    assert set(out["visible"]) == {"a", "b", "c"}
    assert out["counts"]["unknown"] == 3
    assert "No professor has stated a level yet" in out["chipHtml"]


def test_a_real_run_carries_the_students_intents_into_the_export():
    """The chips cannot be pre-ticked from data the export does not carry."""
    conn = pipeline.open_db()
    try:
        run_id = pipeline.runs.create_run(conn)
        result = pipeline._build_result(conn, run_id, "finalized", [],
                                        stats={"extractions": 0}, gaps=0,
                                        plan_intents=["phd", "master"])
        assert result["export"]["run"]["intents"] == ["phd", "master"]
    finally:
        conn.close()


def test_a_hostile_level_value_cannot_reach_the_dom_unescaped(tmp_path):
    """`supervises` will be model-proposed text (P5). It is rendered into chips and cells, so
    it takes the same escaping every other value does."""
    out = _filter(tmp_path, _export([_prof("x", "phd</script><img src=x onerror=alert(1)>")]))
    assert "<img" not in out["chipHtml"] and "<img" not in out["gridHtml"]
