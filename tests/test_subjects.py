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


def _page(topics):
    return json.dumps({"results": topics})


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
