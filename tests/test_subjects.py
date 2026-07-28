"""Phase B3 (D-066) — subject_map groups OpenAlex topic hits domain -> field -> subfield,
null-safely and honestly (cap + mid-pagination failure are PARTIAL, never a false complete),
plus the `map-field` CLI (writes the map JSON, requires a contact email). No live network —
cassettes via the Transport seam; fixtures are synthetic (D-035 safe)."""

import json

from supervisorly import cli
from supervisorly.discover import openalex, subjects
from supervisorly.fetch import transport as transport_mod
from supervisorly.fetch.transport import CassetteTransport

EMAIL = "me@uni.edu"


def _topic(n, name, works, domain=None, field=None, subfield=None):
    t = {"id": f"https://openalex.org/T{n}", "display_name": name, "works_count": works}
    if domain:
        t["domain"] = {"id": f"https://openalex.org/domains/{domain}", "display_name": domain}
    if field:
        t["field"] = {"id": f"https://openalex.org/fields/{field}", "display_name": field}
    if subfield:
        t["subfield"] = {"id": f"https://openalex.org/subfields/{subfield}",
                         "display_name": subfield}
    return t


def _page(topics, count=None):
    return json.dumps({"meta": {"count": count if count is not None else len(topics)},
                       "results": topics})


def test_subject_map_groups_by_domain_field_subfield():
    tp = CassetteTransport()
    tp.record(openalex.topics_url("causal ml", EMAIL), 200, _page([
        _topic(1, "Causal inference", 900, "Physical Sciences", "Mathematics", "Statistics"),
        _topic(2, "Machine learning", 5000, "Physical Sciences", "Computer Science", "AI"),
        _topic(3, "Econometrics", 700, "Social Sciences", "Economics", "Econometrics"),
        _topic(4, "Deep learning", 1200, "Physical Sciences", "Computer Science", "AI"),
    ]))
    smap = subjects.subject_map("causal ml", tp, email=EMAIL)
    assert smap["query"] == "causal ml" and smap["truncated"] is False
    assert smap["truncated_sources"] == []
    # 3 groups (CS/AI holds two topics); ranked by their top topic's works_count
    assert [(g["domain"], g["field"], g["subfield"]) for g in smap["groups"]] == [
        ("Physical Sciences", "Computer Science", "AI"),
        ("Physical Sciences", "Mathematics", "Statistics"),
        ("Social Sciences", "Economics", "Econometrics"),
    ]
    ai = smap["groups"][0]
    # topics sorted by works_count desc; short topic ids (the plan's resolved_topic_ids shape)
    assert [(t["topic_id"], t["works_count"]) for t in ai["topics"]] == [("T2", 5000),
                                                                         ("T4", 1200)]
    assert ai["topics"][0]["name"] == "Machine learning"


def test_subject_map_null_hierarchy_lands_in_ungrouped_bucket():
    tp = CassetteTransport()
    tp.record(openalex.topics_url("x", EMAIL), 200, _page([
        _topic(1, "No hierarchy at all", 10),
        {"id": "https://openalex.org/T2", "display_name": "Null levels", "works_count": 20,
         "domain": None, "field": None, "subfield": None},
    ]))
    smap = subjects.subject_map("x", tp, email=EMAIL)
    assert len(smap["groups"]) == 1                       # one honest bucket, never a crash
    g = smap["groups"][0]
    assert (g["domain"], g["field"], g["subfield"]) == ("ungrouped", "ungrouped", "ungrouped")
    assert [t["topic_id"] for t in g["topics"]] == ["T2", "T1"]


def test_subject_map_cap_marks_truncation():
    # 3 results exist but max_results=2 cuts one off — PARTIAL, never a silent cut (D-037)
    tp = CassetteTransport()
    tp.record(openalex.topics_url("x", EMAIL), 200, _page([
        _topic(1, "A", 30), _topic(2, "B", 20), _topic(3, "C", 10)]))
    smap = subjects.subject_map("x", tp, email=EMAIL, max_results=2)
    total = sum(len(g["topics"]) for g in smap["groups"])
    assert total == 2
    assert smap["truncated"] is True and smap["truncated_sources"] == ["topics@x"]


