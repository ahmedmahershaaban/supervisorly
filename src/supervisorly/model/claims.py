"""Recording claims — where the anti-hallucination guarantee is enforced (D-010).

Every field is a Claim. A **value** claim from a tool/LLM extractor must carry a quote
that is actually present in the stored snapshot; if it isn't, the claim is **rejected
before it is ever written**. This is a code control, not a prose promise — the corpus's
"never invent" instruction was in force when it produced a hallucinated co-authorship.

Verification proves *fidelity* (the model didn't invent text relative to the page), not
*truth*. Human-assisted claims (D-043) have no snapshot to verify against — they are
sourced and dated but not privileged.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..fetch.normalize import quote_in_snapshot
from .db import new_id, utcnow

VALID_STATES = {"value", "searched_absent", "never_attempted", "blocked"}
VALID_CONFIDENCE = {"quoted_official", "derived", "inferred", "unconfirmed", "action_needed"}


@dataclass
class RecordResult:
    claim_id: str | None
    rejected: str | None = None  # reason, when claim_id is None

    @property
    def ok(self) -> bool:
        return self.claim_id is not None


def _is_human(extractor: str | None) -> bool:
    return bool(extractor) and extractor.startswith("human-assisted")


def record_claim(
    conn,
    *,
    entity_kind: str,
    entity_id: str,
    field: str,
    state: str = "value",
    value=None,
    quote: str | None = None,
    source_id: str | None = None,
    snapshot_hash: str | None = None,
    snapshot_html: str | None = None,
    observed_at: str | None = None,
    extractor_agent: str = "deterministic",
    extractor_model: str | None = None,
    prompt_version: str | None = None,
    schema_version: str | None = None,
    confidence: str | None = None,
    verify: bool = True,
    detect_conflicts: bool = True,
) -> RecordResult:
    """Insert a claim, enforcing quote-in-snapshot for tool/LLM value claims.

    Returns a ``RecordResult`` — ``claim_id`` on success, or ``rejected`` with a reason.
    Rejection is normal flow (a hallucination filtered out), not an exception.

    A successful **value** claim is then compared against the live claim for the same
    ``(entity, field)``; a disagreement is recorded in the ``conflict`` table and the loser
    superseded (``conflicts.detect_for_claim``). That happens *here*, at the one choke point
    every claim passes through, for the same reason the quote gate does: a guarantee a
    caller has to remember is not a guarantee. ``detect_conflicts=False`` is for tests that
    want to build history by hand.
    """
    if state not in VALID_STATES:
        return RecordResult(None, f"invalid state {state!r}")
    if confidence is not None and confidence not in VALID_CONFIDENCE:
        return RecordResult(None, f"invalid confidence {confidence!r}")

    if state == "value":
        if value is None:
            return RecordResult(None, "value state requires a value")
        # A tool/LLM value claim must be quote-verified against its snapshot.
        if verify and not _is_human(extractor_agent):
            if snapshot_html is None:
                return RecordResult(None, "value claim has no snapshot to verify against")
            if not quote:
                return RecordResult(None, "value claim has no quote to verify (D-010)")
            if not quote_in_snapshot(quote, snapshot_html):
                return RecordResult(None, "quote not found in snapshot — rejected (D-010)")
        # human-assisted value claims: sourced+dated, no snapshot to verify (D-043)

    claim_id = new_id("claim")
    import json
    conn.execute(
        "INSERT INTO claim(claim_id, entity_kind, entity_id, field, state, value, quote, "
        "source_id, snapshot_hash, observed_at, extractor_agent, extractor_model, "
        "prompt_version, schema_version, confidence, created_at) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (claim_id, entity_kind, entity_id, field, state,
         json.dumps(value) if value is not None else None,
         quote, source_id, snapshot_hash, observed_at, extractor_agent, extractor_model,
         prompt_version, schema_version, confidence, utcnow()),
    )
    conn.commit()
    if detect_conflicts and state == "value":
        from .conflicts import detect_for_claim  # local: avoids a model-layer import cycle
        detect_for_claim(conn, entity_kind=entity_kind, entity_id=entity_id,
                         field=field, claim_id=claim_id)
    return RecordResult(claim_id)


def record_web_source(
    conn,
    url: str,
    *,
    snapshot_hash: str | None = None,
    http_status: int | None = None,
    source_tier: str | None = None,
    robots_allowed: bool | None = None,
) -> str:
    """Record the page a claim came from; returns its source_id (claims reference this)."""
    source_id = new_id("src")
    conn.execute(
        "INSERT INTO web_source(source_id, url, fetched_at, http_status, snapshot_hash, "
        "source_tier, robots_allowed) VALUES(?,?,?,?,?,?,?)",
        (source_id, url, utcnow(), http_status, snapshot_hash, source_tier,
         None if robots_allowed is None else int(robots_allowed)),
    )
    conn.commit()
    return source_id


def supersede_prior(conn, entity_kind: str, entity_id: str, field: str,
                    keep_claim_id: str) -> int:
    """Mark every other live claim for (entity, field) as superseded by ``keep_claim_id``.

    Used when a fresh claim replaces an earlier head — e.g. a human-rung answer filling a
    previously ``blocked`` field. Keeps the history (append-only) while making the new claim
    the single head that ``claims_for`` returns. Returns the number superseded.
    """
    cur = conn.execute(
        "UPDATE claim SET superseded_by=? WHERE entity_kind=? AND entity_id=? AND field=? "
        "AND claim_id != ? AND superseded_by IS NULL",
        (keep_claim_id, entity_kind, entity_id, field, keep_claim_id),
    )
    conn.commit()
    return cur.rowcount


def live_value(conn, entity_kind: str, entity_id: str, field: str) -> bool:
    """True if a non-superseded ``value`` claim already exists for (entity, field).

    Guards against a later no-evidence pass (``searched_absent``/``blocked``) clobbering a real
    value we already hold — e.g. a monthly re-scan must not erase a human-rung answer (D-046/049).
    """
    row = conn.execute(
        "SELECT 1 FROM claim WHERE entity_kind=? AND entity_id=? AND field=? "
        "AND state='value' AND superseded_by IS NULL LIMIT 1",
        (entity_kind, entity_id, field),
    ).fetchone()
    return row is not None


def live_value_is_human(conn, entity_kind: str, entity_id: str, field: str) -> bool:
    """True if the field's live ``value`` head is **human-assisted** (D-043).

    A human-rung answer is never clobbered by a later absence; a stale *deterministic* value is —
    a successful re-fetch whose re-extraction affirmatively finds nothing is a verified removal,
    recorded as ``searched_absent`` so the delta surfaces it (live audit-5).
    """
    row = conn.execute(
        "SELECT extractor_agent FROM claim WHERE entity_kind=? AND entity_id=? AND field=? "
        "AND state='value' AND superseded_by IS NULL LIMIT 1",
        (entity_kind, entity_id, field),
    ).fetchone()
    return row is not None and _is_human(row["extractor_agent"])


def live_reached(conn, entity_kind: str, entity_id: str, field: str) -> bool:
    """True if a live claim shows the field was actually reached (``value`` or
    ``searched_absent``). A later failed fetch (``blocked``) must not downgrade a reached
    field — we already know more than "couldn't reach it" (D-046)."""
    row = conn.execute(
        "SELECT 1 FROM claim WHERE entity_kind=? AND entity_id=? AND field=? "
        "AND state IN ('value','searched_absent') AND superseded_by IS NULL LIMIT 1",
        (entity_kind, entity_id, field),
    ).fetchone()
    return row is not None


def claims_for(conn, entity_kind: str, entity_id: str) -> list[dict]:
    import json
    rows = conn.execute(
        "SELECT c.*, w.url AS source_url FROM claim c "
        "LEFT JOIN web_source w ON c.source_id = w.source_id "
        "WHERE c.entity_kind=? AND c.entity_id=? AND c.superseded_by IS NULL",
        (entity_kind, entity_id),
    ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        # value is stored JSON-encoded; decode to native for callers/export
        if d.get("value") is not None:
            try:
                d["value"] = json.loads(d["value"])
            except (ValueError, TypeError):
                pass
        out.append(d)
    return out
