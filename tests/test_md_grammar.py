"""Phase B (part 1) DoD: the shared Phase-3 Markdown grammar round-trips losslessly
and maps to Claims. This is the human-rung seam (D-051, D-043)."""

import pytest

from supervisorly.extract import md_grammar as mg

FIXTURE = """\
# Supervisorly — human retrieval
target: person=person_abc123  name=Jane Q. Researcher
retrieved_at: 2026-07-23

## field: recruiting_status
value: recruiting for Fall 2027
quote: "I'm looking for 1-2 PhD students to start in Fall 2027."
source_url: https://x.com/jresearcher/status/999
observed_at: 2026-07-20
confidence: quoted_official

## field: email
value: jane@uni.example.edu
quote: Contact me at jane [at] uni [dot] example [dot] edu
source_url: https://cs.uni.example.edu/~jane/
observed_at: 2026-07-20

## field: twitter_recruiting_scan
state: searched_absent
note: checked pinned + last 3 months, no recruiting posts
source_url: https://x.com/jresearcher
observed_at: 2026-07-20
"""


def test_parse_extracts_target_and_entries():
    doc = mg.parse(FIXTURE)
    assert doc.target_kind == "person"
    assert doc.target_ref == "person_abc123"
    assert doc.target_name == "Jane Q. Researcher"
    assert [e.field for e in doc.entries] == [
        "recruiting_status", "email", "twitter_recruiting_scan"
    ]
    rec = doc.entries[0]
    assert rec.state == "value"
    assert rec.value == "recruiting for Fall 2027"
    assert rec.quote.startswith('"I\'m looking')       # verbatim, quotes preserved
    assert rec.confidence == "quoted_official"
    absent = doc.entries[2]
    assert absent.state == "searched_absent"
    assert absent.value is None
    assert "no recruiting posts" in absent.note


def test_roundtrip_is_lossless():
    doc = mg.parse(FIXTURE)
    reparsed = mg.parse(mg.emit(doc))
    assert reparsed == doc  # parse(emit(doc)) == doc


def test_to_claim_dicts_marks_human_assisted():
    doc = mg.parse(FIXTURE)
    claims = mg.to_claim_dicts(doc)
    assert len(claims) == 3
    assert all(c["extractor_agent"] == "human-assisted (Claude for Chrome)" for c in claims)
    assert all(c["entity_id"] == "person_abc123" for c in claims)
    # searched_absent claim carries no value but keeps its provenance
    absent = claims[2]
    assert absent["state"] == "searched_absent" and absent["value"] is None
    assert absent["source_url"].endswith("jresearcher")


def test_missing_target_is_rejected():
    with pytest.raises(mg.MDParseError):
        mg.parse("## field: x\nvalue: y\nsource_url: http://a\n")


def test_value_requires_source_url():
    """A value without a citation violates D-010 and must be rejected."""
    bad = "target: person=p1\n\n## field: recruiting\nvalue: yes\n"
    with pytest.raises(mg.MDParseError):
        mg.parse(bad)


def test_invalid_confidence_is_rejected():
    bad = ("target: person=p1\n\n## field: r\nvalue: yes\n"
           "source_url: http://a\nconfidence: super_sure\n")
    with pytest.raises(mg.MDParseError):
        mg.parse(bad)


def test_unknown_key_is_rejected():
    bad = "target: person=p1\n\n## field: r\nvalue: yes\nsource_url: http://a\nbogus: 1\n"
    with pytest.raises(mg.MDParseError):
        mg.parse(bad)
