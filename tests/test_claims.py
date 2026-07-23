"""Phase D DoD: the anti-hallucination control is real — a value claim whose quote is
not in the snapshot is rejected before storage (D-010); the four states are produced
correctly; human-assisted claims are accepted without a snapshot (D-043)."""

from supervisorly.model import claims
from supervisorly.model.db import open_db

SNAP = ("<html><body><main>"
        "<p>I am recruiting two PhD students for Fall 2027.</p>"
        "</main></body></html>")


def test_real_quote_is_recorded():
    conn = open_db()
    r = claims.record_claim(
        conn, entity_kind="person", entity_id="p1", field="recruiting_status",
        value="recruiting Fall 2027",
        quote="I am recruiting two PhD students for Fall 2027.",
        snapshot_hash="h1", snapshot_html=SNAP,
        extractor_agent="recruiting-analyst", confidence="quoted_official",
    )
    assert r.ok
    stored = claims.claims_for(conn, "person", "p1")
    assert len(stored) == 1 and stored[0]["field"] == "recruiting_status"


def test_hallucinated_quote_is_rejected():
    """The core guarantee: a fabricated quote never reaches the store."""
    conn = open_db()
    r = claims.record_claim(
        conn, entity_kind="person", entity_id="p1", field="funding",
        value="has 3 funded postdoc slots",
        quote="I have three fully funded postdoc positions in quantum gravity.",
        snapshot_hash="h1", snapshot_html=SNAP, extractor_agent="eligibility-analyst",
    )
    assert not r.ok
    assert "not found in snapshot" in r.rejected
    assert claims.claims_for(conn, "person", "p1") == []  # nothing stored


def test_value_without_quote_is_rejected():
    conn = open_db()
    r = claims.record_claim(
        conn, entity_kind="person", entity_id="p1", field="x", value="y",
        snapshot_hash="h1", snapshot_html=SNAP, extractor_agent="recruiting-analyst",
    )
    assert not r.ok and "quote" in r.rejected


def test_searched_absent_needs_no_quote():
    conn = open_db()
    r = claims.record_claim(
        conn, entity_kind="person", entity_id="p1", field="twitter_recruiting",
        state="searched_absent", extractor_agent="recruiting-analyst",
    )
    assert r.ok
    assert claims.claims_for(conn, "person", "p1")[0]["state"] == "searched_absent"


def test_human_assisted_recorded_without_snapshot():
    """Phase-3 human data is sourced + dated but has no snapshot to verify (D-043)."""
    conn = open_db()
    r = claims.record_claim(
        conn, entity_kind="person", entity_id="p1", field="recruiting_status",
        value="recruiting Fall 2027",
        quote="I'm looking for PhD students (from X, read in my own browser)",
        extractor_agent="human-assisted (Claude for Chrome)",
    )
    assert r.ok


def test_invalid_state_and_confidence_rejected():
    conn = open_db()
    assert not claims.record_claim(
        conn, entity_kind="person", entity_id="p1", field="x", state="weird"
    ).ok
    assert not claims.record_claim(
        conn, entity_kind="person", entity_id="p1", field="x", value="y",
        quote="q", snapshot_html=SNAP, confidence="totally_sure"
    ).ok
