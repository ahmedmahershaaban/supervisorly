"""Phase B (part 2) DoD: the four-state JSON export builds from claims and validates,
the four states are distinct, judgements are excluded, and every value cites a source
(D-046, D-024, D-010)."""

from supervisorly.export import json_export as jx

DESCRIPTORS = [
    {"id": "name", "label": "Name", "kind": "search", "datatype": "string"},
    {"id": "recruiting_status", "label": "Recruiting", "kind": "filter", "datatype": "string"},
    {"id": "email", "label": "Email", "kind": "display", "datatype": "string"},
    {"id": "homepage", "label": "Homepage", "kind": "display", "datatype": "url"},
    # an LLM judgement about a person — must NOT be exported (D-024)
    {"id": "bandwidth_risk", "label": "Bandwidth", "kind": "display",
     "datatype": "string", "exportable": False},
]

CLAIMS = {
    "p1": [
        {"field": "recruiting_status", "state": "value", "value": "recruiting Fall 2027",
         "quote": "…", "source_url": "https://x/1", "observed_at": "2026-07-20",
         "confidence": "quoted_official", "extractor_agent": "recruiting-analyst"},
        # honest "we looked, found nothing"
        {"field": "email", "state": "searched_absent", "value": None,
         "source_url": "https://prof/1", "observed_at": "2026-07-20"},
        # a judgement claim exists locally but its field is non-exportable
        {"field": "bandwidth_risk", "state": "value", "value": "high",
         "source_url": "https://x/1", "extractor_agent": "profile-synthesist"},
    ],
    # p2 has no claims at all → every field is never_attempted, but still shown
    "p2": [],
}

PROFESSORS = [{"id": "p1", "name": "Prof One"}, {"id": "p2", "name": "Prof Two"}]


def _build():
    return jx.build_export(
        run_summary={"run_id": "run_x", "status": "finalized"},
        field_descriptors=DESCRIPTORS,
        professors=PROFESSORS,
        claims_by_entity=CLAIMS,
        generated_at="2026-07-23T00:00:00+00:00",
    )


def test_valid_export():
    obj = _build()
    assert jx.validate_export(obj) == [], jx.validate_export(obj)


def test_four_states_are_distinct():
    obj = _build()
    p1 = next(p for p in obj["professors"] if p["id"] == "p1")
    p2 = next(p for p in obj["professors"] if p["id"] == "p2")
    assert p1["fields"]["recruiting_status"]["state"] == "value"
    assert p1["fields"]["email"]["state"] == "searched_absent"
    assert p1["fields"]["email"]["value"] is None
    assert p2["fields"]["recruiting_status"]["state"] == "never_attempted"  # not dropped


def test_judgement_field_is_never_exported():
    obj = _build()
    # descriptor dropped
    assert all(d["id"] != "bandwidth_risk" for d in obj["fields"])
    # and no professor carries it, even though p1 has a local claim for it
    for p in obj["professors"]:
        assert "bandwidth_risk" not in p["fields"]


def test_exportable_flag_never_leaks():
    obj = _build()
    assert all("exportable" not in d for d in obj["fields"])


def test_validator_catches_leaked_judgement():
    obj = _build()
    # simulate a leak: inject the non-exportable field into a professor
    obj["professors"][0]["fields"]["bandwidth_risk"] = {
        "state": "value", "value": "high", "source_url": "https://x/1"
    }
    errs = jx.validate_export(obj)
    assert any("bandwidth_risk" in e for e in errs)


def test_validator_catches_value_without_source():
    obj = _build()
    obj["professors"][0]["fields"]["recruiting_status"]["source_url"] = None
    errs = jx.validate_export(obj)
    assert any("source_url" in e for e in errs)
