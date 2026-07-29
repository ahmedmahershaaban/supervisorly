"""CC-3 — concurrency across hosts, never within one.

The acceptance criterion is a *negative*: no matter how the work is shuffled, two requests to
one host must never be in flight at the same time. So these tests do not check a counter
afterwards — they record overlap **while it happens**, by having the fake work hold its slot
across an await point. A test that only inspected the final tallies would pass against an
implementation with no locking at all.

The second property is subtler and is the one the lock order exists for: a queue dominated by
a single host must not stall the other hosts. That failure is invisible at small scale and
looks like "the scan is slow" at large scale.
"""

from __future__ import annotations

import asyncio

import pytest

from supervisorly.fetch.pool import DEFAULT_MAX_CONCURRENT, HostPool, host_key, run_sync


# ── the key ───────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("url,expected", [
    ("https://uni.edu/staff", "uni.edu"),
    ("https://UNI.edu/Staff", "uni.edu"),
    ("https://uni.edu:8443/x", "uni.edu"),
    ("https://user:pw@uni.edu/x", "uni.edu"),
    ("http://[::1]:9000/x", "[::1]"),
    ("not a url", ""),
    ("", ""),
])
def test_host_key(url, expected):
    assert host_key(url) == expected


def test_subdomains_are_distinct_hosts():
    """CC-3's body is explicit: a main site, a scholar subdomain and faculty subdomains are
    distinct hosts, and twenty concurrent means twenty of them."""
    assert host_key("https://cs.uni.edu/a") != host_key("https://www.uni.edu/a")


def test_the_key_is_injectable():
    """The host-vs-registrable-domain trade-off is a judgement call, so it is swappable
    without touching the pool."""
    pool = HostPool(key=lambda u: "everything-is-one-host")
    order = []

    async def work(u):
        order.append(("start", u))
        await asyncio.sleep(0)
        order.append(("end", u))

    run_sync(pool.map(["https://a.edu/1", "https://b.edu/1"], work))
    assert pool.peak_per_host == 1
    assert order == [("start", "https://a.edu/1"), ("end", "https://a.edu/1"),
                     ("start", "https://b.edu/1"), ("end", "https://b.edu/1")]


# ── the acceptance criterion ──────────────────────────────────────────────────
class _Tracker:
    """Fake work that holds its slot across an await, so real overlap is observable."""

    def __init__(self, hold: float = 0.005):
        self.hold = hold
        self.live: dict[str, int] = {}
        self.max_per_host = 0
        self.max_total = 0
        self.done: list[str] = []

    async def __call__(self, url: str) -> str:
        host = host_key(url)
        self.live[host] = self.live.get(host, 0) + 1
        self.max_per_host = max(self.max_per_host, self.live[host])
        self.max_total = max(self.max_total, sum(self.live.values()))
        await asyncio.sleep(self.hold)          # the window a violation would appear in
        self.live[host] -= 1
        self.done.append(url)
        return url


def test_twenty_urls_across_three_hosts_never_double_up_on_one(tmp_path):
    """CC-3.5, verbatim."""
    hosts = ["a.edu", "b.edu", "c.edu"]
    urls = [f"https://{hosts[i % 3]}/page{i}" for i in range(20)]
    pool, work = HostPool(max_concurrent=10), _Tracker()
    results = run_sync(pool.map(urls, work))

    assert work.max_per_host == 1, "two requests were in flight at one host"
    assert pool.peak_per_host == 1, "the pool's own counter disagrees with the observed one"
    assert len(results) == 20 and set(results) == set(urls), "every URL was run exactly once"


def test_across_many_hosts_it_actually_parallelises():
    """The complement: serialising everything would also pass the test above, and would make
    the pool pointless."""
    urls = [f"https://h{i}.edu/x" for i in range(12)]
    pool, work = HostPool(max_concurrent=6), _Tracker()
    run_sync(pool.map(urls, work))
    assert work.max_total > 1, "nothing ran concurrently — the pool is serialising everything"
    assert work.max_total <= 6, "the global cap was exceeded"


def test_a_single_host_burst_serialises():
    """The other extreme: 20 URLs at ONE host is 20 sequential requests, however wide the
    pool is."""
    urls = [f"https://one.edu/p{i}" for i in range(20)]
    pool, work = HostPool(max_concurrent=10), _Tracker()
    run_sync(pool.map(urls, work))
    assert work.max_per_host == 1 and work.max_total == 1
    assert len(work.done) == 20, "deferred, never dropped"


def test_a_busy_host_does_not_hold_global_slots_hostage():
    """The lock-order bug, pinned.

    Global-semaphore-first would let 10 same-host tasks each take a slot and then queue on
    one lock, holding the whole pool while doing nothing. The other host would finish only
    after them. Host-lock-first means it finishes immediately.
    """
    urls = [f"https://busy.edu/p{i}" for i in range(10)] + ["https://quiet.edu/only"]
    pool, work = HostPool(max_concurrent=4), _Tracker(hold=0.01)
    run_sync(pool.map(urls, work))
    position = work.done.index("https://quiet.edu/only")
    assert position < 4, (
        f"the lone quiet.edu request finished {position + 1}th — a busy host is holding "
        "global capacity while it waits on its own lock")


def test_every_input_produces_an_output_in_order():
    urls = [f"https://h{i % 2}.edu/p{i}" for i in range(8)]
    pool = HostPool(max_concurrent=3)

    async def echo(u):
        await asyncio.sleep(0)
        return u

    assert run_sync(pool.map(urls, echo)) == urls


def test_one_failing_host_does_not_take_down_the_others():
    """Failure is a state, not an exception — one dead host must not cancel nineteen others."""
    urls = ["https://good.edu/1", "https://bad.edu/1", "https://good2.edu/1"]

    async def work(u):
        await asyncio.sleep(0)
        if "bad" in u:
            raise RuntimeError("host exploded")
        return u

    results = run_sync(HostPool().map(urls, work))
    assert results[0] == "https://good.edu/1"
    assert isinstance(results[1], RuntimeError)
    assert results[2] == "https://good2.edu/1"


def test_a_failure_releases_its_locks():
    """A host lock leaked on the error path would wedge that host for the rest of the run."""
    async def work(u):
        await asyncio.sleep(0)
        if u.endswith("1"):
            raise RuntimeError("boom")
        return u

    pool = HostPool()
    out = run_sync(pool.map(["https://h.edu/1", "https://h.edu/2"], work))
    assert isinstance(out[0], RuntimeError)
    assert out[1] == "https://h.edu/2", "the second request never got the lock back"


# ── shape ─────────────────────────────────────────────────────────────────────
def test_an_empty_batch_is_not_an_error():
    assert run_sync(HostPool().map([], lambda u: None)) == []


def test_max_concurrent_must_be_at_least_one():
    with pytest.raises(ValueError):
        HostPool(max_concurrent=0)


def test_the_default_width_is_measured_not_aspirational():
    """~100-200 MB per Chromium page against the worker's 4 GiB. The comment in the module
    says 8-10; pin it so a casual bump has to argue with a test."""
    assert 4 <= DEFAULT_MAX_CONCURRENT <= 10


def test_run_sync_refuses_to_nest():
    """Silently creating a second loop is how "works locally, hangs in the worker" happens."""
    async def outer():
        coro = asyncio.sleep(0)
        try:
            with pytest.raises(RuntimeError, match="running event loop"):
                run_sync(coro)
        finally:
            coro.close()          # refused, so nothing awaited it

    asyncio.run(outer())
