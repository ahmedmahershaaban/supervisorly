"""Program roll-up (D-031) — apply once per program, not once per professor.

Two excellent supervisors in the same department usually share **one** graduate program:
one application, one fee, one deadline. Presenting them as two separate "applications"
would mislead the student into paying twice. So before display we roll shortlisted
professors up to their program: a group carries the program's application details once and
lists the professors it covers. A professor with no known program is its own singleton
group (honest — we don't invent a shared program).

Pure, deterministic grouping — no model call. Order is preserved so the ranking survives.
"""

from __future__ import annotations


def group_by_program(professors: list[dict]) -> list[dict]:
    """Group ``professors`` (each optionally carrying a ``program`` dict) by program.

    ``program`` = ``{"id", "name", "application_url", "fee"}`` (any subset). Returns a list
    of groups in first-seen order, each ``{program_*, members:[ids], one_application_covers,
    note}``.
    """
    groups: dict[str, dict] = {}
    order: list[str] = []
    for p in professors:
        prog = p.get("program") or {}
        # No program id → the professor is its own group; never merged on a guessed key.
        key = prog.get("id") or f"__solo__:{p['id']}"
        if key not in groups:
            groups[key] = {
                "program_id": prog.get("id"),
                "program_name": prog.get("name"),
                "application_url": prog.get("application_url"),
                "fee": prog.get("fee"),
                "members": [],
            }
            order.append(key)
        groups[key]["members"].append(p["id"])

    out = []
    for key in order:
        g = groups[key]
        n = len(g["members"])
        g["one_application_covers"] = n
        g["note"] = (
            f"One application to {g['program_name'] or 'this program'} covers "
            f"{n} shortlisted professors — you apply and pay once (D-031)."
            if n > 1 else "One application."
        )
        out.append(g)
    return out
