"""A field that resolves to no topics must SAY so — and a failed lookup is not an absence.

Found 2026-07-29 while running SPIKE-4: OpenAlex answers `429 {"error":"Rate limit exceeded",
"message":"Insufficient budget…"}` once the day's free budget is spent. `topic_ids` returned
`[]` for that, exactly as it did for "OpenAlex has no such topic", and `build_targets` treats
an empty topic list as "enumerate everything". So a rate-limited lookup silently turned
"professors in my field" into "the most prominent professors at these institutions" — a
full-looking dashboard of the wrong people, with the coverage line still claiming nothing was
dropped.

That is invariant §3 (failure is a state with a reason) and §6 (coverage honesty) in one bug.
It is also the mechanism behind a trap already documented in `01-spikes.md`: "cardiology"
resolves to zero OpenAlex topics, and the unfiltered cohort that produced scored 68% on
SPIKE-0 where the correctly-filtered one scored 28%.
"""

from __future__ import annotations

import json

from supervisorly.discover import ladder as _ladder
from supervisorly.discover.openalex import OpenAlexClient, topics_url
from supervisorly.fetch.transport import CassetteTransport

EMAIL = "me@uni.edu"
RATE_LIMITED = json.dumps({"error": "Rate limit exceeded",
                           "message": "Insufficient budget. This request costs $0.001 but "
                                      "you only have $0 remaining."})


def _client(status: int, body: str, query: str = "cardiology"):
    tp = CassetteTransport()
    tp.record(topics_url(query, EMAIL, None), status, body)
    return OpenAlexClient(tp, email=EMAIL)


def test_a_rate_limited_lookup_records_a_truncation_marker():
    """The 429 that started this. A failure must be visible in coverage, not silent."""
    oa = _client(429, RATE_LIMITED)
    assert oa.topic_ids("cardiology") == []
    assert "topics@cardiology" in oa.truncated_sources


def test_a_genuine_empty_result_records_nothing():
    """OpenAlex really has no topic named "cardiology". That is an ANSWER, and marking it as
    truncation would cry wolf on every honest miss."""
    oa = _client(200, json.dumps({"results": []}))
    assert oa.topic_ids("cardiology") == []
    assert oa.truncated_sources == []


def test_a_transport_failure_is_also_a_marker():
    oa = OpenAlexClient(CassetteTransport(), email=EMAIL)      # no cassette → TransportError
    assert oa.topic_ids("anything") == []
    assert oa.truncated_sources == ["topics@anything"]


def test_unparseable_json_is_a_marker_not_an_absence():
    oa = _client(200, "<html>we are down</html>")
    assert oa.topic_ids("cardiology") == []
    assert oa.truncated_sources == ["topics@cardiology"]


def test_a_successful_lookup_marks_nothing():
    oa = _client(200, json.dumps({"results": [{"id": "https://openalex.org/T123"}]}))
    assert oa.topic_ids("cardiology") == ["T123"]
    assert oa.truncated_sources == []


# ── the consequence, at the ladder ────────────────────────────────────────────
class _FakeRor:
    truncated_sources: list = []

    def institutions_in_country(self, code, **kw):
        return [{"ror_id": "https://ror.org/1", "name": "Uni", "homepage": "https://u.edu"}]


class _FakeOa:
    def __init__(self, topics):
        self._topics = topics
        self.truncated_sources: list = []

    def topic_ids(self, q):
        return list(self._topics)

    def institution_by_ror(self, ror):
        return "I1"

    def authors_by_institution(self, inst, topic_ids=None):
        return []


def test_an_unresolved_field_warns_that_the_scan_was_not_filtered():
    """The user-visible half. A student who typed a field they care about must be told when
    the results are not about that field — otherwise the dashboard looks fine and is wrong."""
    disc = _ladder.build_targets({"country": "EG", "field": "cardiology"},
                                 _FakeRor(), _FakeOa([]))
    joined = " ".join(disc["warnings"])
    assert "NO OpenAlex topics" in joined
    assert "not filtered by field" in joined.lower() or "NOT filtered" in joined
    assert "cardiology" in joined


def test_a_resolved_field_gives_the_normal_filtered_warning_instead():
    disc = _ladder.build_targets({"country": "EG", "field": "cardiology"},
                                 _FakeRor(), _FakeOa(["T1", "T2"]))
    joined = " ".join(disc["warnings"])
    assert "filtered to 2 topic(s)" in joined
    assert "NO OpenAlex topics" not in joined


def test_a_plan_with_no_field_at_all_is_not_warned_about():
    """A country-only scan is deliberately unfiltered — warning there would be noise, and a
    warning that always fires is one nobody reads."""
    disc = _ladder.build_targets({"country": "EG"}, _FakeRor(), _FakeOa([]))
    assert not any("NO OpenAlex topics" in w for w in disc["warnings"])
