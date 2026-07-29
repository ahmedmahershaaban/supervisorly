"""CC-3.3/CC-3.4 — the batch renderer, against real HTTP servers and a real browser.

The pool's locking is proven in ``test_pool.py`` with fake work. That is necessary and not
sufficient: it says the primitive is correct, not that the renderer *uses* it. The failure
this file exists to catch is a batch renderer that acquires pages outside the pool, or holds
them for the whole run — both of which pass every unit test and only show up as a worker
being OOM-killed under load.

So these tests stand up local HTTP servers on distinct loopback ports (distinct hosts, as far
as the pool's key is concerned), record arrival and departure times server-side, and check for
genuine overlap. Nothing here touches a real university.

Skipped without Playwright/Chromium, which the deterministic layer treats as optional
throughout (D-068 fail-closed).
"""

from __future__ import annotations

import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from supervisorly.fetch.render import BatchRenderer

pytest.importorskip("playwright")

PAGE = ("<!doctype html><html><head><title>T{n}</title></head><body><main>"
        "<h1>Page {n}</h1><p>Applications close on 1 December 2026.</p>"
        "</main></body></html>")


class _Server:
    """One loopback HTTP server that records the window each request occupied.

    Bound to a distinct 127.0.0.x **address**, not merely a distinct port. The first version
    of this file used one address and several ports, and every "parallel" test serialised —
    correctly, because ``host_key`` strips the port and two ports on one machine are one
    server. That is the politer reading and it is the intended behaviour, so the fixture
    changed rather than the product. See ``test_two_ports_on_one_address_are_one_host``.
    """

    _next_octet = [1]

    def __init__(self, hold: float = 0.25, host: str | None = None):
        self.hold = hold
        if host is None:
            self._next_octet[0] += 1
            host = f"127.0.0.{self._next_octet[0]}"
        self.host = host
        self.windows: list[tuple[float, float]] = []
        self._lock = threading.Lock()
        outer = self

        class H(BaseHTTPRequestHandler):
            def do_GET(self):                                   # noqa: N802
                start = time.monotonic()
                time.sleep(outer.hold)                          # hold the connection open
                body = PAGE.format(n=self.path.strip("/") or "0").encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                with outer._lock:
                    outer.windows.append((start, time.monotonic()))

            def log_message(self, *a):                          # silence
                pass

        # Threading server: the point is to let concurrent requests actually overlap. A
        # single-threaded server would serialise them itself and every test would pass.
        try:
            self.httpd = ThreadingHTTPServer((self.host, 0), H)
        except OSError:                     # a platform without the 127.0.0.0/8 range
            pytest.skip(f"cannot bind {self.host}")
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def url(self, path: str) -> str:
        return f"http://{self.host}:{self.port}/{path}"

    def max_overlap(self) -> int:
        """Peak simultaneous in-flight requests, from the server's own observations."""
        events = []
        for s, e in self.windows:
            events.append((s, 1))
            events.append((e, -1))
        events.sort()
        cur = peak = 0
        for _t, d in events:
            cur += d
            peak = max(peak, cur)
        return peak

    def stop(self):
        self.httpd.shutdown()
        self.httpd.server_close()


@pytest.fixture()
def servers():
    made = []

    def make(n=1, hold=0.25):
        for _ in range(n):
            made.append(_Server(hold))
        return made[-n:]

    yield make
    for s in made:
        s.stop()


def _renderer(**kw):
    r = BatchRenderer(lambda _u: True, timeout_ms=15_000, **kw)
    if not r.available():
        pytest.skip("chromium not installed for playwright")
    r.close()          # available() launched a SYNC browser; the batch path launches its own
    return BatchRenderer(lambda _u: True, timeout_ms=15_000, **kw)


def test_two_ports_on_one_address_are_one_host(servers):
    """Discovered while writing this file, and worth pinning: the politeness key strips the
    port, so two services on one machine are ONE host and never overlap.

    That is the politer of the two readings and the intended one — a second port is not a
    second server. It is also why the fixture uses distinct 127.0.0.x addresses.
    """
    a, b = servers(2, hold=0.2)
    same_addr = _Server(hold=0.2, host=a.host)      # a second port on a's address
    try:
        r = _renderer(max_concurrent=4)
        r.render_many([a.url("1"), same_addr.url("1")])
        assert r.peak_in_flight == 1, "two ports on one address must not run concurrently"
    finally:
        same_addr.stop()


def test_a_burst_at_one_host_serialises(servers):
    """CC-3's acceptance criterion, observed by the server rather than asserted in-process."""
    (srv,) = servers(1)
    urls = [srv.url(f"p{i}") for i in range(4)]
    out = _renderer(max_concurrent=8).render_many(urls)

    assert len([v for v in out.values() if v]) == 4, "every page must still be rendered"
    assert srv.max_overlap() == 1, (
        f"the server saw {srv.max_overlap()} simultaneous requests — one host must be serial")


def test_across_hosts_it_parallelises(servers):
    """The complement. Without it, a renderer that simply serialised everything would pass
    the test above and be useless."""
    a, b, c = servers(3)
    urls = [a.url("1"), b.url("1"), c.url("1"), a.url("2"), b.url("2"), c.url("2")]
    r = _renderer(max_concurrent=6)
    out = r.render_many(urls)

    assert len([v for v in out.values() if v]) == 6
    assert r.peak_in_flight > 1, "nothing overlapped — distinct hosts must run in parallel"
    assert r.peak_per_host == 1, "the pool recorded two requests in flight at one host"


def test_the_global_cap_is_respected(servers):
    """Concurrency is bounded even when every URL is a different host — the cap is what keeps
    peak memory proportional to the limit rather than to the queue."""
    srvs = servers(6, hold=0.2)
    urls = [s.url("1") for s in srvs]
    r = _renderer(max_concurrent=2)
    r.render_many(urls)
    assert r.peak_in_flight <= 2, f"cap was 2, peak was {r.peak_in_flight}"


def test_the_batch_renders_real_text(servers):
    (srv,) = servers(1, hold=0.0)
    out = _renderer().render_many([srv.url("7")])
    page = out[srv.url("7")]
    assert page is not None
    assert "1 December 2026" in page.text
    assert page.status == 200


def test_a_refused_url_is_None_and_never_fetched(servers):
    """The refusal gate is inherited, not restated — robots says no, nothing is requested."""
    (srv,) = servers(1, hold=0.0)
    r = BatchRenderer(lambda _u: False)
    out = r.render_many([srv.url("1")])
    assert out == {srv.url("1"): None}
    assert srv.windows == [], "a robots-refused URL must never reach the server"
    assert r.refused_by_robots == 1


def test_a_dead_host_does_not_take_down_its_batch(servers):
    """One unreachable host must cost one page, not the run."""
    (srv,) = servers(1, hold=0.0)
    good, dead = srv.url("1"), "http://127.0.0.1:9/nothing-listens-here"
    out = _renderer(max_concurrent=4).render_many([good, dead])
    assert out[good] is not None
    assert out[dead] is None


def test_duplicate_urls_are_rendered_once(servers):
    (srv,) = servers(1, hold=0.0)
    u = srv.url("1")
    out = _renderer().render_many([u, u, u])
    assert list(out) == [u]
    assert len(srv.windows) == 1, "the same URL was fetched more than once"


def test_an_empty_batch_is_not_an_error():
    assert BatchRenderer(lambda _u: True).render_many([]) == {}
