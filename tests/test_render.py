"""Server-side rendering (D-073) — the guarantees, without needing a browser.

Playwright is not installed in the test environment and these tests do not want it: what has
to hold is that the renderer obeys robots, refuses walls, and cannot break a scan. Those are
all decidable with a fake browser, and pinning them here means they are checked on every run
rather than only when someone remembers to build the worker image.
"""

from __future__ import annotations

import pytest

from supervisorly.fetch import render as R


class _Resp:
    def __init__(self, status): self.status = status


class _Page:
    def __init__(self, status=200, text="Prof A. Example is recruiting PhD students.",
                 url="https://x.test/final", goto_raises=False):
        self._status, self._text, self.url = status, text, url
        self._goto_raises = goto_raises
        self.closed = False
        self.navigated_to = None

    def set_default_timeout(self, *_a, **_k): pass
    def goto(self, url, **_k):
        self.navigated_to = url
        if self._goto_raises:
            raise RuntimeError("net::ERR_CERT_AUTHORITY_INVALID")
        return _Resp(self._status)
    def wait_for_load_state(self, *_a, **_k): pass
    def evaluate(self, _js, *_a):
        return {"text": self._text, "title": "T", "finalUrl": self.url}
    def close(self): self.closed = True


class _Browser:
    def __init__(self, page): self._page = page; self.pages_made = 0
    def new_page(self, **_k):
        self.pages_made += 1
        return self._page
    def close(self): pass


def _renderer(robots_check=lambda _u: True, page=None):
    r = R.ChromiumRenderer(robots_check)
    r._browser = _Browser(page or _Page())
    r._js = "() => ({})"                       # stand-in; the fake page ignores it
    return r


# ─────────────────────────────────────────────────── robots is not optional

def test_a_renderer_cannot_be_built_without_a_robots_check():
    """No default, on purpose. A renderer that is robots-gated only when someone remembers to
    pass a checker is not robots-gated — and when WE drive the browser, we are the robot."""
    for bad in (None, "yes", 1, object()):
        with pytest.raises(ValueError, match="robots_check is required"):
            R.ChromiumRenderer(bad)


def test_a_disallowed_url_is_never_navigated_to():
    page = _Page()
    r = _renderer(robots_check=lambda _u: False, page=page)
    assert r.render("https://x.test/private") is None
    assert page.navigated_to is None           # not "navigated then discarded" — never opened
    assert r.refused_by_robots == 1


def test_a_robots_check_that_explodes_is_treated_as_no():
    """Fail closed: an unknown robots answer is a no, never an optimistic yes."""
    def boom(_u): raise RuntimeError("robots.txt unreachable")
    r = _renderer(robots_check=boom)
    assert r.render("https://x.test/") is None
    assert r.refused_by_robots == 1


# ─────────────────────────────────────────────── a wall is a refusal, not an obstacle

@pytest.mark.parametrize("status", [401, 403, 404, 429, 500, 503])
def test_a_non_2xx_page_is_refused_rather_than_scraped_anyway(status):
    """ResearchGate answers 403 to machines. Rendering it anyway is defeating a bot-wall,
    which D-039/D-043 forbid — walls go to the student's own browser untouched. A headless
    Chromium is exactly the tool that COULD get past one, which is why this is a test."""
    r = _renderer(page=_Page(status=status))
    assert r.render("https://walled.test/profile") is None
    assert r.rendered == 0


@pytest.mark.parametrize("walled", [
    "https://www.researchgate.net/profile/Shimaa_Abu_Zeid",
    "https://researchgate.net/profile/X",
    "https://www.academia.edu/123/Paper",
    "https://scholar.google.com/citations?user=abc",
    "https://scholar.google.co.uk/citations?user=abc",
    "https://uk.linkedin.com/in/prof",
    "https://x.com/prof", "https://twitter.com/prof",
])
def test_a_walled_host_is_refused_before_the_browser_is_even_opened(walled):
    """The near-miss this guard was written for, measured against the real host on
    2026-07-28: ResearchGate answers **403 to httpx and 200 to Chromium**, and the renderer
    pulled 55,568 characters of a professor's page off it.

    The status-code guard could never have caught that — a browser is not shown the wall, so
    refusing on the response means refusing on evidence that never arrives. Refusal has to be
    a property of the HOST, decided before the request. If this test ever fails, the tool has
    started using a browser to walk through walls it refuses over plain HTTP."""
    page = _Page(status=200, text="a professor's entire profile page")
    r = _renderer(page=page)
    assert r.render(walled) is None
    assert page.navigated_to is None, "the browser must not even open a walled host"
    assert r.refused_walled == 1
    assert r.rendered == 0


