"""Re-scan delta — "what changed since last time" (Phase L6).

A repeat/scheduled scan reuses the warm cache (≈0 re-extraction on unchanged pages, cost §3b-i);
this computes the honest diff between the previous export and the current one so the student sees
only what moved: **new/removed professors** and **changed fields**, with the two changes they most
care about highlighted — *newly-open recruiting* and *newly-published deadlines*. Pure function over
two export dicts; no fetching, no LLM.
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
    newly_recruiting = []
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
                # highlights: a field that just BECAME a value the student acts on
                became_value = env.get("state") == "value" and penv.get("state") != "value"
                if became_value and fid == "recruiting_signal":
                    newly_recruiting.append(_name(curr[i]))
                if became_value and fid == "deadline":
                    newly_deadline.append({"professor": _name(curr[i]), "deadline": env.get("value")})

    return {
        "new_professors": new,
        "removed_professors": removed,
        "changed_fields": changed_fields,
        "newly_recruiting": newly_recruiting,
        "newly_deadline": newly_deadline,
        "unchanged": not (new or removed or changed_fields),
    }
