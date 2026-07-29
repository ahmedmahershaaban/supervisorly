"""D-073 wired: the model pass actually runs, and every bound holds where it is called.

`llm_claims` was built, tested and called by nothing — which is why dashboards were thin. Its
own contract is covered in `test_llm_claims.py`; what is covered here is the *wiring*: that a
scan reaches it, that the gate is still the gate on the way in, and above all that a run with
no key configured behaves exactly like the run that shipped yesterday.
"""
import json

import pytest

from supervisorly import pipeline
from supervisorly.extract import llm_claims, llm_client
from supervisorly.fetch.fetcher import Fetcher
from supervisorly.fetch.ratelimit import HostRateLimiter
from supervisorly.fetch.snapshot import SnapshotStore
from supervisorly.fetch.transport import CassetteTransport
from supervisorly.model import claims as claims_mod
from supervisorly.model import runs
from supervisorly.model.db import open_db

# Prose a human reads as "recruiting" and no cue-word regex will ever match.
PROSE = ("<html><body><p>Professor A. Example, Department of Computing. I will be reviewing "
         "applications from students interested in joining the group for the 2027 intake. "
         "Prospective candidates should get in touch before the end of term.</p></body></html>")


def _completer(payload):
    """A model that answers with whatever `payload` says. Never touches the network."""
    def complete(_prompt):
        return json.dumps(payload)
    return complete


def _harness(tmp_path, html=PROSE, url="https://u.edu/p"):
    tp = CassetteTransport()
    tp.record("https://u.edu/robots.txt", 200, "User-agent: *\nAllow: /\n")
    tp.record(url, 200, html)
    conn = open_db(tmp_path / "t.sqlite")
    snaps = SnapshotStore(tmp_path / "snaps")
    fetcher = Fetcher(tp, snaps, sleep=lambda _s: None,
                      rate_limiter=HostRateLimiter(min_interval=0.0))
    return conn, snaps, fetcher, runs.create_run(conn), {"id": "p", "name": "Dr. P", "url": url}


def _dive(conn, snaps, fetcher, run_id, target, **kw):
    stats = {"resumed_skipped": 0, "extractions": 0, "cache_hits": 0}
    pipeline._deep_dive_one(conn, run_id, target, fetcher, snaps,
                            stats=stats, resume=False, **kw)
    return stats


def _live(conn, field, pid="p"):
    """The one non-superseded claim for a field, or None if the field has none at all."""
    rows = [c for c in claims_mod.claims_for(conn, "person", pid) if c["field"] == field]
    return rows[0] if rows else None


# ── the wiring ───────────────────────────────────────────────────────────────
def test_without_a_key_the_deep_dive_is_byte_for_byte_yesterdays_run(tmp_path):
    """The default path. No key -> no completer -> no model pass, and no new stats keys."""
    conn, snaps, fetcher, run_id, t = _harness(tmp_path)
    try:
        stats = _dive(conn, snaps, fetcher, run_id, t, complete=None)
        assert "model_proposals" not in stats
        assert "model_claims" not in stats
        assert stats["extractions"] == 1
    finally:
        conn.close()


def test_completer_from_env_is_none_without_a_key():
    assert llm_client.completer_from_env({}) is None
    assert llm_client.completer_from_env({"SUPERVISORLY_EXTRACT_KEY": "  "}) is None
    assert llm_client.completer_from_env({"SUPERVISORLY_EXTRACT_KEY": "k"}) is not None


def test_a_quoted_proposal_becomes_a_real_claim(tmp_path):
    """The point of the whole exercise: prose no regex matches becomes a cited fact."""
    conn, snaps, fetcher, run_id, t = _harness(tmp_path)
    try:
        quote = ("I will be reviewing applications from students interested in joining the "
                 "group for the 2027 intake")
        stats = _dive(conn, snaps, fetcher, run_id, t, complete=_completer(
            {"claims": [{"field": "recruiting_signal", "value": "recruiting for 2027",
                            "quote": quote}]}))
        assert stats.get("model_claims") == 1
        assert stats.get("model_rejected") == 0
        row = _live(conn, "recruiting_signal")
        assert row["state"] == "value"
        assert row["extractor_agent"] == "model"
        assert quote in row["quote"]
        # `derived`, never `quoted_official` — the sentence is the page's, the reading is the
        # model's, and a dashboard that flattened the two would hide which cells it decided.
        assert row["confidence"] == "derived"
    finally:
        conn.close()


