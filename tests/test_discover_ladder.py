"""Phase L1 — the discovery ladder turns a SearchPlan into de-duplicated professor targets from
ROR + OpenAlex (cassettes, no network). Synthetic data (invented names/example domains, D-035)."""

import json

from supervisorly.discover import ladder, openalex, ror
from supervisorly.fetch.transport import CassetteTransport

EMAIL = "me@uni.edu"

ROR_CA = json.dumps({"items": [
    {"id": "https://ror.org/00abc11", "name": "Maple University",
     "country": {"country_code": "CA"}, "links": ["https://maple.example/"], "types": ["Education"]},
    {"id": "https://ror.org/00abc22", "name": "Northern Institute",
     "country": {"country_code": "CA"}, "links": ["https://northern.example/"], "types": ["Education"]},
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
    tp.record(openalex.authors_url("I100", EMAIL), 200, AUTHORS_I100)
    tp.record(openalex.authors_url("I200", EMAIL), 200, AUTHORS_I200)
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
