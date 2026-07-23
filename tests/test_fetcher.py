"""Phase C2: the fetcher is robots-gated, rate-limited, snapshot-storing, and offline
via cassettes. Exercises the edge-case rows 404-mark and robots-blocked."""

from supervisorly.fetch import normalize as nz
from supervisorly.fetch.fetcher import Fetcher
from supervisorly.fetch.ratelimit import HostRateLimiter
from supervisorly.fetch.snapshot import SnapshotStore
from supervisorly.fetch.transport import CassetteTransport

PEOPLE_HTML = (
    "<html><body><main><p>Prof Jane — I am recruiting PhD students for Fall 2027."
    "</p></main></body></html>"
)


def _fake_clock():
    """A controllable clock/sleep pair so the rate limiter is tested without real time."""
    t = {"now": 0.0, "slept": []}
    return t


def _make(tmp_path, cassettes):
    tp = CassetteTransport()
    for url, (status, text) in cassettes.items():
        tp.record(url, status, text)
    snaps = SnapshotStore(tmp_path / "snaps")
    return tp, snaps


def test_fetch_allowed_page_stores_verifiable_snapshot(tmp_path):
    tp, snaps = _make(tmp_path, {
        "https://u.edu/robots.txt": (200, "User-agent: *\nDisallow: /private/\n"),
        "https://u.edu/people/jane": (200, PEOPLE_HTML),
    })
    f = Fetcher(tp, snaps)
    res = f.fetch("https://u.edu/people/jane")
    assert res.ok and res.status == 200 and res.snapshot_hash
    # the stored snapshot supports quote verification (D-010)
    html = snaps.load(res.snapshot_hash)
    assert nz.quote_in_snapshot("I am recruiting PhD students for Fall 2027", html)


def test_robots_disallowed_is_not_fetched(tmp_path):
    tp, snaps = _make(tmp_path, {
        "https://u.edu/robots.txt": (200, "User-agent: *\nDisallow: /private/\n"),
    })
    f = Fetcher(tp, snaps)
    res = f.fetch("https://u.edu/private/roster")
    assert res.allowed is False and res.snapshot_hash is None
    assert "robots" in res.error


def test_404_is_marked_not_crashed(tmp_path):
    tp, snaps = _make(tmp_path, {
        "https://u.edu/robots.txt": (404, ""),
        "https://u.edu/people/ghost": (404, "not found"),
    })
    f = Fetcher(tp, snaps)
    res = f.fetch("https://u.edu/people/ghost")
    assert res.allowed is True and res.status == 404 and res.snapshot_hash is None
    assert "404" in res.error


def test_missing_robots_fails_closed(tmp_path):
    # robots.txt errors (5xx) → deny (fail closed), page never fetched
    tp, snaps = _make(tmp_path, {
        "https://u.edu/robots.txt": (503, "busy"),
        "https://u.edu/people/jane": (200, PEOPLE_HTML),
    })
    f = Fetcher(tp, snaps)
    res = f.fetch("https://u.edu/people/jane")
    assert res.allowed is False


def test_rate_limiter_waits_between_same_host(tmp_path):
    slept: list[float] = []
    clock = {"t": 0.0}
    rl = HostRateLimiter(min_interval=2.0, clock=lambda: clock["t"], sleep=slept.append)
    # first hit: no wait; second immediate hit: waits the full interval
    assert rl.wait("h") == 0.0
    assert rl.wait("h") == 2.0
    assert slept == [2.0]
