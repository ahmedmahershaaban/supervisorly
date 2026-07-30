"""Rung 7 — the search-API page resolver, and its wiring into URL resolution.

This rung exists for one measured number: on a real GB · ML scan, **88% of shortlisted
professors had no page on record at all** and **0% had a page they control**. Everything here
protects two properties — it must never invent a page to fill that gap, and it must never
become a back door to a source D-039/D-044 already refused.
"""
import json

import pytest

from supervisorly import pipeline
from supervisorly.discover import websearch as W

BRAVE_KEY = {"SUPERVISORLY_SEARCH_KEY": "k", "SUPERVISORLY_SEARCH_PROVIDER": "brave"}
TAVILY_KEY = {"SUPERVISORLY_SEARCH_KEY": "k", "SUPERVISORLY_SEARCH_PROVIDER": "tavily"}


def _brave_body(*urls):
    return json.dumps({"web": {"results": [{"url": u} for u in urls]}})


def _transport(status, body, seen=None):
    def t(url, payload, headers, *, timeout=None):
        if seen is not None:
            seen.append({"url": url, "payload": payload, "headers": headers})
        return status, body
    return t


# ── the generated query (D-038) ──────────────────────────────────────────────
def test_the_query_is_generated_from_the_person_not_from_a_field_dictionary():
    q = W.build_query("Ada Lovelace", "University of London")
    assert '"Ada Lovelace"' in q            # quoted: a PERSON lookup, not topic literature
    assert "University of London" in q
    assert "research group" in q            # what a faculty page IS — a shape, not a term list
    assert W.build_query("") == ""


def test_the_query_survives_a_missing_institution():
    assert '"Ada Lovelace"' in W.build_query("Ada Lovelace", None)


# ── fail-closed (D-068) ──────────────────────────────────────────────────────
def test_no_key_means_no_rung_and_no_invented_page():
    assert W.configured({}) is False
    assert W.search("Ada Lovelace", "X", environ={}) == []


def test_an_unknown_provider_is_refused_rather_than_guessed():
    env = {"SUPERVISORLY_SEARCH_KEY": "k", "SUPERVISORLY_SEARCH_PROVIDER": "google"}
    assert W.configured(env) is False
    assert W.search("Ada Lovelace", "X", environ=env) == []


@pytest.mark.parametrize("status,body", [(429, ""), (500, "boom"), (200, "not json"),
                                         (200, "{}"), (200, '{"web": null}')])
def test_every_failure_shape_yields_an_open_gap_not_a_guess(status, body):
    assert W.search("Ada", "X", environ=BRAVE_KEY, transport=_transport(status, body)) == []


def test_a_transport_error_is_an_empty_list_not_an_exception():
    def boom(*_a, **_k):
        raise W.TransportError("timeout")
    assert W.search("Ada", "X", environ=BRAVE_KEY, transport=boom) == []


# ── what counts as "their own page" ──────────────────────────────────────────
@pytest.mark.parametrize("url", [
    "https://scholar.google.com/citations?user=x",
    "https://orcid.org/0000-0002-1825-0097",
    "https://www.semanticscholar.org/author/1",
    "https://en.wikipedia.org/wiki/Ada_Lovelace",
    "https://www.sciencedirect.com/science/article/x",
    "ftp://uni.edu/page",
    "",
])
def test_aggregators_and_registries_are_not_a_professors_own_page(url):
    assert W.is_candidate_page(url) is False


def test_a_walled_host_is_dropped_here_not_downstream():
    """D-039/D-044: a ResearchGate hit must die before anything is tempted to fetch it."""
    assert W.is_candidate_page("https://www.researchgate.net/profile/Ada") is False
    got = W.search("Ada", "X", environ=BRAVE_KEY, transport=_transport(
        200, _brave_body("https://www.researchgate.net/profile/Ada",
                         "https://cs.uni.edu/~ada")))
    assert got == ["https://cs.uni.edu/~ada"]


def test_a_real_faculty_page_is_kept():
    assert W.is_candidate_page("https://cs.uni.edu/people/ada-lovelace") is True


def test_results_are_deduped_and_capped():
    got = W.search("Ada", "X", environ=BRAVE_KEY, count=2, transport=_transport(
        200, _brave_body("https://a.edu/1", "https://a.edu/1",
                         "https://b.edu/2", "https://c.edu/3")))
    assert got == ["https://a.edu/1", "https://b.edu/2"]