def test_the_renderer_and_the_pipeline_share_one_walled_list():
    """Two copies of a refusal rule is two chances to disagree, and the permissive copy is the
    one that ends up on the network. This is exactly how the gap above appeared."""
    from supervisorly import pipeline
    from supervisorly.fetch import walls
    assert pipeline._WALLED_SOCIAL is walls.WALLED_HOSTS


def test_a_page_that_says_yes_and_needs_javascript_is_rendered():
    """The case the whole module exists for: public, robots-allowed, 200, content only after
    JS. That is a reader limitation, not a wall."""
    r = _renderer(page=_Page(status=200, text="I am accepting PhD students for 2027."))
    out = r.render("https://orcid.org/0000-0002-1825-0097")
    assert out is not None
    assert "accepting PhD students" in out.text
    assert out.final_url == "https://x.test/final"     # the FINAL url is what gets cited
    assert r.rendered == 1


# ─────────────────────────────────────────────── nothing here can fail a scan

def test_navigation_failure_is_none_not_an_exception():
    """Egyptian university hosts served broken TLS chains in the 2026-07-28 measurements;
    that must cost one professor's page, never the run."""
    r = _renderer(page=_Page(goto_raises=True))
    assert r.render("https://cu.edu.eg/") is None
    assert r.failed == 1


def test_a_page_that_renders_to_nothing_is_not_an_empty_claim():
    r = _renderer(page=_Page(text="   "))
    assert r.render("https://x.test/") is None


def test_no_url_is_a_no_op():
    r = _renderer()
    assert r.render("") is None and r.render(None) is None


def test_the_page_is_always_closed_even_when_extraction_fails():
    page = _Page()
    page.evaluate = lambda *_a: (_ for _ in ()).throw(RuntimeError("detached"))
    r = _renderer(page=page)
    assert r.render("https://x.test/") is None
    assert page.closed, "a leaked page per professor exhausts the container"


def test_without_playwright_the_renderer_is_simply_unavailable(monkeypatch):
    """The CLI, the suite and the offline demo must need none of this (D-011/D-063)."""
    r = R.ChromiumRenderer(lambda _u: True)
    monkeypatch.setattr(r, "_ensure_browser", lambda: None)
    assert r.available() is False
    assert r.render("https://x.test/") is None


# ─────────────────────────────────────────────── the extractor is the shared one

def test_every_runtime_data_file_is_declared_as_package_data():
    """Files loaded at runtime must be in the WHEEL, not merely in the repo.

    This is the test that would have caught a full deploy cycle: `extract/*.js` was missing
    from pyproject's package-data, which is invisible from a source checkout — running from
    src/ reads the file off disk. The deployed worker failed with "No such file or directory:
    .../supervisorly/extract/page_extract.js" and rendering was silently disabled for the
    entire scan. Any future runtime asset has to be added here AND to pyproject."""
    import re
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    declared = re.search(r'supervisorly\s*=\s*\[(.*?)\]',
                         (root / "pyproject.toml").read_text(encoding="utf-8"), re.S)
    assert declared, "package-data entry for `supervisorly` not found in pyproject.toml"
    patterns = set(re.findall(r'"([^"]+)"', declared.group(1)))
    assert "extract/*.js" in patterns, patterns
    assert "model/*.sql" in patterns, patterns
    # and the files those globs promise really exist
    src = root / "src" / "supervisorly"
    assert (src / "extract" / "page_extract.js").is_file()
    assert list((src / "model").glob("*.sql"))


def test_a_missing_extractor_disables_rendering_with_an_accurate_message(monkeypatch, caplog):
    """The message must name the right component. It used to say "chromium failed to launch"
    for a missing JS file — accurate about the path, wrong about the cause, and believed."""
    import logging
    r = R.ChromiumRenderer(lambda _u: True)
    monkeypatch.setattr(R, "_load_extractor_js",
                        lambda: (_ for _ in ()).throw(FileNotFoundError("page_extract.js")))
    with caplog.at_level(logging.WARNING):
        assert r._ensure_browser() is None
    assert any("page extractor missing" in m for m in caplog.messages), caplog.messages
    assert not any("chromium failed to launch" in m for m in caplog.messages)


def test_the_in_page_extractor_is_the_file_the_human_rung_uses():
    """Not a Python re-implementation. page_extract.js mirrors normalize.main_text, so a
    rendered snapshot is byte-compatible with a fetched one and the D-010 quote gate runs
    unchanged. A second definition of "the text of a page" would make quotes verify against
    one and fail against the other."""
    src = R._load_extractor_js()
    assert "page_extract.js" in src
    assert R._PAGE_EXTRACT_JS.name == "page_extract.js"
    assert R._PAGE_EXTRACT_JS.parent.name == "extract"


