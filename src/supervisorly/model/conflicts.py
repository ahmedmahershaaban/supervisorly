"""Recording disagreement between sources (D-010).

The design has always said: *when two sources disagree, both claims are kept and the
disagreement is recorded with a deterministic resolution policy, instead of silent
last-write-wins.* The `conflict` table has existed since the first schema. Nothing ever
wrote a row into it — so until now the second source simply overwrote the first and the
promise was prose only.

What this module adds is the missing half. When a fresh **value** claim disagrees with the
live claim for the same ``(entity, field)``:

1. a `conflict` row is written, naming both claims — the disagreement is on the record
   even when the policy can pick a winner, so the losing source is never silently dropped;
2. a deterministic policy decides which claim is the head:

   * **higher tier wins** — an institutional/personal page beats an aggregator. Provenance,
     not recency, is the first question.
   * **more recent wins, within a tier** — two equally-trusted sources, the newer one leads.
   * **unresolved** — same tier and no way to order them (equal or missing timestamps).
     The conflict stays ``open``.

3. the loser is superseded rather than deleted, so `claims_for` still returns one head and
   the full history remains queryable.

An unresolved conflict still keeps the newer claim as the head, because the export needs a
single value per field — but it is `open` in the table, which is what makes it *not silent*.
That is the distinction the design draws: a contested field is allowed, a hidden one is not.

Verification proves fidelity, not truth (see `claims.py`), so this module never decides who
is *right* — only which source the product leads with, on rules a reader can check.
"""

from __future__ import annotations

from .db import new_id, utcnow

#: Coarse trust ranking. Higher wins. This must cover **every** tier the schema's
#: ``web_source.source_tier`` CHECK allows — a tier missing here would rank 0 and lose to an
#: aggregator, which is how a registry could quietly be treated as less trustworthy than a
#: scraped listing. `test_conflicts.py` asserts the two vocabularies match, so adding a tier
#: to the schema without ranking it fails the suite.
#:
#: The three "official" tiers sit level on purpose. Which of them is authoritative is
#: field-dependent — a registry knows identity best, a professor's own page knows recruiting
#: best — and encoding that guess here would be a judgement dressed as a rule. Level means
#: recency breaks the tie, and a genuine standoff stays `open` for a human.
TIER_RANK: dict[str, int] = {
    "official_institutional": 3,   # the professor's / department's own page
    "official_api": 3,             # OpenAlex, ROR — the structured front door
    "cris": 3,                     # an institution's own research information system
    "registry": 3,                 # ORCID and friends — identity, self-maintained
    "agent_browser": 2,            # the professor's own walled page, via the student's session
    "human_assisted": 2,           # sourced and dated, but not privileged (D-043)
    "open_social": 2,              # advertised, self-stated (Bluesky, Mastodon)
    "community_unverified": 1,     # aggregators — useful, never authoritative
}

#: The rule that decided a conflict. Recorded in the returned dict for callers/tests;
#: the table stores only the outcome, so these names are the vocabulary for explaining it.
RULE_TIER = "higher_tier_wins"
RULE_RECENT = "more_recent_wins"
RULE_UNRESOLVED = "unresolved"


def _rank(tier: str | None) -> int:
    return TIER_RANK.get(tier or "", 0)


def _claim_row(conn, claim_id: str) -> dict | None:
    row = conn.execute(
        "SELECT c.claim_id, c.value, c.state, c.observed_at, c.created_at, "
        "w.source_tier AS tier FROM claim c "
        "LEFT JOIN web_source w ON c.source_id = w.source_id WHERE c.claim_id=?",
        (claim_id,),
    ).fetchone()
    return dict(row) if row else None


def _live_value_claims(conn, entity_kind: str, entity_id: str, field: str) -> list[dict]:
    rows = conn.execute(
        "SELECT c.claim_id, c.value, c.state, c.observed_at, c.created_at, "
        "w.source_tier AS tier FROM claim c "
        "LEFT JOIN web_source w ON c.source_id = w.source_id "
        "WHERE c.entity_kind=? AND c.entity_id=? AND c.field=? "
        "AND c.state='value' AND c.superseded_by IS NULL",
        (entity_kind, entity_id, field),
    ).fetchall()
    return [dict(r) for r in rows]


