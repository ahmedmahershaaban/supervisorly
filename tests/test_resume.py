"""Edge cases: an abandoned Phase-3 still yields a finalized dashboard (D-049), and a later
human-rung Markdown return fills the gaps and re-exports **without re-fetching** (D-029/043).
The blocked professor is never dropped; the human answer supersedes the blocked placeholder."""

from supervisorly import demo, ingest, pipeline
from supervisorly.export import json_export as jx
from supervisorly.model.db import open_db

# The student's Phase-3 return for the robots-blocked professor (retrieved by hand in a
# browser). Written in the one shared grammar (extract.md_grammar).
EVE_MD = """# Supervisorly — human retrieval
target: person=eve  name=Prof. Eve Walled
retrieved_at: 2026-07-21

## field: recruiting_signal
value: Recruiting a PhD student in HCI for 2027.
quote: I am recruiting a PhD student in HCI for 2027.
source_url: https://x.com/evewalled/status/123
observed_at: 2026-07-21
confidence: unconfirmed

## field: deadline
state: searched_absent
source_url: https://x.com/evewalled
note: no deadline mentioned on the profile
"""


class CountingTransport:
    """Wraps the demo cassette transport and counts every network-ish get()."""

    def __init__(self, inner):
        self._inner = inner
        self.calls = 0

    def get(self, url):
        self.calls += 1
        return self._inner.get(url)

    def record(self, *a, **k):
        return self._inner.record(*a, **k)


def _eve(export):
    return next(p for p in export["professors"] if p["id"] == "eve")


def test_abandoned_phase3_still_finalizes_with_open_gaps(tmp_path):
    tp, targets, plan = demo.demo_fixture()
    result = pipeline.run_offline(plan, targets, tp, tmp_path / "snaps",
                                  db_path=tmp_path / "run.sqlite")
    # a dashboard exists even though the walled professor couldn't be reached
    assert "<!doctype html>" in result["html"].lower()
    assert result["export"]["run"]["status"] == "finalized_with_open_gaps"
    # the blocked professor is present, not dropped, marked blocked (not never_attempted)
    eve = _eve(result["export"])
    assert eve["fields"]["recruiting_signal"]["state"] == "blocked"
    assert eve["fields"]["deadline"]["state"] == "blocked"


def test_md_return_fills_gaps_and_reexports_without_refetching(tmp_path):
    inner_tp, targets, plan = demo.demo_fixture()
    tp = CountingTransport(inner_tp)
    db = tmp_path / "run.sqlite"
    snaps = tmp_path / "snaps"

    pipeline.run_offline(plan, targets, tp, snaps, db_path=db)
    calls_after_scan = tp.calls
    assert calls_after_scan > 0                      # the scan did fetch reachable pages

    # the human rung returns the walled professor's data
    conn = open_db(db)
    out = ingest.ingest_md(conn, EVE_MD)
    conn.close()
    assert out["recorded"] == 2 and out["rejected"] == []

    # re-export from the database + disk snapshots — constructs no transport at all
    re = pipeline.reexport(db, targets)

    # nothing was re-fetched: the counting transport saw no new calls
    assert tp.calls == calls_after_scan

    # the gap is now filled from the human-assisted source, and the run is finalized
    assert re["export"]["run"]["status"] == "finalized"
    eve = _eve(re["export"])
    assert eve["fields"]["recruiting_signal"]["state"] == "value"
    assert "HCI" in eve["fields"]["recruiting_signal"]["value"]
    assert "x.com" in eve["fields"]["recruiting_signal"]["source_url"]
    assert eve["fields"]["deadline"]["state"] == "searched_absent"
    # still a valid, honest export (the human value cites its source_url, D-010)
    assert jx.validate_export(re["export"]) == []

    # the other professors are unchanged (re-exported from the same claims)
    ada = next(p for p in re["export"]["professors"] if p["id"] == "ada")
    assert ada["fields"]["recruiting_signal"]["state"] == "value"
