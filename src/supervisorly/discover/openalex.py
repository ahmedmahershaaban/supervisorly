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


def topics_url(query: str, email: str | None, key: str | None = None) -> str:
    p = {"search": query, "per-page": PER_PAGE}
    if email:
        p["mailto"] = email
    if key:
        p["api_key"] = key
    return _url("topics", p)


def authors_url(institution_id: str, email: str | None, key: str | None = None) -> str:
    p = {"filter": f"last_known_institutions.id:{institution_id}", "per-page": PER_PAGE}
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

    def topic_ids(self, query: str) -> list[str]:
        """Resolve a free-text field to OpenAlex topic IDs (for D-058 overlap), else []."""
        data = self._get_json(topics_url(query, self._email, self._key))
        if not data:
            return []
        return [_short_id(t.get("id")) for t in data.get("results", []) if t.get("id")]

    def authors_by_institution(self, institution_id: str) -> list[dict]:
        """Return professor-target dicts for authors last known at ``institution_id`` (OpenAlex id)."""
        data = self._get_json(authors_url(institution_id, self._email, self._key))
        if not data:
            return []
        return [_map_author(a) for a in data.get("results", [])]

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
