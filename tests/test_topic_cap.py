"""The topic cap: one number, stated where the choice is made, and no OR-list we cannot prove.

Reported from production on 2026-07-29. "Machine Learning · NLP" across nine phrasings offered
**111 topics**; the student checked 49 in a tree whose counter said only "49 of 111 topics
selected"; and the wizard's final click answered

    'resolved_topic_ids' must hold at most 25 topics (got 49)

— a server error, two steps away from the checkboxes that caused it, naming a JSON key and no
way out. Three defects in one:

1. **The cap was invisible until the last click.** D-069/D-070: never a dead end.
2. **The page and the server held separate numbers**, so the page could not have shown it.
3. **25 was too low for a real field**, and the reason it was low was never an API limit — it
   was our own §3.5 collection cap.

The fix keeps the student's breadth (50) without betting on an OpenAlex OR-list width nobody
has measured: wide selections are issued as several proven-width queries and merged.
"""

from __future__ import annotations

import json

from supervisorly import caps, webapi
from supervisorly.discover.openalex import OpenAlexClient, authors_url
from supervisorly.export.webapp import build_webapp
from supervisorly.fetch.transport import CassetteTransport

EMAIL = "me@uni.edu"
INST = "I999"


def _js(html: str) -> str:
    return html.split("<script>")[-1].split("</script>")[0]


def _author(aid: str) -> dict:
    return {"id": f"https://openalex.org/{aid}", "display_name": aid}


def _page(*ids: str) -> str:
    return json.dumps({"results": [_author(i) for i in ids]})


def _ids(authors: list[dict]) -> list[str]:
    return [str(a["openalex_id"]).rsplit("/", 1)[-1] for a in authors]


# ── one number, two enforcers ─────────────────────────────────────────────────
def test_the_page_and_the_server_read_the_same_cap():
    """The whole reason the student met the cap at the wrong moment: nobody told the page."""
    assert webapi.MAX_TOPICS == caps.MAX_TOPICS
    assert f"const MAX_TOPICS = {caps.MAX_TOPICS};" in build_webapp()


def test_the_page_hardcodes_no_cap_of_its_own():
    """A literal in the JS would drift the day the server's number changes."""
    js = _js(build_webapp())
    body = js.split("function updateCount(", 1)[1].split("\n}", 1)[0]
    assert "MAX_TOPICS" in body
    for literal in ("25", "50"):
        assert literal not in body, f"updateCount hardcodes {literal}"


# ── the cap is visible where the checkboxes are ───────────────────────────────
def test_the_counter_states_the_cap_before_anything_is_checked():
    """It read "0 of 0 topics selected" — true, and useless for avoiding the wall."""
    html = build_webapp()
    block = html.split('id="selCount"', 1)[1].split("</div>", 1)[0]
    assert "can be scanned" in " ".join(block.split())
    assert str(caps.MAX_TOPICS) in block


def test_going_over_is_said_out_loud_at_the_moment_it_happens():
    js = _js(build_webapp())
    body = js.split("function updateCount(", 1)[1].split("\n}", 1)[0]
    assert "too many" in body
    assert 'classList.toggle("over"' in body, "nothing marks the counter as over the cap"
    assert ".selcount.over{color:var(--coral)}" in build_webapp()


def test_step_3_refuses_to_advance_an_over_cap_plan():
    """The load-bearing one: step 4 can no longer be where the student learns about the cap."""
    js = _js(build_webapp())
    body = js.split("function step3Next(", 1)[1].split("\n}", 1)[0]
    assert "picked.length > MAX_TOPICS" in body
    assert "showStep(4)" in body
    # the branch that stops must return BEFORE showStep(4)
    stop = body.index("picked.length > MAX_TOPICS")
    assert body.index("showStep(4)") > stop


def test_the_message_says_how_many_to_uncheck():
    """"must hold at most 25 topics (got 49)" tells you the rule, not the move."""
    js = _js(build_webapp())
    body = js.split("function step3Next(", 1)[1].split("\n}", 1)[0]
    assert "picked.length-MAX_TOPICS" in body.replace(" ", "")
    assert "uncheck" in body


# ── the server keeps its backstop ─────────────────────────────────────────────
def test_a_plan_at_the_cap_is_accepted():
    plan = {"resolved_topic_ids": [f"T{i}" for i in range(caps.MAX_TOPICS)]}
    assert webapi._plan_cap_errors(plan) == []