# ── the providers ────────────────────────────────────────────────────────────
def test_brave_is_a_get_with_the_key_in_a_header_never_the_query_string():
    seen = []
    W.search("Ada Lovelace", "Uni", environ=BRAVE_KEY,
             transport=_transport(200, _brave_body("https://a.edu/1"), seen))
    assert seen[0]["payload"] is None                       # GET, not POST
    assert seen[0]["headers"]["X-Subscription-Token"] == "k"
    assert "k" not in seen[0]["url"].split("?")[1].replace("Lovelace", "")
    assert "Ada+Lovelace" in seen[0]["url"] or "Ada%20Lovelace" in seen[0]["url"]


def test_tavily_is_a_post_and_parses_its_own_shape():
    seen = []
    got = W.search("Ada", "Uni", environ=TAVILY_KEY, transport=_transport(
        200, json.dumps({"results": [{"url": "https://a.edu/1"}]}), seen))
    assert got == ["https://a.edu/1"]
    assert seen[0]["payload"]["query"].startswith('"Ada"')


# ── the wiring into URL resolution ───────────────────────────────────────────
def test_a_target_with_a_real_homepage_never_burns_a_search():
    calls = []
    t = {"id": "p", "name": "Ada", "url": "https://cs.uni.edu/~ada", "url_kind": "homepage"}
    url = pipeline._page_url_for(t, None, {}, lambda *a: calls.append(a) or ["https://x/"])
    assert url == "https://cs.uni.edu/~ada"
    assert calls == []


def test_a_target_with_no_page_at_all_is_resolved_by_the_rung():
    """The 88% case."""
    stats = {}
    t = {"id": "p", "name": "Ada Lovelace", "url": None, "url_kind": None,
         "institution_names": ["University of London"]}
    url = pipeline._page_url_for(t, None, stats, lambda n, i: ["https://cs.uni.edu/~ada"])
    assert url == "https://cs.uni.edu/~ada"
    assert stats["search_resolved"] == 1


def test_the_rung_is_given_the_professors_name_and_institution():
    seen = {}

    def search(name, inst):
        seen.update(name=name, inst=inst)
        return []
    pipeline._page_url_for(
        {"id": "p", "name": "Ada Lovelace", "url": None,
         "institution_names": ["University of London", "Other"]}, None, {}, search)
    assert seen == {"name": "Ada Lovelace", "inst": "University of London"}


def test_an_orcid_profile_is_upgraded_to_a_real_page_when_one_is_found():
    """Registries measurably never carry a recruiting sentence — a real page beats one."""
    stats = {}
    t = {"id": "p", "name": "Ada", "url": "https://orcid.org/0000-1", "url_kind": "orcid"}
    url = pipeline._page_url_for(t, None, stats, lambda n, i: ["https://cs.uni.edu/~ada"])
    assert url == "https://cs.uni.edu/~ada"


def test_finding_nothing_leaves_the_target_exactly_as_it_was():
    """No hit is an honest open gap for the human rung, never a substituted page."""
    stats = {}
    t = {"id": "p", "name": "Ada", "url": None, "url_kind": None}
    assert pipeline._page_url_for(t, None, stats, lambda n, i: []) is None
    assert "search_resolved" not in stats
    t2 = {"id": "q", "name": "Ada", "url": "https://orcid.org/0000-1", "url_kind": "orcid"}
    assert pipeline._page_url_for(t2, None, stats, lambda n, i: []) == "https://orcid.org/0000-1"


def test_without_a_configured_rung_resolution_is_unchanged():
    t = {"id": "p", "name": "Ada", "url": None, "url_kind": None}
    assert pipeline._page_url_for(t, None, {}, None) is None


# ── the two no-card providers ────────────────────────────────────────────────
GOOGLE_ENV = {"SUPERVISORLY_SEARCH_KEY": "k", "SUPERVISORLY_SEARCH_PROVIDER": "google",
              "SUPERVISORLY_SEARCH_CX": "cx123"}
GEMINI_ENV = {"SUPERVISORLY_SEARCH_KEY": "k", "SUPERVISORLY_SEARCH_PROVIDER": "gemini"}


