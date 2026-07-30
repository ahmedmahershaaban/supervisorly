"""ROR client — country → institutions, via the open (keyless) ROR API.

ROR's REST API is open and needs no key; we only send a polite ``User-Agent`` carrying the
contact email. The ``Transport`` is injected, so this is **cassette-testable offline** with no
network (D-011). URL builders are module-level so a test can record the exact URL a call will
request.

Generate, don't look up (D-038): the country filter comes from the ``SearchPlan``, never a
hardcoded institution list. Results are mapped to plain dicts the discovery ladder consumes.

Schema note: the **v2** record shape is what the API serves (v1 was retired in Dec 2025 —
the unversioned endpoint already returns v2 records). v2 moves the name to ``names[]`` (pick
the entry typed ``ror_display``), links to ``{type, value}`` objects, and the country to
``locations[].geonames_details``. The envelope (``number_of_results``/``items``) is unchanged,
so the pagination/truncation logic below is schema-independent.
"""

from __future__ import annotations

import json
from urllib.parse import urlencode

from ..fetch.transport import Transport, TransportError

ROR_API = "https://api.ror.org/v2/organizations"


#: ROR v2 returns 20 organisations per page. Page count is derived from how many the caller
#: wants, so raising the ask raises the fetch instead of silently truncating.
PAGE_SIZE = 20

#: Institutions enumerated when the caller does not say. Was effectively 100 (5 hardcoded
#: pages), which a real Canadian scan hit and reported as truncated — ROR lists thousands of
#: organisations per large country, so the first 100 rows are an arbitrary slice, not a
#: shortlist. 200 is a starting point the caller can raise.
DEFAULT_WANT = 200

#: ROR's own organisation types. Only ``education`` is a university or college; the rest are
#: hospitals, companies, government labs, archives. This is ROR's vocabulary, not ours — an
#: enum published by the registry, never a list of institutions (D-038).
EDUCATION_TYPES = ("education",)


def is_education(inst: dict) -> bool:
    """Whether ROR types this organisation as education (a university, college, school)."""
    return any(str(t).strip().lower() in EDUCATION_TYPES for t in (inst.get("types") or []))


def country_url(country_code: str, page: int = 1) -> str:
    """The ROR query URL for all organisations in a 2-letter country code."""
    return f"{ROR_API}?" + urlencode(
        {"filter": f"country.country_code:{country_code.upper()}", "page": page}
    )


def _name(item: dict) -> str | None:
    """v2: the display name is the ``names[]`` entry typed ``ror_display`` (fallback: first)."""
    names = item.get("names") or []
    for n in names:
        if "ror_display" in (n.get("types") or []):
            return n.get("value")
    return names[0].get("value") if names else None


def _homepage(item: dict) -> str | None:
    """v2: ``links[]`` entries are ``{type, value}`` objects — take the ``website`` one."""
    for link in item.get("links") or []:
        if link.get("type") == "website":
            return link.get("value")
    return None


def _country_code(item: dict) -> str | None:
    """v2: the country sits at ``locations[0].geonames_details.country_code`` (null-safe)."""
    locations = item.get("locations") or []
    if not locations:
        return None
    return (locations[0].get("geonames_details") or {}).get("country_code")


def _map_institution(item: dict) -> dict:
    """Map one ROR v2 item to ``{ror_id, name, country_code, homepage, types}``."""
    return {
        "ror_id": item.get("id"),
        "name": _name(item),
        "country_code": _country_code(item),
        "homepage": _homepage(item),
        "types": list(item.get("types") or []),
    }


class RorClient:
    """Thin ROR client over an injected ``Transport``. No key; email is polite context only."""

    def __init__(self, transport: Transport, *, email: str | None = None) -> None:
        self._t = transport
        self._email = email
        # source labels whose enumeration hit the page cap (more existed) — surfaced in coverage.
        self.truncated_sources: list[str] = []

    def _page(self, country_code: str, page: int) -> dict | None:
        try:
            resp = self._t.get(country_url(country_code, page))
        except TransportError:
            return None
        if resp.status != 200:
            return None
        try:
            return json.loads(resp.text)
        except ValueError:
            return None

    def institutions_in_country(self, country_code: str, *, max_pages: int | None = None,
                                want: int | None = None) -> list[dict]:
        """The institutions ROR lists for ``country_code``, **paginated** (empty on error).

        ``want`` is how many institutions the caller intends to scan; the page count is derived
        from it, because a caller asking for 300 and silently receiving 100 is the failure this
        replaced. ``max_pages`` still overrides directly for tests.

        Records a truncation marker if we stop while more results remained (D-037) — so
        "we saw everything" and "we stopped early" stay different statements.

        Nothing is filtered here: the caller decides whether it wants only education-typed
        organisations, and ``types`` travels on every record so it can.
        """
        if max_pages is None:
            target = DEFAULT_WANT if want is None else max(1, int(want))
            max_pages = max(1, -(-target // PAGE_SIZE))       # ceil, so 300 -> 15 pages
        out: list[dict] = []
        page = 1
        while page <= max_pages:
            data = self._page(country_code, page)
            if not data:
                # a page fetch failed mid-enumeration (transport / non-200 / bad JSON) — the rest of
                # the country's institutions are unknown, so record truncation (coverage → PARTIAL,
                # D-037). A country ROR lists as empty returns 200 with items=[] above, not None.
                self.truncated_sources.append(f"institutions@{country_code}")
                return out
            items = data.get("items", [])
            out.extend(_map_institution(it) for it in items)
            total = data.get("number_of_results")
            if not items or (total is not None and len(out) >= total):
                return out
            page += 1
        self.truncated_sources.append(f"institutions@{country_code}")
        return out
