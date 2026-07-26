"""Phase L0 — ROR + OpenAlex clients round-trip recorded cassettes into typed results, with
no live network. Fixtures are synthetic (invented names, example domains) — D-035 safe."""

import json

from supervisorly.discover import openalex, ror
from supervisorly.fetch.transport import CassetteTransport

EMAIL = "me@uni.edu"

# ── synthetic ROR response (v2 shape — v1 was retired Dec 2025; the API now serves
#    names[]/links[{type,value}]/locations[].geonames_details) ────────────────────────────
ROR_CA = json.dumps({
    "number_of_results": 2,
    "items": [
        {"id": "https://ror.org/00abc11",
         "names": [{"value": "Maple University", "types": ["ror_display", "label"], "lang": "en"}],
         "locations": [{"geonames_id": 101,
                        "geonames_details": {"country_code": "CA", "country_name": "Canada"}}],
         "links": [{"type": "website", "value": "https://maple.example/"}],
         "types": ["education"]},
        {"id": "https://ror.org/00abc22",
         "names": [{"value": "Northern Institute", "types": ["ror_display", "label"], "lang": "en"}],
         "locations": [{"geonames_id": 102,
                        "geonames_details": {"country_code": "CA", "country_name": "Canada"}}],
         "links": [], "types": ["facility"]},
    ],
})

# ── synthetic OpenAlex responses ──────────────────────────────────────────────
OA_TOPICS = json.dumps({"results": [
    {"id": "https://openalex.org/T10001", "display_name": "Causal inference"},
    {"id": "https://openalex.org/T10002", "display_name": "Machine learning"},
]})
OA_AUTHORS = json.dumps({"results": [
    {"id": "https://openalex.org/A200", "display_name": "Dr. Ada Maple",
     "works_count": 42, "cited_by_count": 1200,
     "ids": {"orcid": "https://orcid.org/0000-0002-1825-0097"},
     "topics": [{"id": "https://openalex.org/T10001"}, {"id": "https://openalex.org/T10002"}],
     "last_known_institutions": [{"id": "https://openalex.org/I100"}],
     "homepage_url": "https://maple.example/~ada"},
]})
OA_WORKS = json.dumps({"results": [
    {"id": "https://openalex.org/W1", "title": "On causal ML", "publication_year": 2025,
     "topics": [{"id": "https://openalex.org/T10001"}]},
]})


def test_ror_client_maps_country_institutions():
    tp = CassetteTransport()
    tp.record(ror.country_url("CA"), 200, ROR_CA)
    insts = ror.RorClient(tp, email=EMAIL).institutions_in_country("CA")
    assert len(insts) == 2
    m = insts[0]
    assert m["ror_id"] == "https://ror.org/00abc11" and m["name"] == "Maple University"
    assert m["country_code"] == "CA" and m["homepage"] == "https://maple.example/"
    assert insts[1]["homepage"] is None                 # no links → honest None, not dropped


def test_ror_v2_mapping_picks_display_name_website_link_and_country():
    # v2 regression (audit): name = names[] entry typed "ror_display" (fallback: first entry),
    # homepage = the links[] entry typed "website", country = locations[].geonames_details.
    item = {"id": "https://ror.org/00x",
            "names": [{"value": "MU", "types": ["acronym"], "lang": None},
                      {"value": "Maple Varsity", "types": ["ror_display", "label"], "lang": "en"}],
            "links": [{"type": "wikipedia", "value": "https://en.wikipedia.org/wiki/mu"},
                      {"type": "website", "value": "https://maple.example/"}],
            "locations": [{"geonames_id": 1, "geonames_details": {"country_code": "CA"}}],
            "types": ["education"]}
    m = ror._map_institution(item)
    assert m["name"] == "Maple Varsity"                 # ror_display, not the acronym
    assert m["homepage"] == "https://maple.example/"    # website link, not wikipedia
    assert m["country_code"] == "CA"
    # fallbacks, null-safe at every step: no ror_display → first names[] entry;
    # no website link / no locations → honest None
    m2 = ror._map_institution({"id": "https://ror.org/00y",
                               "names": [{"value": "Only Name", "types": ["label"]}],
                               "links": None, "locations": None, "types": None})
    assert m2["name"] == "Only Name"
    assert m2["homepage"] is None and m2["country_code"] is None and m2["types"] == []


