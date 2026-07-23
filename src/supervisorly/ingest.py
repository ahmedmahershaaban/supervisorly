"""The md-ingester — the receiving half of the human rung (D-043, D-051).

The student runs the ``chrome-prompt-generator``'s prompt in Claude for Chrome, and pastes
back Markdown in the **one shared grammar** (``extract.md_grammar``). This module parses that
Markdown and records each block as a normal Claim — human-returned data is *not privileged*:
it is sourced, dated, and marked ``extractor = 'human-assisted (Claude for Chrome)'`` (D-043).

A filled field **supersedes** whatever was there before (typically a ``blocked`` placeholder),
so the previously-open gap closes without re-fetching anything. This is what makes an abandoned
Phase-3 resumable: the run already finalised a dashboard; the later return just fills gaps.
"""

from __future__ import annotations

import sqlite3

from .extract import md_grammar
from .model import claims

HUMAN_EXTRACTOR = "human-assisted (Claude for Chrome)"


def ingest_md(conn: sqlite3.Connection, md_text: str) -> dict:
    """Parse a Phase-3 Markdown return and record its claims. Never fetches.

    Returns ``{"recorded": n, "rejected": [reasons], "entity": (kind, ref)}``.
    """
    doc = md_grammar.parse(md_text)                 # raises MDParseError on malformed input
    recorded = 0
    rejected: list[str] = []
    for c in md_grammar.to_claim_dicts(doc):
        source_id = None
        if c.get("source_url"):
            # the walled page the student retrieved by hand (X/LinkedIn/Scholar/…) — logged
            # as a human-assisted source so the claim is still fully provenance-carrying.
            source_id = claims.record_web_source(
                conn, c["source_url"], source_tier="human_assisted", robots_allowed=None,
            )
        rec = claims.record_claim(
            conn,
            entity_kind=c["entity_kind"], entity_id=c["entity_id"], field=c["field"],
            state=c["state"], value=c.get("value"), quote=c.get("quote"),
            source_id=source_id, observed_at=c.get("observed_at"),
            extractor_agent=HUMAN_EXTRACTOR, confidence=c.get("confidence"),
        )
        if rec.ok:
            # the human answer becomes the single live head for this field (closes the gap)
            claims.supersede_prior(conn, c["entity_kind"], c["entity_id"], c["field"],
                                   rec.claim_id)
            recorded += 1
        else:
            rejected.append(f"{c['field']}: {rec.rejected}")
    return {"recorded": recorded, "rejected": rejected,
            "entity": (doc.target_kind, doc.target_ref)}
