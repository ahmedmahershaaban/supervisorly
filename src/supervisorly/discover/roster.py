"""Directory triage: open vs login-walled vs not-found — and the roster-enumeration rung.

A faculty directory can be one of three things, and the honest, ethical response differs:

* **open** — proceed to enumerate people from it (the normal path).
* **login-walled** (robots ``Disallow`` on the directory, or a login/bot wall in the page)
  — **we do not defeat it** (D-039/044). Instead a ``roster_enumerate`` task goes to the
  **human rung** (D-052): the student pastes the roster back via the Phase-3 grammar. The
  unit is marked ``LOGIN_WALL`` so the coverage stays honest.
* **not-found** (404 / unreachable) — a genuine coverage gap, marked ``NOT_FOUND`` so it is
  distinct from "there was nothing there" (edge-case matrix).

Pure logic over a ``FetchResult`` + optional page text — deterministic and offline-testable.
"""

from __future__ import annotations

import re
import sqlite3

from ..model import runs, units

# decisions
OPEN = "OPEN"
LOGIN_WALL = "LOGIN_WALL"
NOT_FOUND = "NOT_FOUND"

# Strong, near-unambiguous login / bot-wall phrases: a match anywhere means the real content is
# behind the wall, so we never extract it (D-039/044) and we don't mislabel a real roster.
_WALL_MARKERS = re.compile(
    r"(sign\s*in\s+to\s+(?:continue|view|access)|log\s*in\s+to\s+(?:continue|view|access)|"
    r"create\s+an?\s+account\s+to\s+(?:view|continue)|"
    r"access\s+denied|you\s+must\s+be\s+logged\s+in|captcha)",
    re.IGNORECASE,
)
# "Please enable JavaScript" is AMBIGUOUS: a genuinely JS-only page shows only this, but
# content-rich pages (WordPress, embedded maps, Disqus) ship the same <noscript> fallback
# ALONGSIDE their real, extractable text. So it signals a wall ONLY when the server rendered
# essentially no content — otherwise the real signals must still be extracted (D-022/037/046).
_JS_WALL = re.compile(
    r"(please\s+enable\s+javascript|enable\s+javascript\s+to\s+(?:run|use|view))",
    re.IGNORECASE,
)
# A JS banner is a wall only when the page has essentially NO extractable text of its own — a
# content-free JS shell (main_text ≈ empty). The floor sits well below the smallest real content
# page (a lone recruiting sentence ≈ 40 chars) so we never drop extractable content; a shell
# (`<div id="root"></div>` + a stripped <noscript>) yields ~0 chars and is correctly a wall.
_JS_CONTENT_FLOOR = 30


def detect_login_wall(html: str | None) -> bool:
    """True if the page looks like a login / bot / JS wall rather than a real content page.

    Strong login markers fire on their own. The ubiquitous "please enable JavaScript" fallback is
    a wall ONLY when the page rendered essentially no content (``main_text`` — which strips
    ``<noscript>`` — is near-empty); a content-rich page that merely ships a ``<noscript>`` banner
    is NOT a wall, so its real signals are still extracted (live audit-2).
    """
    if not html:
        return False
    if _WALL_MARKERS.search(html):
        return True
    if _JS_WALL.search(html):
        from ..fetch.normalize import main_text
        return len(main_text(html)) < _JS_CONTENT_FLOOR
    return False


def classify_directory(fetch_result, html: str | None = None) -> str:
    """Classify a directory fetch into OPEN / LOGIN_WALL / NOT_FOUND.

    ``fetch_result`` is a ``fetch.fetcher.FetchResult`` (``.allowed``, ``.status``, ``.ok``).
    """
    if not getattr(fetch_result, "allowed", False):
        return LOGIN_WALL                       # robots Disallow → treat as walled, human rung
    status = getattr(fetch_result, "status", None)
    if status == 404:
        return NOT_FOUND
    if not getattr(fetch_result, "ok", False):
        return NOT_FOUND                        # transport error / other non-200 → coverage gap
    if detect_login_wall(html):
        return LOGIN_WALL
    return OPEN


def route_directory(
    conn: sqlite3.Connection,
    run_id: str,
    *,
    directory_url: str,
    fetch_result,
    html: str | None = None,
    institution_id: str | None = None,
    unit_name: str | None = None,
) -> dict:
    """Record a unit for ``directory_url`` and route it per its classification.

    Returns ``{"decision", "unit_id", "task_id"?}``. For a LOGIN_WALL it enqueues a
    ``roster_enumerate`` **human** task (status ``awaiting_human``) and marks the unit
    ``LOGIN_WALL`` — it never reads or scrapes the walled content.
    """
    decision = classify_directory(fetch_result, html)
    unit_id = units.upsert_unit(
        conn, institution_id=institution_id, name=unit_name, kind="department",
        directory_url=directory_url,
        coverage_note=None if decision == OPEN else decision,
    )
    out = {"decision": decision, "unit_id": unit_id}
    if decision == LOGIN_WALL:
        task_id = runs.add_task(
            conn, run_id, "unit", unit_id, stage="roster_enumerate", phase="human"
        )
        runs.set_task_status(conn, task_id, "awaiting_human")
        out["task_id"] = task_id
    return out