def test_ror_client_returns_empty_on_error_not_crash():
    tp = CassetteTransport()
    tp.record(ror.country_url("ZZ"), 500, "boom")
    assert ror.RorClient(tp).institutions_in_country("ZZ") == []
    # a URL with no cassette (transport error) is also handled, not raised
    assert ror.RorClient(CassetteTransport()).institutions_in_country("ZZ") == []


def test_openalex_institution_resolution_failure_records_truncation():
    # audit: a 500 on the ROR→OpenAlex resolution is a FAILURE, not absence — the university's
    # professors are unknown, so a PARTIAL marker naming the ROR id is recorded (D-037).
    tp = CassetteTransport()
    tp.record(openalex.institutions_url("https://ror.org/00abc11", EMAIL), 500, "{}")
    oa = openalex.OpenAlexClient(tp, email=EMAIL)
    assert oa.institution_by_ror("https://ror.org/00abc11") is None
    assert oa.truncated_sources == ["inst@00abc11"]


def test_openalex_institution_genuinely_absent_stays_silent():
    # 200 with empty results = OpenAlex honestly has no such institution — no marker
    tp = CassetteTransport()
    tp.record(openalex.institutions_url("https://ror.org/00abc11", EMAIL), 200,
              json.dumps({"results": []}))
    oa = openalex.OpenAlexClient(tp, email=EMAIL)
    assert oa.institution_by_ror("https://ror.org/00abc11") is None
    assert oa.truncated_sources == []


def test_openalex_topic_ids_resolve():
    tp = CassetteTransport()
    tp.record(openalex.topics_url("causal ml", EMAIL), 200, OA_TOPICS)
    ids = openalex.OpenAlexClient(tp, email=EMAIL).topic_ids("causal ml")
    assert ids == ["T10001", "T10002"]                  # short ids for D-058 overlap


def test_openalex_authors_become_professor_targets():
    tp = CassetteTransport()
    tp.record(openalex.authors_url("https://openalex.org/I100", EMAIL), 200, OA_AUTHORS)
    authors = openalex.OpenAlexClient(tp, email=EMAIL).authors_by_institution(
        "https://openalex.org/I100")
    assert len(authors) == 1
    a = authors[0]
    assert a["short_id"] == "A200" and a["name"] == "Dr. Ada Maple"
    assert a["works_count"] == 42
    assert a["topic_ids"] == ["T10001", "T10002"]
    assert a["orcid"] == "https://orcid.org/0000-0002-1825-0097"


def test_openalex_works_give_activity_signal():
    tp = CassetteTransport()
    tp.record(openalex.works_url("https://openalex.org/A200", EMAIL), 200, OA_WORKS)
    works = openalex.OpenAlexClient(tp, email=EMAIL).works_by_author("https://openalex.org/A200")
    assert works == [{"openalex_id": "https://openalex.org/W1", "title": "On causal ML",
                      "year": 2025, "topic_ids": ["T10001"]}]


def _authors(n, start=0):
    return json.dumps({"results": [
        {"id": f"https://openalex.org/A{start+i}", "display_name": f"P{start+i}",
         "works_count": 1, "topics": [], "last_known_institutions": []} for i in range(n)]})


def test_openalex_authors_paginate_across_pages():
    # audit (live): a full page triggers a next-page fetch; a partial page ends it — no silent cap
    tp = CassetteTransport()
    tp.record(openalex.authors_url("I1", EMAIL, page=1), 200, _authors(25))    # full page
    tp.record(openalex.authors_url("I1", EMAIL, page=2), 200, _authors(3, 25))  # partial → last
    oa = openalex.OpenAlexClient(tp, email=EMAIL)
    authors = oa.authors_by_institution("I1")
    assert len(authors) == 28 and oa.truncated_sources == []


