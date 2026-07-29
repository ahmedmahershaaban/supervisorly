"""§4.1 progress events + cooperative stop (web build, plan step 3): run_live emits a
structured event stream at phase transitions, a PARTIAL marker also fires
``partial_warning``, and ``should_stop`` cancels cleanly at a target checkpoint — partials
exported honestly, run status ``cancelled``, remainder resumable. All on cassettes (D-035).
"""

import copy
import json

import pytest
from helpers_export import stable_bytes

from supervisorly import pipeline
from supervisorly.discover import openalex, ror
from supervisorly.export import json_export as jx
from supervisorly.fetch.transport import CassetteTransport
from supervisorly.model import runs
from supervisorly.model.db import open_db

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
        "resolved_topic_ids": ["T10001"], "university_mode": "all"}


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


def _trunc_transport():
    """A discovery whose OpenAlex author enumeration is cut short by a mid-pagination 500 → PARTIAL."""
    def _authors(n):
        return json.dumps({"results": [
            {"id": f"https://openalex.org/A{i}", "display_name": f"P{i}", "works_count": 1,
             "cited_by_count": 1, "topics": [{"id": "https://openalex.org/T10001"}],
             "last_known_institutions": [], "homepage_url": None} for i in range(n)]})
    tp = CassetteTransport()
    tp.record(ror.country_url("CA"), 200, json.dumps({"number_of_results": 1, "items": [
        {"id": "https://ror.org/00abc11",
         "names": [{"value": "Maple University", "types": ["ror_display", "label"]}],
         "locations": [{"geonames_details": {"country_code": "CA"}}],
         "links": [{"type": "website", "value": "https://maple.example/"}],
         "types": ["education"]}]}))
    tp.record(openalex.institutions_url("https://ror.org/00abc11", EMAIL), 200, _oa_inst("I100"))
    tp.record(openalex.authors_url("I100", EMAIL, page=1, topic_ids=["T10001"]), 200, _authors(25))
    tp.record(openalex.authors_url("I100", EMAIL, page=2, topic_ids=["T10001"]), 500, "boom")
    return tp


_FAST = {"rate_limit": 0, "backoff_sleep": lambda _s: None}   # cassettes need no politeness delay


def _states(r):
    return {p["id"]: p["fields"]["recruiting_signal"]["state"]
            for p in r["export"]["professors"]}


# ── the §4.1 event stream ───────────────────────────────────────────────────

def test_progress_events_fire_in_order_with_payloads(tmp_path):
    events = []
    r = pipeline.run_live(PLAN, _transport(), tmp_path / "snaps", email=EMAIL,
                          progress=events.append, **_FAST)
    assert events == [
        ("enumerated", 3, 2),                    # 3 targets across 2 institutions
        ("deep_dive_start", 3),                  # k = post-gate, post-opt-out
        ("deep_dive_progress", 1, 3),
        ("deep_dive_progress", 2, 3),
        ("deep_dive_progress", 3, 3),
        ("scoring",),
        ("exported",),
    ]
    assert jx.validate_export(r["export"]) == []   # the run itself is unchanged


def test_partial_marker_also_emits_a_partial_warning_event(tmp_path):
    events = []
    pipeline.run_live(PLAN, _trunc_transport(), tmp_path / "snaps", email=EMAIL,
                      progress=events.append, **_FAST)
    phases = [e[0] for e in events]
    assert "partial_warning" in phases
    # it rides alongside the warnings channel: after enumeration/gate, before the deep-dive
    assert phases.index("partial_warning") == phases.index("deep_dive_start") + 1
    msg = next(e[1] for e in events if e[0] == "partial_warning")
    assert "PARTIAL" in msg and "authors@I100" in msg
    assert msg.isascii()                              # console-safe by construction


def test_no_progress_arg_matches_a_noop_callback_byte_for_byte(tmp_path):
    # default None must be EXACTLY today's behavior — same result shape a no-op gets
    r_none = pipeline.run_live(PLAN, _transport(), tmp_path / "a" / "snaps", email=EMAIL, **_FAST)
    r_noop = pipeline.run_live(PLAN, _transport(), tmp_path / "b" / "snaps", email=EMAIL,
                               progress=lambda _e: None, **_FAST)

    # The volatile-field list lives in helpers_export because the phase-flag test needs the
    # same one: run_id, the two timestamps, and the CC-1 ledger's own elapsed-time columns.
    assert stable_bytes(r_none["export"]) == stable_bytes(r_noop["export"])
    assert r_none["stats"] == r_noop["stats"]


