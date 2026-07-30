"""--render-all: Chromium as the main reader, not the fallback.

The behaviour under test is one decision with four outcomes, and the dangerous one is the
fourth: a page that fetched perfectly well and merely could not be rendered must keep its
fetched text. Reporting our own missing browser as the site's wall would manufacture a
`blocked` row out of nothing, and `blocked` is the state that routes a professor to the human
rung — so the cost of getting this wrong is a student sent to do work that was never needed.

| fetched text | render result | outcome                       |
|--------------|---------------|-------------------------------|
| walled       | real content  | rendered text used (D-073)    |
| walled       | still walled  | blocked — it really was a wall|
| walled       | None          | blocked — unchanged           |
| **fine**     | **None**      | **fetched text kept**         |
"""
from supervisorly import pipeline
from supervisorly.fetch import render as R
from supervisorly.fetch.fetcher import Fetcher
from supervisorly.fetch.ratelimit import HostRateLimiter
from supervisorly.fetch.snapshot import SnapshotStore
from supervisorly.model import runs
from supervisorly.model.db import open_db
from supervisorly.fetch.transport import CassetteTransport

WALL = ("<html><body><p>Sign in to continue. Please log in to view this profile. "
        "Create an account.</p></body></html>")
REAL = ("<html><body><p>Professor A. Example, Department of Computing. I am accepting PhD "
        "students for the 2027 intake.</p></body></html>")
RENDERED_TEXT = ("Professor A. Example, Department of Computing. I am recruiting PhD students "
                 "for the 2027 intake and supervise MSc projects.")


class _Renderer:
    """A renderer that answers with a fixed text, or refuses by answering None."""

    def __init__(self, text=RENDERED_TEXT):
        self._text = text
        self.calls = []

    def render(self, url):
        self.calls.append(url)
        if self._text is None:
            return None
        return R.RenderedPage(final_url=url, title="T", text=self._text, status=200)

    def render_many(self, urls):
        urls = list(urls)
        self.calls.extend(urls)
        return {u: (None if self._text is None
                    else R.RenderedPage(final_url=u, title="T", text=self._text, status=200))
                for u in urls}


def _harness(tmp_path, html, url="https://u.edu/p"):
    tp = CassetteTransport()
    tp.record("https://u.edu/robots.txt", 200, "User-agent: *\nAllow: /\n")
    tp.record(url, 200, html)
    conn = open_db(tmp_path / "t.sqlite")
    snaps = SnapshotStore(tmp_path / "snaps")
    fetcher = Fetcher(tp, snaps, sleep=lambda _s: None,
                      rate_limiter=HostRateLimiter(min_interval=0.0))
    run_id = runs.create_run(conn)
    target = {"id": "p", "name": "Dr. Page", "url": url}
    return conn, snaps, fetcher, run_id, target


def _dive(conn, snaps, fetcher, run_id, target, **kw):
    stats = {"resumed_skipped": 0, "extractions": 0, "cache_hits": 0}
    pipeline._deep_dive_one(conn, run_id, target, fetcher, snaps,
                            stats=stats, resume=False, **kw)
    return stats


def _blocked(conn, pid="p"):
    return pipeline._target_open_gap(conn, pid)


# ── the decision table ────────────────────────────────────────────────────────
def test_without_render_all_a_healthy_page_never_touches_the_browser(tmp_path):
    """The default is unchanged: Chromium fires only for a page that read as a wall."""
    conn, snaps, fetcher, run_id, t = _harness(tmp_path, REAL)
    try:
        r = _Renderer()
        _dive(conn, snaps, fetcher, run_id, t, renderer=r, render_all=False)
        assert r.calls == []
    finally:
        conn.close()


def test_with_render_all_a_healthy_page_is_rendered_anyway(tmp_path):
    """The whole point of the flag: the HTTP read only sees what the server sent."""
    conn, snaps, fetcher, run_id, t = _harness(tmp_path, REAL)
    try:
        r = _Renderer()
        stats = _dive(conn, snaps, fetcher, run_id, t, renderer=r, render_all=True)
        assert r.calls == ["https://u.edu/p"]
        assert stats.get("rendered") == 1
    finally:
        conn.close()


