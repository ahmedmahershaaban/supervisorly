"""Rung 7 — resolve a named professor to the page they actually control.

**The measured problem this exists for.** `tools/spikes/spike_page_supply.py`, on a real
GB · machine-learning scan of 49 shortlisted professors: **88% had no page at all**, 12% a
registry profile (ORCID, Publons), and **0% a page the professor controls**. Sixteen of those
pages were then read — fifteen needed the browser — and an independent model was asked whether
any stated something about recruiting. **None did.**

That is why dashboards are thin, and no reader fixes it. "I am recruiting PhD students for
2027" is a sentence a person writes on *their own page*; ORCID has no field for it and Publons
has no field for it. Rungs 1–6 enumerate people; this rung finds their page.

**Why a search API and not a crawl.** The obvious idea — take the top results for each topic
and crawl outward — fails twice. Google's own `robots.txt` carries `Disallow: /search`, so
scraping the results page is precisely what D-039 forbids; and depth is arithmetic, not a
tuning knob: at 50–150 links per page, ten levels from any university homepage reaches
essentially the whole domain, which at a polite one request per second is ~55 hours for **one**
institution. A consented search API answers the same question in one request.

**Why the query is per PERSON, not per topic.** A topic search returns pages *about* machine
learning; this rung needs the page of *one named human*. Searching per topic is the wrong
question asked efficiently. Per professor, the query can only return the right kind of page.

**D-038 holds.** The query is *generated* from the professor's own name and affiliation plus a
fixed set of structural words that describe what a faculty page IS ("faculty", "research
group", "lab"). That is a shape, not a dictionary of a field's search terms — nothing here
knows what "machine learning" means, and adding a per-field term list would be the violation.

**Fail-closed** (D-068): no key configured means `search()` returns `[]` and the scan proceeds
on exactly today's page supply. A timeout, a non-200 or a malformed body is also `[]`. Nobody's
search dies because a search API was unavailable, and no result is ever *invented* to fill a
gap — an empty list keeps the professor an honest open gap for the human rung.
"""

from __future__ import annotations

import json
import os
import re
from urllib.parse import quote_plus, urlsplit

from ..fetch import walls
from .expand import TransportError

ENV_KEY = "SUPERVISORLY_SEARCH_KEY"
ENV_PROVIDER = "SUPERVISORLY_SEARCH_PROVIDER"

#: Providers with a documented, consented programmatic search endpoint. An enum of providers
#: is not a lookup table of answers — D-038 forbids shipping the *facts*, not the plumbing.
PROVIDERS = ("brave", "tavily")
DEFAULT_PROVIDER = "brave"

BRAVE_URL = "https://api.search.brave.com/res/v1/web/search"
TAVILY_URL = "https://api.tavily.com/search"

#: Enough to catch the real page without funding a crawl. Beyond ~5 the results stop being
#: about this person and start being namesakes and citation aggregators.
MAX_RESULTS = 5
DEFAULT_TIMEOUT = 15.0

#: Hosts that are never "the professor's own page" however high they rank. Aggregators and
#: citation databases are already covered by rungs 1–5, and the walled ones we must not read
#: at all — routing them here would quietly re-introduce a source D-039/D-044 excluded.
_NOT_A_HOMEPAGE = re.compile(
    r"(?:^|\.)(?:"
    r"scholar\.google\.|orcid\.org|publons\.com|semanticscholar\.org|"
    r"webofscience\.com|scopus\.com|springer\.com|sciencedirect\.com|"
    r"wiley\.com|tandfonline\.com|ieee\.org|acm\.org|arxiv\.org|"
    r"wikipedia\.org|youtube\.com|facebook\.com|amazon\."
    r")", re.I)


def configured(environ=None) -> bool:
    """Whether this rung can run at all. Asked once per scan, not once per professor."""
    environ = os.environ if environ is None else environ
    if not (environ.get(ENV_KEY) or "").strip():
        return False
    return (environ.get(ENV_PROVIDER) or DEFAULT_PROVIDER).strip().lower() in PROVIDERS


