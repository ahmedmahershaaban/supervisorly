"""ORCID public-API resolution (D-072) — the fix for the run that found 331 professors and
zero facts.

The behaviour under test is not "we can parse XML". It is the set of properties that make
this safe to have unlocked: a walled URL is never fetched, a lookup failure is never read as
an absence, and nothing reaches the API path that is not an ORCID iD.
"""

from __future__ import annotations

import pytest

from supervisorly import pipeline
from supervisorly.discover import orcid
from supervisorly.fetch.transport import CassetteTransport, Response, TransportError

NS = 'xmlns:researcher-url="http://www.orcid.org/ns/researcher-url"'


def _xml(*urls: str) -> str:
    items = "".join(
        f"<researcher-url:researcher-url><researcher-url:url-name>x</researcher-url:url-name>"
        f"<researcher-url:url>{u}</researcher-url:url></researcher-url:researcher-url>"
        for u in urls)
    return f'<?xml version="1.0"?><researcher-url:researcher-urls {NS}>{items}</researcher-url:researcher-urls>'


def _client(orcid_id: str, *urls: str, status: int = 200, body: str | None = None):
    t = CassetteTransport()
    t.record(orcid.researcher_urls_url(orcid_id), status,
             _xml(*urls) if body is None else body)
    return orcid.OrcidClient(t)


ID = "0000-0002-1825-0097"


# ---------------------------------------------------------------- the identifier guard

@pytest.mark.parametrize("given", [
    "https://orcid.org/0000-0002-1825-0097",
    "0000-0002-1825-0097",
    "orcid.org/0000-0002-1825-0097",
])
def test_an_orcid_is_recognised_in_every_form_a_target_carries_it(given):
    """Targets hold the iD as a URI in one field and bare in another; both must work."""
    assert orcid.normalize_id(given) == ID


def test_the_check_digit_x_is_an_orcid_not_a_typo():
    assert orcid.normalize_id("https://orcid.org/0000-0002-4543-692X") == "0000-0002-4543-692X"


@pytest.mark.parametrize("junk", [
    None, "", "not-an-orcid", "https://example.com/", "1234", "0000-0002-1825",
    "../../etc/passwd", "0000/0002/1825/0097",
])
def test_nothing_that_is_not_an_orcid_ever_reaches_the_api_path(junk):
    """The guard that stops a stray value being pasted into a URL. A client asked for junk
    must make NO request at all — not a request that happens to 404."""
    assert orcid.normalize_id(junk) is None
    t = CassetteTransport()          # empty: any request raises, so a call would fail loudly
    assert orcid.OrcidClient(t).researcher_urls(junk) == []


def test_an_embedded_orcid_is_not_extracted_from_an_attacker_controlled_host():
    """`normalize_id` searches, so a hostile string containing a valid iD yields that iD —
    which is FINE precisely because the iD, never the input, is what builds the URL."""
    c = _client(ID, "https://lab.example.edu/")
    assert c.researcher_urls(f"https://evil.test/{ID}?x=1") == ["https://lab.example.edu/"]


@pytest.mark.parametrize("hostile", [
    f"{ID}'; DROP TABLE claim;--",
    f"{ID}/../../admin",
    f"https://evil.test/{ID}#@attacker.test",
    f"{ID}?callback=http://evil.test",
])
def test_a_hostile_string_carrying_a_real_orcid_still_builds_a_safe_url(hostile):
    """The property that matters is not "hostile input is rejected" — it is that only the
    16 characters matching the iD pattern ever reach the URL. Everything after them is
    dropped, so no query, fragment or traversal can ride along into the API path."""
    assert orcid.researcher_urls_url(orcid.normalize_id(hostile)) == \
        f"{orcid.PUB_API}/{ID}/researcher-urls"


# ---------------------------------------------------------------- reading the record

def test_the_professors_page_is_read_from_the_public_record():
    assert _client(ID, "https://cs.example.edu/~prof").researcher_urls(ID) == \
        ["https://cs.example.edu/~prof"]


def test_a_hand_typed_url_with_no_scheme_is_still_a_homepage():
    """Records are typed by people: a bare `www.rheumatology4u.com` was 1 of the 6 real URLs
    found in the sample. Discarding it over a missing prefix would lose a real page."""
    assert _client(ID, "www.rheumatology4u.com").researcher_urls(ID) == \
        ["https://www.rheumatology4u.com"]


@pytest.mark.parametrize("bad", ["mailto:prof@uni.edu", "ftp://files.example.edu", "   ", "notaurl"])
def test_things_that_are_not_web_pages_are_dropped(bad):
    assert _client(ID, bad).researcher_urls(ID) == []


def test_order_is_preserved_and_duplicates_collapse():
    c = _client(ID, "https://a.edu/", "https://b.edu/", "https://a.edu/")
    assert c.researcher_urls(ID) == ["https://a.edu/", "https://b.edu/"]


def test_a_record_with_no_urls_is_an_answer_not_a_failure():
    """Three quarters of real records list nothing. That is honest absence (D-037) and must
    NOT be recorded as a failed lookup, or coverage would report a problem that isn't one."""
    c = _client(ID)
    assert c.researcher_urls(ID) == []
    assert c.failed_lookups == []


@pytest.mark.parametrize("status,body", [(404, None), (500, None), (200, "<not xml")])
def test_a_failed_lookup_is_distinguishable_from_an_empty_record(status, body):
    """Both return [], and that is deliberate — but the caller that cares must still be able
    to tell "ORCID says none" from "we never found out" (D-037)."""
    c = _client(ID, status=status, body=body if body is not None else _xml())
    assert c.researcher_urls(ID) == []
    assert c.failed_lookups == [ID]


