"""Phase C (part 1): the cache-hash stability property (cost §3b-i), quote-in-snapshot
verification (D-010), and robots enforcement (D-019/D-039)."""

from supervisorly.fetch import normalize as nz
from supervisorly.fetch import robots

# same main content, different volatile chrome (footer, timestamp, hit counter)
PAGE_A = """
<html><head><style>.x{}</style></head><body>
  <nav>Home About</nav>
  <main>
    <p>I am recruiting 1-2 PhD students to start in Fall 2027.</p>
    <p>Application deadline: 2027-12-15.</p>
    <p>Last updated: 2026-07-20</p>
    <p>12,345 views</p>
  </main>
  <footer>© 2026 University · build 4821</footer>
</body></html>
"""
PAGE_B = """
<html><head><style>.y{}</style></head><body>
  <nav>Home About Contact</nav>
  <main>
    <p>I am recruiting 1-2 PhD students to start in Fall 2027.</p>
    <p>Application deadline: 2027-12-15.</p>
    <p>Last updated: 2026-07-24</p>
    <p>98,765 views</p>
  </main>
  <footer>© 2026 University · build 9999</footer>
</body></html>
"""
# genuinely changed recruiting content
PAGE_C = PAGE_A.replace("recruiting 1-2 PhD students", "NOT taking students this year")


def test_content_hash_stable_across_volatile_chrome():
    """The load-bearing cache property: identical main content but different
    timestamps / counters / footer must hash identically."""
    assert nz.content_hash(PAGE_A) == nz.content_hash(PAGE_B)


def test_content_hash_changes_on_real_content_change():
    assert nz.content_hash(PAGE_A) != nz.content_hash(PAGE_C)


def test_deadline_change_invalidates_cache():
    """Regression: a changed application deadline is a REAL content change and must
    change the hash — content dates are not masked (D-061)."""
    changed = PAGE_A.replace("2027-12-15", "2028-06-30")
    assert nz.content_hash(PAGE_A) != nz.content_hash(changed)


def test_deadline_right_after_an_updated_keyword_invalidates_cache():
    """Regression (audit): the old volatile mask swallowed 40 chars of prose after
    "updated", hiding a real deadline change from the cache hash forever (D-061).
    The keyword tail must mask only timestamp-shaped tokens."""
    page = ("<html><body><main><p>Site updated{pad} applications close {d} for entry."
            "</p></main></body></html>")
    for pad in ("", " Monday:", " xxxxxxxxxx"):   # 0–10 chars between keyword and sentence
        a = page.format(pad=pad, d="1 Dec 2026")
        b = page.format(pad=pad, d="5 Jun 2027")
        assert nz.content_hash(a) != nz.content_hash(b)


def test_stamp_timestamp_change_still_hashes_identically():
    """Only the stamp's OWN timestamp is masked — a page whose stamp alone changed
    still hits the warm cache."""
    page = ("<html><body><main><p>Application deadline: 2027-12-15.</p>"
            "<p>Last updated: {d}</p></main></body></html>")
    assert nz.content_hash(page.format(d="2026-07-20")) == \
        nz.content_hash(page.format(d="2026-07-24"))
    assert nz.content_hash(page.format(d="July 20, 2026")) == \
        nz.content_hash(page.format(d="July 24, 2026"))
    assert nz.content_hash(page.format(d="1 Dec 2026")) == \
        nz.content_hash(page.format(d="5 Jun 2027"))


def test_comma_less_counter_change_hashes_identically():
    """Regression (audit): the counter mask required comma groups, so '42 views' ->
    '43 views' busted the cache on unchanged content."""
    page = ("<html><body><main><p>I am recruiting PhD students for Fall 2027.</p>"
            "<p>{n} views</p></main></body></html>")
    assert nz.content_hash(page.format(n=42)) == nz.content_hash(page.format(n=43))
    # the noun guard stays: a bare number next to real content is NOT masked
    assert nz.content_hash(page.format(n=42)) != nz.content_hash(
        page.format(n=42).replace("Fall 2027", "Fall 2028"))


def test_main_text_keeps_dates_but_drops_boilerplate():
    t = nz.main_text(PAGE_A)
    assert "Fall 2027" in t
    assert "2027-12-15" in t          # a real deadline is kept for quote verification
    assert "Home About" not in t      # nav dropped
    assert "build 4821" not in t      # footer dropped


def test_quote_in_snapshot_true_for_real_quote():
    assert nz.quote_in_snapshot(
        "I am recruiting 1-2 PhD students to start in Fall 2027.", PAGE_A
    )
    # whitespace/case tolerant
    assert nz.quote_in_snapshot("i am   RECRUITING 1-2 phd students", PAGE_A)


def test_quote_in_snapshot_false_for_hallucination():
    assert not nz.quote_in_snapshot(
        "I have funding for three postdocs in quantum gravity.", PAGE_A
    )
    assert not nz.quote_in_snapshot("", PAGE_A)


def test_robots_disallow_is_obeyed():
    rt = "User-agent: *\nDisallow: /private/\n"
    assert robots.is_allowed(rt, "https://u.edu/people/jane") is True
    assert robots.is_allowed(rt, "https://u.edu/private/list") is False


def test_robots_fail_closed_when_unavailable():
    assert robots.is_allowed(None, "https://u.edu/people/jane") is False
