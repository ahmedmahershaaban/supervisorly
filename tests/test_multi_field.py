"""Several fields, not one (step 2).

A student rarely has exactly one way to name what they work on: "ML", "AI safety" and "NLP"
are three doors into overlapping literatures, and making them pick one door before they have
seen anything is the tool narrowing their search on their behalf.

The rule these tests hold to: `fields` is the truth, `field` is its readable join. One source,
one derivation — never two places that can disagree about what was searched.
"""

from __future__ import annotations

import pytest

from supervisorly import cli
from supervisorly.discover import ladder
from supervisorly.export.webapp import build_webapp


# ────────────────────────────────────────────────────────── reading a plan

def test_both_plan_shapes_are_read_by_one_function():
    """New plans send `fields`; every plan written before today, and the CLI still, sends
    `field`. One reader serves both so no caller has to know which era a plan came from."""
    assert ladder.plan_fields({"fields": ["ML", "AI safety"]}) == ["ML", "AI safety"]
    assert ladder.plan_fields({"field": "molecular biology"}) == ["molecular biology"]
    assert ladder.plan_fields({"subfield": "cardiology"}) == ["cardiology"]


def test_the_readable_join_is_never_searched_as_a_field_of_its_own():
    """The page sends BOTH `fields=["ML","AI safety"]` and `field="ML · AI safety"`, the
    second being the readable join. Merging them — which the first version of this function
    did — produced a phantom third field named after the join. Nobody works in "ML · AI
    safety", and asking OpenAlex for it returns nothing at best and something at worst.

    So `fields` wins outright when present; it is not combined with `field`."""
    plan = {"fields": ["ML", "AI safety"], "field": "ML · AI safety"}
    assert ladder.plan_fields(plan) == ["ML", "AI safety"]


@pytest.mark.parametrize("plan,expect", [
    ({"fields": ["ML", "ml", "  ML  "]}, ["ML", "ml"]),        # exact-dupes and padding only
    ({"fields": ["", "   ", "NLP"]}, ["NLP"]),                 # blanks are not fields
    ({}, []),
    ({"fields": None, "field": None}, []),
])
def test_junk_never_becomes_a_field(plan, expect):
    assert ladder.plan_fields(plan) == expect


# ────────────────────────────────────────────────── resolving topics per field

class _OA:
    def __init__(self, mapping): self.mapping, self.asked = mapping, []
    def topic_ids(self, field):
        self.asked.append(field)
        return self.mapping.get(field, [])


def test_each_field_is_resolved_separately_and_merged():
    """Joining them into one query would ask OpenAlex for a field nobody works in
    ("ML AI safety"); the union of two real searches is the honest answer."""
    oa = _OA({"ML": ["T1", "T2"], "AI safety": ["T2", "T9"]})
    ids = ladder.resolve_topic_ids({"fields": ["ML", "AI safety"]}, oa)
    assert oa.asked == ["ML", "AI safety"]
    assert ids == ["T1", "T2", "T9"]              # merged, de-duped, order preserved


def test_explicit_topic_ids_still_win_over_any_field():
    """The wizard resolves topics itself; this fallback must not second-guess it."""
    oa = _OA({"ML": ["T1"]})
    assert ladder.resolve_topic_ids(
        {"fields": ["ML"], "resolved_topic_ids": ["T77"]}, oa) == ["T77"]
    assert oa.asked == []


def test_a_field_that_resolves_to_nothing_does_not_sink_the_others():
    oa = _OA({"ML": ["T1"], "underwater basket weaving": []})
    assert ladder.resolve_topic_ids(
        {"fields": ["underwater basket weaving", "ML"]}, oa) == ["T1"]


# ──────────────────────────────────────────────────────── plan validation

def test_a_plan_may_carry_several_fields():
    assert cli._plan_value_errors({"fields": ["ML", "AI safety"]}) == []


def test_fields_must_be_a_list_of_strings():
    errs = cli._plan_value_errors({"fields": "ML"})
    assert any("list of strings" in e for e in errs)


def test_blank_entries_are_refused_rather_than_silently_dropped():
    """A blank field means the student's intent was mangled somewhere upstream. Dropping it
    quietly would search for less than they asked for and say nothing."""
    errs = cli._plan_value_errors({"fields": ["ML", "   "]})
    assert any("blank" in e for e in errs)


def test_the_number_of_fields_is_capped():
    """Each field costs an expansion plus one map call per phrasing, so this bounds the §5.2
    throttle spend of a single Understand click, not just the payload."""
    errs = cli._plan_value_errors({"fields": [f"f{i}" for i in range(cli.PLAN_MAX_FIELDS + 1)]})
    assert any("at most" in e for e in errs)
    assert cli._plan_value_errors({"fields": [f"f{i}" for i in range(cli.PLAN_MAX_FIELDS)]}) == []


# ──────────────────────────────────────────────────────────── the page

@pytest.fixture(scope="module")
def page():
    return build_webapp(api_base="https://example.test")


def test_the_page_offers_a_multi_field_input(page):
    for marker in ('id="fieldAdd"', 'id="fieldChips"', "function addField",
                   "function gatherFields", "function renderFieldChips"):
        assert marker in page, marker
    assert "Your field(s), in your words" in page


def test_the_page_cap_matches_the_server_cap(page):
    """Two caps that can disagree is a form the student can fill and the server will reject."""
    assert f"var MAX_FIELDS = {cli.PLAN_MAX_FIELDS};" in page


def test_enter_adds_a_field_rather_than_submitting(page):
    """With a multi-value input, submitting on the first Enter makes a second field
    unreachable from the keyboard."""
    i = page.index('getElementById("field").addEventListener("keydown"')
    assert "addField();" in page[i:i + 220]
    assert "understand();" not in page[i:i + 220]


def test_text_left_unadded_in_the_box_is_still_searched(page):
    """Forgetting to press "+ add" before Understand is the obvious mistake; dropping that
    text silently would search for something the student did not ask for."""
    i = page.index("function gatherFields")
    body = page[i:i + 400]
    assert 'getElementById("field").value' in body
    assert "all.push(typed)" in body


def test_the_plan_carries_the_list_and_the_join(page):
    assert "fields: state.fields.slice()," in page
    assert "field: state.field," in page
    assert 'state.field = fields.join(" · ");' in page
