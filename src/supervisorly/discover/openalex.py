"""OpenAlex client — topics, authors-by-institution, works-by-author (free, keyless API).

OpenAlex is free; the ``mailto`` parameter joins the polite pool (faster, more reliable). An
optional premium key is passed as ``api_key`` when present. The ``Transport`` is injected, so
this is **cassette-testable offline** (D-011). Topic IDs feed the deterministic topic-ID overlap
research-fit (D-058); authors become professor targets; works give activity + recency signals —
all reconciled and scored by the existing engine.
"""

from __future__ import annotations

import json
from urllib.parse import urlencode

from ..fetch.transport import Transport, TransportError

OPENALEX_API = "https://api.openalex.org"
PER_PAGE = 25


def _url(path: str, params: dict) -> str:
    return f"{OPENALEX_API}/{path}?" + urlencode(params)


def topics_url(query: str, email: str | None, key: str | None = None,
               page: int = 1) -> str:
    p = {"search": query, "per-page": PER_PAGE}
    if page > 1:                       # page 1 omits the param → matches the un-paged URL
        p["page"] = page
    if email:
        p["mailto"] = email
    if key:
        p["api_key"] = key
    return _url("topics", p)


def author_search_url(query: str, email: str | None, key: str | None = None) -> str:
    p = {"search": query, "per-page": PER_PAGE}
    if email:
        p["mailto"] = email
    if key:
        p["api_key"] = key
    return _url("authors", p)


def author_url(short_id: str, email: str | None, key: str | None = None) -> str:
    """Single-author endpoint (``/authors/A…``) for resolving a URL-form target directly."""
    p: dict = {}
    if email:
        p["mailto"] = email
    if key:
        p["api_key"] = key
    base = f"{OPENALEX_API}/authors/{short_id}"
    return base + ("?" + urlencode(p) if p else "")


def institutions_url(ror_url: str, email: str | None, key: str | None = None) -> str:
    p = {"filter": f"ror:{ror_url}", "per-page": PER_PAGE}
    if email:
        p["mailto"] = email
    if key:
        p["api_key"] = key
    return _url("institutions", p)


def authors_url(institution_id: str, email: str | None, key: str | None = None,
                page: int = 1) -> str:
    p = {"filter": f"last_known_institutions.id:{institution_id}", "per-page": PER_PAGE}
    if page > 1:                       # page 1 omits the param → matches the un-paged URL
        p["page"] = page
    if email:
        p["mailto"] = email
    if key:
        p["api_key"] = key
    return _url("authors", p)


def works_url(author_id: str, email: str | None, key: str | None = None) -> str:
    p = {"filter": f"author.id:{author_id}", "per-page": PER_PAGE}
    if email:
        p["mailto"] = email
    if key:
        p["api_key"] = key
    return _url("works", p)


def _short_id(full: str | None) -> str | None:
    """'https://openalex.org/A123' -> 'A123' (the id the API filters accept)."""
    return full.rstrip("/").rsplit("/", 1)[-1] if full else None


def _map_author(a: dict) -> dict:
    """Map an OpenAlex author to a professor-target dict (nothing dropped for missing data)."""
    insts = a.get("last_known_institutions") or []
    topics = a.get("topics") or a.get("x_concepts") or []
    return {
        "openalex_id": a.get("id"),
        "short_id": _short_id(a.get("id")),
        "name": a.get("display_name"),
        "orcid": (a.get("ids") or {}).get("orcid"),
        "works_count": int(a.get("works_count") or 0),
        "cited_by_count": int(a.get("cited_by_count") or 0),
        "topic_ids": [_short_id(t.get("id")) for t in topics if t.get("id")],
        "institution_ids": [i.get("id") for i in insts if i.get("id")],
        "homepage": a.get("homepage_url"),
    }


