"""Phase C2: the fetcher is robots-gated, rate-limited, snapshot-storing, and offline
via cassettes. Exercises the edge-case rows 404-mark and robots-blocked."""

from supervisorly.fetch import normalize as nz
from supervisorly.fetch.fetcher import Fetcher
from supervisorly.fetch.ratelimit import HostRateLimiter
from supervisorly.fetch.snapshot import SnapshotStore
from supervisorly.fetch.transport import CassetteTransport, Response

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


# ── redirects: robots applies to the FINAL url, not just the requested one ──────
def _redirect_response(_requested: str, final: str, text: str = PEOPLE_HTML):
    """A cassette Response whose URL differs from the request — a followed redirect."""
    return Response(final, 200, text)


def test_redirect_into_disallowed_path_is_denied_and_not_snapshotted(tmp_path):
    """Audit: a same-host redirect into a Disallow'd path must not be fetched —
    robots is re-checked against the final URL, fail closed (D-019)."""
    tp = CassetteTransport({
        "https://u.edu/robots.txt": _redirect_response(
            "https://u.edu/robots.txt", "https://u.edu/robots.txt",
            "User-agent: *\nDisallow: /private/\n"),
        "https://u.edu/people/jane": _redirect_response(
            "https://u.edu/people/jane", "https://u.edu/private/roster"),
    })
    snaps = SnapshotStore(tmp_path / "snaps")
    res = Fetcher(tp, snaps).fetch("https://u.edu/people/jane")
    assert res.allowed is False and res.snapshot_hash is None   # body discarded, NO snapshot
    assert res.final_url == "https://u.edu/private/roster"
    assert "robots" in res.error


def test_cross_host_redirect_to_a_disallow_all_host_is_denied(tmp_path):
    """Audit: a cross-host redirect lands on a host robots never vetted — re-check there too."""
    tp = CassetteTransport({
        "https://u.edu/robots.txt": _redirect_response(
            "https://u.edu/robots.txt", "https://u.edu/robots.txt", "User-agent: *\nAllow: /\n"),
        "https://u.edu/people/jane": _redirect_response(
            "https://u.edu/people/jane", "https://other.example/track"),
        "https://other.example/robots.txt": _redirect_response(
            "https://other.example/robots.txt", "https://other.example/robots.txt",
            "User-agent: *\nDisallow: /\n"),
    })
    res = Fetcher(tp, SnapshotStore(tmp_path / "snaps")).fetch("https://u.edu/people/jane")
    assert res.allowed is False and res.snapshot_hash is None
    assert res.final_url == "https://other.example/track"


def test_allowed_redirect_is_fetched_and_source_recorded_under_the_final_url(tmp_path):
    """An allowed redirect is fetched; the pipeline records provenance under the FINAL
    url so the export never cites a page the claim didn't come from (D-010)."""
    from supervisorly import pipeline
    from supervisorly.model.db import open_db
    tp = CassetteTransport({
        "https://u.edu/robots.txt": _redirect_response(
            "https://u.edu/robots.txt", "https://u.edu/robots.txt", "User-agent: *\nAllow: /\n"),
        "https://u.edu/people/jane": _redirect_response(
            "https://u.edu/people/jane", "https://u.edu/people/jane-new"),
    })
    # fetcher level: the redirect is followed, fetched, and the final URL surfaced
    res = Fetcher(tp, SnapshotStore(tmp_path / "snaps")).fetch("https://u.edu/people/jane")
    assert res.ok and res.final_url == "https://u.edu/people/jane-new"
    # pipeline level: the recorded web_source cites the final URL, not the requested one
    db = tmp_path / "run.sqlite"
    targets = [{"id": "p1", "name": "Prof Jane", "url": "https://u.edu/people/jane"}]
    pipeline.run_offline({"intent_kind": "pre_phd"}, targets, tp, tmp_path / "snaps2",
                         db_path=db)
    urls = [r[0] for r in open_db(db).execute("SELECT url FROM web_source")]
    assert urls == ["https://u.edu/people/jane-new"]


def test_rate_limiter_waits_between_same_host(tmp_path):
    slept: list[float] = []
    clock = {"t": 0.0}
    rl = HostRateLimiter(min_interval=2.0, clock=lambda: clock["t"], sleep=slept.append)
    # first hit: no wait; second immediate hit: waits the full interval
    assert rl.wait("h") == 0.0
    assert rl.wait("h") == 2.0
    assert slept == [2.0]