def test_ingest_records_truthful_provenance_for_a_server_render(tmp_path):
    """The server rung is NOT the human rung: robots WAS consulted, and an institutional page
    is still institutional when Chromium reads it. Recording `agent_browser` /
    robots_allowed=None here would state two falsehoods."""
    from supervisorly.fetch import browser_rung
    from supervisorly.model.db import open_db
    conn = open_db(tmp_path / "t.sqlite")
    try:
        out = browser_rung.ingest_page(
            conn, tmp_path / "snaps", final_url="https://uni.example.edu/prof",
            text="I am accepting PhD students.", title="Prof",
            source_tier="official_institutional", robots_allowed=True)
        row = conn.execute("SELECT source_tier, robots_allowed FROM web_source "
                           "WHERE source_id=?", (out["source_id"],)).fetchone()
        assert row["source_tier"] == "official_institutional"
        assert row["robots_allowed"] in (1, True)
    finally:
        conn.close()


class _FakeRenderer:
    def __init__(self, text): self._text = text
    def render(self, url):
        return R.RenderedPage(final_url=url, title="T", text=self._text, status=200)


def test_a_login_page_cannot_get_in_by_being_rendered(tmp_path):
    """The guard that stops "render it" quietly becoming "defeat it".

    A login wall renders perfectly — it is a real page, just not the professor's. So the
    rendered text goes back through the SAME detector that sent us here, and if it still looks
    walled the target stays blocked and routed to the human rung (D-039/D-043)."""
    from supervisorly import pipeline
    from supervisorly.fetch.snapshot import SnapshotStore
    from supervisorly.model.db import open_db
    conn = open_db(tmp_path / "t.sqlite")
    try:
        snaps = SnapshotStore(tmp_path / "snaps")
        stats = {}
        walled = "Sign in to continue. Please log in to view this profile. Create an account."
        out = pipeline._render_page(conn, snaps, "https://x.test/p", None,
                                    _FakeRenderer(walled), stats)
        assert out is None
        assert stats.get("render_still_walled") == 1
    finally:
        conn.close()


def test_a_javascript_page_that_renders_to_real_content_is_accepted(tmp_path):
    from supervisorly import pipeline
    from supervisorly.fetch.snapshot import SnapshotStore
    from supervisorly.model.db import open_db
    conn = open_db(tmp_path / "t.sqlite")
    try:
        snaps = SnapshotStore(tmp_path / "snaps")
        stats = {}
        real = ("Professor A. Example, Department of Computing. I am accepting PhD students "
                "for the 2027 intake and supervise MSc projects.")
        out = pipeline._render_page(conn, snaps, "https://uni.example.edu/p", None,
                                    _FakeRenderer(real), stats)
        assert out is not None
        html, source_id, snapshot_hash = out
        assert "accepting PhD students" in html
        assert stats.get("rendered") == 1
        # the evidence must cite the RENDERED snapshot, and the quote must verify against it
        from supervisorly.fetch.normalize import quote_in_snapshot
        assert quote_in_snapshot("I am accepting PhD students for the 2027 intake", html)
        # ...and a quote with one character the page does not contain does NOT verify. The
        # first version of this test asserted the sentence WITH a full stop, which the page
        # does not have ("intake and supervise…"), and the gate rejected it — the mechanism
        # working on its author.
        assert not quote_in_snapshot("I am accepting PhD students for the 2027 intake.", html)
        assert snaps.load(snapshot_hash) == html
    finally:
        conn.close()


def test_no_renderer_means_exactly_todays_behaviour(tmp_path):
    from supervisorly import pipeline
    from supervisorly.fetch.snapshot import SnapshotStore
    from supervisorly.model.db import open_db
    conn = open_db(tmp_path / "t.sqlite")
    try:
        assert pipeline._render_page(conn, SnapshotStore(tmp_path / "s"), "https://x.test/",
                                     None, None, {}) is None
    finally:
        conn.close()


def test_the_human_rung_default_is_unchanged(tmp_path):
    """The existing CLI path must keep saying robots was never consulted."""
    from supervisorly.fetch import browser_rung
    from supervisorly.model.db import open_db
    conn = open_db(tmp_path / "t2.sqlite")
    try:
        out = browser_rung.ingest_page(conn, tmp_path / "s2",
                                       final_url="https://x.test/", text="hello")
        row = conn.execute("SELECT source_tier, robots_allowed FROM web_source "
                           "WHERE source_id=?", (out["source_id"],)).fetchone()
        assert row["source_tier"] == browser_rung.SOURCE_TIER == "agent_browser"
        assert row["robots_allowed"] is None
    finally:
        conn.close()