def test_google_cse_is_unconfigured_without_an_engine_id():
    """A key alone cannot succeed there — say so once, not 25 failing requests later."""
    assert W.configured({"SUPERVISORLY_SEARCH_KEY": "k",
                         "SUPERVISORLY_SEARCH_PROVIDER": "google"}) is False
    assert W.configured(GOOGLE_ENV) is True
    assert W.search("Ada", "Uni", environ={"SUPERVISORLY_SEARCH_KEY": "k",
                                           "SUPERVISORLY_SEARCH_PROVIDER": "google"},
                    transport=_transport(200, "{}")) == []


def test_google_cse_parses_its_own_shape_and_hides_the_key_from_the_path():
    seen = []
    got = W.search("Ada Lovelace", "Uni", environ=GOOGLE_ENV, transport=_transport(
        200, json.dumps({"items": [{"link": "https://cs.uni.edu/~ada"},
                                   {"link": "https://orcid.org/0000-1"}]}), seen))
    assert got == ["https://cs.uni.edu/~ada"]        # the registry hit is filtered out
    assert seen[0]["payload"] is None                 # GET
    assert "cx=cx123" in seen[0]["url"]


def test_gemini_reads_grounding_sources_not_the_models_prose():
    """We consume the URLs it consulted, never its sentences — it cannot mint a page."""
    body = json.dumps({"candidates": [{
        "content": {"parts": [{"text": "https://totally-made-up.example/ada"}]},
        "groundingMetadata": {"groundingChunks": [
            {"web": {"uri": "https://cs.uni.edu/~ada", "title": "cs.uni.edu"}}]}}]})
    got = W.search("Ada", "Uni", environ=GEMINI_ENV, transport=_transport(200, body))
    assert got == ["https://cs.uni.edu/~ada"]
    assert not [u for u in got if "made-up" in u]     # the prose URL never enters


def test_gemini_asks_for_a_page_and_names_the_institution():
    seen = []
    W.search("Ada Lovelace", "University of Toronto", environ=GEMINI_ENV,
             transport=_transport(200, "{}", seen))
    prompt = seen[0]["payload"]["contents"][0]["parts"][0]["text"]
    assert "Ada Lovelace" in prompt and "University of Toronto" in prompt
    assert seen[0]["payload"]["tools"] == [{"google_search": {}}]   # grounding actually on


def test_a_grounding_redirect_is_resolved_before_it_can_be_fetched():
    """Fetching the proxy would robots-check Google, not the university. Resolve first."""
    body = json.dumps({"candidates": [{"groundingMetadata": {"groundingChunks": [
        {"web": {"uri": "https://vertexaisearch.cloud.google.com/grounding-api-redirect/xyz"}}]}}]})
    got = W.search("Ada", "Uni", environ=GEMINI_ENV, transport=_transport(200, body),
                   resolver=lambda u: "https://cs.uni.edu/~ada")
    assert got == ["https://cs.uni.edu/~ada"]


def test_a_redirect_that_will_not_resolve_is_dropped_not_passed_through():
    body = json.dumps({"candidates": [{"groundingMetadata": {"groundingChunks": [
        {"web": {"uri": "https://vertexaisearch.cloud.google.com/grounding-api-redirect/xyz"}}]}}]})
    got = W.search("Ada", "Uni", environ=GEMINI_ENV, transport=_transport(200, body),
                   resolver=lambda u: None)
    assert got == []                                  # an open gap beats fetching a proxy


def test_a_resolved_redirect_still_passes_the_aggregator_filter():
    """Resolution is not a bypass — a redirect that lands on ORCID is still not a homepage."""
    body = json.dumps({"candidates": [{"groundingMetadata": {"groundingChunks": [
        {"web": {"uri": "https://vertexaisearch.cloud.google.com/grounding-api-redirect/x"}}]}}]})
    got = W.search("Ada", "Uni", environ=GEMINI_ENV, transport=_transport(200, body),
                   resolver=lambda u: "https://orcid.org/0000-1")
    assert got == []


def test_every_provider_fails_closed_on_a_bad_response():
    for env in (BRAVE_KEY, TAVILY_KEY, GOOGLE_ENV, GEMINI_ENV):
        assert W.search("Ada", "Uni", environ=env, transport=_transport(500, "boom")) == []
        assert W.search("Ada", "Uni", environ=env, transport=_transport(200, "not json")) == []
