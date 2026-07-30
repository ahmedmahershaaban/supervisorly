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
#: Google Programmable Search needs a search-engine id alongside the key. Only that provider
#: uses it; the others ignore it entirely.
ENV_CX = "SUPERVISORLY_SEARCH_CX"
#: Only ``gemini`` uses this — which model runs the grounded search.
ENV_MODEL = "SUPERVISORLY_SEARCH_MODEL"

#: Providers with a documented, consented programmatic search endpoint. An enum of providers
#: is not a lookup table of answers — D-038 forbids shipping the *facts*, not the plumbing.
#: Four rather than one because the free tiers differ in what they demand: Brave wants a card,
#: Google's CSE wants a second id, Gemini wants neither. Nobody should have to pay to find out
#: whether this rung fixes their dashboard.
PROVIDERS = ("brave", "tavily", "google", "gemini")
DEFAULT_PROVIDER = "brave"

BRAVE_URL = "https://api.search.brave.com/res/v1/web/search"
TAVILY_URL = "https://api.tavily.com/search"
GOOGLE_CSE_URL = "https://www.googleapis.com/customsearch/v1"
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models"
DEFAULT_GEMINI_MODEL = "gemini-2.0-flash"

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
    """Whether this rung can run at all. Asked once per scan, not once per professor.

    Google's Programmable Search is the one provider that needs a second value — an engine id
    — so a key alone is not enough there. Reporting it unconfigured is better than sending 25
    requests that cannot succeed.
    """
    environ = os.environ if environ is None else environ
    if not (environ.get(ENV_KEY) or "").strip():
        return False
    provider = (environ.get(ENV_PROVIDER) or DEFAULT_PROVIDER).strip().lower()
    if provider not in PROVIDERS:
        return False
    if provider == "google" and not (environ.get(ENV_CX) or "").strip():
        return False
    return True


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


def _google(query, key, url, poster, timeout, count, cx=None):
    """Google Programmable Search (Custom Search JSON API).

    A real index like Brave's, with a free 100 queries/day, but it needs a **search-engine id**
    as well as a key — and that engine must be configured to search the entire web, or it will
    answer only from whatever sites it was scoped to. Without ``cx`` we return nothing rather
    than sending a request that cannot succeed.
    """
    if not cx:
        return []
    status, text = poster(
        f"{url}?key={quote_plus(key)}&cx={quote_plus(cx)}&q={quote_plus(query)}"
        f"&num={min(int(count), 10)}",
        None, {"Accept": "application/json"}, timeout=timeout)
    if status != 200:
        return []
    return [r.get("link") for r in json.loads(text).get("items") or []]


def _gemini(query, key, url, poster, timeout, count, model=None, name="", institution=""):
    """Gemini with Google Search grounding — a model that searches, not a search index.

    **Why it is here.** It is the only provider whose free tier asks for no payment details, so
    it is the one that lets someone find out whether this rung fixes their dashboard before
    deciding to pay for a better one.

    **Why it is not equivalent.** Brave returns a ranked list; this returns whichever sources
    the model chose to cite while answering, so it may return fewer, may differ between
    identical calls, and may cite a news article about the person rather than their department
    page. Good enough to test the hypothesis; not the one to standardise on.

    The prompt asks for a page rather than for prose, because what we consume is
    ``groundingMetadata`` — the URLs it consulted — and never the model's own sentences. A
    model cannot mint a professor here: anything it says that is not a real page it visited is
    simply absent from the grounding chunks, and every fact still passes the D-010 quote gate
    later against a page we fetched ourselves.
    """
    who = name or query
    where = f" at {institution}" if institution else ""
    prompt = (f"Find the official university, department, or research-group page for {who}"
              f"{where}. Prefer a page on the institution's own website over any aggregator, "
              f"news article, or publisher page. Answer with the URL only.")
    status, text = poster(
        f"{url}/{model or DEFAULT_GEMINI_MODEL}:generateContent?key={quote_plus(key)}",
        {"contents": [{"parts": [{"text": prompt}]}], "tools": [{"google_search": {}}]},
        {"Content-Type": "application/json"}, timeout=timeout)
    if status != 200:
        return []
    data = json.loads(text)
    out = []
    for cand in data.get("candidates") or []:
        for chunk in (cand.get("groundingMetadata") or {}).get("groundingChunks") or []:
            uri = (chunk.get("web") or {}).get("uri")
            if uri:
                out.append(uri)
    return out[:count * 3]      # redirect resolution drops some; ask for headroom


#: Gemini's grounding chunks cite a Google redirect, not the page itself. Fetching the proxy
#: would consult the WRONG host's robots.txt and record the wrong provenance, so these are
#: resolved to their destination before they are allowed anywhere near the fetcher.
_GROUNDING_REDIRECT = re.compile(r"(?:^|\.)vertexaisearch\.cloud\.google\.com$", re.I)


def resolve_redirect(url: str, timeout: float = DEFAULT_TIMEOUT) -> str | None:
    """Follow a redirect to the page it points at. ``None`` if it will not resolve.

    Only used for grounding URLs. ``None`` is the right failure: a proxy URL we could not
    resolve is not a page we may fetch, and passing it through would defeat the robots check.
    """
    import httpx  # noqa: PLC0415 — intentional lazy import
    try:
        r = httpx.head(url, follow_redirects=True, timeout=timeout)
        final = str(r.url)
    except Exception:                      # noqa: BLE001 — fail-closed to an open gap
        return None
    if not final or urlsplit(final).netloc.lower() == urlsplit(url).netloc.lower():
        return None                        # never resolved off the proxy
    return final


def search(name: str, institution: str | None = None, *, environ=None, transport=None,
           timeout: float = DEFAULT_TIMEOUT, count: int = MAX_RESULTS, resolver=None) -> list[str]:
    """Candidate URLs for this professor's own page, best first. ``[]`` on any failure.

    ``transport`` is the test seam — the same ``(url, payload, headers, *, timeout) ->
    (status, text)`` contract ``expand.expand_query`` uses, so the whole rung is testable with
    no key and no network (D-011/D-063). ``resolver`` is the same seam for redirect following.
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
    resolve = resolver if resolver is not None else resolve_redirect
    try:
        if provider == "brave":
            urls = _brave(query, key, BRAVE_URL, poster, timeout, count)
        elif provider == "tavily":
            urls = _tavily(query, key, TAVILY_URL, poster, timeout, count)
        elif provider == "google":
            urls = _google(query, key, GOOGLE_CSE_URL, poster, timeout, count,
                           cx=(environ.get(ENV_CX) or "").strip())
        else:
            urls = _gemini(query, key, GEMINI_URL, poster, timeout, count,
                           model=(environ.get(ENV_MODEL) or "").strip() or None,
                           name=name, institution=institution or "")
    except (TransportError, ValueError, TypeError, KeyError, IndexError, AttributeError):
        return []                          # fail-closed: an open gap, never an invented page
    out, seen = [], set()
    for u in urls:
        if not isinstance(u, str):
            continue
        if _GROUNDING_REDIRECT.search(urlsplit(u).netloc or ""):
            u = resolve(u)
            if not u:
                continue
        if not is_candidate_page(u) or u in seen:
            continue
        seen.add(u)
        out.append(u)
        if len(out) >= count:
            break
    return out