def test_a_healthy_page_whose_render_fails_keeps_its_fetched_text(tmp_path):
    """The one that must not regress.

    No Playwright, a timeout, a redirect that robots refuses — render-all asked for a browser
    and did not get one. The page itself answered 200 with real content, so the target is NOT
    blocked and the fetched text is still extracted from.
    """
    conn, snaps, fetcher, run_id, t = _harness(tmp_path, REAL)
    try:
        r = _Renderer(text=None)                     # every render refuses
        stats = _dive(conn, snaps, fetcher, run_id, t, renderer=r, render_all=True)
        assert stats.get("render_fallback") == 1
        assert stats.get("rendered") is None
        assert stats["extractions"] == 1             # the fetched html was still read
        assert not _blocked(conn)                    # and no wall was invented
    finally:
        conn.close()


def test_a_walled_page_whose_render_fails_is_still_blocked(tmp_path):
    """The mirror image: here the page really did refuse, so blocked is the honest answer."""
    conn, snaps, fetcher, run_id, t = _harness(tmp_path, WALL)
    try:
        r = _Renderer(text=None)
        stats = _dive(conn, snaps, fetcher, run_id, t, renderer=r, render_all=True)
        assert stats.get("render_fallback") is None  # NOT the fallback path
        assert _blocked(conn)
    finally:
        conn.close()


def test_a_login_wall_still_cannot_get_in_by_being_rendered(tmp_path):
    """render-all does not weaken the second wall check — rendering a login page is not entry."""
    conn, snaps, fetcher, run_id, t = _harness(tmp_path, WALL)
    try:
        r = _Renderer(text="Sign in to continue. Please log in to view this profile.")
        stats = _dive(conn, snaps, fetcher, run_id, t, renderer=r, render_all=True)
        assert stats.get("render_still_walled") == 1
        assert _blocked(conn)
    finally:
        conn.close()


# ── the batch ────────────────────────────────────────────────────────────────
def test_prerender_is_inert_unless_render_all_is_on(tmp_path):
    conn, snaps, fetcher, run_id, t = _harness(tmp_path, REAL)
    try:
        r = _Renderer()
        urls, pages = pipeline._prerender_batch(conn, [t], r, None, stats={},
                                                resume=False, render_all=False)
        assert (urls, pages) == ({}, {})
        assert r.calls == []
    finally:
        conn.close()


def test_prerender_renders_every_target_in_one_batch(tmp_path):
    conn, snaps, fetcher, run_id, t = _harness(tmp_path, REAL)
    try:
        r = _Renderer()
        t2 = {"id": "q", "name": "Dr. Two", "url": "https://v.edu/q"}
        urls, pages = pipeline._prerender_batch(conn, [t, t2], r, None, stats={},
                                                resume=False, render_all=True)
        assert urls == {"p": "https://u.edu/p", "q": "https://v.edu/q"}
        assert set(pages) == {"https://u.edu/p", "https://v.edu/q"}
        assert r.calls == ["https://u.edu/p", "https://v.edu/q"]   # ONE render_many call
    finally:
        conn.close()


def test_a_prerendered_page_is_not_rendered_a_second_time(tmp_path):
    """The batch is the read. A serial re-render would double every page load."""
    conn, snaps, fetcher, run_id, t = _harness(tmp_path, REAL)
    try:
        batch = _Renderer()
        urls, pages = pipeline._prerender_batch(conn, [t], batch, None, stats={},
                                                resume=False, render_all=True)
        serial = _Renderer()
        stats = _dive(conn, snaps, fetcher, run_id, t, renderer=serial, render_all=True,
                      url_override=urls["p"], prerendered=pages)
        assert serial.calls == []                    # the batch's page was used
        assert stats.get("render_batched") == 1
        assert stats.get("rendered") == 1
    finally:
        conn.close()


