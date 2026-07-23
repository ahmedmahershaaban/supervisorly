"""Edge case: monthly re-scan, nothing changed → ~zero re-extraction (cost §3b-i).

A second run over the same (unchanged) pages must hit the ExtractionCache on every reachable
professor, do no fresh extraction, and create **no duplicate claims** — while still producing
the same honest export."""

from supervisorly import demo, pipeline
from supervisorly.model import claims
from supervisorly.model.db import open_db


def _states(export):
    return {p["id"]: {k: v["state"] for k, v in p["fields"].items()}
            for p in export["professors"]}


def test_warm_rescan_hits_cache_and_adds_no_new_claims(tmp_path):
    tp, targets, plan = demo.demo_fixture()
    db = tmp_path / "run.sqlite"
    snaps = tmp_path / "snaps"

    r1 = pipeline.run_offline(plan, targets, tp, snaps, db_path=db)
    # cold run: every reachable page (ada, ben, cara, dana) was actually extracted
    assert r1["stats"]["extractions"] >= 4
    assert r1["stats"]["cache_hits"] == 0

    conn = open_db(db)
    before = len(claims.claims_for(conn, "person", "ada"))
    assert before >= 1

    r2 = pipeline.run_offline(plan, targets, tp, snaps, db_path=db)
    # warm run: nothing changed → no fresh extraction, every reachable page a cache hit
    assert r2["stats"]["extractions"] == 0
    assert r2["stats"]["cache_hits"] >= 4

    # no duplicate claims were written for the same content
    after = len(claims.claims_for(open_db(db), "person", "ada"))
    assert after == before

    # and the honest output is unchanged across the re-scan
    assert _states(r1["export"]) == _states(r2["export"])


def test_changed_content_busts_the_cache(tmp_path):
    """If a page's real content changes, the hash changes and extraction re-runs (not a hit)."""
    tp, targets, plan = demo.demo_fixture()
    db = tmp_path / "run.sqlite"
    snaps = tmp_path / "snaps"
    pipeline.run_offline(plan, targets, tp, snaps, db_path=db)

    # Ada's page now advertises a *different* recruiting message — a genuine content change.
    tp.record("https://ca-uni.example/people/ada", 200,
              "<html><body><main><h1>Dr. Ada Placeholder</h1>"
              "<p>I am now recruiting three postdocs in reinforcement learning.</p>"
              "</main></body></html>")

    r2 = pipeline.run_offline(plan, targets, tp, snaps, db_path=db)
    # Ada re-extracts (miss); the unchanged pages still hit cache
    assert r2["stats"]["extractions"] >= 1
    assert r2["stats"]["cache_hits"] >= 3
