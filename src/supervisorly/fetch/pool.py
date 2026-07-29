"""Concurrency across hosts, never within one (CC-3).

**The unit is the host, not the institution** *(Ahmed's correction, 2026-07-29)*. One
university spans a main site, a scholar subdomain and faculty subdomains; sources span
domains belonging to no institution at all. "Twenty concurrent" means twenty **distinct
hosts** — never twenty requests at one server.

**Async, not threads** (CC-3.4). Playwright's sync API is bound to the thread that created
it, so a thread pool around it buys contention rather than speed: every call marshals back to
the owning thread and the "parallel" workers queue behind each other. The whole point of this
module disappears if it is built on threads.

**The lock order is the design.** Each task takes its *host* lock first and the *global*
semaphore second. The reverse — which is the obvious way to write it — deadlocks the fleet in
a way that only shows up under load: twenty URLs for one host would each grab a global slot,
then all queue on that one host's lock, holding every slot while doing nothing. Nineteen
other hosts would sit idle behind a pool that looks saturated. Host lock first means a task
waiting its turn at a busy host holds no global capacity at all.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Iterable
from typing import Any, TypeVar
from urllib.parse import urlsplit

T = TypeVar("T")

#: Start here and measure before raising. Chromium costs roughly 100–200 MB per page against
#: the worker's 4 GiB, so 8–10 pages is ~1–2 GB — headroom for the scan itself. Raising this
#: without measuring is how a worker starts being OOM-killed mid-run, which looks like a
#: mysterious cancellation rather than a resource limit.
DEFAULT_MAX_CONCURRENT = 8


def host_key(url: str) -> str:
    """The politeness key for a URL: its host, lowercased, without port or credentials.

    **Host, not registrable domain.** CC-3's body is explicit that a main site, a scholar
    subdomain and faculty subdomains are *distinct hosts* and that twenty concurrent means
    twenty of them — so `cs.uni.edu` and `www.uni.edu` run in parallel. That is the looser
    of the two readings, and it is a deliberate choice rather than an oversight: they are
    usually distinct servers, and collapsing them to `uni.edu` would serialise a whole
    university behind one lock and make a wide scan crawl.

    The key is injectable (``HostPool(key=…)``) precisely because that trade-off could
    reasonably be revisited — a public-suffix-based key can be swapped in without touching
    the pool. An empty host returns ``""``, which shares one lock: a URL we cannot parse is
    the case to be *most* cautious with, not least.
    """
    netloc = urlsplit(url or "").netloc
    host = netloc.rsplit("@", 1)[-1]          # strip any user:pass@
    if host.startswith("["):                  # IPv6 literal: [::1]:8080
        host = host[: host.index("]") + 1] if "]" in host else host
    elif ":" in host:
        host = host.split(":", 1)[0]
    return host.lower()


class HostPool:
    """Runs work concurrently across hosts, serialised within each host.

    ``max_concurrent`` bounds the total in flight; the per-host rule is absolute and is not
    a tunable — two simultaneous requests to one server is the thing this exists to prevent.
    """

    def __init__(self, max_concurrent: int = DEFAULT_MAX_CONCURRENT, *,
                 key: Callable[[str], str] = host_key) -> None:
        if max_concurrent < 1:
            raise ValueError("max_concurrent must be at least 1")
        self.max_concurrent = max_concurrent
        self._key = key
        self._sem: asyncio.Semaphore | None = None
        self._locks: dict[str, asyncio.Lock] = {}
        #: Peak simultaneous in-flight requests, and the peak per host. `peak_per_host` must
        #: never exceed 1; it is recorded rather than asserted so a violation is visible in a
        #: run's numbers and not only in a test.
        self.peak_in_flight = 0
        self.peak_per_host = 0
        self._in_flight = 0
        self._per_host: dict[str, int] = {}

    def _lock_for(self, host: str) -> asyncio.Lock:
        # Created lazily on the running loop. Building them in __init__ would bind them to
        # whatever loop happened to exist at construction time — or to none at all.
        lock = self._locks.get(host)
        if lock is None:
            lock = self._locks[host] = asyncio.Lock()
        return lock

    async def run(self, url: str, fn: Callable[[str], Awaitable[T]]) -> T:
        """Await ``fn(url)`` under both limits: one at a time per host, N overall."""
        if self._sem is None:
            self._sem = asyncio.Semaphore(self.max_concurrent)
        host = self._key(url)
        # HOST FIRST, then global. See the module docstring — the other order starves the
        # pool whenever one host is over-represented in the queue, which is the normal case
        # when a scan walks one university's site.
        async with self._lock_for(host):
            async with self._sem:
                self._in_flight += 1
                n = self._per_host[host] = self._per_host.get(host, 0) + 1
                self.peak_in_flight = max(self.peak_in_flight, self._in_flight)
                self.peak_per_host = max(self.peak_per_host, n)
                try:
                    return await fn(url)
                finally:
                    self._in_flight -= 1
                    self._per_host[host] -= 1

    async def map(self, urls: Iterable[str],
                  fn: Callable[[str], Awaitable[T]]) -> list[T | BaseException]:
        """Run ``fn`` over every URL, returning results in input order.

        A URL whose host is busy is **deferred, not dropped** (CC-3.2) — every input produces
        an entry. A failure comes back as the exception object rather than cancelling its
        siblings: one dead host must not take down the other nineteen, which is the same
        "failure is a state, not an exception" rule the rest of the pipeline follows.
        """
        urls = list(urls)
        if not urls:
            return []
        tasks = [asyncio.create_task(self.run(u, fn)) for u in urls]
        return list(await asyncio.gather(*tasks, return_exceptions=True))


def run_sync(coro: Awaitable[Any]) -> Any:
    """Drive one coroutine to completion from synchronous code.

    The pipeline is synchronous and stays that way; the pool is an implementation detail of
    the fetch layer rather than a rewrite of everything above it. Refuses to run inside an
    existing loop instead of silently creating a second one — nested loops are how "it works
    locally, hangs in the worker" happens.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    raise RuntimeError(
        "run_sync called from inside a running event loop — await the coroutine directly")