def test_a_url_the_batch_failed_is_not_retried_serially(tmp_path):
    """Present-but-None means tried and failed, not unknown — 200 dead urls, paid for once."""
    conn, snaps, fetcher, run_id, t = _harness(tmp_path, REAL)
    try:
        serial = _Renderer()
        stats = _dive(conn, snaps, fetcher, run_id, t, renderer=serial, render_all=True,
                      url_override="https://u.edu/p",
                      prerendered={"https://u.edu/p": None})
        assert serial.calls == []
        assert stats.get("render_fallback") == 1     # fell back, did not retry
        assert not _blocked(conn)
    finally:
        conn.close()


def test_the_url_is_resolved_once_not_once_per_pass(tmp_path):
    """`_page_url_for` can call ORCID's API, so resolving in both passes doubles those hits."""
    conn, snaps, fetcher, run_id, t = _harness(tmp_path, REAL)
    try:
        calls = []
        real = pipeline._page_url_for
        pipeline._page_url_for = (
            lambda tt, oc, st, se=None: calls.append(tt["id"]) or real(tt, oc, st, se))
        try:
            urls, pages = pipeline._prerender_batch(conn, [t], _Renderer(), None, stats={},
                                                    resume=False, render_all=True)
            _dive(conn, snaps, fetcher, run_id, t, renderer=_Renderer(), render_all=True,
                  url_override=urls["p"], prerendered=pages)
        finally:
            pipeline._page_url_for = real
        assert calls == ["p"]
    finally:
        conn.close()


def test_a_resumed_target_is_neither_resolved_nor_rendered(tmp_path):
    conn, snaps, fetcher, run_id, t = _harness(tmp_path, REAL)
    try:
        _dive(conn, snaps, fetcher, run_id, t, renderer=None, render_all=False)
        r = _Renderer()
        urls, pages = pipeline._prerender_batch(conn, [t], r, None, stats={},
                                                resume=True, render_all=True)
        assert urls == {} and pages == {}
        assert r.calls == []
    finally:
        conn.close()


# ── the flags ────────────────────────────────────────────────────────────────
def test_the_scan_command_exposes_both_flags_and_defaults_to_todays_behaviour():
    from supervisorly.cli import build_parser
    from supervisorly.fetch import pool as pool_mod
    a = build_parser().parse_args(["scan", "--demo"])
    assert a.render_all is False                     # opt-in, never a silent default
    assert a.concurrency == pool_mod.DEFAULT_MAX_CONCURRENT
    b = build_parser().parse_args(["scan", "--demo", "--render-all", "--concurrency", "3"])
    assert b.render_all is True and b.concurrency == 3


# ── the artifact must say which rungs ran ────────────────────────────────────
def test_the_export_records_which_rungs_actually_fired(tmp_path):
    """A real scan had to be diagnosed by noticing every source host was orcid.org.

    `--progress` prints phase names, so a run that rendered every page and one that rendered
    none are indistinguishable in the console — and the artifact carried no counter either.
    These are facts about the tool, never about a person, so they export freely.
    """
    from supervisorly import pipeline as P
    for key in ("rendered", "crawl_pages", "search_resolved", "model_claims"):
        assert key in P._RUNG_COUNTERS, f"{key} must be visible in the artifact"


def test_a_rung_that_never_ran_is_absent_rather_than_zero(tmp_path):
    """Absent means 'did not run'; 0 would read as 'ran and found nothing'. Different facts."""
    from supervisorly import pipeline as P
    from supervisorly.model.db import open_db
    conn = open_db(tmp_path / "t.sqlite")
    try:
        res = P._build_result(conn, P.runs.create_run(conn), "finalized", [],
                              stats={"extractions": 3, "rendered": 0}, gaps=0)
        rungs = res["export"]["run"]["rungs"]
        assert rungs.get("extractions") == 3
        assert "rendered" not in rungs          # zero is not evidence the browser ran
        assert "crawl_pages" not in rungs       # never touched at all
    finally:
        conn.close()
