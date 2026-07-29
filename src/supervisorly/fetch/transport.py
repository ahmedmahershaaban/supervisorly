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


#: Refuse to download a body larger than this (CC-5.4). A 200 MB prospectus PDF must not be
#: pulled into a 4 GiB worker to extract one date from it — and the refusal has to happen
#: BEFORE the bytes arrive, which is why the live transport streams rather than calling
#: ``client.get``. Generous enough that no real admissions page or prospectus is refused.
MAX_RESPONSE_BYTES = 25 * 1024 * 1024


@dataclass
class Response:
    url: str
    status: int
    text: str
    headers: dict = field(default_factory=dict)
    #: The raw body. Needed because a PDF cannot be recovered from ``text`` — decoding binary
    #: as UTF-8 destroys it — and because the magic-byte sniff (CC-5.2) has to see real bytes.
    #: ``None`` on responses nobody asked to keep bytes for, which is the common case.
    content: bytes | None = None
    #: True when the body was REFUSED for exceeding ``MAX_RESPONSE_BYTES``. A refusal is a
    #: state with a reason, never an exception — the caller records it and moves on, exactly
    #: like a 404. ``content``/``text`` are empty when this is set: nothing was downloaded.
    oversize: bool = False

    def content_type(self) -> str:
        """The bare content type, lowercased, without parameters (``; charset=…``)."""
        for k, v in (self.headers or {}).items():
            if k.lower() == "content-type":
                return str(v).split(";", 1)[0].strip().lower()
        return ""


class Transport(Protocol):
    def get(self, url: str) -> Response: ...


class CassetteTransport:
    """Serves recorded responses; a request with no cassette raises, so an offline
    test can never silently hit the network."""

    def __init__(self, cassettes: dict[str, Response] | None = None) -> None:
        self._c: dict[str, Response] = dict(cassettes or {})

    def record(self, url: str, status: int, text: str, headers: dict | None = None,
               content: bytes | None = None, oversize: bool = False) -> None:
        """Record one response. ``content`` lets a cassette carry a real binary body (a PDF
        fixture); it defaults to the UTF-8 encoding of ``text`` so every existing caller keeps
        working and a sniff never sees ``None`` where a real fetch would have bytes."""
        self._c[url] = Response(url, status, text, headers or {},
                                content=(content if content is not None
                                         else text.encode("utf-8", "replace")),
                                oversize=oversize)

    def get(self, url: str) -> Response:
        if url not in self._c:
            raise TransportError(f"no cassette recorded for {url}")
        return self._c[url]


def httpx_transport(timeout: float = 20.0, user_agent: str = USER_AGENT,
                    max_bytes: int = MAX_RESPONSE_BYTES) -> Transport:
    """A live transport. httpx is imported lazily so offline use needs no dependency.

    Streams rather than calling ``client.get`` so an oversized body can be refused *before*
    it is downloaded (CC-5.4). Two guards, because either alone has a hole: ``Content-Length``
    catches the honest case up front, and the running byte count catches a chunked response
    that never declared its size.
    """
    import httpx  # noqa: PLC0415 — intentional lazy import

    client = httpx.Client(
        timeout=timeout, headers={"User-Agent": user_agent}, follow_redirects=True
    )

    def _decode(data: bytes, r) -> str:
        """Text for a body we streamed ourselves. ``r.text`` is unavailable after a stream,
        so the charset comes from the response's own encoding, with a lossy fallback — a
        mis-declared charset must not turn a readable page into an exception."""
        try:
            return data.decode(r.encoding or "utf-8", "replace")
        except (LookupError, TypeError):        # a bogus charset name
            return data.decode("utf-8", "replace")

    class _Httpx:
        def get(self, url: str) -> Response:
            try:
                with client.stream("GET", url) as r:
                    declared = r.headers.get("content-length")
                    if declared is not None and declared.isdigit() and int(declared) > max_bytes:
                        # Refused without reading the body — the point of streaming.
                        return Response(str(r.url), r.status_code, "", dict(r.headers),
                                        content=b"", oversize=True)
                    chunks, total = [], 0
                    for chunk in r.iter_bytes():
                        total += len(chunk)
                        if total > max_bytes:
                            # Undeclared size, caught mid-flight. Closing the context manager
                            # aborts the rest of the transfer rather than draining it.
                            return Response(str(r.url), r.status_code, "", dict(r.headers),
                                            content=b"", oversize=True)
                        chunks.append(chunk)
                    data = b"".join(chunks)
                    return Response(str(r.url), r.status_code, _decode(data, r),
                                    dict(r.headers), content=data)
            except httpx.HTTPError as exc:  # network/DNS/timeout → transport error
                raise TransportError(str(exc)) from exc

    return _Httpx()
