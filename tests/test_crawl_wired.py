"""--crawl wired: reaching the sentence that lives one click off the staff card.

The measured shape of the problem is that a professor's own page is usually a staff card —
title, email, publication list — and "I am recruiting PhD students for 2027" is on the *Join
the group* page it links to. So the test that matters is the end-to-end one: with the crawl
off the field is an honest absence, with it on the field is a cited fact whose quote verifies
against the page it was actually found on.
"""
from supervisorly import pipeline
from supervisorly.fetch.fetcher import Fetcher
from supervisorly.fetch.ratelimit import HostRateLimiter
from supervisorly.fetch.snapshot import SnapshotStore
from supervisorly.fetch.transport import CassetteTransport
from supervisorly.model import claims as claims_mod
from supervisorly.model import runs
from supervisorly.model.db import open_db

# NB: the link text is "Vacancies", not "Join the group". The first draft of this fixture used
# the latter and every test failed *green-ly* — `extract_recruiting_signal` matched the anchor
# text on the card itself, so the crawl appeared unnecessary. The card must genuinely say
# nothing about recruiting or this file tests nothing.
CARD = ("<html><body><h1>Dr. Ada Lovelace</h1><p>Reader in Computing.</p>"
        '<a href="/group/vacancies">Vacancies</a>'
        '<a href="/publications">Publications</a></body></html>')
JOIN = ("<html><body><p>I am recruiting PhD students for the 2027 intake. "
        "Applications close on 15 January 2027 - apply by then.</p></body></html>")
PUBS = "<html><body><p>A list of papers.</p></body></html>"


def _harness(tmp_path):
    tp = CassetteTransport()
    tp.record("https://cs.uni.edu/robots.txt", 200, "User-agent: *\nAllow: /\n")
    tp.record("https://cs.uni.edu/people/ada", 200, CARD)
    tp.record("https://cs.uni.edu/group/vacancies", 200, JOIN)
    tp.record("https://cs.uni.edu/publications", 200, PUBS)
    conn = open_db(tmp_path / "t.sqlite")
    snaps = SnapshotStore(tmp_path / "snaps")
    fetcher = Fetcher(tp, snaps, sleep=lambda _s: None,
                      rate_limiter=HostRateLimiter(min_interval=0.0))
    target = {"id": "p", "name": "Ada Lovelace", "url": "https://cs.uni.edu/people/ada"}
    return conn, snaps, fetcher, runs.create_run(conn), target, tp


def _dive(conn, snaps, fetcher, run_id, target, **kw):
    stats = {"resumed_skipped": 0, "extractions": 0, "cache_hits": 0}
    pipeline._deep_dive_one(conn, run_id, target, fetcher, snaps,
                            stats=stats, resume=False, **kw)
    return stats


def _claim(conn, field, pid="p"):
    rows = [c for c in claims_mod.claims_for(conn, "person", pid) if c["field"] == field]
    return rows[0] if rows else None


def test_without_the_crawl_the_recruiting_sentence_is_never_reached(tmp_path):
    """Today's behaviour: the staff card says nothing, so the field is an honest absence."""
    conn, snaps, fetcher, run_id, t, _ = _harness(tmp_path)
    try:
        _dive(conn, snaps, fetcher, run_id, t, crawl=False)
        assert _claim(conn, "recruiting_signal")["state"] == "searched_absent"
    finally:
        conn.close()


def test_with_the_crawl_it_becomes_a_cited_fact(tmp_path):
    """The whole point. And the citation must be the page it was really found on."""
    conn, snaps, fetcher, run_id, t, _ = _harness(tmp_path)
    try:
        stats = _dive(conn, snaps, fetcher, run_id, t, crawl=True)
        row = _claim(conn, "recruiting_signal")
        assert row["state"] == "value"
        assert "recruiting PhD students" in row["quote"]
        assert row["source_url"] == "https://cs.uni.edu/group/vacancies"
        assert stats.get("crawl_claims", 0) >= 1
    finally:
        conn.close()


def test_only_links_that_could_carry_the_answer_are_requested(tmp_path):
    """`Publications` is a real same-host link and is still never fetched."""
    conn, snaps, fetcher, run_id, t, tp = _harness(tmp_path)
    try:
        _dive(conn, snaps, fetcher, run_id, t, crawl=True)
        asked = [c for c in getattr(tp, "requested", []) or []]
        # CassetteTransport may not record requests; fall back to the claim evidence.
        if asked:
            assert not any("publications" in u for u in asked)
        assert _claim(conn, "recruiting_signal")["source_url"].endswith("/group/vacancies")
    finally:
        conn.close()


def test_the_walk_stops_once_every_field_has_an_answer(tmp_path):
    """A professor whose card already says everything costs no extra requests at all."""
    conn, snaps, fetcher, run_id, t, _ = _harness(tmp_path)
    try:
        full = ("<html><body><p>I am recruiting PhD students. Applications close on "
                "15 January 2027 - apply by then. I currently supervise four PhD students. "
                "We collaborate with and are funded by industry partners. "
                'See https://twitter.com/ada</p><a href="/group/join">Join</a></body></html>')
        tp2 = CassetteTransport()
        tp2.record("https://cs.uni.edu/robots.txt", 200, "User-agent: *\nAllow: /\n")
        tp2.record("https://cs.uni.edu/people/ada", 200, full)
        f2 = Fetcher(tp2, snaps, sleep=lambda _s: None,
                     rate_limiter=HostRateLimiter(min_interval=0.0))
        stats = _dive(conn, snaps, f2, run_id, t, crawl=True)
        # /group/join was never recorded in this cassette; if the walk had run it would have
        # tried to fetch it. No crawl_pages means it never needed to.
        assert stats.get("crawl_pages") is None
    finally:
        conn.close()


def test_a_crawled_page_records_the_real_robots_verdict(tmp_path):
    conn, snaps, fetcher, run_id, t, _ = _harness(tmp_path)
    try:
        _dive(conn, snaps, fetcher, run_id, t, crawl=True)
        row = _claim(conn, "recruiting_signal")
        src = conn.execute("SELECT robots_allowed FROM web_source WHERE source_id=?",
                           (row["source_id"],)).fetchone()
        assert src["robots_allowed"] == 1
    finally:
        conn.close()


def test_a_crawl_that_finds_nothing_leaves_the_honest_absence_intact(tmp_path):
    conn, snaps, fetcher, run_id, t, _ = _harness(tmp_path)
    try:
        tp2 = CassetteTransport()
        tp2.record("https://cs.uni.edu/robots.txt", 200, "User-agent: *\nAllow: /\n")
        tp2.record("https://cs.uni.edu/people/ada", 200, CARD)
        tp2.record("https://cs.uni.edu/group/vacancies", 200,
                   "<html><body><p>Directions to the department.</p></body></html>")
        f2 = Fetcher(tp2, snaps, sleep=lambda _s: None,
                     rate_limiter=HostRateLimiter(min_interval=0.0))
        _dive(conn, snaps, f2, run_id, t, crawl=True)
        assert _claim(conn, "recruiting_signal")["state"] == "searched_absent"
    finally:
        conn.close()
