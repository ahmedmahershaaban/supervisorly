"""P6-1 — historical cycles, and the refusals that make a projection safe.

The dangerous output here is a *date*. A student who reads "1 December 2027" as a deadline and
plans around it has been given a fabricated fact wearing a plausible costume — so nearly every
test below is about the module DECLINING to project, and the acceptance criterion is stated in
those terms: two snapshots yield no projected date, four yield one that renders as `watch`.

SPIKE-6 measured that the history exists (50% of admissions URLs have >= 3 cycles). These
tests measure that having it does not make us reckless with it.
"""

from __future__ import annotations

import json

from supervisorly.discover import archive
from supervisorly.fetch.transport import CassetteTransport

URL = "https://www.asu.edu.eg/postgraduate"


def _cdx(*rows):
    """A CDX response: header row, then (timestamp, statuscode) pairs."""
    return json.dumps([["timestamp", "statuscode"], *[list(r) for r in rows]])


def _tp(status=200, body=None, url=URL):
    tp = CassetteTransport()
    tp.record(archive.cdx_url(url), status, body if body is not None else _cdx())
    return tp


# ── reading the archive ───────────────────────────────────────────────────────
def test_only_2xx_captures_count_as_cycles():
    """A 404 capture proves the URL existed; it is not a cycle whose deadline could be read.
    Counting it would inflate the history that gates the projection."""
    tp = _tp(body=_cdx(("20220101000000", "200"), ("20230101000000", "404"),
                       ("20240101000000", "200")))
    h = archive.cycles_for(tp, URL)
    assert h.years == ["2022", "2024"]
    assert not h.enough


def test_many_captures_in_one_year_are_one_cycle():
    """The CDX query collapses per year, but the parser must not double-count either — fifty
    captures in a busy year is one cycle, and treating it as fifty manufactures a pattern."""
    tp = _tp(body=_cdx(*[(f"2024{m:02d}01000000", "200") for m in range(1, 13)]))
    h = archive.cycles_for(tp, URL)
    assert h.years == ["2024"]


def test_three_good_years_is_enough():
    tp = _tp(body=_cdx(("20220101000000", "200"), ("20230101000000", "200"),
                       ("20240101000000", "200")))
    h = archive.cycles_for(tp, URL)
    assert h.years == ["2022", "2023", "2024"] and h.enough


def test_an_empty_archive_is_an_answer_not_a_failure():
    """`searched` is the four-state distinction: the archive was asked and had nothing, which
    is different from not being able to ask."""
    h = archive.cycles_for(_tp(body=_cdx()), URL)
    assert h.years == [] and h.searched and h.reason is None


def test_rate_limiting_is_a_failure_not_an_empty_history():
    """The archive is a charity and throttles. Reporting its 429 as "no history" would turn
    their rate limit into our claim about an institution."""
    h = archive.cycles_for(_tp(status=429, body="slow down"), URL)
    assert h.years == [] and not h.searched
    assert "rate-limited" in h.reason


def test_an_unreachable_archive_never_raises():
    """Historical enrichment is never load-bearing (P6-1.5)."""
    h = archive.cycles_for(CassetteTransport(), URL)     # no cassette -> TransportError
    assert not h.searched and "unreachable" in h.reason


def test_a_server_error_and_bad_json_are_reasons_not_crashes():
    assert "http 503" in archive.cycles_for(_tp(status=503, body="down"), URL).reason
    assert "unparseable" in archive.cycles_for(_tp(body="<html>nope</html>"), URL).reason


def test_a_url_we_did_not_get_from_discovery_is_refused():
    """P6-1.1 / invariants §2: the archive is queried for URLs discovery produced. A non-URL
    is the shape a constructed guess arrives in, and it is refused rather than normalised."""
    assert "not a fetchable url" in archive.cycles_for(_tp(), "staff/admissions").reason
    assert "not a fetchable url" in archive.cycles_for(_tp(), "").reason


# ── the acceptance criterion ──────────────────────────────────────────────────
def _hist(*years):
    return archive.CycleHistory(url=URL, years=list(years))


def test_two_snapshots_yield_no_projected_date():
    """P6-1.3, verbatim from the acceptance line. Two points are not a pattern."""
    p = archive.project_next(_hist("2023", "2024"), ["2023-12-01", "2024-12-01"])
    assert p.projected is None
    assert "fewer than the 3 needed" in p.reason
    assert "two points are not a pattern" in p.reason


def test_four_snapshots_yield_a_projection_labelled_watch():
    """The other half of the acceptance line: it projects, and it is never `firm`."""
    p = archive.project_next(
        _hist("2022", "2023", "2024", "2025"),
        ["2022-12-01", "2023-12-01", "2024-12-01", "2025-12-01"])
    assert p.projected == "2026-12-01"
    assert p.confidence == "watch"
    assert p.confidence != "firm"


def test_the_projection_says_it_is_a_pattern_not_a_published_date():
    p = archive.project_next(_hist("2022", "2023", "2024"),
                             ["2022-12-01", "2023-12-01", "2024-12-01"])
    assert "not a published date" in p.reason
    assert "confirm on the official page" in p.reason


def test_enough_cycles_but_too_few_readable_dates_still_refuses():
    """Snapshots exist and carry no date → `searched_absent` for the pattern. Projecting from
    two dates because four CAPTURES exist would sidestep the rule through the back door."""
    p = archive.project_next(_hist("2022", "2023", "2024", "2025"),
                             ["2024-12-01", "2025-12-01"])
    assert p.projected is None
    assert "only 2 of 4 archived cycle(s) carried a readable date" in p.reason


def test_a_failed_lookup_never_projects():
    h = archive.CycleHistory(url=URL, reason="archive unreachable: boom")
    p = archive.project_next(h, ["2022-12-01", "2023-12-01", "2024-12-01"])
    assert p.projected is None and "archive unreachable" in p.reason


def test_the_projection_uses_the_commonest_date_not_the_newest():
    """One late year must not drag the projection with it — the pattern is the point."""
    p = archive.project_next(
        _hist("2021", "2022", "2023", "2024"),
        ["2021-12-01", "2022-12-01", "2023-03-15", "2024-12-01"])
    assert p.projected == "2025-12-01"


def test_malformed_dates_are_ignored_rather_than_guessed():
    p = archive.project_next(_hist("2022", "2023", "2024"),
                             ["not a date", "2023-12-01", ""])
    assert p.projected is None, "one readable date out of three must not become a pattern"


def test_a_projection_never_claims_to_be_a_current_deadline():
    """The live page wins for "current" (the module's stated line). Nothing here returns a
    field named `deadline`, so a caller cannot mistake a projection for one."""
    p = archive.project_next(_hist("2022", "2023", "2024"),
                             ["2022-12-01", "2023-12-01", "2024-12-01"])
    assert not hasattr(p, "deadline")
    assert p.confidence == "watch"
