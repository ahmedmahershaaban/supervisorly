"""D-010 conflicts: when two sources disagree, BOTH are kept and the disagreement recorded.

The `conflict` table shipped with the first schema and nothing ever wrote to it, so the
second source silently overwrote the first. These tests pin the behaviour that closes that
gap — including the case the design cares about most: a disagreement the policy cannot
settle must stay visibly `open`, not be quietly decided.
"""

from __future__ import annotations

import sqlite3

import pytest

from supervisorly.model import claims, conflicts
from supervisorly.model.db import open_db

SNAP = "<html><body><p>Accepting PhD students for Fall 2027. Contact the lab.</p></body></html>"
QUOTE = "Accepting PhD students for Fall 2027."


@pytest.fixture
def conn(tmp_path):
    c = open_db(tmp_path / "t.sqlite")
    yield c
    c.close()


def _src(conn, url: str, tier: str) -> str:
    return claims.record_web_source(conn, url, source_tier=tier)


def _claim(conn, value, *, tier="official_institutional", url=None, observed_at=None,
           field="recruiting_state", entity_id="p1"):
    sid = _src(conn, url or f"https://x.test/{tier}", tier)
    return claims.record_claim(
        conn, entity_kind="person", entity_id=entity_id, field=field,
        value=value, quote=QUOTE, snapshot_html=SNAP, source_id=sid,
        observed_at=observed_at, extractor_agent="deterministic",
    )


def test_agreement_is_not_a_conflict(conn):
    """Two sources saying the same thing is corroboration — it must not create a row."""
    a = _claim(conn, "open", tier="official_institutional")
    b = _claim(conn, "open", tier="community_unverified")
    assert a.ok and b.ok
    assert conflicts.conflicts_for(conn, "person", "p1") == []
    # and both remain live: agreement never supersedes
    live = [r["claim_id"] for r in conflicts._live_value_claims(conn, "person", "p1",
                                                                "recruiting_state")]
    assert set(live) == {a.claim_id, b.claim_id}


def test_an_official_page_beats_an_aggregator_and_the_disagreement_is_recorded(conn):
    """higher_tier_wins — provenance is the first question, not recency."""
    agg = _claim(conn, "closed", tier="community_unverified")
    off = _claim(conn, "open", tier="official_institutional")

    (c,) = conflicts.conflicts_for(conn, "person", "p1")
    assert c["field"] == "recruiting_state"
    assert {c["claim_a"], c["claim_b"]} == {agg.claim_id, off.claim_id}
    assert c["resolution_state"] == "resolved_a"        # the new (official) claim leads

    # the loser is superseded, never deleted — the disagreement stays queryable
    row = conn.execute("SELECT superseded_by FROM claim WHERE claim_id=?",
                       (agg.claim_id,)).fetchone()
    assert row["superseded_by"] == off.claim_id
    assert conn.execute("SELECT COUNT(*) c FROM claim").fetchone()["c"] == 2


def test_a_stale_official_page_loses_to_a_newer_one(conn):
    """more_recent_wins — inside one tier, the fresher observation leads."""
    old = _claim(conn, "closed", observed_at="2026-01-01T00:00:00Z")
    new = _claim(conn, "open", observed_at="2026-07-01T00:00:00Z")
    (c,) = conflicts.conflicts_for(conn, "person", "p1")
    assert c["resolution_state"] == "resolved_a"
    assert conn.execute("SELECT superseded_by FROM claim WHERE claim_id=?",
                        (old.claim_id,)).fetchone()["superseded_by"] == new.claim_id


def test_an_older_claim_arriving_late_does_not_win(conn):
    """Order of arrival must not beat order of observation — otherwise it is last-write-wins
    wearing a policy's clothes."""
    new = _claim(conn, "open", observed_at="2026-07-01T00:00:00Z")
    old = _claim(conn, "closed", observed_at="2026-01-01T00:00:00Z")
    (c,) = conflicts.conflicts_for(conn, "person", "p1")
    assert c["resolution_state"] == "resolved_b"        # the PRIOR claim still leads
    assert conn.execute("SELECT superseded_by FROM claim WHERE claim_id=?",
                        (old.claim_id,)).fetchone()["superseded_by"] == new.claim_id


