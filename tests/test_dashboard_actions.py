"""A blocked cell must offer an ACTION, not just an instruction.

"⏳ awaiting your browser" told the student to do something and gave them nothing to click —
a terminal state that is a dead end, which is precisely what D-070 forbids. These tests pin
that the three actions exist, that the prompt is the real D-043 grammar rather than a
hand-written imitation, and that offering actions did not quietly become a way to send
automation at walled hosts.
"""

from __future__ import annotations

from supervisorly import pipeline
from supervisorly.export import dashboard as dash

TARGET = {
    "id": "A1", "name": "Dr Example",
    "institution_names": ["Cairo University"],
    "orcid": "https://orcid.org/0000-0002-1825-0097",
    "openalex_id": "https://openalex.org/A1",
    "url": "https://orcid.org/0000-0002-1825-0097", "url_kind": "orcid",
    "works_count": 12, "cited_by_count": 30, "topic_ids": ["T1"],
}
BLOCKED = ["deadline", "recruiting_signal"]


# ────────────────────────────────────────────────── the generated prompt

def test_the_prompt_is_generated_for_a_professor_with_open_gaps():
    p = pipeline._human_prompt_for(TARGET, BLOCKED)
    assert p and "Dr Example" in p
    for f in BLOCKED:
        assert f in p, f


def test_no_prompt_when_there_is_nothing_to_ask_for():
    """A professor whose fields were all answered must not be handed busywork."""
    assert pipeline._human_prompt_for(TARGET, []) is None


def test_the_prompt_carries_the_rules_that_make_the_answer_checkable():
    """The point of the human rung is that what comes back is a CLAIM with provenance, not a
    person's recollection — so the prompt has to demand a quote, a URL and a date, and has to
    make "found nothing" a first-class answer (D-037/D-043)."""
    p = pipeline._human_prompt_for(TARGET, BLOCKED)
    assert "Quote verbatim" in p
    assert "Cite a URL and a date" in p
    assert "searched_absent" in p
    assert "do NOT invent or infer" in p or "not invent" in p.lower()
    assert "Do not defeat any login" in p


def test_the_prompt_uses_the_real_grammar_not_a_hand_written_copy():
    """It is emitted through md_grammar — the module the ingester parses — so the two sides
    cannot drift. A dashboard that hand-rolled the shape in JavaScript would have produced
    Markdown nothing could read back."""
    from supervisorly.extract import md_grammar as mg
    p = pipeline._human_prompt_for(TARGET, BLOCKED)
    doc = p.split("```")[1]
    parsed = mg.parse(doc.replace("<the date you looked>", "2026-07-28"))
    assert parsed is not None


def test_the_anchor_links_lead_somewhere_and_do_not_repeat():
    links = pipeline._anchor_links(TARGET)
    assert links[0] == TARGET["url"]                 # the best lead first
    assert len(links) == len(set(links))             # url == orcid here, deduped
    assert any("openalex" in u for u in links)


# ────────────────────────────────────────────────── the dashboard surface

def _js() -> str:
    return dash.DASHBOARD_JS if hasattr(dash, "DASHBOARD_JS") else dash.build_dashboard(
        {"schema_version": 1, "generated_at": "2026-07-28T00:00:00+00:00",
         "run": {"run_id": "r", "status": "finalized_with_open_gaps"},
         "fields": [{"id": "deadline", "label": "Deadline"}],
         "professors": []})


def test_the_three_actions_are_offered():
    html = _js()
    assert "Open the page we found" in html
    assert "Search for their page" in html
    assert "Copy research prompt" in html


def test_the_actions_only_appear_where_something_is_blocked():
    """A professor whose fields were answered gets no call to action — the buttons hang off
    the same `anyBlocked` branch as the explanation."""
    html = _js()
    assert "anyBlocked?" in html.replace(" ", "")
    assert "actionsHtml(p)" in html


def test_copying_works_without_the_clipboard_api():
    """A downloaded dashboard opened from disk is a normal way to read this, and file:// is
    not a secure context — the Clipboard API is simply unavailable there. A copy button that
    silently does nothing is worse than no button."""
    html = _js()
    assert "fallbackCopyText" in html
    assert "execCommand" in html


def test_a_failed_copy_is_never_reported_as_a_successful_one():
    """Found by the e2e run on 2026-07-29, which clicked Copy, read "Copied ✓", and pasted the
    word **music** — whatever had been on the clipboard before. `writeText` is refused on an
    unfocused document and `execCommand("copy")` reports failure by RETURNING FALSE rather than
    throwing, so every path reached the same unconditional success message.

    A false success is worse than a plain failure here: the student pastes into their assistant
    and gets a confident answer about the wrong thing, with nothing on screen to explain it."""
    js = _js()
    body = js.split("function fallbackCopyText(", 1)[1].split("\n}", 1)[0]
    assert "return ok" in body, "the fallback still swallows its own failure"
    assert 'document.execCommand("copy")===true' in body.replace(" ", ""), \
        "execCommand's return value must be read — it reports failure without throwing"
    copy = js.split("function copyPrompt(", 1)[1].split("\nfunction ", 1)[0]
    assert "settle(fallbackCopyText(txt))" in copy, "the fallback's verdict must be used"
    assert 'settle(true)' in copy
    # the success message may only be assigned inside the success branch
    said = 'el.textContent="Copied'
    ok_branch = copy.split("if(ok){", 1)[1].split("else", 1)[0]
    assert said in ok_branch
    assert copy.count(said) == 1, "the success message is reachable from more than one path"


def test_a_refused_clipboard_hands_the_student_the_text():
    """The recovery has to be a real one. A blocked copy on a professor with no page removes
    the only action that row had left, so the prompt itself appears, selected, one Ctrl+C
    away — not an apology."""
    js = _js()
    assert "function offerManualCopy(" in js
    copy = js.split("function copyPrompt(", 1)[1].split("\nfunction ", 1)[0]
    assert "offerManualCopy(el,txt)" in copy.replace(" ", "")
    manual = js.split("function offerManualCopy(", 1)[1].split("\n}", 1)[0]
    assert ".select()" in manual and "textarea" in manual
    assert "press Ctrl+C" in copy, "the student must be told what to do"
    assert "textarea.manualcopy" in js, "the box has no styling, so it appears unreadable"


def test_the_search_action_is_a_search_not_a_scrape():
    """It opens a SEARCH in the student's own browser. The tool is not fetching anything, and
    must not start: this is the human rung (D-043/D-044), where a person reads pages they can
    already reach."""
    html = _js()
    assert "duckduckgo.com/?q=" in html
    assert 'target="_blank"' in html and 'rel="noopener noreferrer"' in html


def test_no_action_ever_points_the_TOOL_at_a_walled_host():
    """The buttons are links a human clicks. If any of them ever became a fetch, the walled
    rule would be bypassed by the UI rather than by the fetcher."""
    html = _js()
    for bad in ("fetch(", "XMLHttpRequest", "researchgate.net", "linkedin.com/in"):
        assert bad not in html, bad