def test_subject_map_full_last_page_marks_truncation():
    # the page cap was hit while a FULL page remained — more results existed (D-037)
    tp = CassetteTransport()
    tp.record(openalex.topics_url("x", EMAIL), 200,
              _page([_topic(i, f"T{i}", i) for i in range(openalex.PER_PAGE)]))
    smap = subjects.subject_map("x", tp, email=EMAIL)   # max_results == one full page
    assert smap["truncated"] is True and smap["truncated_sources"] == ["topics@x"]


def test_subject_map_mid_pagination_failure_is_partial():
    # a full page then a transient 500: the partial groups are kept AND marked (D-037)
    tp = CassetteTransport()
    tp.record(openalex.topics_url("x", EMAIL, page=1), 200,
              _page([_topic(i, f"T{i}", i) for i in range(openalex.PER_PAGE)]))
    tp.record(openalex.topics_url("x", EMAIL, page=2), 500, "boom")
    smap = subjects.subject_map("x", tp, email=EMAIL, max_results=50)
    total = sum(len(g["topics"]) for g in smap["groups"])
    assert total == openalex.PER_PAGE
    assert smap["truncated"] is True and smap["truncated_sources"] == ["topics@x"]


def test_subject_map_first_page_failure_is_honest_empty_partial():
    tp = CassetteTransport()
    tp.record(openalex.topics_url("x", EMAIL), 500, "boom")
    smap = subjects.subject_map("x", tp, email=EMAIL)
    assert smap["groups"] == []                           # honest empty, not a crash
    assert smap["truncated"] is True and smap["truncated_sources"] == ["topics@x"]


def test_subject_map_empty_query_and_no_results_are_honest_empties():
    # empty query: no transport call at all (an empty cassette would raise on any get)
    smap = subjects.subject_map("  ", CassetteTransport(), email=EMAIL)
    assert smap["groups"] == [] and smap["truncated"] is False
    # a genuine 200 with no results: absence, NOT truncation
    tp = CassetteTransport()
    tp.record(openalex.topics_url("zzz", EMAIL), 200, _page([]))
    smap = subjects.subject_map("zzz", tp, email=EMAIL)
    assert smap["groups"] == [] and smap["truncated"] is False
    assert smap["truncated_sources"] == []


# ── map-field CLI ─────────────────────────────────────────────────────────────

def test_map_field_writes_json_and_ascii_summary(tmp_path, monkeypatch, capsys):
    tp = CassetteTransport()
    tp.record(openalex.topics_url("causal ml", EMAIL), 200, _page([
        _topic(1, "Causal inference", 900, "Physical Sciences", "Mathematics", "Statistics"),
        _topic(2, "Machine learning", 5000, "Physical Sciences", "Computer Science", "AI"),
    ]))
    monkeypatch.setattr(transport_mod, "httpx_transport", lambda **kw: tp)
    out = tmp_path / "map.json"
    rc = cli.main(["map-field", "--field", "causal ml", "--email", EMAIL, "--out", str(out)])
    assert rc == 0
    printed = capsys.readouterr().out
    assert "mapped 2 topics in 2 groups" in printed and printed.isascii()
    smap = json.loads(out.read_text(encoding="utf-8"))
    assert smap["query"] == "causal ml" and len(smap["groups"]) == 2


