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

    def institutions_in_country(self, country_code: str, *, page: int = 1) -> list[dict]:
        """Return the institutions ROR lists for ``country_code`` (empty on error/none).

        Only degree-granting / education-type organisations are usually relevant; the caller
        filters — here we return everything ROR gives, mapped, so nothing is silently dropped.
        """
        try:
            resp = self._t.get(country_url(country_code, page))
        except TransportError:
            return []
        if resp.status != 200:
            return []
        try:
            data = json.loads(resp.text)
        except ValueError:
            return []
        return [_map_institution(it) for it in data.get("items", [])]
