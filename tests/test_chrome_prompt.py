"""Phase G (part 1): the chrome-prompt-generator emits a prompt whose example output is
valid under the SAME grammar the ingester parses — the two halves of the human rung
cannot drift (D-051, D-043)."""

import re

import pytest

from supervisorly.extract import chrome_prompt as cp
from supervisorly.extract import md_grammar as mg


def test_prompt_contains_target_fields_and_rules():
    p = cp.generate_prompt(
        target_kind="person", target_ref="person_x", target_name="Dr. Kim",
        missing_fields=["recruiting_status", "email"],
        anchor_links=["https://kim.example.edu/", "https://x.com/drkim"],
    )
    assert "Dr. Kim" in p and "person_x" in p
    assert "recruiting_status" in p and "email" in p
    assert "https://x.com/drkim" in p
    # the ethics/provenance rules must be present
    assert "verbatim" in p and "searched_absent" in p and "date" in p.lower()


def test_embedded_example_parses_under_the_real_grammar():
    """The example the student is shown must itself be valid input to the ingester —
    proving the emitting and parsing halves share one grammar."""
    p = cp.generate_prompt(
        target_kind="person", target_ref="person_x", target_name="Dr. Kim",
        missing_fields=["recruiting_status", "twitter_scan"], anchor_links=[],
    )
    block = re.search(r"```\n(.*?)\n```", p, re.S)
    assert block, "prompt should contain a fenced example"
    doc = mg.parse(block.group(1))          # must not raise
    assert doc.target_ref == "person_x"
    assert doc.entries[1].state == "searched_absent"


def test_no_fields_is_rejected():
    with pytest.raises(ValueError):
        cp.generate_prompt(target_kind="person", target_ref="p", target_name=None,
                           missing_fields=[], anchor_links=[])
