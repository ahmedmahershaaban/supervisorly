"""CC-1 — the phase ledger.

The property under test is *coverage honesty applied to the engine itself* (D-037): after a
run, "we did not look" must stay distinguishable from "we looked and found nothing". Three
times in this project's history a thin dashboard cost an afternoon of log archaeology
because the pipeline reported only what it FOUND. A phase that reached nothing therefore
still writes a row, and a skip without a reason is refused at the API boundary rather than
discovered later as a blank cell in production.
"""

from __future__ import annotations

import pytest

from supervisorly import pipeline
from supervisorly.fetch.transport import CassetteTransport
from supervisorly.model import runs
from supervisorly.model.db import open_db


@pytest.fixture()
def conn():
    c = open_db()
    yield c
    c.close()


def _run(c):
    return runs.create_run(c)


# ── the acceptance case ───────────────────────────────────────────────────────
def test_phase_that_reached_nothing_still_appears_with_its_reason(conn):
    """The CC-1 acceptance criterion, verbatim: P1 attempted 10, reached 0, skipped 10."""
    run_id = _run(conn)
    runs.record_phase(conn, run_id, "p1", attempted=10, reached=0, skipped=10,
                      reason="no admissions page found")

    rows = runs.phase_ledger(conn, run_id)
    assert len(rows) == 1, "a phase that reached nothing must still be in the ledger"
    row = rows[0]
    assert (row["phase"], row["attempted"], row["reached"], row["skipped"]) == ("p1", 10, 0, 10)
    assert row["reason"] == "no admissions page found"


def test_a_skip_without_a_reason_is_refused(conn):
    """A silent skip is the exact failure the ledger exists to remove, so it cannot be written.

    This is a guard, not a policy preference: `skipped=10, reason=None` renders as a blank
    'Why' cell, which reads to a student as "no reason" rather than as "nobody recorded one".
    """
    run_id = _run(conn)
    with pytest.raises(runs.StateError):
        runs.record_phase(conn, run_id, "p1", attempted=10, skipped=10)
    with pytest.raises(runs.StateError):
        runs.record_phase(conn, run_id, "p1", attempted=10, skipped=10, reason="   ")
    assert runs.phase_ledger(conn, run_id) == [], "the refused row must not be half-written"


def test_a_phase_that_skipped_nothing_needs_no_reason(conn):
    """The guard is on skips, not on rows — a clean phase must not be forced to invent prose."""
    run_id = _run(conn)
    runs.record_phase(conn, run_id, "p0", attempted=40, reached=40)
    assert runs.phase_ledger(conn, run_id)[0]["reason"] is None


def test_rows_keep_insertion_order_within_one_second(conn):
    """Ordering is by rowid, not by timestamp.

    `utcnow()` is second-resolution, so phases that finish inside the same second carry
    identical `created_at` values. Ordering on that would let the ledger shuffle between two
    reads of the same run — and a ledger that reorders itself is one nobody trusts.
    """
    run_id = _run(conn)
    for name in ("discovery", "p0", "p1", "deep_dive"):
        runs.record_phase(conn, run_id, name, attempted=1, reached=1)
    assert [r["phase"] for r in runs.phase_ledger(conn, run_id)] == [
        "discovery", "p0", "p1", "deep_dive"]


def test_ledger_is_scoped_to_its_run(conn):
    """Two runs in one database (the warm-cache / resume path) must not read each other's rows."""
    a, b = _run(conn), _run(conn)
    runs.record_phase(conn, a, "p0", attempted=3, reached=3)
    runs.record_phase(conn, b, "p0", attempted=7, reached=0, skipped=7, reason="flag off")
    assert [r["attempted"] for r in runs.phase_ledger(conn, a)] == [3]
    assert [r["reached"] for r in runs.phase_ledger(conn, b)] == [0]


def test_a_phase_may_be_recorded_twice(conn):
    """A resumed run re-enters a phase; both attempts must show, not the last one only."""
    run_id = _run(conn)
    runs.record_phase(conn, run_id, "p0", attempted=40, reached=12, skipped=28,
                      reason="ORCID record has no current employment")
    runs.record_phase(conn, run_id, "p0", attempted=28, reached=4, skipped=24,
                      reason="ORCID record has no current employment")
    assert len(runs.phase_ledger(conn, run_id)) == 2


def test_unknown_run_reads_as_empty_not_as_an_error(conn):
    """Absence is an answer. The reexport path passes a synthetic run id when no run exists."""
    assert runs.phase_ledger(conn, "run_nonexistent") == []


# ── it has to reach the student, not just the database ────────────────────────
def test_the_ledger_travels_into_the_export(conn):
    """CC-1.3 — an operator-only ledger would help the wrong person.

    The reader who most needs "why is this thin?" answered is the student looking at the
    dashboard, not someone with `gcloud logging read`.
    """
    run_id = _run(conn)
    runs.record_phase(conn, run_id, "p1", attempted=10, reached=0, skipped=10,
                      reason="no admissions page found")
    result = pipeline._build_result(conn, run_id, "finalized", [],
                                    stats={"extractions": 0}, gaps=0)
    ledger = result["export"]["run"]["ledger"]
    assert [(r["phase"], r["reached"], r["reason"]) for r in ledger] == [
        ("p1", 0, "no admissions page found")]


