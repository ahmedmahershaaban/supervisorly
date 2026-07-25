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

ROR_CA = json.dumps({"number_of_results": 2, "items": [   # real ROR always returns the total;
    # v2 record shape (v1 retired Dec 2025)
    {"id": "https://ror.org/00abc11",
     "names": [{"value": "Maple University", "types": ["ror_display", "label"], "lang": "en"}],
     "locations": [{"geonames_details": {"country_code": "CA"}}],
     "links": [{"type": "website", "value": "https://maple.example/"}], "types": ["education"]},
    {"id": "https://ror.org/00abc22",
     "names": [{"value": "Northern Institute", "types": ["ror_display", "label"], "lang": "en"}],
     "locations": [{"geonames_details": {"country_code": "CA"}}],
     "links": [{"type": "website", "value": "https://northern.example/"}], "types": ["education"]},
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


_FAST = {"rate_limit": 0, "backoff_sleep": lambda _s: None}   # cassettes need no politeness delay


def _run(tmp_path):
    return pipeline.run_live(PLAN, _transport(), tmp_path / "snaps", email=EMAIL, **_FAST)


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
    r = pipeline.run_live(PLAN, _transport(), tmp_path / "snaps", email=EMAIL, **_FAST)
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
        pipeline.run_live(PLAN, _transport(), tmp_path / "snaps", email="", **_FAST)


def test_live_scan_respects_optout_on_a_discovered_professor(tmp_path):
    # someone discovered by the ladder who is on the opt-out list is dropped before any fetch (D-023)
    f = tmp_path / "optout.txt"
    f.write_text("A200\n", encoding="utf-8")            # suppress Ada by her id
    r = pipeline.run_live(PLAN, _transport(), tmp_path / "snaps", email=EMAIL,
                          optout_path=str(f), **_FAST)
    ids = {p["id"] for p in r["export"]["professors"]}
    assert "A200" not in ids and "A202" in ids
    assert r["stats"]["opted_out"] == 1


def _trunc_transport():
    """A discovery whose OpenAlex author enumeration is cut short by a mid-pagination 500 → PARTIAL."""
    def _authors(n):
        return json.dumps({"results": [
            {"id": f"https://openalex.org/A{i}", "display_name": f"P{i}", "works_count": 1,
             "cited_by_count": 1, "topics": [{"id": "https://openalex.org/T10001"}],
             "last_known_institutions": [], "homepage_url": None} for i in range(n)]})
    tp = CassetteTransport()
    tp.record(ror.country_url("CA"), 200, json.dumps({"number_of_results": 1, "items": [
        {"id": "https://ror.org/00abc11",
         "names": [{"value": "Maple University", "types": ["ror_display", "label"]}],
         "locations": [{"geonames_details": {"country_code": "CA"}}],
         "links": [{"type": "website", "value": "https://maple.example/"}],
         "types": ["education"]}]}))
    tp.record(openalex.institutions_url("https://ror.org/00abc11", EMAIL), 200, _oa_inst("I100"))
    tp.record(openalex.authors_url("I100", EMAIL, page=1), 200, _authors(25))   # full page → page 2
    tp.record(openalex.authors_url("I100", EMAIL, page=2), 500, "boom")          # fails mid-pagination
    return tp


def test_reexport_preserves_partial_coverage_after_the_human_rung(tmp_path):
    # audit-3 finding 7: a run whose DISCOVERY was truncated must NOT silently claim completeness on
    # the human-rung re-export path — the PARTIAL coverage disclosure survives the resume boundary.
    db = tmp_path / "run.sqlite"
    r1 = pipeline.run_live(PLAN, _trunc_transport(), tmp_path / "snaps", email=EMAIL,
                           db_path=str(db), **_FAST)
    assert "PARTIAL" in r1["export"]["run"]["coverage"]          # the live run discloses it
    assert r1["stats"]["truncated"] == ["authors@I100"]
    targets = [{"id": p["id"], "name": p.get("name")} for p in r1["export"]["professors"]]
    r2 = pipeline.reexport(str(db), targets)                     # resume: re-export from the DB only
    assert "PARTIAL" in r2["export"]["run"]["coverage"]          # still discloses it (was silently lost)
    assert "authors@I100" in r2["export"]["run"]["coverage"]


def test_live_scan_warns_on_sparse_country_coverage_and_continues(tmp_path):
    # D-060 (Phase L0 DoD): the sparse-country preflight is wired into run_live — it warns
    # (2 ROR institutions < 5) and the run still finalizes.
    r = _run(tmp_path)
    assert any("ROR lists only 2 institution(s)" in w for w in r["stats"]["warnings"])
    assert any("OpenAlex coverage" in w for w in r["stats"]["warnings"])   # 90 works < 500
    assert r["export"]["run"]["status"] == "finalized_with_open_gaps"      # never blocks (D-049)
    assert "Warning:" in r["export"]["run"]["coverage"]                    # reaches the export
    assert all(w.isascii() for w in r["stats"]["warnings"])                # console-safe


def test_live_scan_marks_partial_when_institution_resolution_fails(tmp_path):
    # audit: a 500 on Maple University's ROR→OpenAlex resolution must NOT vanish the university —
    # coverage reports PARTIAL naming the ROR id; the surviving institution still deep-dives.
    tp = CassetteTransport()
    tp.record(ror.country_url("CA"), 200, ROR_CA)
    tp.record(openalex.institutions_url("https://ror.org/00abc11", EMAIL), 500, "{}")
    tp.record(openalex.institutions_url("https://ror.org/00abc22", EMAIL), 200, _oa_inst("I200"))
    tp.record(openalex.authors_url("I200", EMAIL), 200, json.dumps({"results": [
        _author("A202", "A/Prof. Cara Cedar", "https://northern.example/~cara"),
    ]}))
    tp.record("https://northern.example/robots.txt", 200, ALLOW)
    tp.record("https://northern.example/~cara", 200, CARA_PAGE)
    r = pipeline.run_live(PLAN, tp, tmp_path / "snaps", email=EMAIL, **_FAST)
    cov = r["export"]["run"]["coverage"]
    assert "PARTIAL" in cov and "inst@00abc11" in cov
    assert r["stats"]["truncated"] == ["inst@00abc11"]
    assert {p["id"] for p in r["export"]["professors"]} == {"A202"}


# ── Wave B audit fixes: marker hand-off, ladder fail-loud, honest opt-out (S1/S4/S6) ──

def test_run_live_merges_cli_side_target_truncation_markers(tmp_path):
    # S1 (pipeline half, D-037): markers recorded by the CLI-side client that resolved
    # --targets merge into the run's truncated list like the ladder's own — the named
    # target UNIONED with the ladder still discloses the failed lookup as PARTIAL.
    target = {"id": "A200", "name": "Dr. Ada Maple", "url": "https://maple.example/~ada",
              "openalex_id": "https://openalex.org/A200"}
    r = pipeline.run_live(PLAN, _transport(), tmp_path / "snaps", email=EMAIL,
                          targets_override=[target],
                          targets_truncated=["author-search@Ghost Prof"], **_FAST)
    assert "author-search@Ghost Prof" in r["stats"]["truncated"]
    cov = r["export"]["run"]["coverage"]
    assert "PARTIAL" in cov and "author-search@Ghost Prof" in cov


def test_select_institutions_fails_loud_on_an_unknown_mode():
    # S4 (defense in depth): the ladder itself raises on an unrecognized university_mode
    # instead of falling through to "all" — silently widening "only these" to the whole
    # country is the worst failure direction (D-002/D-045).
    from supervisorly.discover import ladder

    class _RorStub:
        def institutions_in_country(self, country):
            return []

    with pytest.raises(ValueError, match="unrecognized university_mode 'onyl'"):
        ladder.select_institutions({"country": "CA", "university_mode": "onyl",
                                    "universities": ["Elsewhere U"]}, _RorStub())


def test_opt_out_of_every_target_is_not_misreported_as_a_coverage_gap(tmp_path):
    # S6 (D-023/D-046): when the opt-out list removed everyone, the coverage line says so
    # honestly — an opt-out is a FILTERED result, never a "coverage gap".
    f = tmp_path / "optout.txt"
    f.write_text("A200\nA201\nA202\n", encoding="utf-8")
    r = pipeline.run_live(PLAN, _transport(), tmp_path / "snaps", email=EMAIL,
                          optout_path=str(f), **_FAST)
    assert r["stats"]["opted_out"] == 3
    cov = r["export"]["run"]["coverage"]
    assert "3 professor(s) removed by the opt-out list; none remain to scan." in cov
    assert "coverage gap" not in cov


def test_partial_opt_out_keeps_the_normal_coverage_line(tmp_path):
    # S6 (other half): with some targets remaining, the coverage line is the normal one —
    # the opt-out count is not misreported as a removal of everyone.
    f = tmp_path / "optout.txt"
    f.write_text("A200\n", encoding="utf-8")
    r = pipeline.run_live(PLAN, _transport(), tmp_path / "snaps", email=EMAIL,
                          optout_path=str(f), **_FAST)
    assert r["stats"]["opted_out"] == 1
    cov = r["export"]["run"]["coverage"]
    assert "2 professor(s) enumerated; none were dropped" in cov
    assert "opt-out list" not in cov
