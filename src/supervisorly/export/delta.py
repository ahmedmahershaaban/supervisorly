"""Re-scan delta — "what changed since last time" (Phase L6).

A repeat/scheduled scan reuses the warm cache (≈0 re-extraction on unchanged pages, cost §3b-i);
this computes the honest diff between the previous export and the current one so the student sees
only what moved: **new/removed professors** and **changed fields**, with two review highlights —
*recruiting signal changed* (any change to the raw recruiting candidate — a signal to review, **not**
an assertion the professor is now recruiting; open/closed is the Stage-2 LLM's call) and
*newly-published deadlines*. Pure function over two export dicts; no fetching, no LLM.
"""

from __future__ import annotations

# Confidences that read as a FIRM deadline on the dashboard (mirrors FIRM_CONF in
# dashboard.py, D-061). A watch→firm flip is the "newly-published deadline" event a
# re-scan exists to surface, even when the date string itself didn't change.
FIRM_CONFIDENCE = {"quoted_official", "derived"}


def _by_id(export: dict | None) -> dict:
    return {p["id"]: p for p in (export or {}).get("professors", [])}


def _name(p: dict) -> str:
    return p.get("name") or p.get("id")


def compute_delta(previous: dict | None, current: dict) -> dict:
    """Return what changed between ``previous`` and ``current`` exports.

    ``{new_professors, removed_professors, changed_fields, recruiting_changed,
    newly_deadline, renamed, schema_mismatch, unchanged}``. A first-ever run
    (``previous`` None) reports every professor as new. Per-field comparison covers
    state, value AND confidence, over the UNION of field keys — a vanished field
    surfaces as a removal instead of being silently dropped. A schema_version mismatch
    is reported up front (``schema_mismatch``) and per-field diffing is skipped: a
    schema-wide field addition would otherwise flood phantom from_state: None changes.
    """
    prev, curr = _by_id(previous), _by_id(current)
    new = [_name(curr[i]) for i in curr if i not in prev]
    removed = [_name(prev[i]) for i in prev if i not in curr]

    schema_mismatch = None
    if previous is not None:
        prev_v, curr_v = previous.get("schema_version"), current.get("schema_version")
        if prev_v != curr_v:
            schema_mismatch = {"previous": prev_v, "current": curr_v}

    changed_fields = []
    recruiting_changed = []
    newly_deadline = []
    renamed = [{"id": i, "from": _name(prev[i]), "to": _name(curr[i])}
               for i in curr if i in prev and _name(prev[i]) != _name(curr[i])]
    if schema_mismatch is None:
        for i in curr:
            if i not in prev:
                continue
            prev_fields = prev[i].get("fields", {})
            curr_fields = curr[i].get("fields", {})
            for fid in prev_fields.keys() | curr_fields.keys():
                env = curr_fields.get(fid, {})      # missing on one side = absent there
                penv = prev_fields.get(fid, {})
                if (env.get("state") != penv.get("state")
                        or env.get("value") != penv.get("value")
                        or env.get("confidence") != penv.get("confidence")):
                    change = {"professor": _name(curr[i]), "field": fid,
                              "from_state": penv.get("state"),
                              "to_state": env.get("state"),
                              "value": env.get("value")}
                    changed_fields.append(change)
                    # The recruiting_signal field is a *candidate sentence*, not an open/closed
                    # classification (that's the Stage-2 LLM's job, D-009/D-021). So we flag it
                    # as a signal to REVIEW on ANY change — never assert "now recruiting" (a
                    # negative sentence like "not accepting students" must not read as newly-open).
                    if fid == "recruiting_signal":
                        recruiting_changed.append(_name(curr[i]))
                    # a deadline DATE appearing — or flipping watch→firm with the same date —
                    # is a concrete actionable event (a date is a date, D-061)
                    if fid == "deadline" and env.get("state") == "value" and (
                            penv.get("state") != "value"
                            or (penv.get("confidence") not in FIRM_CONFIDENCE
                                and env.get("confidence") in FIRM_CONFIDENCE)):
                        newly_deadline.append({"professor": _name(curr[i]),
                                               "deadline": env.get("value")})

    return {
        "new_professors": new,
        "removed_professors": removed,
        "changed_fields": changed_fields,
        "recruiting_changed": recruiting_changed,   # review these — NOT "now recruiting"
        "newly_deadline": newly_deadline,
        "renamed": renamed,
        "schema_mismatch": schema_mismatch,         # not None → per-field diff skipped
        "unchanged": not (new or removed or changed_fields or renamed),
    }
