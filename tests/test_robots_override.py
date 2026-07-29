"""--ignore-robots: an override that cannot lie about itself.

The flag is the operator's to set. What is not theirs to set is what the *export* then claims:
"we fetched it" and "we were allowed to" are different facts, and a run that conflates them
would hand a student a dashboard asserting consent nobody gave. So the verdict is still read
and still stored per source — the override changes enforcement, never provenance.
"""
from supervisorly.fetch.fetcher import Fetcher
from supervisorly.fetch.ratelimit import HostRateLimiter
from supervisorly.fetch.snapshot import SnapshotStore
from supervisorly.fetch.transport import CassetteTransport

DENY = "User-agent: *\nDisallow: /\n"
PAGE = "<html><body><p>Professor A. Example supervises PhD students.</p></body></html>"


def _fetcher(tmp_path, *, obey, robots=DENY):
    tp = CassetteTransport()
    tp.record("https://u.edu/robots.txt", 200, robots)
    tp.record("https://u.edu/p", 200, PAGE)
    return Fetcher(tp, SnapshotStore(tmp_path / "s"), sleep=lambda _s: None,
                   rate_limiter=HostRateLimiter(min_interval=0.0), obey_robots=obey)


def test_the_default_is_still_to_obey(tmp_path):
    f = _fetcher(tmp_path, obey=True)
    assert f.obey_robots is True
    assert f.robots_allows("https://u.edu/p") is False
    assert f.fetch("https://u.edu/p").allowed is False


def test_the_override_lets_the_fetch_through(tmp_path):
    f = _fetcher(tmp_path, obey=False)
    res = f.fetch("https://u.edu/p")
    assert res.ok and res.status == 200


def test_the_override_never_rewrites_what_robots_actually_said(tmp_path):
    """The load-bearing one. Enforcement is off; the truth is unchanged."""
    f = _fetcher(tmp_path, obey=False)
    assert f.robots_allows("https://u.edu/p") is True       # what we will do
    assert f.robots_verdict("https://u.edu/p") is False     # what we were told
    assert f.robots_verdict("https://u.edu/p") is not f.robots_allows("https://u.edu/p")


def test_an_allowing_site_reads_the_same_either_way(tmp_path):
    allow = "User-agent: *\nAllow: /\n"
    on = _fetcher(tmp_path / "a", obey=True, robots=allow)
    off = _fetcher(tmp_path / "b", obey=False, robots=allow)
    for f in (on, off):
        assert f.robots_allows("https://u.edu/p") is True
        assert f.robots_verdict("https://u.edu/p") is True


def test_the_renderer_follows_the_same_switch(tmp_path):
    """One switch moves BOTH readers.

    The renderer is constructed with ``fetcher.robots_allows``, so a browser that quietly kept
    obeying while the HTTP client did not is structurally impossible — which is the whole
    reason the override lives on the fetcher rather than in two places.
    """
    from supervisorly.fetch import render as R
    off = _fetcher(tmp_path, obey=False)
    r = R.ChromiumRenderer(off.robots_allows)
    assert r._refusal("https://u.edu/p") is None            # no robots refusal
    on = _fetcher(tmp_path / "on", obey=True)
    assert R.ChromiumRenderer(on.robots_allows)._refusal("https://u.edu/p") is not None


def test_a_walled_host_is_still_refused_by_the_renderer_with_robots_off(tmp_path):
    """--ignore-robots is impoliteness, not a licence to defeat a bot-wall (D-039/D-043)."""
    from supervisorly.fetch import render as R
    off = _fetcher(tmp_path, obey=False)
    r = R.ChromiumRenderer(off.robots_allows)
    assert r._refusal("https://www.researchgate.net/profile/Someone") is not None


# ── the flag and the banner ──────────────────────────────────────────────────
def test_the_flag_defaults_to_off():
    from supervisorly.cli import build_parser
    assert build_parser().parse_args(["scan", "--demo"]).ignore_robots is False
    assert build_parser().parse_args(["scan", "--demo", "--ignore-robots"]).ignore_robots is True


def test_a_nonpositive_concurrency_fails_loud_instead_of_scanning_nothing(tmp_path):
    """Guarded before any directory is made or any request sent — 0 would render nothing."""
    from supervisorly.cli import build_parser, cmd_scan
    args = build_parser().parse_args(
        ["scan", "--demo", "--concurrency", "0", "--out", str(tmp_path / "d.html")])
    assert cmd_scan(args) == 2
    assert not (tmp_path / "d.html").exists()          # it really did stop first


def test_turning_robots_off_prints_a_banner_naming_whose_ip_pays(tmp_path, capsys):
    """A setting this consequential must not be discoverable only by reading the flags back.

    The banner must precede the work, so this run is made to die at the concurrency guard —
    if the banner only printed later, there would be nothing captured here.
    """
    from supervisorly.cli import build_parser, cmd_scan
    args = build_parser().parse_args(
        ["scan", "--demo", "--ignore-robots", "--concurrency", "0",
         "--out", str(tmp_path / "d.html")])
    assert cmd_scan(args) == 2
    out = capsys.readouterr().out
    assert "robots.txt WILL NOT BE ENFORCED" in out
    assert "IP" in out


def test_an_ordinary_demo_scan_prints_no_banner(tmp_path, capsys):
    from supervisorly.cli import build_parser, cmd_scan
    args = build_parser().parse_args(["scan", "--demo", "--out", str(tmp_path / "d.html")])
    assert cmd_scan(args) == 0
    assert "WILL NOT BE ENFORCED" not in capsys.readouterr().out
