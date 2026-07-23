"""Phase L0 — ROR + OpenAlex clients round-trip recorded cassettes into typed results, with
no live network. Fixtures are synthetic (invented names, example domains) — D-035 safe."""

import json

from supervisorly.discover import openalex, ror
from supervisorly.fetch.transport import CassetteTransport

EMAIL = "me@uni.edu"

# ── synthetic ROR response (v1 shape) ─────────────────────────────────────────
ROR_CA = json.dumps({
    "number_of_results": 2,
    "items": [
        {"id": "https://ror.org/00abc11", "name": "Maple University",
         "country": {"country_code": "CA", "country_name": "Canada"},
         "links": ["https://maple.example/"], "types": ["Education"]},
        {"id": "https://ror.org/00abc22", "name": "Northern Institute",
         "country": {"country_code": "CA", "country_name": "Canada"},
         "links": [], "types": ["Facility"]},
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


def test_ror_client_returns_empty_on_error_not_crash():
    tp = CassetteTransport()
    tp.record(ror.country_url("ZZ"), 500, "boom")
    assert ror.RorClient(tp).institutions_in_country("ZZ") == []
    # a URL with no cassette (transport error) is also handled, not raised
    assert ror.RorClient(CassetteTransport()).institutions_in_country("ZZ") == []


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


def test_openalex_premium_key_is_included_when_present():
    # the optional paid key rides in the query when configured; email always does
    url = openalex.topics_url("x", EMAIL, key="sk-123")
    assert "mailto=me%40uni.edu" in url and "api_key=sk-123" in url
    assert "api_key" not in openalex.topics_url("x", EMAIL)   # omitted when no key
