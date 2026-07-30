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
    tp.record(openalex.authors_url("I100", EMAIL, topic_ids=["T10001"]), 200, json.dumps({"results": [
        _author("A200", "Dr. Ada Maple", "https://maple.example/~ada"),
        _author("A201", "Prof. Ben Birch", None),           # no homepage → open gap
    ]}))
    tp.record(openalex.authors_url("I200", EMAIL, topic_ids=["T10001"]), 200, json.dumps({"results": [
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
    tp.record(openalex.authors_url("I100", EMAIL, page=1, topic_ids=["T10001"]), 200, _authors(25))   # full page → page 2
    tp.record(openalex.authors_url("I100", EMAIL, page=2, topic_ids=["T10001"]), 500, "boom")          # fails mid-pagination
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
    tp.record(openalex.authors_url("I200", EMAIL, topic_ids=["T10001"]), 200, json.dumps({"results": [
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
        def institutions_in_country(self, country, **kw):
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


# ── live fix: the D-056 shortlist gate bounds the deep-dive ───────────────────
# Live defect: the ladder deep-dived EVERY enumerated professor (6,123 targets for a
# niche field -> 2+ hours). Now ladder targets are ranked by topic overlap (works_count
# breaks ties) and only the top ``shortlist_size`` are deep-dived; the rest stay listed
# with fields never_attempted, and named --targets bypass the gate.

_GATE_ROR = json.dumps({"number_of_results": 1, "items": [
    {"id": "https://ror.org/00abc11",
     "names": [{"value": "Maple University", "types": ["ror_display", "label"], "lang": "en"}],
     "locations": [{"geonames_details": {"country_code": "CA"}}],
     "links": [{"type": "website", "value": "https://maple.example/"}],
     "types": ["education"]}]})


def _gate_author(aid, name, topics, works, home):
    return {"id": f"https://openalex.org/{aid}", "display_name": name,
            "works_count": works, "cited_by_count": works * 10,
            "topics": [{"id": f"https://openalex.org/{t}"} for t in topics],
            "last_known_institutions": [], "homepage_url": home}


_GATE_PAGE = ("<html><body><main><p>I am recruiting a PhD student for 2027.</p>"
              "</main></body></html>")

# ranking against PLAN's resolved_topic_ids ["T10001"]: A300 (overlap 1, works 5) and
# A301 (overlap 1, works 3) beat A302 (overlap 0, works 100) — topic fit outranks size.
_GATE_AUTHORS = json.dumps({"results": [
    _gate_author("A300", "Dr. Fit One", ["T10001"], 5, "https://maple.example/~fit1"),
    _gate_author("A301", "Dr. Fit Two", ["T10001"], 3, "https://maple.example/~fit2"),
    _gate_author("A302", "Dr. Off Topic", ["T10002"], 100, "https://maple.example/~big"),
    _gate_author("A303", "Dr. No Topics", [], 1, "https://maple.example/~small"),
]})


def _gate_transport(with_pages=True):
    tp = CassetteTransport()
    tp.record(ror.country_url("CA"), 200, _GATE_ROR)
    tp.record(openalex.institutions_url("https://ror.org/00abc11", EMAIL), 200,
              _oa_inst("I100"))
    tp.record(openalex.authors_url("I100", EMAIL, topic_ids=["T10001"]), 200, _GATE_AUTHORS)
    if with_pages:
        # pages for the two expected shortlist members ONLY: CassetteTransport raises on any
        # other fetch, so an unchecked target being deep-dived would fail the test outright.
        tp.record("https://maple.example/robots.txt", 200, ALLOW)
        tp.record("https://maple.example/~fit1", 200, _GATE_PAGE)
        tp.record("https://maple.example/~fit2", 200, _GATE_PAGE)
    return tp


def test_shortlist_gate_deep_dives_only_the_top_n_by_topic_fit(tmp_path):
    r = pipeline.run_live(PLAN, _gate_transport(), tmp_path / "snaps", email=EMAIL,
                          shortlist_size=2, **_FAST)
    assert jx.validate_export(r["export"]) == []
    # nobody dropped: all four enumerated professors are exported
    states = {p["id"]: p["fields"]["recruiting_signal"]["state"]
              for p in r["export"]["professors"]}
    assert set(states) == {"A300", "A301", "A302", "A303"}
    # claims exist ONLY for the two shortlisted (highest topic overlap, not highest works)
    assert states["A300"] == "value" and states["A301"] == "value"
    # the rest were never fetched: every field honestly never_attempted, not "searched"
    for p in r["export"]["professors"]:
        if p["id"] in ("A302", "A303"):
            assert all(f["state"] == "never_attempted" for f in p["fields"].values())
    assert r["stats"]["shortlisted"] == 2 and r["stats"]["unchecked"] == 2
    cov = r["export"]["run"]["coverage"]
    assert "4 professor(s) enumerated" in cov
    assert "Deep-dived the top 2 by topic fit" in cov
    assert "the remaining 2 stay listed, unchecked (never_attempted)" in cov


def test_shortlist_gate_never_gates_named_targets(tmp_path):
    # D-066: a named --targets professor always deep-dives, even with no topic overlap and
    # a shortlist already full of ladder targets.
    tp = _gate_transport()
    tp.record("https://named.example/robots.txt", 200, ALLOW)
    tp.record("https://named.example/~prof", 200, _GATE_PAGE)
    named = {"id": "A900", "name": "Dr. Named", "url": "https://named.example/~prof",
             "url_kind": "homepage", "openalex_id": "https://openalex.org/A900",
             "topic_ids": [], "works_count": 0}
    r = pipeline.run_live(PLAN, tp, tmp_path / "snaps", email=EMAIL,
                          targets_override=[named], shortlist_size=2, **_FAST)
    states = {p["id"]: p["fields"]["recruiting_signal"]["state"]
              for p in r["export"]["professors"]}
    assert states["A900"] == "value"                       # bypassed the gate
    assert states["A300"] == "value" and states["A301"] == "value"
    assert r["stats"]["shortlisted"] == 3 and r["stats"]["unchecked"] == 2


def test_shortlist_gate_falls_back_to_works_count_without_plan_topics(tmp_path):
    # a plan with no resolved topic ids still gates (an ungated 6,123-target deep-dive is
    # the defect); with every overlap 0 the ranking is works_count desc.
    tp = CassetteTransport()
    tp.record(ror.country_url("CA"), 200, _GATE_ROR)
    tp.record(openalex.institutions_url("https://ror.org/00abc11", EMAIL), 200,
              _oa_inst("I100"))
    tp.record(openalex.authors_url("I100", EMAIL), 200, json.dumps({"results": [  # unfiltered
        _gate_author("A310", "Dr. Small", ["T10001"], 1, "https://maple.example/~s"),
        _gate_author("A311", "Dr. Big", ["T10001"], 9, "https://maple.example/~b"),
        _gate_author("A312", "Dr. Mid", ["T10001"], 5, "https://maple.example/~m"),
    ]}))
    tp.record("https://maple.example/robots.txt", 200, ALLOW)
    tp.record("https://maple.example/~b", 200, _GATE_PAGE)   # only the works leader's page
    plan = {"intent_kind": "pre_phd", "country": "CA", "university_mode": "all"}  # no topics
    r = pipeline.run_live(plan, tp, tmp_path / "snaps", email=EMAIL,
                          shortlist_size=1, **_FAST)
    states = {p["id"]: p["fields"]["recruiting_signal"]["state"]
              for p in r["export"]["professors"]}
    assert states["A311"] == "value"
    assert states["A310"] == "never_attempted" and states["A312"] == "never_attempted"
    assert "Deep-dived the top 1 by topic fit" in r["export"]["run"]["coverage"]


def test_shortlist_gate_resume_still_skips_completed_targets(tmp_path):
    # resume is unchanged: the shortlisted targets of a prior persisted run are skipped,
    # the unchecked remainder stays listed-and-unchecked (it was never attempted).
    db = tmp_path / "run.sqlite"
    r1 = pipeline.run_live(PLAN, _gate_transport(), tmp_path / "snaps", email=EMAIL,
                           db_path=str(db), shortlist_size=2, **_FAST)
    assert r1["stats"]["shortlisted"] == 2
    r2 = pipeline.run_live(PLAN, _gate_transport(with_pages=False), tmp_path / "snaps",
                           email=EMAIL, db_path=str(db), resume=True, shortlist_size=2, **_FAST)
    assert r2["stats"]["resumed_skipped"] == 2               # no page was re-fetched
    states = {p["id"]: p["fields"]["recruiting_signal"]["state"]
              for p in r2["export"]["professors"]}
    assert states["A300"] == "value" and states["A302"] == "never_attempted"


def test_shortlist_gate_does_nothing_when_targets_fit(tmp_path):
    # at/under the cap the run is exactly as before: everyone deep-dived, no split line
    r = _run(tmp_path)                                       # 3 targets, default cap 40
    assert "shortlisted" not in r["stats"]
    assert "Deep-dived" not in r["export"]["run"]["coverage"]


def test_run_live_reads_plan_max_institutions(tmp_path):
    # the §4.3 scale control: the plan's own max_institutions caps the institution scan,
    # and the cut is disclosed in the run warnings (D-037), never silent
    r = pipeline.run_live({**PLAN, "max_institutions": 1}, _transport(), tmp_path / "snaps",
                          email=EMAIL, **_FAST)
    assert r["stats"]["institutions"] == 1
    assert {p["id"] for p in r["export"]["professors"]} == {"A200", "A201"}
    assert any("institution scan capped at 1 of 2" in w for w in r["stats"]["warnings"])


def test_run_live_max_institutions_param_wins_over_the_plan(tmp_path):
    r = pipeline.run_live({**PLAN, "max_institutions": 1}, _transport(), tmp_path / "snaps",
                          email=EMAIL, max_institutions=2, **_FAST)
    assert r["stats"]["institutions"] == 2                  # explicit param beats the plan
    assert not any("capped" in w for w in r["stats"]["warnings"])