def test_map_field_requires_a_contact_email(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("SUPERVISORLY_CONTACT_EMAIL", raising=False)
    rc = cli.main(["map-field", "--field", "causal ml", "--out", str(tmp_path / "m.json")])
    assert rc == 2
    assert "SUPERVISORLY_CONTACT_EMAIL" in capsys.readouterr().out
    assert not (tmp_path / "m.json").exists()


# ── query relaxation (genuine-empty fallback) ─────────────────────────────────

class _Counting:
    """Wraps a CassetteTransport, recording the requested URLs (dedupe assertions)."""

    def __init__(self, tp):
        self.tp, self.urls = tp, []

    def get(self, url):
        self.urls.append(url)
        return self.tp.get(url)


def test_subject_map_genuine_empty_relaxes_to_per_word_union():
    # live-verified shape: the full phrase matches no topic display name, but single
    # words hit the right neighborhood (mechanistic interpretability -> XAI & co.)
    tp = CassetteTransport()
    tp.record(openalex.topics_url("mechanistic interpretability", EMAIL), 200, _page([]))
    tp.record(openalex.topics_url("mechanistic", EMAIL), 200, _page([
        _topic(9, "Mechanistic modeling", 100, "Physical Sciences", "Physics", "Mechanics"),
        _topic(5, "Mechanistic interpretability of Transformers", 50,
               "Physical Sciences", "Computer Science", "AI"),
        # word-boundary: "Mechanisms" does NOT contain the word "mechanistic" -> overlap 0
        _topic(7, "Mechanisms of action", 9999, "Health Sciences", "Medicine", "Pharma"),
    ]))
    tp.record(openalex.topics_url("interpretability", EMAIL), 200, _page([
        _topic(1, "Explainable Artificial Intelligence (XAI)", 800,
               "Physical Sciences", "Computer Science", "AI"),
        _topic(2, "Interpretability methods", 300,
               "Physical Sciences", "Computer Science", "AI"),
        _topic(5, "Mechanistic interpretability of Transformers", 50,  # dup id -> unioned
               "Physical Sciences", "Computer Science", "AI"),
    ]))
    smap = subjects.subject_map("mechanistic interpretability", tp, email=EMAIL)
    assert smap["relaxed_from"] == "mechanistic interpretability"
    assert smap["truncated"] is False and smap["truncated_sources"] == []
    flat = [t for g in smap["groups"] for t in g["topics"]]
    # deduped by topic id (T5 once); global rank is word overlap desc then works_count desc
    # (T5: 2 words; T2/T9: 1 word, 300 > 100; T7/T1: 0 words, 9999 > 800), and groups keep
    # their topics in that rank order — so the AI group lists T5, T2, T1
    assert [(t["topic_id"], t["works_count"]) for t in flat] == [
        ("T5", 50), ("T2", 300), ("T1", 800), ("T9", 100), ("T7", 9999)]
    # grouping/capping still applied: AI holds the top-ranked topic -> the first group
    assert smap["groups"][0]["subfield"] == "AI"
    assert [t["topic_id"] for t in smap["groups"][0]["topics"]] == ["T5", "T2", "T1"]


def test_subject_map_relaxation_ranks_keyword_matches_above_works_count():
    # live-verified shape (2026-07-25): XAI's display name contains neither query word,
    # but its OpenAlex keywords carry "Machine Learning Interpretability" — a name-only
    # overlap would rank the off-target mega-topic (Hermeneutics, 1M works) above it.
    xai = _topic(1, "Explainable Artificial Intelligence (XAI)", 800,
                 "Physical Sciences", "Computer Science", "AI")
    xai["keywords"] = ["Machine Learning Interpretability", "Model Interpretability"]
    tp = CassetteTransport()
    tp.record(openalex.topics_url("mechanistic interpretability", EMAIL), 200, _page([]))
    tp.record(openalex.topics_url("mechanistic", EMAIL), 200, _page([]))
    tp.record(openalex.topics_url("interpretability", EMAIL), 200, _page([
        _topic(2, "Hermeneutics and Narrative Identity", 1019564,
               "Arts and Humanities", "Philosophy", "Philosophy"),
        xai,
    ]))
    smap = subjects.subject_map("mechanistic interpretability", tp, email=EMAIL)
    flat = [t for g in smap["groups"] for t in g["topics"]]
    assert [t["topic_id"] for t in flat] == ["T1", "T2"]   # keyword overlap beats works_count


def test_subject_map_relaxation_ranks_distinctive_words_above_generic_ones():
    # live-verified motivation (2026-07-25): "causal machine learning" relaxed per-word and
    # "Machine Learning in Healthcare" (2 generic matches) outranked the causal-inference
    # topics (1 distinctive match). idf-weighting fixes the vote: causal (27 hits) is
    # ~1000x more distinctive than machine (2_000) or learning (50_000).
    tp = CassetteTransport()
    tp.record(openalex.topics_url("causal machine learning", EMAIL), 200, _page([], count=0))
    tp.record(openalex.topics_url("causal", EMAIL), 200, _page([
        _topic(1, "Advanced Causal Inference Techniques", 300,
               "Physical Sciences", "Mathematics", "Statistics"),
    ], count=27))
    tp.record(openalex.topics_url("machine", EMAIL), 200, _page([
        _topic(2, "Machine Learning in Healthcare", 900000,
               "Physical Sciences", "Computer Science", "AI"),
    ], count=2000))
    tp.record(openalex.topics_url("learning", EMAIL), 200, _page([
        _topic(2, "Machine Learning in Healthcare", 900000,   # same id -> unioned
               "Physical Sciences", "Computer Science", "AI"),
        _topic(3, "Online and Blended Learning", 700000,
               "Social Sciences", "Education", "Education"),
    ], count=50000))
    smap = subjects.subject_map("causal machine learning", tp, email=EMAIL)
    flat = [t for g in smap["groups"] for t in g["topics"]]
    # T1 matches only "causal" (score 1/28) but outranks T2 (machine+learning ≈ 0.0005)
    # and T3 (learning ≈ 0.00002) despite their far bigger works_count
    assert [t["topic_id"] for t in flat] == ["T1", "T2", "T3"]


def test_subject_map_relaxation_dedupes_words_case_insensitively():
    tp = CassetteTransport()
    tp.record(openalex.topics_url("Causal CAUSAL models", EMAIL), 200, _page([]))
    tp.record(openalex.topics_url("Causal", EMAIL), 200,
              _page([_topic(1, "Causal inference", 900)]))
    tp.record(openalex.topics_url("models", EMAIL), 200,
              _page([_topic(2, "Statistical models", 700)]))
    counting = _Counting(tp)
    smap = subjects.subject_map("Causal CAUSAL models", counting, email=EMAIL)
    assert smap["relaxed_from"] == "Causal CAUSAL models"
    assert [t["topic_id"] for g in smap["groups"] for t in g["topics"]] == ["T1", "T2"]
    # "Causal"/"CAUSAL" collapse to ONE per-word search (first casing kept)
    assert counting.urls == [
        openalex.topics_url("Causal CAUSAL models", EMAIL),
        openalex.topics_url("Causal", EMAIL),
        openalex.topics_url("models", EMAIL),
    ]


def test_subject_map_relaxation_finding_nothing_is_honest_empty():
    tp = CassetteTransport()
    tp.record(openalex.topics_url("zztop nothingness", EMAIL), 200, _page([]))
    tp.record(openalex.topics_url("zztop", EMAIL), 200, _page([]))
    tp.record(openalex.topics_url("nothingness", EMAIL), 200, _page([]))
    smap = subjects.subject_map("zztop nothingness", tp, email=EMAIL)
    assert smap["groups"] == [] and smap["truncated"] is False
    assert smap["truncated_sources"] == []
    assert "relaxed_from" not in smap                    # same honest empty as a direct miss


def test_subject_map_short_words_are_not_searched():
    # every word < 4 chars -> no per-word searches at all -> plain honest empty
    tp = CassetteTransport()
    tp.record(openalex.topics_url("AI for X", EMAIL), 200, _page([]))
    counting = _Counting(tp)
    smap = subjects.subject_map("AI for X", counting, email=EMAIL)
    assert smap["groups"] == [] and smap["truncated"] is False
    assert "relaxed_from" not in smap
    assert counting.urls == [openalex.topics_url("AI for X", EMAIL)]


def test_subject_map_failure_on_original_query_never_relaxes():
    tp = CassetteTransport()
    tp.record(openalex.topics_url("quantum", EMAIL), 500, "boom")
    smap = subjects.subject_map("quantum", tp, email=EMAIL)
    assert smap["groups"] == []
    assert smap["truncated"] is True
    assert smap["truncated_sources"] == ["topics@quantum"]  # no topics@<word> markers
    assert "relaxed_from" not in smap


def test_subject_map_failure_during_relaxation_is_partial_naming_the_word():
    tp = CassetteTransport()
    tp.record(openalex.topics_url("mechanistic interpretability", EMAIL), 200, _page([]))
    tp.record(openalex.topics_url("mechanistic", EMAIL), 200, _page([
        _topic(9, "Mechanistic modeling", 100, "Physical Sciences", "Physics", "Mechanics"),
    ]))
    tp.record(openalex.topics_url("interpretability", EMAIL), 500, "boom")
    smap = subjects.subject_map("mechanistic interpretability", tp, email=EMAIL)
    assert smap["relaxed_from"] == "mechanistic interpretability"
    assert smap["truncated"] is True
    # the marker names the FAILING word-query; the kept partial groups are still returned
    assert smap["truncated_sources"] == ["topics@interpretability"]
    flat = [t for g in smap["groups"] for t in g["topics"]]
    assert [t["topic_id"] for t in flat] == ["T9"]


def test_map_field_prints_relaxation_note(tmp_path, monkeypatch, capsys):
    tp = CassetteTransport()
    tp.record(openalex.topics_url("mechanistic interpretability", EMAIL), 200, _page([]))
    tp.record(openalex.topics_url("mechanistic", EMAIL), 200,
              _page([_topic(9, "Mechanistic modeling", 100)]))
    tp.record(openalex.topics_url("interpretability", EMAIL), 200, _page([
        _topic(1, "Explainable Artificial Intelligence (XAI)", 800),
        _topic(2, "Interpretability methods", 300),
    ]))
    monkeypatch.setattr(transport_mod, "httpx_transport", lambda **kw: tp)
    out = tmp_path / "map.json"
    rc = cli.main(["map-field", "--field", "mechanistic interpretability",
                   "--email", EMAIL, "--out", str(out)])
    assert rc == 0
    printed = capsys.readouterr().out
    assert "mapped 3 topics in 1 groups" in printed and printed.isascii()
    assert ("note: no exact topics for 'mechanistic interpretability'; broadened to "
            "per-word search over the OpenAlex topic index") in printed
    smap = json.loads(out.read_text(encoding="utf-8"))
    assert smap["relaxed_from"] == "mechanistic interpretability"


def test_map_field_no_note_on_honest_empty(tmp_path, monkeypatch, capsys):
    tp = CassetteTransport()
    tp.record(openalex.topics_url("AI for X", EMAIL), 200, _page([]))
    monkeypatch.setattr(transport_mod, "httpx_transport", lambda **kw: tp)
    out = tmp_path / "map.json"
    rc = cli.main(["map-field", "--field", "AI for X", "--email", EMAIL, "--out", str(out)])
    assert rc == 0
    printed = capsys.readouterr().out
    assert "mapped 0 topics in 0 groups" in printed
    assert "note:" not in printed
    assert "relaxed_from" not in json.loads(out.read_text(encoding="utf-8"))


# ── subject_map_multi (D-068 multi-variant merge) ─────────────────────────────

def test_subject_map_multi_merges_variants_best_rank_and_found_by():
    tp = CassetteTransport()
    tp.record(openalex.topics_url("causal ml", EMAIL), 200, _page([
        _topic(1, "Causal inference", 900, "Physical Sciences", "Mathematics", "Statistics"),
        _topic(2, "Machine learning", 5000, "Physical Sciences", "Computer Science", "AI"),
    ]))
    tp.record(openalex.topics_url("causal inference", EMAIL), 200, _page([
        _topic(2, "Machine learning", 5000, "Physical Sciences", "Computer Science", "AI"),
        _topic(3, "Econometrics", 700, "Social Sciences", "Economics", "Econometrics"),
    ]))
    smap = subjects.subject_map_multi(["causal ml", "causal inference"], tp, email=EMAIL)
    assert smap["queries"] == ["causal ml", "causal inference"]
    assert smap["truncated"] is False and smap["truncated_sources"] == []
    flat = [t for g in smap["groups"] for t in g["topics"]]
    # each variant is works_count-sorted first (T2 rank 0 in both); T2 surfaced in BOTH
    # variants, ties on best rank keep first-seen order
    assert [t["topic_id"] for t in flat] == ["T2", "T1", "T3"]
    assert flat[0]["found_by"] == ["causal ml", "causal inference"]
    assert flat[1]["found_by"] == ["causal ml"] and flat[2]["found_by"] == ["causal inference"]
    # the SAME domain/field/subfield clustering as a single-query map — never merged across
    assert [(g["domain"], g["field"], g["subfield"]) for g in smap["groups"]] == [
        ("Physical Sciences", "Computer Science", "AI"),
        ("Physical Sciences", "Mathematics", "Statistics"),
        ("Social Sciences", "Economics", "Econometrics"),
    ]


def test_subject_map_multi_unions_truncation_and_keeps_partial_topics():
    tp = CassetteTransport()
    tp.record(openalex.topics_url("x", EMAIL), 200, _page([_topic(1, "A", 30)]))
    tp.record(openalex.topics_url("y", EMAIL), 500, "boom")
    smap = subjects.subject_map_multi(["x", "y"], tp, email=EMAIL)
    assert [t["topic_id"] for g in smap["groups"] for t in g["topics"]] == ["T1"]
    assert smap["truncated"] is True and smap["truncated_sources"] == ["topics@y"]


def test_subject_map_multi_honest_empty_variant_contributes_nothing():
    tp = CassetteTransport()
    tp.record(openalex.topics_url("causal", EMAIL), 200,
              _page([_topic(1, "Causal inference", 900)]))
    tp.record(openalex.topics_url("zzz", EMAIL), 200, _page([]))   # 200, zero results
    smap = subjects.subject_map_multi(["causal", "zzz"], tp, email=EMAIL)
    assert smap["truncated"] is False and smap["truncated_sources"] == []
    flat = [t for g in smap["groups"] for t in g["topics"]]
    assert [(t["topic_id"], t["found_by"]) for t in flat] == [("T1", ["causal"])]


def test_subject_map_multi_dedupes_case_insensitively_and_caps_input_at_MAX_QUERIES():
    tp = CassetteTransport()
    for i in range(1, 9):
        tp.record(openalex.topics_url(f"q{i}", EMAIL), 200, _page([]))
    counting = _Counting(tp)
    queries = ["q1", "Q1"] + [f"q{i}" for i in range(2, 10)]       # 9 unique after dedupe
    smap = subjects.subject_map_multi(queries, counting, email=EMAIL)
    assert smap["queries"] == [f"q{i}" for i in range(1, 10)]      # first casing kept
    # the cap rose 8 -> 50 with the step-2 slider: one request carries every phrasing the
    # student asked for, and capping here would silently drop what they chose.
    assert subjects.MAX_QUERIES == 50
    assert len(counting.urls) == 9      # one upstream call per unique phrasing