def build_query(name: str, institution: str | None = None) -> str:
    """The generated query: a quoted human name, their institution, and what a page IS.

    Quoting the name is what keeps this a *person* lookup — unquoted, a common surname
    dissolves into the topic literature the OpenAlex rungs already cover.
    """
    name = (name or "").strip()
    if not name:
        return ""
    parts = [f'"{name}"']
    if institution and institution.strip():
        parts.append(institution.strip())
    parts.append("(faculty OR \"research group\" OR lab OR homepage)")
    return " ".join(parts)


def is_candidate_page(url: str) -> bool:
    """Could this URL be a page the professor controls? Cheap structural filter, no fetching.

    Walled hosts are excluded here rather than downstream so this rung can never become a
    back door to a source D-039/D-044 already refused — a ResearchGate hit is dropped before
    anything is tempted to fetch it.
    """
    if not url or not url.lower().startswith(("http://", "https://")):
        return False
    host = urlsplit(url).netloc.lower()
    if not host:
        return False
    if walls.is_walled(url):
        return False
    return not _NOT_A_HOMEPAGE.search(host)


def http_json(url: str, payload: dict | None, headers: dict, *, timeout: float = DEFAULT_TIMEOUT):
    """``(status, text)`` for a GET (``payload is None``) or a JSON POST.

    ``expand.post_json`` is POST-only and Brave's endpoint is a GET, so this widens that
    contract by exactly one case rather than growing a second transport shape for tests to
    keep in step. httpx stays a lazy import — offline use needs no dependency.
    """
    import httpx  # noqa: PLC0415 — intentional lazy import
    try:
        if payload is None:
            r = httpx.get(url, headers=headers, timeout=timeout)
        else:
            r = httpx.post(url, json=payload, headers=headers, timeout=timeout)
    except httpx.TimeoutException as exc:
        raise TransportError("timeout") from exc
    except httpx.HTTPError as exc:
        raise TransportError("transport error") from exc
    return r.status_code, r.text


def _brave(query, key, url, poster, timeout, count):
    status, text = poster(f"{url}?q={quote_plus(query)}&count={count}", None,
                          {"X-Subscription-Token": key, "Accept": "application/json"},
                          timeout=timeout)
    if status != 200:
        return []
    data = json.loads(text)
    return [r.get("url") for r in (data.get("web") or {}).get("results") or []]


def _tavily(query, key, url, poster, timeout, count):
    status, text = poster(url, {"api_key": key, "query": query, "max_results": count},
                          {"Content-Type": "application/json"}, timeout=timeout)
    if status != 200:
        return []
    data = json.loads(text)
    return [r.get("url") for r in data.get("results") or []]


def search(name: str, institution: str | None = None, *, environ=None, transport=None,
           timeout: float = DEFAULT_TIMEOUT, count: int = MAX_RESULTS) -> list[str]:
    """Candidate URLs for this professor's own page, best first. ``[]`` on any failure.

    ``transport`` is the test seam — the same ``(url, payload, headers, *, timeout) ->
    (status, text)`` contract ``expand.expand_query`` uses, so the whole rung is testable with
    no key and no network (D-011/D-063).
    """
    environ = os.environ if environ is None else environ
    key = (environ.get(ENV_KEY) or "").strip()
    query = build_query(name, institution)
    if not key or not query:
        return []
    provider = (environ.get(ENV_PROVIDER) or DEFAULT_PROVIDER).strip().lower()
    if provider not in PROVIDERS:
        return []
    poster = transport if transport is not None else http_json
    fn, url = ((_brave, BRAVE_URL) if provider == "brave" else (_tavily, TAVILY_URL))
    try:
        urls = fn(query, key, url, poster, timeout, count)
    except (TransportError, ValueError, TypeError, KeyError, IndexError, AttributeError):
        return []                          # fail-closed: an open gap, never an invented page
    out, seen = [], set()
    for u in urls:
        if not isinstance(u, str) or not is_candidate_page(u):
            continue
        if u in seen:
            continue
        seen.add(u)
        out.append(u)
        if len(out) >= count:
            break
    return out
