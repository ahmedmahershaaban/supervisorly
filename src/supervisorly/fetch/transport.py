"""HTTP transport behind a seam, so the whole pipeline runs offline on cassettes.

Tests and ``--offline --demo`` use ``CassetteTransport`` (recorded responses, no
network). A live run uses the httpx-backed transport. The seam is why the eval set
and self-run need neither credentials nor a network (D-011, D-063).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from .robots import USER_AGENT


class TransportError(RuntimeError):
    """A transport-level failure (no response at all) — distinct from an HTTP 4xx/5xx."""


@dataclass
class Response:
    url: str
    status: int
    text: str
    headers: dict = field(default_factory=dict)


class Transport(Protocol):
    def get(self, url: str) -> Response: ...


class CassetteTransport:
    """Serves recorded responses; a request with no cassette raises, so an offline
    test can never silently hit the network."""

    def __init__(self, cassettes: dict[str, Response] | None = None) -> None:
        self._c: dict[str, Response] = dict(cassettes or {})

    def record(self, url: str, status: int, text: str, headers: dict | None = None) -> None:
        self._c[url] = Response(url, status, text, headers or {})

    def get(self, url: str) -> Response:
        if url not in self._c:
            raise TransportError(f"no cassette recorded for {url}")
        return self._c[url]


def httpx_transport(timeout: float = 20.0, user_agent: str = USER_AGENT) -> Transport:
    """A live transport. httpx is imported lazily so offline use needs no dependency."""
    import httpx  # noqa: PLC0415 — intentional lazy import

    client = httpx.Client(
        timeout=timeout, headers={"User-Agent": user_agent}, follow_redirects=True
    )

    class _Httpx:
        def get(self, url: str) -> Response:
            try:
                r = client.get(url)
            except httpx.HTTPError as exc:  # network/DNS/timeout → transport error
                raise TransportError(str(exc)) from exc
            return Response(str(r.url), r.status_code, r.text, dict(r.headers))

    return _Httpx()
