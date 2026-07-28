"""Hosts the tool must not read with a machine, in ONE place.

**Why this module exists — a measured near-miss.** The walled-host pattern used to live in
``pipeline.py`` and the server-side renderer relied on a different guard: "a non-2xx response
is a refusal". That guard is worthless against a wall that only closes for non-browser
clients. Measured 2026-07-28 against a real ResearchGate profile:

    plain HTTP client (httpx)  -> 403, refused, correct
    headless Chromium          -> 200, 55,568 characters of the professor's page

The browser did not *bypass* a check we wrote; it was never shown the wall at all. A guard
that reads the server's status code cannot see a wall that opens for the reader it is looking
through — so refusal has to be a property of the HOST, decided before any request is made.

That is the whole reason this list is not "the social-media list": it is the list of places
we do not point automation at, whatever they answer, whoever is asking. D-039/D-043/D-044
route them to the student's own browser, where a human is reading their own session — which
is a completely different act from a datacentre rendering the same page at scale.

One definition, imported by both the fetcher path and the render path. Two copies of a rule
like this is two chances for them to disagree, and the permissive copy is the one that would
end up on the network.
"""

from __future__ import annotations

import re

#: Profile hosts that refuse machines, or whose terms put automated reading out of bounds.
#: Subdomains are matched (``uk.linkedin.com``, ``www.researchgate.net``) because the
#: previous ``(?:www\.)?`` form let country subdomains straight through.
#:
#: Each was measured with a plain GET on 2026-07-28, and the status is only half the story —
#: see the module docstring for why the browser sees something different:
#:   researchgate.net  403 to httpx, 200 to Chromium, robots.txt SELECTIVE
#:   academia.edu      403,                            robots.txt Disallow: /
#:   scholar.google.*  302 away,                       robots.txt Disallow: /
#:   x.com / twitter.com / linkedin.com                login-walled
WALLED_HOSTS = re.compile(
    r"^https?://(?:[\w-]+\.)*(?:"
    r"twitter\.com|x\.com|linkedin\.com|researchgate\.net|academia\.edu"
    r"|scholar\.google\.[a-z.]+"
    r")(?:[/?#]|$)",
    re.IGNORECASE,
)


def is_walled(url: str | None) -> bool:
    """True if this URL must not be read by automation, whatever it would answer."""
    return bool(url) and bool(WALLED_HOSTS.search(str(url)))
