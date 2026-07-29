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