def test_a_plan_over_the_cap_is_still_rejected_on_the_wire():
    """A plan can arrive from a file or a script that never ran the page (D-069)."""
    plan = {"resolved_topic_ids": [f"T{i}" for i in range(caps.MAX_TOPICS + 1)]}
    errors = webapi._plan_cap_errors(plan)
    assert len(errors) == 1
    assert "resolved_topic_ids" in errors[0] and str(caps.MAX_TOPICS) in errors[0]


# ── chunking: breadth without an unmeasured OR-list ───────────────────────────
def test_chunking_splits_at_the_proven_width():
    assert caps.chunk_topics([]) == []
    assert caps.chunk_topics(None) == []
    ids = [f"T{i}" for i in range(caps.MAX_TOPICS)]
    chunks = caps.chunk_topics(ids)
    assert [len(c) for c in chunks] == [25, 25]
    assert [t for c in chunks for t in c] == ids, "order must survive the split"
    assert max(len(c) for c in chunks) <= caps.TOPIC_FILTER_CHUNK


def test_no_chunk_is_wider_than_one_query_is_proven_to_carry():
    """The cap may rise again; this is the invariant that must hold when it does."""
    for n in (1, 24, 25, 26, 49, caps.MAX_TOPICS):
        chunks = caps.chunk_topics([f"T{i}" for i in range(n)])
        assert sum(len(c) for c in chunks) == n
        assert all(len(c) <= caps.TOPIC_FILTER_CHUNK for c in chunks)


def test_a_wide_selection_is_issued_as_several_queries_and_merged():
    """30 topics -> a 25-wide query and a 5-wide one. Recording ONLY those two URLs is the
    proof: any other shape would miss the cassette and show up as truncation."""
    ids = [f"T{i}" for i in range(30)]
    tp = CassetteTransport()
    tp.record(authors_url(INST, EMAIL, None, topic_ids=ids[:25]), 200, _page("A1"))
    tp.record(authors_url(INST, EMAIL, None, topic_ids=ids[25:]), 200, _page("A2"))
    oa = OpenAlexClient(tp, email=EMAIL)
    got = oa.authors_by_institution(INST, topic_ids=ids)
    assert [a["openalex_id"] for a in got] == ["https://openalex.org/A1",
                                               "https://openalex.org/A2"]
    assert oa.truncated_sources == [], "the client issued a URL we did not chunk"


def test_an_author_matching_two_chunks_is_counted_once():
    """Chunks overlap by nature — the same professor can be in topics from both halves."""
    ids = [f"T{i}" for i in range(30)]
    tp = CassetteTransport()
    tp.record(authors_url(INST, EMAIL, None, topic_ids=ids[:25]), 200, _page("A1", "A2"))
    tp.record(authors_url(INST, EMAIL, None, topic_ids=ids[25:]), 200, _page("A2", "A3"))
    oa = OpenAlexClient(tp, email=EMAIL)
    got = oa.authors_by_institution(INST, topic_ids=ids)
    assert _ids(got) == ["A1", "A2", "A3"]


def test_one_failing_chunk_does_not_discard_the_others():
    """Honest partial beats an empty institution: keep what we have, say coverage is partial."""
    ids = [f"T{i}" for i in range(30)]
    tp = CassetteTransport()
    tp.record(authors_url(INST, EMAIL, None, topic_ids=ids[:25]), 200, _page("A1"))
    # the second chunk is never recorded -> TransportError -> truncation
    oa = OpenAlexClient(tp, email=EMAIL)
    got = oa.authors_by_institution(INST, topic_ids=ids)
    assert _ids(got) == ["A1"]
    assert oa.truncated_sources == [f"authors@{INST}"]


def test_a_narrow_selection_still_issues_exactly_one_query():
    """The common case must not have got more expensive. 25 topics = one request, as before."""
    ids = [f"T{i}" for i in range(25)]
    tp = CassetteTransport()
    tp.record(authors_url(INST, EMAIL, None, topic_ids=ids), 200, _page("A1"))
    oa = OpenAlexClient(tp, email=EMAIL)
    assert len(oa.authors_by_institution(INST, topic_ids=ids)) == 1
    assert oa.truncated_sources == []


def test_a_plan_with_no_topics_is_still_one_unfiltered_enumeration():
    """The no-topic path is unchanged — chunking must not invent a filter."""
    tp = CassetteTransport()
    tp.record(authors_url(INST, EMAIL, None), 200, _page("A1"))
    oa = OpenAlexClient(tp, email=EMAIL)
    assert len(oa.authors_by_institution(INST, topic_ids=None)) == 1
    assert oa.truncated_sources == []
