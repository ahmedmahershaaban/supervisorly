"""Phase L2 — the live driver: discovery (ROR + OpenAlex) → the same fetch/extract/claim/export
pipeline, end to end on cassettes (no network, no real keys). Synthetic data (D-035)."""

import json

import pytest

from supervisorly import pipeline, preflight
from supervisorly.discover import openalex, ror
from supervisorly.export import json_export as jx
from supervisorly.fetch.normalize import quote_in_snapshot
from supervisorly.fetch.snapshot import SnapshotStore
from supervisorly.fetch.transport import CassetteTransport

EMAIL = "me@uni.edu"
ALLOW = "User-agent: *\nAllow: /\n"

ROR_CA = json.dumps({"items": [
    {"id": "https://ror.org/00abc11", "name": "Maple University",
     "country": {"country_code": "CA"}, "links": ["https://maple.example/"], "types": ["Education"]},
    {"id": "https://ror.org/00abc22", "name": "Northern Institute",
     "country": {"country_code": "CA"}, "links": ["https://northern.example/"], "types": ["Education"]},
]})


def _oa_inst(oid):
    return json.dumps({"results": [{"id": f"https://openalex.org/{oid}"}]})


def _author(aid, name, home):
    return {"id": f"https://openalex.org/{aid}", "display_name": name, "works_count": 30,
            "cited_by_count": 300, "topics": [{"id": "https://openalex.org/T10001"}],
            "last_known_institutions": [], "homepage_url": home}


ADA_PAGE = ("<html><body><main><h1>Dr. Ada Maple</h1>"
            "<p>I am recruiting two PhD students for Fall 2027.</p>"
            "<p>Applications close on 1 December 2026.</p></main></body></html>")
CARA_PAGE = ("<html><body><main><h1>A/Prof. Cara Cedar</h1>"
             "<p>I am accepting a new PhD student for 2027.</p></main></body></html>")

PLAN = {"intent_kind": "pre_phd", "country": "CA", "field": "causal ml",
        "resolved_topic_ids": ["T10001"], "university_mode": "all"}


def _transport():
    tp = CassetteTransport()
    tp.record(ror.country_url("CA"), 200, ROR_CA)
    tp.record(openalex.institutions_url("https://ror.org/00abc11", EMAIL), 200, _oa_inst("I100"))
    tp.record(openalex.institutions_url("https://ror.org/00abc22", EMAIL), 200, _oa_inst("I200"))
    tp.record(openalex.authors_url("I100", EMAIL), 200, json.dumps({"results": [
        _author("A200", "Dr. Ada Maple", "https://maple.example/~ada"),
        _author("A201", "Prof. Ben Birch", None),           # no homepage → open gap
    ]}))
    tp.record(openalex.authors_url("I200", EMAIL), 200, json.dumps({"results": [
        _author("A202", "A/Prof. Cara Cedar", "https://northern.example/~cara"),
    ]}))
    # professor pages (robots + html)
    tp.record("https://maple.example/robots.txt", 200, ALLOW)
    tp.record("https://maple.example/~ada", 200, ADA_PAGE)
    tp.record("https://northern.example/robots.txt", 200, ALLOW)
    tp.record("https://northern.example/~cara", 200, CARA_PAGE)
    return tp


def _run(tmp_path):
    return pipeline.run_live(PLAN, _transport(), tmp_path / "snaps", email=EMAIL)


def test_live_scan_discovers_and_produces_valid_export(tmp_path):
    r = _run(tmp_path)
    assert jx.validate_export(r["export"]) == []
    assert r["stats"]["discovered"] == 3 and r["stats"]["institutions"] == 2
    ids = {p["id"] for p in r["export"]["professors"]}
    assert ids == {"A200", "A201", "A202"}              # every discovered professor, nobody dropped


def test_live_scan_states_are_honest(tmp_path):
    r = _run(tmp_path)
    st = {p["id"]: p["fields"]["recruiting_signal"]["state"] for p in r["export"]["professors"]}
    assert st["A200"] == "value" and st["A202"] == "value"
    assert st["A201"] == "blocked"                       # no page url → open gap for the human rung
    assert r["export"]["run"]["status"] == "finalized_with_open_gaps"


def test_live_scan_has_zero_hallucinations(tmp_path):
    r = pipeline.run_live(PLAN, _transport(), tmp_path / "snaps", email=EMAIL)
    snaps = SnapshotStore(tmp_path / "snaps")
    checked = 0
    for p in r["export"]["professors"]:
        for env in p["fields"].values():
            if env["state"] == "value":
                assert quote_in_snapshot(env["quote"], snaps.load(env["snapshot_hash"]))
                checked += 1
    assert checked >= 2


def test_live_scan_fails_loud_without_a_contact_email(tmp_path):
    with pytest.raises(preflight.MissingCredentials):
        pipeline.run_live(PLAN, _transport(), tmp_path / "snaps", email="")
