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
# behind the wall, so we never extract it (D-039/044) and we don't mislabel a real roster. Includes
# anti-DDoS/JS-challenge interstitials (Cloudflare & co.), which are walls regardless of chrome
# length — their challenge text is longer than any character floor (live audit-3 finding 5).
_WALL_MARKERS = re.compile(
    r"(sign\s*in\s+to\s+(?:continue|view|access)|log\s*in\s+to\s+(?:continue|view|access)|"
    r"create\s+an?\s+account\s+to\s+(?:view|continue)|"
    r"access\s+denied|you\s+must\s+be\s+logged\s+in|captcha|"
    r"checking\s+your\s+browser|checking\s+(?:if|the)\s+(?:the\s+)?site\s+connection|"
    r"attention\s+required|enable\s+javascript\s+and\s+cookies|\bray\s+id\b)",
    re.IGNORECASE,
)
# "Please enable JavaScript" (and the CRA "you need to enable JavaScript to run this app") is
# AMBIGUOUS: a genuinely JS-only page shows only this, but content-rich pages (WordPress, embedded
# maps, Disqus) ship the same <noscript> fallback ALONGSIDE their real text. So it signals a wall
# ONLY when nothing substantive remains once the banner itself is removed (D-022/037/046).
_JS_WALL = re.compile(
    r"(please\s+enable\s+javascript|(?:you\s+need\s+to\s+)?enable\s+javascript\s+to\s+(?:run|use|view))",
    re.IGNORECASE,
)
# The JS-enable banner is chrome, not the professor's content — strip the whole sentence carrying it
# before measuring, so a page whose ONLY text is the banner is a wall while a page that also has real
# content is not (live audit-3 findings 3/4: the banner text must never be counted as content, nor
# extracted as a professor fact).
_JS_BANNER_SENTENCE = re.compile(
    r"[^.!?]*\b(?:please\s+enable\s+javascript|enable\s+javascript\s+to\s+(?:run|use|view)|"
    r"you\s+need\s+to\s+enable\s+javascript)\b[^.!?]*[.!?]?",
    re.IGNORECASE,
)
# below this many characters of REAL content (banner removed), the page is a content-free JS shell
_JS_RESIDUE_FLOOR = 20


def detect_login_wall(html: str | None) -> bool:
    """True if the page looks like a login / bot / JS wall rather than a real content page.

    Strong login / bot-challenge markers fire on their own. The ubiquitous "please enable
    JavaScript" fallback is a wall ONLY when, after removing the banner sentence itself (it is
    chrome), essentially no content remains — a genuine JS shell. A content-rich page that merely
    ships a ``<noscript>`` banner keeps its real, extractable signals (live audit-3).
    """
    if not html:
        return False
    if _WALL_MARKERS.search(html):
        return True
    if _JS_WALL.search(html):
        from ..fetch.normalize import main_text
        residue = _JS_BANNER_SENTENCE.sub(" ", main_text(html)).strip()
        return len(residue) < _JS_RESIDUE_FLOOR
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