def test_a_transport_error_never_escapes_into_the_scan():
    """A registry being down must not fail the run that was using it."""
    class Dead:
        def get(self, url):
            raise TransportError("orcid down")
    c = orcid.OrcidClient(Dead())
    assert c.researcher_urls(ID) == []
    assert c.failed_lookups == [ID]


def test_the_small_endpoint_is_used_not_the_whole_record():
    """~3.5 KB vs ~44 KB, once per shortlisted professor."""
    assert orcid.researcher_urls_url(ID).endswith(f"/{ID}/researcher-urls")
    assert "/record" not in orcid.researcher_urls_url(ID)


# ---------------------------------------------------------------- the pipeline seam

def test_a_walled_researcher_url_is_skipped_not_fetched():
    """The line D-072 does not cross. 2 of the 6 real URLs found were ResearchGate and
    LinkedIn; scraping them is forbidden (D-039/043/044) whatever robots.txt allows. If this
    test ever fails, the tool has started scraping walled sources.

    Asserts the PROPERTY (no walled URL is ever handed onward) rather than a particular
    return value — the fallback changed under D-073 and this rule did not."""
    t = {"url": f"https://orcid.org/{ID}", "url_kind": "orcid", "orcid": ID}
    c = _client(ID, "https://www.linkedin.com/in/prof/", "https://x.com/prof")
    picked = pipeline._page_url_for(t, c, {})
    assert picked is None or not pipeline._WALLED_SOCIAL.search(picked)


@pytest.mark.parametrize("walled", [
    "https://www.researchgate.net/profile/Some_Prof",   # 403 to bots, robots.txt SELECTIVE
    "https://researchgate.net/profile/Some_Prof",       # ...and without the www
    "https://www.academia.edu/12345/Paper",
    "https://scholar.google.com/citations?user=abc",
    "https://scholar.google.co.uk/citations?user=abc",
    "https://twitter.com/prof", "https://x.com/prof",
    "https://uk.linkedin.com/in/prof",                  # country subdomain
])
def test_every_measured_bot_walled_profile_host_is_refused(walled):
    """ResearchGate is the one that matters: its robots.txt is SELECTIVE, so the robots gate
    ALLOWS /profile/ and nothing else would stop the fetch — it just 403s. A live ORCID
    record listed exactly such a URL as a professor's only page, which is how this was found."""
    t = {"url": f"https://orcid.org/{ID}", "url_kind": "orcid", "orcid": ID}
    picked = pipeline._page_url_for(t, _client(ID, walled), {})
    assert picked != walled and not pipeline._WALLED_SOCIAL.search(picked or "")


def test_a_real_page_wins_over_a_walled_one_in_the_same_record():
    t = {"url": f"https://orcid.org/{ID}", "url_kind": "orcid", "orcid": ID}
    c = _client(ID, "https://www.linkedin.com/in/prof/", "https://eng.example.edu/prof")
    stats = {}
    assert pipeline._page_url_for(t, c, stats) == "https://eng.example.edu/prof"
    assert stats["orcid_resolved"] == 1


def test_a_resolved_page_is_preferred_over_the_orcid_profile():
    """A real homepage always wins — that is what resolution is for."""
    t = {"url": f"https://orcid.org/{ID}", "url_kind": "orcid", "orcid": ID}
    assert pipeline._page_url_for(t, _client(ID, "https://ok.edu/"), {}) == "https://ok.edu/"


def test_with_no_researcher_url_we_fall_back_to_the_orcid_profile_itself():
    """This REVERSES the original D-072 behaviour, deliberately.

    D-072 returned None here, to skip fetching a page "known in advance to be walled". True
    while the only reader was an HTTP client; false once the render rung (D-073) existed —
    the profile is public, robots-allowed and merely needs JavaScript, and a browser reads it
    (29,109 chars measured on a real Cairo professor).

    Keeping the skip made the render rung dead code for exactly the targets it was built for:
    the first hosted run after shipping it deep-dived 12 professors in 3 seconds and never
    opened a browser, because no URL was ever handed to the fetcher."""
    t = {"url": f"https://orcid.org/{ID}", "url_kind": "orcid", "orcid": ID}
    assert pipeline._page_url_for(t, _client(ID), {}) == f"https://orcid.org/{ID}"


def test_a_record_of_only_walled_urls_still_falls_back_rather_than_giving_up():
    """The walled candidates are skipped, but the ORCID profile is not walled — it is the
    honest remaining lead."""
    t = {"url": f"https://orcid.org/{ID}", "url_kind": "orcid", "orcid": ID}
    c = _client(ID, "https://www.linkedin.com/in/prof/", "https://x.com/prof")
    assert pipeline._page_url_for(t, c, {}) == f"https://orcid.org/{ID}"


def test_a_target_with_a_real_homepage_is_left_completely_alone():
    """Only the ORCID fallback is rerouted. A homepage from OpenAlex must not cost an API
    call, so an empty cassette (which raises on any request) proves none is made."""
    t = {"url": "https://prof.example.edu/", "url_kind": "homepage"}
    assert pipeline._page_url_for(t, orcid.OrcidClient(CassetteTransport()), {}) == \
        "https://prof.example.edu/"


def test_without_a_client_behaviour_is_exactly_what_it_was():
    """The offline/demo path passes no client and must stay network-free (D-011/D-063)."""
    t = {"url": f"https://orcid.org/{ID}", "url_kind": "orcid", "orcid": ID}
    assert pipeline._page_url_for(t, None, {}) == t["url"]