# ── cooperative stop → cancelled ────────────────────────────────────────────

def _stop_after(n):
    """A should_stop that returns True once n targets have been processed."""
    calls = {"n": 0}

    def _should_stop():
        calls["n"] += 1
        return calls["n"] >= n
    return _should_stop


def test_should_stop_cancels_cleanly_and_exports_an_honest_partial(tmp_path):
    db = tmp_path / "run.sqlite"
    events = []
    r = pipeline.run_live(PLAN, _transport(), tmp_path / "snaps", email=EMAIL,
                          db_path=str(db), progress=events.append,
                          should_stop=_stop_after(1), **_FAST)
    assert r["stats"]["cancelled"] is True
    # cancelled wins the status audit: never a finalized status, whatever the gaps say
    assert r["export"]["run"]["status"] == "cancelled"
    # only the first target (A200) was deep-dived; the rest are honestly never_attempted
    assert _states(r) == {"A200": "value", "A201": "never_attempted",
                          "A202": "never_attempted"}
    # the partial export + dashboard were genuinely built (four-state model, D-046)
    assert jx.validate_export(r["export"]) == []
    assert r["html"]
    progress_events = [e for e in events if e[0] == "deep_dive_progress"]
    assert progress_events == [("deep_dive_progress", 1, 3)]     # stopped after target 1
    assert ("scoring",) in events and ("exported",) in events    # partials still exported
    # the run status persisted as cancelled (schema v3 CHECK accepts it)
    conn = open_db(str(db))
    assert runs.get_run(conn, r["run_id"])["status"] == "cancelled"


def test_cancelled_run_resumes_and_completes_the_remainder(tmp_path):
    db = tmp_path / "run.sqlite"
    r1 = pipeline.run_live(PLAN, _transport(), tmp_path / "snaps", email=EMAIL,
                           db_path=str(db), should_stop=_stop_after(1), **_FAST)
    assert r1["stats"]["cancelled"] is True
    # resume: a FRESH run reuses the completed target's persisted claims (D-029) and
    # finishes the rest — the cassette seam proves nothing completed was re-fetched
    r2 = pipeline.run_live(PLAN, _transport(), tmp_path / "snaps", email=EMAIL,
                           db_path=str(db), resume=True, **_FAST)
    assert "cancelled" not in r2["stats"]
    assert r2["stats"]["resumed_skipped"] == 1               # A200 not re-fetched
    assert _states(r2) == {"A200": "value", "A201": "blocked", "A202": "value"}
    assert r2["export"]["run"]["status"] == "finalized_with_open_gaps"   # A201's open gap
    # the first run's cancelled status is untouched by the second run
    conn = open_db(str(db))
    assert runs.get_run(conn, r1["run_id"])["status"] == "cancelled"


# ── observer robustness ─────────────────────────────────────────────────────

def test_raising_progress_and_should_stop_callbacks_do_not_break_the_run(tmp_path):
    def _boom(*_a):
        raise RuntimeError("broken observer")
    r = pipeline.run_live(PLAN, _transport(), tmp_path / "snaps", email=EMAIL,
                          progress=_boom, should_stop=_boom, **_FAST)
    # a raising should_stop is "keep going", never a forced stop
    assert "cancelled" not in r["stats"]
    assert r["export"]["run"]["status"] == "finalized_with_open_gaps"
    assert jx.validate_export(r["export"]) == []


def test_ctrl_c_inside_a_callback_is_not_swallowed(tmp_path):
    # Ctrl+C safety: KeyboardInterrupt is a BaseException — the guards catch Exception
    # only, so an interrupt still aborts the run (and the state machine keeps it resumable)
    def _interrupt(_event):
        raise KeyboardInterrupt
    with pytest.raises(KeyboardInterrupt):
        pipeline.run_live(PLAN, _transport(), tmp_path / "snaps", email=EMAIL,
                          progress=_interrupt, **_FAST)