def test_openalex_truncation_is_recorded_when_cap_hit():
    tp = CassetteTransport()
    tp.record(openalex.authors_url("I1", EMAIL, page=1), 200, _authors(25))     # full, cap=1
    oa = openalex.OpenAlexClient(tp, email=EMAIL)
    authors = oa.authors_by_institution("I1", max_pages=1)
    assert len(authors) == 25 and oa.truncated_sources == ["authors@I1"]


def test_ror_truncation_is_recorded_when_cap_hit():
    tp = CassetteTransport()
    tp.record(ror.country_url("CA", 1), 200, json.dumps({"number_of_results": 500, "items": [
        {"id": "https://ror.org/1", "names": [{"value": "U", "types": ["ror_display"]}],
         "locations": [{"geonames_details": {"country_code": "CA"}}], "links": []}]}))
    rc = ror.RorClient(tp)
    insts = rc.institutions_in_country("CA", max_pages=1)
    assert len(insts) == 1 and rc.truncated_sources == ["institutions@CA"]


def test_openalex_mid_pagination_failure_records_truncation():
    # live audit-2: a full page then a transient non-200 stops enumeration — coverage must report
    # PARTIAL (a truncation marker), never silently claim completeness (D-037).
    tp = CassetteTransport()
    tp.record(openalex.authors_url("I1", EMAIL, page=1), 200, _authors(25))   # full page
    tp.record(openalex.authors_url("I1", EMAIL, page=2), 500, "boom")          # transient failure
    oa = openalex.OpenAlexClient(tp, email=EMAIL)
    authors = oa.authors_by_institution("I1")
    assert len(authors) == 25 and oa.truncated_sources == ["authors@I1"]


def test_ror_mid_pagination_failure_records_truncation():
    # ror.py has the same defect/fix: a mid-pagination failure before natural completion is PARTIAL.
    tp = CassetteTransport()
    tp.record(ror.country_url("CA", 1), 200, json.dumps({"number_of_results": 500, "items": [
        {"id": "https://ror.org/1", "names": [{"value": "U", "types": ["ror_display"]}],
         "locations": [{"geonames_details": {"country_code": "CA"}}], "links": []}]}))
    tp.record(ror.country_url("CA", 2), 500, "boom")
    rc = ror.RorClient(tp)
    insts = rc.institutions_in_country("CA")
    assert len(insts) == 1 and rc.truncated_sources == ["institutions@CA"]


def test_openalex_premium_key_is_included_when_present():
    # the optional paid key rides in the query when configured; email always does
    url = openalex.topics_url("x", EMAIL, key="sk-123")
    assert "mailto=me%40uni.edu" in url and "api_key=sk-123" in url
    assert "api_key" not in openalex.topics_url("x", EMAIL)   # omitted when no key


# ── live fix: server-side topic filter on the authors enumeration ─────────────

def test_authors_url_appends_the_topic_filter_only_when_topics_are_given():
    # live defect: enumerating EVERY author at an institution (353 x N institutions =
    # 6,123 targets for a niche field). The plan's topics now filter server-side
    # (OpenAlex "," = AND, "|" = OR); a no-topics call stays exactly as before.
    from urllib.parse import unquote
    filtered = unquote(openalex.authors_url("I100", EMAIL,
                                            topic_ids=["T10001", "T10002"]))
    assert "last_known_institutions.id:I100,topics.id:T10001|T10002" in filtered
    plain = unquote(openalex.authors_url("I100", EMAIL))
    assert "topics.id" not in plain


def test_authors_by_institution_requests_the_filtered_url():
    # the cassette is keyed on the FILTERED url — CassetteTransport raises on any other,
    # so a served response proves the filter string reached the request.
    tp = CassetteTransport()
    tp.record(openalex.authors_url("I100", EMAIL, topic_ids=["T10001"]), 200, OA_AUTHORS)
    oa = openalex.OpenAlexClient(tp, email=EMAIL)
    authors = oa.authors_by_institution("I100", topic_ids=["T10001"])
    assert len(authors) == 1 and oa.truncated_sources == []
