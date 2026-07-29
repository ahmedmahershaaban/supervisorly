"""A bounded walk from a professor's page to the page that says whether they are recruiting.

**The gap this closes.** Rung 7 finds the page a professor controls. That page is often a
staff card — title, email, publication list — while the sentence a student needs ("I am
recruiting PhD students for 2027") lives one click away, on *Join the group*, *Vacancies*,
*Prospective students*. Reading only the entry point misses it; reading the whole site is not
an option.

**Why this is bounded rather than deep.** The tempting version — follow every link, ten levels
down — is not a slow crawl, it is a mirror. A university page carries 50–150 links; same-domain
with dedup, depth 10 from any homepage reaches essentially the entire estate, and a mid-size
university site is ~200,000 pages. At the polite one request per second that is **~55 hours for
one institution**, times the shortlist. So the walk is bounded three independent ways, and each
bound is a hard stop rather than a heuristic:

1. **Depth ≤ 2** from the entry page.
2. **Same registrable host only** — a link off-site is someone else's server and someone
   else's robots.txt.
3. **≤ 20 pages per professor**, counted, and the caller is told when the cap bit.

**And a fourth bound that does most of the work: link *text*.** A link is followed only when
its visible text or its URL says it leads somewhere a recruiting sentence lives. That is what
makes 20 pages enough — it is not a sample of the site, it is the handful of pages a person
would have clicked. The vocabulary describes *page roles* ("vacancies", "people", "join"), not
a research field's terms, so D-038 is untouched: nothing here knows what "machine learning"
means, and a per-field term list would be the violation.

**Politeness is the caller's, not ours.** This module never fetches. It is handed a
``fetch(url) -> (ok, html)`` callable, so the ordinary ``Fetcher`` supplies robots, rate
limiting, snapshots and the override — one definition of "may we read this", not two.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from urllib.parse import urldefrag, urljoin, urlsplit

MAX_DEPTH = 2
MAX_PAGES = 20

#: Page ROLES, not research terms (D-038). A link reading "Join the lab" leads to a page that
#: may carry a recruiting sentence whatever the field is; "deep learning" would be a term list.
_WORTH_FOLLOWING = re.compile(
    r"join|vacanc|opening|recruit|hiring|position|prospective|apply|application|"
    r"admission|studentship|scholarship|phd|doctoral|postdoc|master|msc|"
    r"people|member|team|group|lab|staff|student|supervis|opportunit|research",
    re.I)

#: Never worth a request from here: binaries, feeds, and the endless tail of a CMS.
_SKIP = re.compile(
    r"\.(?:pdf|docx?|pptx?|xlsx?|zip|gz|tar|jpe?g|png|gif|svg|webp|mp4|mp3|ico|css|js)$"
    r"|/(?:tag|tags|category|categories|archive|archives|feed|rss|print|share|login|"
    r"signin|search|calendar|event)s?(?:/|$)"
    r"|[?&](?:share|print|replytocom|utm_)", re.I)


class _Links(HTMLParser):
    """Anchor hrefs with their visible text. Deliberately not a DOM — this runs per page."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.out: list[tuple[str, str]] = []
        self._href: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag != "a":
            return
        href = dict(attrs).get("href")
        if href:
            self._href, self._text = href, []

    def handle_data(self, data):
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self._href is not None:
            self.out.append((self._href, " ".join(self._text).strip()))
            self._href, self._text = None, []


def _same_host(a: str, b: str) -> bool:
    ha, hb = urlsplit(a).netloc.lower(), urlsplit(b).netloc.lower()
    return bool(ha) and (ha == hb or ha.lstrip("www.") == hb.lstrip("www."))


def links_worth_following(html: str, base_url: str) -> list[str]:
    """Absolute, same-host, deduped links whose text or path suggests a recruiting page.

    Order is the page's own — a "Join the group" link near the top of a staff card is more
    likely the real one than the same words in a footer.
    """
    p = _Links()
    try:
        p.feed(html or "")
    except Exception:                      # noqa: BLE001 — malformed markup is not an error
        pass
    out, seen = [], set()
    for href, text in p.out:
        if not href or href.startswith(("mailto:", "tel:", "javascript:", "#")):
            continue
        url = urldefrag(urljoin(base_url, href)).url
        if not url.lower().startswith(("http://", "https://")):
            continue
        if not _same_host(url, base_url) or _SKIP.search(url):
            continue
        if not (_WORTH_FOLLOWING.search(text) or _WORTH_FOLLOWING.search(urlsplit(url).path)):
            continue
        if url in seen:
            continue
        seen.add(url)
        out.append(url)
    return out


def crawl(entry_url: str, fetch, *, max_depth: int = MAX_DEPTH, max_pages: int = MAX_PAGES):
    """Walk from ``entry_url``, breadth-first. Returns ``(pages, truncated)``.

    ``pages`` is ``[(url, html), ...]`` including the entry page, in visit order.
    ``truncated`` is True when the page cap stopped the walk with links still queued — the
    caller reports PARTIAL rather than implying the site was exhausted (D-037). A silent cap
    reads as "we looked everywhere", which is the one thing it must never mean.

    ``fetch(url) -> (ok, html)``; anything falsy for ``ok`` simply ends that branch. This
    module makes no request itself, so robots, rate limiting and the snapshot store stay in
    the one place that already defines them.
    """
    if not entry_url:
        return [], False
    pages: list[tuple[str, str]] = []
    seen = {entry_url}
    queue = [(entry_url, 0)]
    truncated = False
    while queue:
        if len(pages) >= max_pages:
            truncated = True
            break
        url, depth = queue.pop(0)
        try:
            ok, html = fetch(url)
        except Exception:                  # noqa: BLE001 — one dead page is not a dead crawl
            continue
        if not ok or not html:
            continue
        pages.append((url, html))
        if depth >= max_depth:
            continue
        for nxt in links_worth_following(html, url):
            if nxt not in seen:
                seen.add(nxt)
                queue.append((nxt, depth + 1))
    return pages, truncated
