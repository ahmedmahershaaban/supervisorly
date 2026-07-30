"""ROR enumeration scale, the education filter, and the exported match rating.

Three defects sat together here. The page count was hardcoded at 5 (100 rows), so a caller
asking for more silently got ROR's arbitrary first hundred. The education filter that
`ror.py` documented the caller as applying did not exist in any caller, so scans spent that
budget on hospitals and companies. And `score/scorer.py` — a working fit scorer — was called
by nothing, so 493 professors exported in discovery order with no signal about which to read.
"""
import pytest

from supervisorly.discover import ladder, ror as ror_mod


class _FakeRor:
    """Answers pages of 20, remembering how many were asked for."""

    def __init__(self, total=500, types=("education",)):
        self.total, self.types, self.pages = total, list(types), 0
        self.truncated_sources = []

    def institutions_in_country(self, country, *, want=None, max_pages=None):
        return ror_mod.RorClient.institutions_in_country(self, country,
                                                         want=want, max_pages=max_pages)

    def _page(self, country, page):
        self.pages = max(self.pages, page)
        start = (page - 1) * ror_mod.PAGE_SIZE
        n = max(0, min(ror_mod.PAGE_SIZE, self.total - start))
        return {"items": [{"id": f"https://ror.org/{start+i}",
                           "names": [{"types": ["ror_display"], "value": f"Inst {start+i}"}],
                           "types": self.types} for i in range(n)],
                "number_of_results": self.total}


# ── the page cap ─────────────────────────────────────────────────────────────
def test_the_default_reach_is_no_longer_a_hardcoded_hundred():
    r = _FakeRor(total=500)
    got = r.institutions_in_country("CA")
    assert len(got) == ror_mod.DEFAULT_WANT == 200
    assert r.pages == 10


def test_asking_for_three_hundred_fetches_enough_pages_for_three_hundred():
    """The ask drives the FETCH. Asking for 300 and receiving 100 was the bug."""
    r = _FakeRor(total=500)
    got = r.institutions_in_country("CA", want=300)
    assert len(got) == 300
    assert r.pages == 15                       # ceil(300/20)


def test_a_country_smaller_than_the_ask_is_not_reported_as_truncated():
    r = _FakeRor(total=37)
    got = r.institutions_in_country("CA", want=300)
    assert len(got) == 37
    assert r.truncated_sources == []           # we saw everything; say nothing


def test_stopping_early_is_still_disclosed():
    r = _FakeRor(total=5000)
    r.institutions_in_country("CA", want=40)
    assert "institutions@CA" in r.truncated_sources


# ── the education filter ─────────────────────────────────────────────────────
def test_only_education_typed_organisations_are_scanned():
    """A hospital cannot supply a PhD supervisor; enumerating its authors wastes the budget."""
    insts = [{"name": "Uni", "types": ["education"]},
             {"name": "Hospital", "types": ["healthcare"]},
             {"name": "Corp", "types": ["company"]},
             {"name": "College", "types": ["education", "nonprofit"]}]
    kept = [i for i in insts if ror_mod.is_education(i)]
    assert [i["name"] for i in kept] == ["Uni", "College"]


def test_the_filter_says_how_many_it_dropped_and_names_the_pool_it_left():
    """The census is the point: a student who can't see that 54 hospitals exist can't decide
    whether to scan them."""
    warnings = []
    ladder.select_institutions(
        {"country": "CA"},
        type("R", (), {"institutions_in_country": lambda s, c, **k: [
            {"name": "Uni", "types": ["education"]},
            {"name": "Hospital", "types": ["healthcare"]}]})(),
        warnings=warnings)
    assert any("kept 1 of 2 ROR institutions for CA" in w for w in warnings)
    assert any("Not scanned: healthcare 1" in w for w in warnings)


def test_a_country_with_no_typed_records_fails_open_rather_than_reporting_none():
    """"This country has no universities" is a worse lie than scanning a few hospitals."""
    warnings = []
    got = ladder.select_institutions(
        {"country": "XX"},
        type("R", (), {"institutions_in_country": lambda s, c, **k: [
            {"name": "A", "types": []}, {"name": "B", "types": ["other"]}]})(),
        warnings=warnings)
    assert len(got) == 2
    assert any("scanning all types rather than reporting none" in w for w in warnings)


def test_all_institution_types_opts_back_in():
    got = ladder.select_institutions(
        {"country": "CA", "all_institution_types": True},
        type("R", (), {"institutions_in_country": lambda s, c, **k: [
            {"name": "Uni", "types": ["education"]},
            {"name": "Hospital", "types": ["healthcare"]}]})())
    assert len(got) == 2


# ── the match rating ─────────────────────────────────────────────────────────
def _rate(topics, plan_topics, works=0, claims=()):
    from supervisorly import pipeline
    return pipeline._match_rating({"topic_ids": topics, "works_count": works},
                                  plan_topics, list(claims))


def test_every_professor_gets_a_rating_not_only_the_deep_dived_ones():
    """Rating uses registry facts discovery already fetched, so the shortlist is a budget,
    not a verdict — an unchecked professor still has a place in the order."""
    m = _rate(["T1", "T2"], ["T1", "T2"], works=40)
    assert m["percent"] > 0
    assert m["components"]["topic_match"] == 100


def test_topic_overlap_drives_the_number():
    full = _rate(["T1", "T2"], ["T1", "T2"])
    half = _rate(["T1"], ["T1", "T2"])
    none = _rate(["T9"], ["T1", "T2"])
    assert full["percent"] > half["percent"] > none["percent"]


def test_a_recruiting_claim_raises_the_rating():
    without = _rate(["T1"], ["T1"])
    with_ = _rate(["T1"], ["T1"], claims=[{"field": "recruiting_signal", "state": "value"}])
    assert with_["percent"] > without["percent"]


def test_the_components_ship_so_the_number_can_be_argued_with():
    m = _rate(["T1"], ["T1", "T2"])
    assert set(m["components"]) == {"topic_match", "recruiting", "funding", "activity"}
    assert m["components"]["topic_match"] == 50


def test_professors_are_exported_best_match_first(tmp_path):
    import pathlib
    from supervisorly.demo import demo_fixture
    from supervisorly.pipeline import run_offline
    tp, targets, plan = demo_fixture()
    r = run_offline(plan, targets, tp, tmp_path / "s")
    pcts = [p["match"]["percent"] for p in r["export"]["professors"]]
    assert pcts == sorted(pcts, reverse=True), "the export must lead with the best match"


def test_the_rating_is_not_inside_the_quote_gated_fields_block(tmp_path):
    """D-010: `fields` is evidence with quotes. A computed number is not evidence."""
    from supervisorly.demo import demo_fixture
    from supervisorly.pipeline import run_offline
    tp, targets, plan = demo_fixture()
    r = run_offline(plan, targets, tp, tmp_path / "s")
    for p in r["export"]["professors"]:
        assert "match" not in p["fields"]
        assert "match" in p
