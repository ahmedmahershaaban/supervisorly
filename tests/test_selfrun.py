"""Phase I — the self-run. A full end-to-end scan on cassettes (no network, no LLM)
must produce a valid four-state export + a self-contained dashboard, with ZERO
hallucinated facts and no professor dropped (the goal's §4 centrepiece)."""

from supervisorly import pipeline
from supervisorly.export import json_export as jx
from supervisorly.fetch.normalize import quote_in_snapshot
from supervisorly.fetch.snapshot import SnapshotStore
from supervisorly.fetch.transport import CassetteTransport

ROBOTS = "User-agent: *\nDisallow: /private/\n"
P1 = ("<html><body><main><h1>Prof One</h1>"
      "<p>I am recruiting two PhD students to start in Fall 2027.</p>"
      "</main></body></html>")
P2 = ("<html><body><main><h1>Prof Two</h1>"
      "<p>My research is on causal inference and NLP.</p>"   # no recruiting sentence
      "</main></body></html>")
# P3 lives behind a disallowed path → blocked


def _run(tmp_path):
    tp = CassetteTransport()
    tp.record("https://u.edu/robots.txt", 200, ROBOTS)
    tp.record("https://u.edu/people/one", 200, P1)
    tp.record("https://u.edu/people/two", 200, P2)
    targets = [
        {"id": "p1", "name": "Prof One", "url": "https://u.edu/people/one"},
        {"id": "p2", "name": "Prof Two", "url": "https://u.edu/people/two"},
        {"id": "p3", "name": "Prof Three", "url": "https://u.edu/private/three"},  # robots-blocked
    ]
    plan = {"intent_kind": "pre_phd", "resolved_topic_ids": ["T_nlp"]}
    result = pipeline.run_offline(plan, targets, tp, tmp_path / "snaps")
    return result, SnapshotStore(tmp_path / "snaps")


def test_self_run_produces_valid_export(tmp_path):
    result, _ = _run(tmp_path)
    assert jx.validate_export(result["export"]) == [], jx.validate_export(result["export"])


def test_self_run_shows_all_four_relevant_states_and_drops_no_one(tmp_path):
    result, _ = _run(tmp_path)
    profs = {p["id"]: p for p in result["export"]["professors"]}
    assert set(profs) == {"p1", "p2", "p3"}                       # nobody dropped
    assert profs["p1"]["fields"]["recruiting_signal"]["state"] == "value"
    assert profs["p2"]["fields"]["recruiting_signal"]["state"] == "searched_absent"
    assert profs["p3"]["fields"]["recruiting_signal"]["state"] == "blocked"  # robots-blocked


def test_self_run_has_zero_hallucinated_facts(tmp_path):
    """Every value in the export must be a quote actually present in its snapshot."""
    result, snaps = _run(tmp_path)
    checked = 0
    for p in result["export"]["professors"]:
        for env in p["fields"].values():
            if env["state"] == "value":
                assert env["snapshot_hash"], "a value must reference its snapshot"
                html = snaps.load(env["snapshot_hash"])
                assert quote_in_snapshot(env["quote"], html), \
                    f"hallucination: quote not in snapshot for {p['id']}"
                checked += 1
    assert checked >= 1   # we actually verified at least one real value


def test_self_run_dashboard_is_self_contained(tmp_path):
    result, _ = _run(tmp_path)
    html = result["html"]
    assert "<!doctype html>" in html.lower()
    assert "<script src=" not in html and "cdn" not in html.lower()
    assert "Prof One" in html and "Prof Three" in html
