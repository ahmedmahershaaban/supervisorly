"""Edge cases: an abandoned Phase-3 still yields a finalized dashboard (D-049), and a later
human-rung Markdown return fills the gaps and re-exports **without re-fetching** (D-029/043).
The blocked professor is never dropped; the human answer supersedes the blocked placeholder."""

from supervisorly import demo, ingest, pipeline
from supervisorly.export import json_export as jx
from supervisorly.fetch.transport import CassetteTransport
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
    """Wraps a cassette transport and records every network-ish get()."""

    def __init__(self, inner):
        self._inner = inner
        self.urls = []

    @property
    def calls(self):
        return len(self.urls)

    def get(self, url):
        self.urls.append(url)
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


def _page(who):
    return (f"<html><body><main><p>{who} is recruiting PhD students for 2027.</p>"
            "</main></body></html>")


def test_resume_does_not_refetch_already_completed_targets(tmp_path):
    """Edge (D-029): an interrupted scan, resumed later, resumes from Task state and does not
    re-fetch targets already completed — only the remaining ones hit the network."""
    inner = CassetteTransport()
    inner.record("https://u.edu/robots.txt", 200, "User-agent: *\nAllow: /\n")
    for who in ("p1", "p2", "p3"):
        inner.record(f"https://u.edu/people/{who}", 200, _page(who))
    tp = CountingTransport(inner)
    db = tmp_path / "run.sqlite"
    snaps = tmp_path / "snaps"
    plan = {"intent_kind": "pre_phd", "resolved_topic_ids": ["T"]}
    t = lambda who: {"id": who, "name": who, "url": f"https://u.edu/people/{who}"}

    # first pass completes p1 and p2
    pipeline.run_offline(plan, [t("p1"), t("p2")], tp, snaps, db_path=db)

    # resume with an added p3 — completed targets must not be re-requested
    mark = len(tp.urls)
    r2 = pipeline.run_offline(plan, [t("p1"), t("p2"), t("p3")], tp, snaps,
                              db_path=db, resume=True)
    fetched_on_resume = tp.urls[mark:]

    assert "https://u.edu/people/p1" not in fetched_on_resume   # not re-fetched
    assert "https://u.edu/people/p2" not in fetched_on_resume
    assert "https://u.edu/people/p3" in fetched_on_resume       # the new one IS fetched
    assert r2["stats"]["resumed_skipped"] == 2
    # all three are present in the final export (completed ones from persisted claims)
    ids = {p["id"] for p in r2["export"]["professors"]}
    assert ids == {"p1", "p2", "p3"}
    assert all(p["fields"]["recruiting_signal"]["state"] == "value"
               for p in r2["export"]["professors"])