def _order_key(c: dict) -> str:
    """Prefer the source's own observation time; fall back to when we wrote it."""
    return c.get("observed_at") or c.get("created_at") or ""


def decide(new: dict, prior: dict) -> tuple[str, str]:
    """Which claim leads, and under which rule. Returns ``(winner_claim_id, rule)``.

    Pure and total: given two claim rows it always returns a head, so a caller never has to
    handle "no decision". ``RULE_UNRESOLVED`` means the tie was broken for display only and
    the disagreement genuinely needs a human.
    """
    rn, rp = _rank(new.get("tier")), _rank(prior.get("tier"))
    if rn != rp:
        return (new["claim_id"] if rn > rp else prior["claim_id"]), RULE_TIER

    kn, kp = _order_key(new), _order_key(prior)
    if kn and kp and kn != kp:
        return (new["claim_id"] if kn > kp else prior["claim_id"]), RULE_RECENT

    # same tier, no usable ordering — lead with the newer write, but say it is unresolved
    return new["claim_id"], RULE_UNRESOLVED


def record_conflict(conn, *, entity_kind: str, entity_id: str, field: str,
                    claim_a: str, claim_b: str, resolution_state: str) -> str:
    conflict_id = new_id("conflict")
    conn.execute(
        "INSERT INTO conflict(conflict_id, entity_kind, entity_id, field, claim_a, claim_b, "
        "resolution_state, created_at) VALUES(?,?,?,?,?,?,?,?)",
        (conflict_id, entity_kind, entity_id, field, claim_a, claim_b,
         resolution_state, utcnow()),
    )
    return conflict_id


def detect_for_claim(conn, *, entity_kind: str, entity_id: str, field: str,
                     claim_id: str) -> list[dict]:
    """Compare a freshly inserted value claim against the live ones for the same field.

    Returns one dict per conflict recorded: ``{conflict_id, other, winner, rule,
    resolution_state}``. An empty list is the normal case — agreement, or nothing to
    compare against. Never raises on a missing/odd row; a conflict check must not be able
    to fail a scan.
    """
    new = _claim_row(conn, claim_id)
    if not new or new.get("state") != "value":
        return []

    out: list[dict] = []
    for prior in _live_value_claims(conn, entity_kind, entity_id, field):
        if prior["claim_id"] == claim_id:
            continue
        if prior.get("value") == new.get("value"):
            continue                       # agreement — corroboration, not conflict
        winner, rule = decide(new, prior)
        loser = prior["claim_id"] if winner == claim_id else claim_id
        state = "open" if rule == RULE_UNRESOLVED else (
            "resolved_a" if winner == claim_id else "resolved_b")
        cid = record_conflict(conn, entity_kind=entity_kind, entity_id=entity_id,
                              field=field, claim_a=claim_id, claim_b=prior["claim_id"],
                              resolution_state=state)
        conn.execute("UPDATE claim SET superseded_by=? WHERE claim_id=?", (winner, loser))
        out.append({"conflict_id": cid, "other": prior["claim_id"], "winner": winner,
                    "rule": rule, "resolution_state": state})
    if out:
        conn.commit()
    return out


def open_conflicts(conn, entity_kind: str | None = None,
                   entity_id: str | None = None) -> list[dict]:
    """Conflicts a human still needs to look at — the honest 'contested' set."""
    sql = "SELECT * FROM conflict WHERE resolution_state='open'"
    args: list = []
    if entity_kind is not None:
        sql += " AND entity_kind=?"
        args.append(entity_kind)
    if entity_id is not None:
        sql += " AND entity_id=?"
        args.append(entity_id)
    return [dict(r) for r in conn.execute(sql + " ORDER BY created_at", args).fetchall()]


def conflicts_for(conn, entity_kind: str, entity_id: str) -> list[dict]:
    """Every recorded disagreement for one entity, resolved or not."""
    return [dict(r) for r in conn.execute(
        "SELECT * FROM conflict WHERE entity_kind=? AND entity_id=? ORDER BY created_at",
        (entity_kind, entity_id),
    ).fetchall()]
