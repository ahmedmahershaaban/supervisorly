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
) -> RecordResult:
    """Insert a claim, enforcing quote-in-snapshot for tool/LLM value claims.

    Returns a ``RecordResult`` — ``claim_id`` on success, or ``rejected`` with a reason.
    Rejection is normal flow (a hallucination filtered out), not an exception.
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
    return RecordResult(claim_id)


def claims_for(conn, entity_kind: str, entity_id: str) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM claim WHERE entity_kind=? AND entity_id=? AND superseded_by IS NULL",
        (entity_kind, entity_id),
    ).fetchall()
    return [dict(r) for r in rows]