class OpenAlexClient:
    """Thin OpenAlex client over an injected ``Transport``."""

    def __init__(self, transport: Transport, *, email: str | None = None,
                 key: str | None = None) -> None:
        self._t = transport
        self._email = email
        self._key = key
        # source labels whose enumeration hit the page cap (more results existed) — surfaced
        # honestly in the run coverage so completeness is never claimed while truncating (D-037).
        self.truncated_sources: list[str] = []

    def _get_json(self, url: str) -> dict | None:
        try:
            resp = self._t.get(url)
        except TransportError:
            return None
        if resp.status != 200:
            return None
        try:
            return json.loads(resp.text)
        except ValueError:
            return None

    def institution_by_ror(self, ror_url: str | None) -> str | None:
        """Resolve a ROR id to the OpenAlex institution id (``I…``) used to filter authors.

        None means OpenAlex GENUINELY has no institution for that ROR id (200, empty results) —
        silent, honest absence. A lookup FAILURE (transport error / non-200 / bad JSON) is not
        absence: the whole university's professors are unknown, so record a truncation marker
        naming it — the coverage then reports PARTIAL instead of claiming none were dropped
        (D-037; same failure class as the mid-pagination markers below).
        """
        if not ror_url:
            return None
        data = self._get_json(institutions_url(ror_url, self._email, self._key))
        if data is None:
            self.truncated_sources.append(f"inst@{_short_id(ror_url) or ror_url}")
            return None
        results = data.get("results") or []
        return _short_id(results[0].get("id")) if results else None

    def topic_ids(self, query: str) -> list[str]:
        """Resolve a free-text field to OpenAlex topic IDs (for D-058 overlap), else []."""
        data = self._get_json(topics_url(query, self._email, self._key))
        if not data:
            return []
        return [_short_id(t.get("id")) for t in data.get("results", []) if t.get("id")]

    def author_search(self, name: str, affiliation: str | None = None) -> dict | None:
        """Best-match author for a ``--targets`` name (D-066), or None when OpenAlex has none.

        Best match = the top search hit. When ``affiliation`` is given, a hit whose last-known
        institution display name contains it (casefold, substring) is preferred; if NO hit
        matches, the top hit is returned anyway with ``resolution="unverified"`` — an honest
        flag, never a silent guess. ``resolution`` is ALWAYS set on a returned hit:
        ``verified`` (affiliation given and matched), ``unverified`` (affiliation given, no
        hit matched it), ``unchecked`` (no affiliation given — nothing to check against).
        A lookup FAILURE (transport / non-200 / bad JSON) records a truncation marker and
        returns None, same failure class as the other enumerations (D-037); a 200 with empty
        results is a genuine "no such author" — no marker, honest skip.
        """
        data = self._get_json(author_search_url(name, self._email, self._key))
        if data is None:
            self.truncated_sources.append(f"author-search@{name}")
            return None
        results = data.get("results") or []
        if not results:
            return None
        pick, resolution = results[0], "unchecked"      # no affiliation to check against
        if affiliation:
            want = affiliation.casefold()
            for a in results:
                names = [(i.get("display_name") or "").casefold()
                         for i in (a.get("last_known_institutions") or [])]
                if any(want in n for n in names):
                    pick, resolution = a, "verified"
                    break
            else:
                resolution = "unverified"       # top hit, affiliation NOT confirmed — say so
        out = _map_author(pick)
        out["institution_names"] = [i.get("display_name") for i in
                                    (pick.get("last_known_institutions") or [])
                                    if i.get("display_name")]
        out["resolution"] = resolution
        return out

    def author_by_id(self, short_id: str) -> dict | None:
        """Resolve a URL-form ``--targets`` entry (``https://openalex.org/A…``) to an author.

        A 404 is a GENUINE "no such author" — None, no marker (the caller reports the skip).
        A lookup FAILURE (transport / other non-200 / bad JSON) records a truncation marker
        (D-037) and returns None."""
        try:
            resp = self._t.get(author_url(short_id, self._email, self._key))
        except TransportError:
            resp = None
        if resp is None or resp.status != 200:
            if resp is not None and resp.status == 404:
                return None                     # genuinely absent — honest skip, not PARTIAL
            self.truncated_sources.append(f"author@{short_id}")
            return None
        try:
            data = json.loads(resp.text)
        except ValueError:
            self.truncated_sources.append(f"author@{short_id}")
            return None
        out = _map_author(data)
        out["institution_names"] = [i.get("display_name") for i in
                                    (data.get("last_known_institutions") or [])
                                    if i.get("display_name")]
        return out

    def authors_by_institution(self, institution_id: str, *, max_pages: int = 5) -> list[dict]:
        """Professor-target dicts for authors last known at ``institution_id`` — **paginated**.

        Fetches up to ``max_pages`` pages; if the cap is hit while a full page remained, records a
        truncation marker in ``truncated_sources`` so the coverage stays honest (never a silent cut).
        """
        out: list[dict] = []
        page = 1
        while page <= max_pages:
            data = self._get_json(authors_url(institution_id, self._email, self._key, page=page))
            if not data:
                # a page fetch failed mid-enumeration (transport / non-200 / bad JSON) — we do NOT
                # know what those pages held, so record truncation: coverage reports PARTIAL, never
                # a false "complete" (D-037). A legit empty institution returns 200/[] above, not None.
                self.truncated_sources.append(
                    f"authors@{_short_id(institution_id) or institution_id}")
                return out
            results = data.get("results", [])
            out.extend(_map_author(a) for a in results)
            if len(results) < PER_PAGE:          # last page reached
                return out
            page += 1
        self.truncated_sources.append(f"authors@{_short_id(institution_id) or institution_id}")
        return out

    def works_by_author(self, author_id: str) -> list[dict]:
        """Return the author's works as ``{id, title, year, topic_ids}`` (activity/recency signal)."""
        data = self._get_json(works_url(author_id, self._email, self._key))
        if not data:
            return []
        out = []
        for w in data.get("results", []):
            topics = w.get("topics") or []
            out.append({
                "openalex_id": w.get("id"),
                "title": w.get("title") or w.get("display_name"),
                "year": w.get("publication_year"),
                "topic_ids": [_short_id(t.get("id")) for t in topics if t.get("id")],
            })
        return out
