"""Round AM — the archive rung, and the line it must not cross.

`discover/archive.py` was the last "built, tested, called by nothing" module, and the reason it
stayed unwired was a real question, not laziness: **a projection has no snapshot.** D-010 says
every field carries a quote verified against the page it came from, and no page exists yet for
a future deadline. So the answer is not "wire it into `fields` carefully" — it is that a
projection can never go there at all. It rides in `profile`, beside `match`, on the terms that
block already sets.

These tests pin the line, not the arithmetic (`test_archive.py` already covers the module).
"""

from __future__ import annotations

import json

import pytest

from supervisorly import cli, demo, pipeline
from supervisorly.discover import archive
from supervisorly.export import json_export as jx

DEADLINE_HTML = """<html><body><main>
<h1>Dr. Alex Example</h1>
<p>Applications for the PhD programme close on 15 December {year}.</p>
</main></body></html>"""


class _CdxTransport:
    """Answers the CDX query and nothing else — a capture fetch goes through the Fetcher."""

    def __init__(self, years=("2022", "2023", "2024"), status=200, body=None):
        self.years, self.status, self.body, self.calls = years, status, body, []

    def get(self, url, headers=None):
        self.calls.append(url)
        rows = [["timestamp", "statuscode"]]
        rows += [[f"{y}0601000000", "200"] for y in self.years]
        text = self.body if self.body is not None else json.dumps(rows)
        return type("R", (), {"status": self.status, "text": text,
                              "headers": {}, "url": url})()


class _StubFetcher:
    """Returns an archived capture for any web.archive.org replay url."""

    def __init__(self, snaps, per_year=None):
        self._snaps = snaps
        self._per_year = per_year or {y: DEADLINE_HTML.format(year=y)
                                      for y in ("2022", "2023", "2024")}
        self.fetched = []

    def fetch(self, url):
        self.fetched.append(url)
        year = url.split("/web/")[1][:4]
        html = self._per_year.get(year)
        if html is None:
            return type("F", (), {"ok": False, "snapshot_hash": None})()
        return type("F", (), {"ok": True,
                              "snapshot_hash": self._snaps.store(html)})()


@pytest.fixture()
def snaps(tmp_path):
    from supervisorly.fetch.snapshot import SnapshotStore
    return SnapshotStore(tmp_path / "snaps")


def _project(snaps, transport, fetcher, stats=None):
    return pipeline._archive_projection(
        {"id": "p1"}, "https://uni.example/~alex", fetcher, snaps, transport,
        stats=stats if stats is not None else {})


# ── the line ────────────────────────────────────────────────────────────────
def test_a_projection_never_becomes_a_claim(snaps):
    """The whole reason this stayed unwired. No snapshot of a future date exists, so there is
    nothing a quote could be verified against — `fields` is closed to it by construction."""
    tp = _CdxTransport()
    got = _project(snaps, tp, _StubFetcher(snaps))
    assert got["projected"] == "2025-12-15"
    assert got["confidence"] == "watch"          # never "firm", never "quoted_official"
    assert "quote" not in got and "state" not in got


def test_it_lands_in_profile_and_survives_the_export(tmp_path):
    tp, targets, plan = demo.demo_fixture()
    for t in targets:
        t["deadline_projection"] = {"projected": "2027-01-15", "confidence": "watch",
                                    "reason": "projected from 3 archived cycle(s)",
                                    "from_years": ["2023", "2024", "2025"],
                                    "observed_dates": ["2024-01-15"],
                                    "source_url": "https://uni.example/x"}
    r = pipeline.run_offline(plan, targets, tp, tmp_path / "s")
    prof = r["export"]["professors"][0]
    assert prof["profile"]["deadline_projection"]["projected"] == "2027-01-15"
    assert "deadline_projection" not in prof["fields"]
    assert prof["fields"]["deadline"]["state"] != "value" or \
        prof["fields"]["deadline"]["quote"]        # a real deadline still needs its quote
    assert jx.validate_export(r["export"]) == []


def test_a_run_that_never_asked_carries_no_projection_key(tmp_path):
    """Honest emptiness: 'we did not look' and 'we looked and could not' are different, and
    only one of them is a reason to go and check the page yourself."""
    tp, targets, plan = demo.demo_fixture()
    r = pipeline.run_offline(plan, targets, tp, tmp_path / "s")
    assert all("deadline_projection" not in p["profile"]
               for p in r["export"]["professors"])


