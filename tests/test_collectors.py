"""Phase L3 — the extra collectors: students / industry-collaborations / advertised social, each an
honest, quote-verified Claim (value where present, searched_absent where not). Walled social CONTENT
is never fetched — only an advertised link in the visible text is recorded (D-039/043)."""

from supervisorly import pipeline
from supervisorly.export import json_export as jx
from supervisorly.fetch.normalize import quote_in_snapshot
from supervisorly.fetch.snapshot import SnapshotStore
from supervisorly.fetch.transport import CassetteTransport

RICH = ("<html><body><main><h1>Dr. Rich Page</h1>"
        "<p>I am recruiting a PhD student for 2027.</p>"
        "<p>Current members of my lab include three PhD students and two postdocs.</p>"
        "<p>We collaborate with Acme Corp; this work is funded by BigTech.</p>"
        "<p>Find me on Twitter: https://twitter.com/drrichpage for updates.</p>"
        "</main></body></html>")
BARE = "<html><body><main><h1>Dr. Plain</h1><p>My research is on graph theory.</p></main></body></html>"


# ── unit: each extractor returns a quoted signal or None ──────────────────────
def test_students_extractor():
    v = pipeline.extract_students_signal(RICH)
    assert v and "current members of my lab" in v[0].lower() and v[2] == "quoted_official"
    assert pipeline.extract_students_signal(BARE) is None


def test_industry_extractor():
    v = pipeline.extract_industry_signal(RICH)
    assert v and ("collaborate with" in v[0].lower() or "funded by" in v[0].lower())
    assert pipeline.extract_industry_signal(BARE) is None


def test_social_extractor_records_only_the_link():
    v = pipeline.extract_social(RICH)
    assert v and v[0] == "https://twitter.com/drrichpage"    # trailing text/punctuation trimmed
    assert pipeline.extract_social(BARE) is None


def test_recruiting_sentence_is_not_mistaken_for_a_students_roster():
    # "recruiting PhD students" (future) must not be read as a current-students roster
    assert pipeline.extract_students_signal(
        "<html><body><p>I am recruiting two PhD students for Fall 2027.</p></body></html>") is None


# ── integration: the collectors flow into an honest export ────────────────────
def _run(tmp_path, html):
    tp = CassetteTransport()
    tp.record("https://u.edu/robots.txt", 200, "User-agent: *\nAllow: /\n")
    tp.record("https://u.edu/p", 200, html)
    targets = [{"id": "p", "name": "Dr. Page", "url": "https://u.edu/p"}]
    plan = {"intent_kind": "pre_phd", "resolved_topic_ids": ["T"]}
    return pipeline.run_offline(plan, targets, tp, tmp_path / "snaps")


def test_rich_page_yields_all_collectors_as_values(tmp_path):
    r = _run(tmp_path, RICH)
    assert jx.validate_export(r["export"]) == []
    f = r["export"]["professors"][0]["fields"]
    assert f["students_signal"]["state"] == "value"
    assert f["industry_signal"]["state"] == "value"
    assert f["social"]["state"] == "value" and f["social"]["value"] == "https://twitter.com/drrichpage"
    # every value is quote-verified against the snapshot (zero hallucinations)
    snaps = SnapshotStore(tmp_path / "snaps")
    for env in f.values():
        if env["state"] == "value":
            assert quote_in_snapshot(env["quote"], snaps.load(env["snapshot_hash"]))


def test_bare_page_yields_honest_searched_absent(tmp_path):
    f = _run(tmp_path, BARE)["export"]["professors"][0]["fields"]
    for field in ("students_signal", "industry_signal", "social", "recruiting_signal"):
        assert f[field]["state"] == "searched_absent", field


def test_login_wall_page_is_not_extracted_and_is_blocked(tmp_path):
    # audit (live): a robots-allowed 200 that is really a login/bot wall must NOT have its chrome
    # extracted (even recruiting-ish chrome) — it is routed to the human rung as blocked (D-039/044).
    wall = ("<html><body><main><p>Sign in to view this profile. People also viewed: "
            "labs hiring PhD students now.</p></main></body></html>")
    r = _run(tmp_path, wall)
    f = r["export"]["professors"][0]["fields"]
    for field in ("recruiting_signal", "deadline", "students_signal", "industry_signal", "social"):
        assert f[field]["state"] == "blocked", field       # nothing extracted from the wall
    assert r["export"]["run"]["status"] == "finalized_with_open_gaps"


def test_content_page_with_noscript_js_banner_is_extracted_not_blocked(tmp_path):
    # live audit-2: wiring the wall gate into the deep-dive must NOT block a normal, content-rich page
    # that merely carries a <noscript>Please enable JavaScript</noscript> fallback — its real signals
    # are extracted, not thrown away as false "blocked" emptiness.
    page = RICH.replace(
        "<main>",
        "<noscript>Please enable JavaScript to use all features of this site.</noscript><main>", 1)
    r = _run(tmp_path, page)
    f = r["export"]["professors"][0]["fields"]
    assert f["recruiting_signal"]["state"] == "value"
    assert f["students_signal"]["state"] == "value"
    assert f["social"]["state"] == "value" and f["social"]["value"] == "https://twitter.com/drrichpage"
