"""robots.txt enforcement — obeyed in code, fail-closed (D-019, D-039).

The tool never fetches a path a site disallows. If robots.txt can't be read or is
ambiguous, the fetch does not happen (fail closed). Uses the stdlib parser so the
policy is pure and testable; the caller supplies the robots.txt text (fetched via the
transport layer and cached), keeping this module network-free.
"""

from __future__ import annotations

from urllib.robotparser import RobotFileParser

# Honest User-Agent carrying a contact URL (D-019). Never spoofs a browser.
USER_AGENT = "SupervisorlyBot/0.1 (+https://github.com/ahmedmahershaaban/supervisorly)"


def is_allowed(robots_txt: str | None, url: str, user_agent: str = USER_AGENT) -> bool:
    """Return True iff ``url`` is allowed for ``user_agent``.

    ``robots_txt=None`` means robots.txt could not be fetched → **fail closed** (deny).
    An empty robots.txt (present but no rules) allows, per the standard.
    """
    if robots_txt is None:
        return False  # fail closed
    rp = RobotFileParser()
    rp.parse(robots_txt.splitlines())
    return rp.can_fetch(user_agent, url)
