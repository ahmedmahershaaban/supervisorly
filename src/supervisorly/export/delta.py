"""Re-scan delta — "what changed since last time" (Phase L6).

A repeat/scheduled scan reuses the warm cache (≈0 re-extraction on unchanged pages, cost §3b-i);
this computes the honest diff between the previous export and the current one so the student sees
only what moved: **new/removed professors** and **changed fields**, with two review highlights —
*recruiting signal changed* (any change to the raw recruiting candidate — a signal to review, **not**
an assertion the professor is now recruiting; open/closed is the Stage-2 LLM's call) and
*newly-published deadlines*. Pure function over two export dicts; no fetching, no LLM.
"""

from __future__ import annotations


def _by_id(export: dict | None) -> dict:
    return {p["id"]: p for p in (export or {}).get("professors", [])}


def _name(p: dict) -> str:
    return p.get("name") or p.get("id")


def compute_delta(previous: dict | None, current: dict) -> dict:
    """Return what changed between ``previous`` and ``current`` exports.

    ``{new_professors, removed_professors, changed_fields, newly_recruiting, newly_deadline,
    unchanged}``. A first-ever run (``previous`` None) reports every professor as new.
    """
    prev, curr = _by_id(previous), _by_id(current)
    new = [_name(curr[i]) for i in curr if i not in prev]
    removed = [_name(prev[i]) for i in prev if i not in curr]

    changed_fields = []
    recruiting_changed = []
    newly_deadline = []
    for i in curr:
        if i not in prev:
            continue
        for fid, env in curr[i].get("fields", {}).items():
            penv = prev[i].get("fields", {}).get(fid, {})
            if env.get("state") != penv.get("state") or env.get("value") != penv.get("value"):
                change = {"professor": _name(curr[i]), "field": fid,
                          "from_state": penv.get("state"), "to_state": env.get("state"),
                          "value": env.get("value")}
                changed_fields.append(change)
                # The recruiting_signal field is a *candidate sentence*, not an open/closed
                # classification (that's the Stage-2 LLM's job, D-009/D-021). So we flag it as a
                # signal to REVIEW on ANY change — never assert "now recruiting" (a negative
                # sentence like "not accepting students" must not read as newly-open).
                if fid == "recruiting_signal":
                    recruiting_changed.append(_name(curr[i]))
                # a deadline DATE appearing is a concrete actionable event (a date is a date)
                if fid == "deadline" and env.get("state") == "value" and penv.get("state") != "value":
                    newly_deadline.append({"professor": _name(curr[i]), "deadline": env.get("value")})

    return {
        "new_professors": new,
        "removed_professors": removed,
        "changed_fields": changed_fields,
        "recruiting_changed": recruiting_changed,   # review these — NOT "now recruiting"
        "newly_deadline": newly_deadline,
        "unchanged": not (new or removed or changed_fields),
    }