def test_an_unsettleable_disagreement_stays_open(conn):
    """Same tier, no usable ordering: the head is chosen so the export has a value, but the
    conflict is `open` — which is the whole point. A contested field is allowed; a hidden
    one is not."""
    # The SAME observed_at on both, stated explicitly. Relying on two inserts landing in
    # the same clock second made this flaky: utcnow() has second resolution, so two claims
    # usually share a timestamp (unorderable -> open) but occasionally straddle a boundary
    # (orderable -> resolved by recency) and the test failed for a reason that had nothing
    # to do with the behaviour it is describing.
    same = "2026-03-01T12:00:00+00:00"
    a = _claim(conn, "open", observed_at=same)
    b = _claim(conn, "closed", observed_at=same)
    (c,) = conflicts.conflicts_for(conn, "person", "p1")
    assert c["resolution_state"] == "open"
    assert conflicts.open_conflicts(conn) and conflicts.open_conflicts(conn)[0]["conflict_id"] == c["conflict_id"]
    assert {c["claim_a"], c["claim_b"]} == {a.claim_id, b.claim_id}


def test_an_unknown_tier_never_outranks_a_known_one():
    """Fail closed: an unrecognised provenance is the least trusted, not the most.
    (`decide` is pure, so this needs no database — and the schema's CHECK would reject a
    bogus tier long before it reached here, which is the belt to this braces.)"""
    assert conflicts.decide({"claim_id": "new", "tier": "mystery_tier"},
                            {"claim_id": "old", "tier": "community_unverified"}) \
        == ("old", conflicts.RULE_TIER)


def test_every_tier_the_schema_allows_is_ranked():
    """The ranking must cover the schema's whole vocabulary. A tier added to the CHECK but
    not ranked here would score 0 and lose to an aggregator — a registry silently treated as
    less trustworthy than a scraped listing. This is the test that makes that impossible."""
    import re
    from pathlib import Path
    sql = (Path(__file__).resolve().parents[1]
           / "src/supervisorly/model/schema.sql").read_text(encoding="utf-8")
    block = re.search(r"source_tier\s+TEXT[^;]*?CHECK\s*\((.*?)\)\s*,", sql, re.S)
    assert block, "could not find the source_tier CHECK in schema.sql"
    allowed = set(re.findall(r"'([a-z_]+)'", block.group(1)))
    assert allowed, "parsed no tiers out of the CHECK constraint"
    assert allowed == set(conflicts.TIER_RANK), (
        f"schema-only: {sorted(allowed - set(conflicts.TIER_RANK))} | "
        f"ranking-only: {sorted(set(conflicts.TIER_RANK) - allowed)}")


def test_an_aggregator_never_outranks_any_official_tier():
    """The rule the product leans on most: provenance beats recency."""
    for official in ("official_institutional", "official_api", "cris", "registry"):
        winner, rule = conflicts.decide(
            {"claim_id": "agg", "tier": "community_unverified"},
            {"claim_id": "off", "tier": official})
        assert (winner, rule) == ("off", conflicts.RULE_TIER), official


def test_conflicts_are_scoped_to_one_field_and_one_entity(conn):
    """A different field, or a different professor, is not a disagreement."""
    _claim(conn, "open", field="recruiting_state")
    _claim(conn, "closed", field="funding_state")
    _claim(conn, "closed", entity_id="p2")
    assert conflicts.conflicts_for(conn, "person", "p1") == []
    assert conflicts.conflicts_for(conn, "person", "p2") == []


def test_non_value_states_never_conflict(conn):
    """`searched_absent` is an honest answer, not a competing value (D-037)."""
    _claim(conn, "open")
    r = claims.record_claim(conn, entity_kind="person", entity_id="p1",
                            field="recruiting_state", state="searched_absent")
    assert r.ok
    assert conflicts.conflicts_for(conn, "person", "p1") == []


def test_detection_can_be_switched_off_for_hand_built_history(conn):
    a = _claim(conn, "open")
    sid = _src(conn, "https://x.test/2", "official_institutional")
    b = claims.record_claim(conn, entity_kind="person", entity_id="p1",
                            field="recruiting_state", value="closed", quote=QUOTE,
                            snapshot_html=SNAP, source_id=sid, detect_conflicts=False)
    assert a.ok and b.ok
    assert conflicts.conflicts_for(conn, "person", "p1") == []


def test_a_conflict_check_can_never_fail_a_scan(conn, monkeypatch):
    """The guarantee is worth nothing if recording it can break the run that produced it."""
    a = _claim(conn, "open")
    assert a.ok
    monkeypatch.setattr(conflicts, "_live_value_claims",
                        lambda *_a, **_k: (_ for _ in ()).throw(sqlite3.Error("boom")))
    with pytest.raises(sqlite3.Error):
        conflicts.detect_for_claim(conn, entity_kind="person", entity_id="p1",
                                   field="recruiting_state", claim_id=a.claim_id)
