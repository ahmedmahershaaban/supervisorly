"""D-073: a model may point at text that exists; it may never invent text.

These tests are about the boundary, not the happy path. The happy path is one test; the rest
are the ways a model output could become a fact it has not earned.
"""

from __future__ import annotations

import json

import pytest

from supervisorly.extract import llm_claims as lc

PAGE = ("Prof A. Example, Department of Computing.\n"
        "I am accepting PhD students for the 2027 intake. Applications close 15 January 2027.\n"
        "I also supervise MSc projects. The group collaborates with Siemens.\n")
SNAP = f"<html><body><main>{PAGE}</main></body></html>"


def _reply(*claims):
    return json.dumps({"claims": list(claims)})


def _c(field, value, quote):
    return {"field": field, "value": value, "quote": quote}


# ───────────────────────────────────────────────────────── the happy path

def test_a_quote_that_is_really_on_the_page_becomes_a_proposal():
    kept, dropped = lc.propose(PAGE, "https://x.test/", SNAP, lambda _p: _reply(
        _c("recruiting_signal", "open for PhD 2027",
           "I am accepting PhD students for the 2027 intake."),
        _c("deadline", "2027-01-15", "Applications close 15 January 2027.")))
    assert [p.field for p in kept] == ["recruiting_signal", "deadline"]
    assert dropped == []


# ───────────────────────────────────────── the reason this is safe at all

def test_an_invented_quote_is_dropped_however_plausible_it_sounds():
    """The whole design in one test. The model says something entirely reasonable — this is a
    professor, they might well be recruiting — and cites a sentence that is not on the page.
    It must not survive."""
    kept, dropped = lc.propose(PAGE, "https://x.test/", SNAP, lambda _p: _reply(
        _c("recruiting_signal", "recruiting",
           "I am currently recruiting postdocs with full funding.")))
    assert kept == []
    assert len(dropped) == 1 and "not found in snapshot" in dropped[0][1]


def test_a_quote_that_is_only_ALMOST_right_is_still_dropped():
    """Near-misses are the dangerous case: a model that 'tidies' a quote produces text that
    reads like evidence and cites a sentence nobody wrote. Paraphrase is not citation."""
    for tampered in [
        "I am accepting PhD students for the 2028 intake.",     # a digit changed
        "I am accepting PhD students for the 2027 intakes.",    # a word changed
        "We are accepting PhD students for the 2027 intake.",   # I -> We
    ]:
        kept, dropped = lc.propose(PAGE, "https://x.test/", SNAP,
                                   lambda _p, t=tampered: _reply(_c("recruiting_signal", "open", t)))
        assert kept == [], tampered
        assert len(dropped) == 1, tampered


def test_the_gate_is_imported_not_reimplemented():
    """A second implementation of a security check is how the check grows a hole. This module
    must use the same function record_claim uses (D-010/D-047)."""
    from supervisorly.fetch import normalize
    assert lc.quote_in_snapshot is normalize.quote_in_snapshot


# ─────────────────────────────────────────────── the model cannot widen the schema

@pytest.mark.parametrize("field", ["is_nice", "email", "salary", "identity_resolution",
                                   "profile", "", None, 7])
def test_a_field_the_export_does_not_have_is_dropped(field):
    """The column vocabulary is fixed in code. A model must not be able to add to it — an
    invented field would arrive with no descriptor, no label and no policy about exporting."""
    kept, _ = lc.propose(PAGE, "https://x.test/", SNAP, lambda _p: _reply(
        {"field": field, "value": "x", "quote": "I also supervise MSc projects."}))
    assert kept == []


def test_supervision_levels_are_an_enum_not_free_text():
    """`supervises` is matched against the student's intent_kind, so it has to speak the same
    vocabulary. Unrecognised words are DROPPED rather than mapped: mapping them would be a
    dictionary of a field's search terms, which D-038 forbids."""
    kept, _ = lc.propose(PAGE, "https://x.test/", SNAP, lambda _p: _reply(
        _c("supervises", "phd, doctoral, PhD students, postdoc, nonsense",
           "I also supervise MSc projects.")))
    assert [p.value for p in kept] == ["phd, postdoc"]


def test_a_supervises_claim_with_no_recognised_level_is_dropped_entirely():
    kept, _ = lc.propose(PAGE, "https://x.test/", SNAP, lambda _p: _reply(
        _c("supervises", "undergraduates only", "I also supervise MSc projects.")))
    assert kept == []


# ─────────────────────────────────────────────────────────── fail-closed

@pytest.mark.parametrize("raw", ["", "   ", "not json", "{}", "null", "[1,2,3]",
                                 '{"claims": "phd"}', '{"claims": [null, 3, "x"]}'])
def test_unusable_output_yields_nothing_and_never_raises(raw):
    kept, dropped = lc.propose(PAGE, "https://x.test/", SNAP, lambda _p: raw)
    assert kept == [] and dropped == []


def test_a_model_that_throws_cannot_fail_the_scan():
    """Nobody's supervisor search dies because a model was unavailable (the D-068 pattern)."""
    def boom(_p):
        raise RuntimeError("no key / timeout / 500")
    assert lc.propose(PAGE, "https://x.test/", SNAP, boom) == ([], [])


def test_a_markdown_fence_is_tolerated_because_that_is_formatting_not_content():
    raw = "```json\n" + _reply(_c("deadline", "2027-01-15",
                                  "Applications close 15 January 2027.")) + "\n```"
    kept, _ = lc.propose(PAGE, "https://x.test/", SNAP, lambda _p: raw)
    assert len(kept) == 1


# ─────────────────────────────────────────────────────────── bounded work

def test_a_flood_of_proposals_is_capped():
    many = [_c("students_signal", f"v{i}", "I also supervise MSc projects.") for i in range(80)]
    kept, _ = lc.propose(PAGE, "https://x.test/", SNAP, lambda _p: _reply(*many))
    assert len(kept) <= lc.MAX_PROPOSALS


def test_oversized_values_and_quotes_are_refused():
    kept, _ = lc.propose(PAGE, "https://x.test/", SNAP, lambda _p: _reply(
        _c("students_signal", "x" * (lc.MAX_VALUE_CHARS + 1), "I also supervise MSc projects."),
        _c("industry_signal", "ok", "y" * (lc.MAX_QUOTE_CHARS + 1))))
    assert kept == []


def test_duplicate_proposals_collapse():
    q = "The group collaborates with Siemens."
    kept, _ = lc.propose(PAGE, "https://x.test/", SNAP, lambda _p: _reply(
        _c("industry_signal", "Siemens", q), _c("industry_signal", "siemens", q)))
    assert len(kept) == 1


# ─────────────────────────────────────────────────────────── the prompt

def test_the_prompt_tells_the_model_the_rule_the_code_enforces():
    """Stating the gate makes the model cooperate with it instead of fighting it — and
    absence has to be offered as a valid answer, or a model asked for five fields returns
    five fields and honest emptiness (D-037) is lost."""
    p = lc.build_prompt(PAGE, "https://x.test/")
    assert "verbatim" in p.lower() or "EXACTLY" in p
    assert "discarded" in p
    assert "OMIT" in p and "empty list is a valid" in p
    assert "Never infer from the person's title" in p


def test_the_page_text_shown_to_the_model_is_capped():
    """Counted with a character the prompt's own wording cannot contain — the first version of
    this test used "A" and failed at 12,007, which was seven letters of boilerplate, not a
    leak. A cap test that also counts the template is measuring the wrong string."""
    p = lc.build_prompt("Ω" * 100_000, "https://x.test/")
    assert p.count("Ω") == lc.MAX_PAGE_CHARS