def test_an_empty_ledger_is_still_a_key_in_the_export(conn):
    """Present-and-empty, never missing: a vanishing key makes "nothing recorded" look like
    an older export rather than like an answer."""
    run_id = _run(conn)
    result = pipeline._build_result(conn, run_id, "finalized", [],
                                    stats={"extractions": 0}, gaps=0)
    assert result["export"]["run"]["ledger"] == []


def test_the_dashboard_shows_a_zero_reach_phase_and_its_reason(conn):
    """CC-1.4 — rendering only the productive phases would rebuild the original silence."""
    run_id = _run(conn)
    runs.record_phase(conn, run_id, "p1", attempted=10, reached=0, skipped=10,
                      reason="no admissions page found")
    html = pipeline._build_result(conn, run_id, "finalized", [],
                                  stats={"extractions": 0}, gaps=0)["html"]
    assert "no admissions page found" in html
    assert 'id="ledger"' in html, "the panel the ledger renders into must exist"
    assert "What each phase did" in html


# ── a real run has to actually write rows ─────────────────────────────────────
def _offline(tmp_path, html, *, url="https://u.edu/p"):
    tp = CassetteTransport()
    tp.record("https://u.edu/robots.txt", 200, "User-agent: *\nAllow: /\n")
    tp.record(url, 200, html)
    return pipeline.run_offline(
        {"intent_kind": "pre_phd", "resolved_topic_ids": ["T"]},
        [{"id": "p", "name": "Dr. Page", "url": url}], tp, tmp_path / "snaps")


def test_a_real_run_writes_a_deep_dive_row(tmp_path):
    """The mechanism is worthless if nothing calls it — an always-empty ledger is a panel
    that says "no phase reported" forever, which is worse than no panel at all."""
    result = _offline(tmp_path, "<html><body><p>I am recruiting PhD students.</p></body></html>")
    ledger = result["export"]["run"]["ledger"]
    dive = [r for r in ledger if r["phase"] == "deep_dive"]
    assert len(dive) == 1
    assert dive[0]["attempted"] == 1
    assert dive[0]["reached"] == 1, "a page that yielded evidence is a target we reached"
    assert dive[0]["skipped"] == 0


def test_a_run_that_reached_nobody_says_why(tmp_path):
    """The acceptance criterion on the live path: a blocked target is skipped WITH a reason,
    not merely absent from the ledger."""
    tp = CassetteTransport()
    tp.record("https://u.edu/robots.txt", 200, "User-agent: *\nDisallow: /\n")
    result = pipeline.run_offline(
        {"intent_kind": "pre_phd", "resolved_topic_ids": ["T"]},
        [{"id": "p", "name": "Dr. Page", "url": "https://u.edu/p"}], tp, tmp_path / "snaps")
    dive = [r for r in result["export"]["run"]["ledger"] if r["phase"] == "deep_dive"][0]
    assert dive["reached"] == 0 and dive["skipped"] == 1
    assert dive["reason"], "a skip must carry its reason all the way to the export"
    assert "human rung" in dive["reason"]


def test_an_opted_out_person_is_its_own_row_not_a_coverage_gap(tmp_path, monkeypatch):
    """D-023: an opt-out is a FILTERED result. Folding it into the deep-dive's skip count
    would report a person's own choice as a limit of the scan."""
    optout = tmp_path / "optout.txt"
    optout.write_text("p\n", encoding="utf-8")
    tp = CassetteTransport()
    tp.record("https://u.edu/robots.txt", 200, "User-agent: *\nAllow: /\n")
    result = pipeline.run_offline(
        {"intent_kind": "pre_phd", "resolved_topic_ids": ["T"]},
        [{"id": "p", "name": "Dr. Page", "url": "https://u.edu/p"}], tp,
        tmp_path / "snaps", optout_path=str(optout))
    phases = {r["phase"]: r for r in result["export"]["run"]["ledger"]}
    assert phases["optout"]["skipped"] == 1
    assert "opt-out" in phases["optout"]["reason"]
    assert phases["deep_dive"]["attempted"] == 0, "a suppressed person is never even requested"


def test_a_reason_cannot_break_out_of_the_inlined_json(conn):
    """A reason is free text that ends up inside a <script> block, so it takes the same
    escaping every other value does — a phase name is not a trusted string."""
    run_id = _run(conn)
    runs.record_phase(conn, run_id, "p1", attempted=1, skipped=1,
                      reason="</script><img src=x onerror=alert(1)>")
    html = pipeline._build_result(conn, run_id, "finalized", [],
                                  stats={"extractions": 0}, gaps=0)["html"]
    assert "</script><img" not in html
