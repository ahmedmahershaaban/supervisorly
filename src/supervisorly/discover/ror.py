"""ROR client — country → institutions, via the open (keyless) ROR API.

ROR's REST API is open and needs no key; we only send a polite ``User-Agent`` carrying the
contact email. The ``Transport`` is injected, so this is **cassette-testable offline** with no
network (D-011). URL builders are module-level so a test can record the exact URL a call will
request.

Generate, don't look up (D-038): the country filter comes from the ``SearchPlan``, never a
hardcoded institution list. Results are mapped to plain dicts the discovery ladder consumes.
"""

from __future__ import annotations

import json
from urllib.parse import urlencode

from ..fetch.transport import Transport, TransportError

ROR_API = "https://api.ror.org/organizations"


def country_url(country_code: str, page: int = 1) -> str:
    """The ROR query URL for all organisations in a 2-letter country code."""
    return f"{ROR_API}?" + urlencode(
        {"filter": f"country.country_code:{country_code.upper()}", "page": page}
    )


def _homepage(item: dict) -> str | None:
    links = item.get("links") or []
    return links[0] if links else None


def _map_institution(item: dict) -> dict:
    """Map one ROR item to ``{ror_id, name, country_code, homepage, types}``."""
    return {
        "ror_id": item.get("id"),
        "name": item.get("name"),
        "country_code": (item.get("country") or {}).get("country_code"),
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

    def institutions_in_country(self, country_code: str, *, max_pages: int = 5) -> list[dict]:
        """The institutions ROR lists for ``country_code``, **paginated** to ``max_pages`` (empty on
        error). Records a truncation marker if the cap is hit while more results remained (D-037).
        The caller filters to education types; nothing is silently dropped here."""
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