def test_an_invented_quote_never_becomes_a_claim(tmp_path):
    """A hallucination dies at the gate, not in front of a student (D-073)."""
    conn, snaps, fetcher, run_id, t = _harness(tmp_path)
    try:
        stats = _dive(conn, snaps, fetcher, run_id, t, complete=_completer(
            {"claims": [{"field": "deadline", "value": "2027-01-15",
                            "quote": "Applications close on 15 January 2027."}]}))
        assert stats.get("model_rejected") == 1
        assert stats.get("model_claims") is None
        row = _live(conn, "deadline")
        assert row["state"] != "value"          # still the honest absence, not the invention
    finally:
        conn.close()


def test_the_rejection_is_counted_not_swallowed(tmp_path):
    """D-073 bound 6 — a model whose quotes stop matching must be visible, not a quiet fade."""
    conn, snaps, fetcher, run_id, t = _harness(tmp_path)
    try:
        stats = _dive(conn, snaps, fetcher, run_id, t, complete=_completer(
            {"claims": [{"field": "deadline", "value": "x", "quote": "not on the page"},
                           {"field": "students_signal", "value": "y", "quote": "nor this"}]}))
        assert stats["model_proposals"] == 2
        assert stats["model_rejected"] == 2
    finally:
        conn.close()


def test_a_model_that_errors_does_not_kill_the_scan(tmp_path):
    """Fail-closed: the deterministic extractors still ran and the target is not blocked."""
    def boom(_prompt):
        raise RuntimeError("http 500")
    conn, snaps, fetcher, run_id, t = _harness(tmp_path)
    try:
        stats = _dive(conn, snaps, fetcher, run_id, t, complete=boom)
        assert stats.get("model_unavailable") == 1
        assert stats["extractions"] == 1
        assert not pipeline._target_open_gap(conn, "p")
    finally:
        conn.close()


def test_the_model_is_not_asked_about_fields_the_regex_already_answered(tmp_path):
    """Gap-filling, not overruling — and a shorter prompt for free."""
    rich = ("<html><body><p>I am recruiting PhD students. Applications close on "
            "15 January 2027 — apply by then.</p></body></html>")
    seen = {}

    def spy(prompt):
        seen["prompt"] = prompt
        return json.dumps({"claims": []})

    conn, snaps, fetcher, run_id, t = _harness(tmp_path, html=rich)
    try:
        _dive(conn, snaps, fetcher, run_id, t, complete=spy)
        assert "recruiting_signal" not in seen["prompt"]   # the regex got it
        assert "supervises" in seen["prompt"]              # no regex ever attempts this one
    finally:
        conn.close()


def test_a_model_cannot_invent_a_column(tmp_path):
    """D-073 bound 1 — a field the export has no descriptor for is dropped, not added."""
    conn, snaps, fetcher, run_id, t = _harness(tmp_path)
    try:
        stats = _dive(conn, snaps, fetcher, run_id, t, complete=_completer(
            {"claims": [{"field": "lab_wellbeing", "value": "great",
                            "quote": "Professor A. Example, Department of Computing"}]}))
        assert stats.get("model_claims") is None
        assert _live(conn, "lab_wellbeing") is None
    finally:
        conn.close()


def test_the_extraction_key_is_never_returned_in_an_error(tmp_path):
    """The key goes into a header and nowhere else — not into a message a log could catch."""
    def poster(_url, _payload, _headers, *, timeout=None):
        return 401, "unauthorized"
    complete = llm_client.completer_from_env(
        {"SUPERVISORLY_EXTRACT_KEY": "sk-secret-value"}, transport=poster)
    with pytest.raises(RuntimeError) as e:
        complete("prompt")
    assert "sk-secret-value" not in str(e.value)
    assert str(e.value) == "http 401"


def test_the_page_text_sent_to_the_model_is_capped(tmp_path):
    """D-073 bound 4 — the same cap page_extract.js already applies in-page."""
    big = "<html><body><p>" + ("supervision. " * 4000) + "</p></body></html>"
    seen = {}

    def spy(prompt):
        seen["n"] = len(prompt)
        return json.dumps({"claims": []})

    conn, snaps, fetcher, run_id, t = _harness(tmp_path, html=big)
    try:
        _dive(conn, snaps, fetcher, run_id, t, complete=spy)
        assert seen["n"] < llm_claims.MAX_PAGE_CHARS + 4000   # page cap + prompt scaffolding
    finally:
        conn.close()
