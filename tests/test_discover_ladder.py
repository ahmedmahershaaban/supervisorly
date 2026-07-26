"""Phase L1 — the discovery ladder turns a SearchPlan into de-duplicated professor targets from
ROR + OpenAlex (cassettes, no network). Synthetic data (invented names/example domains, D-035)."""

import json

from supervisorly.discover import ladder, openalex, ror
from supervisorly.fetch.transport import CassetteTransport

EMAIL = "me@uni.edu"

ROR_CA = json.dumps({"number_of_results": 2, "items": [   # ROR v2 shape (v1 retired Dec 2025)
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


def _author(aid, name, topics, works, home=None):
    return {"id": f"https://openalex.org/{aid}", "display_name": name,
            "works_count": works, "cited_by_count": works * 10,
            "topics": [{"id": f"https://openalex.org/{t}"} for t in topics],
            "last_known_institutions": [], "homepage_url": home}


AUTHORS_I100 = json.dumps({"results": [
    _author("A200", "Dr. Ada Maple", ["T10001", "T10002"], 42, "https://maple.example/~ada"),
    _author("A201", "Prof. Ben Birch", ["T10002"], 20),
]})
AUTHORS_I200 = json.dumps({"results": [
    _author("A200", "Dr. Ada Maple", ["T10003"], 40),          # same author, other institution
    _author("A202", "A/Prof. Cara Cedar", ["T10001"], 15, "https://northern.example/~cara"),
]})


def _clients():
    tp = CassetteTransport()
    tp.record(ror.country_url("CA"), 200, ROR_CA)
    tp.record(openalex.institutions_url("https://ror.org/00abc11", EMAIL), 200, _oa_inst("I100"))
    tp.record(openalex.institutions_url("https://ror.org/00abc22", EMAIL), 200, _oa_inst("I200"))
    tp.record(openalex.authors_url("I100", EMAIL, topic_ids=["T10001", "T10002"]),
              200, AUTHORS_I100)
    tp.record(openalex.authors_url("I200", EMAIL, topic_ids=["T10001", "T10002"]),
              200, AUTHORS_I200)
    return ror.RorClient(tp, email=EMAIL), openalex.OpenAlexClient(tp, email=EMAIL)


PLAN = {"intent_kind": "pre_phd", "country": "CA", "field": "causal ml",
        "resolved_topic_ids": ["T10001", "T10002"], "university_mode": "all"}


def test_build_targets_enumerates_and_dedupes():
    rc, oa = _clients()
    out = ladder.build_targets(PLAN, rc, oa)
    ids = [t["id"] for t in out["targets"]]
    assert ids == ["A200", "A201", "A202"]              # nobody dropped, no duplicate Ada
    ada = out["targets"][0]
    # Ada appeared at both institutions → reconciled into ONE target (D-057)
    assert set(ada["institution_names"]) == {"Maple University", "Northern Institute"}
    assert set(ada["topic_ids"]) == {"T10001", "T10002", "T10003"}   # topics unioned
    assert ada["works_count"] == 42                     # max across sightings
    assert ada["url"] == "https://maple.example/~ada"


def test_topic_ids_resolved_from_field_when_absent():
    tp = CassetteTransport()
    tp.record(openalex.topics_url("causal ml", EMAIL), 200, json.dumps(
        {"results": [{"id": "https://openalex.org/T10001"}]}))
    oa = openalex.OpenAlexClient(tp, email=EMAIL)
    plan = {"field": "causal ml"}                        # no resolved_topic_ids
    assert ladder.resolve_topic_ids(plan, oa) == ["T10001"]


def test_university_mode_only_restricts_to_named():
    rc, oa = _clients()
    insts = ladder.select_institutions({**PLAN, "university_mode": "only",
                                        "universities": ["maple"]}, rc)
    assert [i["name"] for i in insts] == ["Maple University"]


def test_university_mode_prioritise_orders_named_first():
    rc, oa = _clients()
    insts = ladder.select_institutions({**PLAN, "university_mode": "prioritise",
                                        "universities": ["northern"]}, rc)
    assert [i["name"] for i in insts] == ["Northern Institute", "Maple University"]


def test_all_mode_is_default_and_covers_everything():
    rc, oa = _clients()
    insts = ladder.select_institutions(PLAN, rc)
    assert {i["name"] for i in insts} == {"Maple University", "Northern Institute"}


class _FakeRor:
    def __init__(self, insts):
        self._i = insts

    def institutions_in_country(self, cc, **kw):
        return self._i


def test_university_mode_uses_word_boundary_not_substring():
    # audit (live): "york" must not select "Yorkshire Institute" (substring within a word);
    # a whole-word token still matches.
    rc = _FakeRor([{"name": "Yorkshire Institute", "ror_id": "https://ror.org/1"},
                   {"name": "University of York", "ror_id": "https://ror.org/2"},
                   {"name": "University of Toronto", "ror_id": "https://ror.org/3"}])
    sel = ladder.select_institutions(
        {"country": "X", "university_mode": "only", "universities": ["york"]}, rc)
    names = {i["name"] for i in sel}
    assert "University of York" in names and "Yorkshire Institute" not in names
    sel2 = ladder.select_institutions(
        {"country": "X", "university_mode": "only", "universities": ["toronto"]}, rc)
    assert {i["name"] for i in sel2} == {"University of Toronto"}


def test_build_targets_surfaces_truncation():
    rc, oa = _clients()
    oa.truncated_sources = ["authors@I100"]              # simulate a capped source
    out = ladder.build_targets(PLAN, rc, oa)
    assert out["truncated"] == ["authors@I100"]


def test_university_matching_folds_diacritics():
    # audit: accentless user input must match the accented ROR name in only/prioritise mode
    rc = _FakeRor([{"name": "Université de Montréal", "ror_id": "https://ror.org/0161xgx34"},
                   {"name": "Ludwig-Maximilians-Universität München",
                    "ror_id": "https://ror.org/02wt2p731"}])
    sel = ladder.select_institutions(
        {"country": "CA", "university_mode": "only",
         "universities": ["Universite de Montreal"]}, rc)
    assert [i["name"] for i in sel] == ["Université de Montréal"]
    sel2 = ladder.select_institutions(
        {"country": "DE", "university_mode": "only",
         "universities": ["Ludwig-Maximilians-Universitat Munchen"]}, rc)
    assert [i["name"] for i in sel2] == ["Ludwig-Maximilians-Universität München"]


def test_zero_named_universities_matched_surfaces_a_warning():
    # a typo'd name silently narrowed the scan to nothing — the 0-of-N fact must reach the user
    rc, oa = _clients()
    out = ladder.build_targets({**PLAN, "university_mode": "only",
                                "universities": ["Atlantis University"]}, rc, oa)
    assert out["institutions"] == [] and out["targets"] == []
    assert any("0 of 1 named universities matched" in w for w in out["warnings"])
    # a matching name produces no university-match warning (the topic-filter coverage note
    # still applies — PLAN carries resolved_topic_ids, so the enumeration is filtered)
    out2 = ladder.build_targets({**PLAN, "university_mode": "only",
                                 "universities": ["maple"]}, rc, oa)
    assert not any("0 of" in w for w in out2["warnings"])


class _FakeOa:
    truncated_sources = []

    def __init__(self, authors):
        self._authors = authors

    def institution_by_ror(self, ror_id):
        return "I1"

    def authors_by_institution(self, inst_id, **kw):
        return self._authors


def _split_author(aid, orcid, works, topics, home="https://uni.example/~wwang"):
    return {"openalex_id": f"https://openalex.org/{aid}", "short_id": aid, "name": "Wei Wang",
            "orcid": orcid, "works_count": works, "cited_by_count": works * 5,
            "topic_ids": topics, "institution_ids": ["I1"], "homepage": home}


def test_split_profiles_sharing_an_orcid_merge_into_one_target():
    # D-030/D-057: two OpenAlex author-ids, same ORCID → ONE target reconciled before scoring:
    # topics unioned, works SUMMED (the fragments' works are disjoint), both ids retained.
    oa = _FakeOa([
        _split_author("A111", "https://orcid.org/0000-0002-1825-0097", 12, ["T1", "T2"]),
        _split_author("A222", "https://orcid.org/0000-0002-1825-0097", 9, ["T2", "T3"]),
    ])
    targets = ladder.enumerate_professors([{"ror_id": "https://ror.org/00x", "name": "Uni"}], oa)
    assert len(targets) == 1
    t = targets[0]
    assert t["works_count"] == 21                        # summed, not maxed
    assert set(t["topic_ids"]) == {"T1", "T2", "T3"}     # unioned
    assert set(t["merged_openalex_ids"]) == {"https://openalex.org/A111",
                                             "https://openalex.org/A222"}


def test_same_name_and_homepage_without_orcid_stays_two_targets():
    # D-030: name+homepage is NOT decisive identity evidence — flag, never silently merge
    oa = _FakeOa([
        _split_author("A111", None, 12, ["T1"]),
        _split_author("A222", None, 9, ["T2"]),
    ])
    targets = ladder.enumerate_professors([{"ror_id": "https://ror.org/00x", "name": "Uni"}], oa)
    assert len(targets) == 2
    assert "merged_openalex_ids" not in targets[0]


# ── live fix: server-side topic filter in enumeration + ORCID url fallback ────

def test_build_targets_filters_by_plan_topics_and_surfaces_the_coverage_note():
    # _clients() cassettes are keyed on the FILTERED urls (topic_ids=T10001,T10002) —
    # CassetteTransport raises on any other url, so being served proves the filter was sent.
    rc, oa = _clients()
    out = ladder.build_targets(PLAN, rc, oa)
    assert [t["id"] for t in out["targets"]] == ["A200", "A201", "A202"]
    # OpenAlex topic coverage is imperfect — the note says WHO excludes those authors
    assert any("filtered to 2 topic(s)" in w and "excluded by the API, not by us" in w
               for w in out["warnings"])


def test_build_targets_without_topics_enumerates_unfiltered_and_stays_silent():
    # a plan with no resolved topics keeps the old behavior exactly: no filter, no note
    tp = CassetteTransport()
    tp.record(ror.country_url("CA"), 200, ROR_CA)
    tp.record(openalex.institutions_url("https://ror.org/00abc11", EMAIL), 200, _oa_inst("I100"))
    tp.record(openalex.institutions_url("https://ror.org/00abc22", EMAIL), 200, _oa_inst("I200"))
    tp.record(openalex.authors_url("I100", EMAIL), 200, AUTHORS_I100)   # UNFILTERED urls
    tp.record(openalex.authors_url("I200", EMAIL), 200, AUTHORS_I200)
    rc = ror.RorClient(tp, email=EMAIL)
    oa = openalex.OpenAlexClient(tp, email=EMAIL)
    plan = {"intent_kind": "pre_phd", "country": "CA", "university_mode": "all"}
    out = ladder.build_targets(plan, rc, oa)
    assert len(out["targets"]) == 3                       # served → the unfiltered url was used
    assert not any("filtered to" in w for w in out["warnings"])
    assert out["truncated"] == []                         # truncation markers unchanged


def test_orcid_is_the_deep_dive_url_fallback_when_no_homepage():
    # live evidence: real OpenAlex author objects carry no homepage key at all, but many
    # carry an ORCID (a public, fetchable page) — without the fallback every target was
    # url=None and 100% of the run routed to the human rung ("no page url").
    oa = _FakeOa([_split_author("A111", "https://orcid.org/0000-0002-1825-0097", 12, ["T1"],
                                home=None)])
    t = ladder.enumerate_professors([{"ror_id": "https://ror.org/00x", "name": "Uni"}], oa)[0]
    assert t["url"] == "https://orcid.org/0000-0002-1825-0097"
    assert t["url_kind"] == "orcid"


def test_homepage_wins_over_orcid_and_neither_stays_honestly_url_less():
    oa = _FakeOa([
        _split_author("A111", "https://orcid.org/0000-0002-1825-0097", 12, ["T1"]),
        _split_author("A222", None, 9, ["T2"], home=None),
    ])
    targets = ladder.enumerate_professors([{"ror_id": "https://ror.org/00x", "name": "Uni"}], oa)
    assert targets[0]["url"] == "https://uni.example/~wwang"
    assert targets[0]["url_kind"] == "homepage"           # homepage wins (cassette compat)
    assert targets[1]["url"] is None and targets[1]["url_kind"] is None  # honest blocked path


def test_author_url_reads_orcid_from_the_raw_ids_shape():
    # _map_author output carries "orcid" directly; a raw API-shaped dict carries ids.orcid —
    # both resolve, and the API's full https://orcid.org/... url is used as-is.
    assert ladder._author_url({"ids": {"orcid": "https://orcid.org/0000-0002-1825-0097"}}) == \
        ("https://orcid.org/0000-0002-1825-0097", "orcid")
    assert ladder._author_url({}) == (None, None)
