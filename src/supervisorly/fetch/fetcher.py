"""The polite fetcher: robots-gated, rate-limited, snapshot-storing.

One page fetch, done correctly: check robots (fail closed), wait for the per-host
budget, fetch through the transport, and store a content-addressed snapshot. This is
the unit the three-phase escalation (D-039) drives; it never defeats a login or a
bot-wall — a blocked page becomes a marked result routed onward, not a harder retry.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit

from . import robots
from .ratelimit import HostRateLimiter
from .snapshot import SnapshotStore
from .transport import Response, Transport, TransportError


@dataclass
class FetchResult:
    url: str
    allowed: bool
    status: int | None = None
    snapshot_hash: str | None = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.allowed and self.status == 200 and self.snapshot_hash is not None


class Fetcher:
    def __init__(
        self,
        transport: Transport,
        snapshots: SnapshotStore,
        *,
        rate_limiter: HostRateLimiter | None = None,
        user_agent: str = robots.USER_AGENT,
    ) -> None:
        self._t = transport
        self._snap = snapshots
        self._rl = rate_limiter or HostRateLimiter()
        self._ua = user_agent
        self._robots: dict[str, str | None] = {}  # host -> robots.txt text (None = unavailable)

    def _robots_for(self, scheme: str, host: str) -> str | None:
        if host in self._robots:
            return self._robots[host]
        text: str | None
        try:
            self._rl.wait(host)
            r = self._t.get(f"{scheme}://{host}/robots.txt")
            if r.status == 200:
                text = r.text
            elif r.status == 404:
                text = ""          # standard: no robots.txt → allow all
            else:
                text = None        # 5xx / weird → fail closed
        except TransportError:
            text = None            # can't reach robots → fail closed (D-019)
        self._robots[host] = text
        return text

    def fetch(self, url: str) -> FetchResult:
        parts = urlsplit(url)
        host = parts.netloc
        robots_txt = self._robots_for(parts.scheme or "https", host)
        if not robots.is_allowed(robots_txt, url, self._ua):
            return FetchResult(url=url, allowed=False, error="disallowed by robots.txt")
        self._rl.wait(host)
        try:
            resp: Response = self._t.get(url)
        except TransportError as exc:
            return FetchResult(url=url, allowed=True, error=f"transport: {exc}")
        if resp.status != 200:
            return FetchResult(url=url, allowed=True, status=resp.status,
                               error=f"http {resp.status}")
        h = self._snap.store(resp.text)
        return FetchResult(url=url, allowed=True, status=200, snapshot_hash=h)