# ── refusals ────────────────────────────────────────────────────────────────
def test_two_cycles_are_not_a_pattern(snaps):
    tp = _CdxTransport(years=("2023", "2024"))
    got = _project(snaps, tp, _StubFetcher(snaps))
    assert got["projected"] is None
    assert "fewer than the 3 needed" in got["reason"]


def test_captures_without_a_readable_date_refuse_rather_than_guess(snaps):
    tp = _CdxTransport()
    blank = {y: "<html><body><main>Dr. Alex Example</main></body></html>"
             for y in ("2022", "2023", "2024")}
    got = _project(snaps, tp, _StubFetcher(snaps, per_year=blank))
    assert got["projected"] is None
    assert "carried a readable date" in got["reason"]


def test_a_rate_limited_archive_is_never_our_claim(snaps):
    """The archive is a charity. Their throttle must not become our statement about an
    institution's admissions."""
    tp = _CdxTransport(status=429)
    got = _project(snaps, tp, _StubFetcher(snaps))
    assert got["projected"] is None
    assert "rate-limited" in got["reason"]
    assert got["from_years"] == []


def test_an_unreachable_archive_cannot_fail_a_scan(snaps):
    class _Dead:
        def get(self, url, headers=None):
            from supervisorly.fetch.transport import TransportError
            raise TransportError("connection reset")

    got = _project(snaps, _Dead(), _StubFetcher(snaps))
    assert got["projected"] is None and "unreachable" in got["reason"]


def test_no_captures_are_fetched_when_there_is_no_pattern(snaps):
    """Below three cycles the answer is already 'no' — spending the archive's bandwidth to
    confirm it would be rude and pointless."""
    fetcher = _StubFetcher(snaps)
    _project(snaps, _CdxTransport(years=("2024",)), fetcher)
    assert fetcher.fetched == []


def test_at_most_five_captures_are_read(snaps):
    fetcher = _StubFetcher(snaps, per_year={str(y): DEADLINE_HTML.format(year=y)
                                            for y in range(2010, 2025)})
    _project(snaps, _CdxTransport(years=[str(y) for y in range(2010, 2025)]), fetcher)
    assert len(fetcher.fetched) == pipeline.ARCHIVE_MAX_CAPTURES


def test_the_newest_cycles_are_the_ones_read(snaps):
    """A 2011 capture of a since-restructured programme describes something that no longer
    exists; the recent ones describe the current process."""
    years = [str(y) for y in range(2010, 2025)]
    fetcher = _StubFetcher(snaps, per_year={y: DEADLINE_HTML.format(year=y) for y in years})
    _project(snaps, _CdxTransport(years=years), fetcher)
    read = {u.split("/web/")[1][:4] for u in fetcher.fetched}
    assert read == {"2020", "2021", "2022", "2023", "2024"}


# ── the replay url is the archive's addressing, not an authored candidate ────
def test_replay_url_addresses_the_url_we_were_given():
    url = "https://uni.example/~alex/admissions"
    got = archive.replay_url(url, "2023")
    assert got == f"https://web.archive.org/web/20230601000000id_/{url}"
    assert url in got                     # never a different page


def test_the_cdx_query_names_the_same_url():
    assert "uni.example" in archive.cdx_url("https://uni.example/x")


# ── wiring ──────────────────────────────────────────────────────────────────
def test_archive_is_a_registered_flag():
    ns = cli.build_parser().parse_args(
        ["scan", "--country", "CA", "--field", "ml", "--archive"])
    assert ns.use_archive is True


def test_the_counters_reach_the_run_summary():
    for key in ("archive_lookups", "archive_pages", "archive_projected"):
        assert key in pipeline._RUNG_COUNTERS


def test_the_rung_only_runs_where_the_deadline_is_missing(snaps):
    """A page that published its date needs no projection, and asking the archive anyway
    spends a charity's bandwidth to re-derive what the page already said."""
    src = open(pipeline.__file__, encoding="utf-8").read()
    assert 'if archive_transport is not None and not claims.live_value(' in src
    assert '"deadline")' in src


def test_the_stats_are_counted(snaps):
    stats: dict = {}
    _project(snaps, _CdxTransport(), _StubFetcher(snaps), stats)
    assert stats["archive_lookups"] == 1
    assert stats["archive_pages"] == 3
    assert stats["archive_projected"] == 1
