"""Phase F DoD: the dashboard is a single self-contained HTML file (no external
resources), renders the four states distinctly, and shows every professor (D-033/046/037)."""

from supervisorly.export import dashboard as db
from supervisorly.export import json_export as jx


def _export():
    return jx.build_export(
        run_summary={"run_id": "run_x", "status": "finalized_with_open_gaps"},
        field_descriptors=[
            {"id": "recruiting", "label": "Recruiting", "kind": "filter", "datatype": "string"},
            {"id": "email", "label": "Email", "kind": "display", "datatype": "string"},
        ],
        professors=[{"id": "p1", "name": "Prof One"}, {"id": "p2", "name": "Prof Two"}],
        claims_by_entity={
            "p1": [
                {"field": "recruiting", "state": "value", "value": "recruiting Fall 2027",
                 "quote": "q", "source_url": "https://prof1/", "observed_at": "2026-07-20"},
                {"field": "email", "state": "searched_absent", "source_url": "https://prof1/"},
            ],
            "p2": [],   # no claims → all never_attempted, still shown
        },
        generated_at="2026-07-23T00:00:00+00:00",
    )


def test_dashboard_is_self_contained_no_external_resources():
    html = db.build_dashboard(_export())
    assert "<!doctype html>" in html.lower()
    # no external script/style/font/link loads (data source_urls are data, not resources)
    assert "<script src=" not in html
    assert "<link " not in html
    assert "cdn" not in html.lower() and "googleapis" not in html.lower()


def test_four_states_are_rendered_distinctly():
    html = db.build_dashboard(_export())
    for cls in ("s-value", "s-searched_absent", "s-never_attempted"):
        assert cls in html, f"missing state style {cls}"
    assert "we looked, found nothing" in html      # searched_absent copy
    assert "not checked yet" in html               # never_attempted copy


def test_every_professor_present_in_data():
    html = db.build_dashboard(_export())
    assert "Prof One" in html and "Prof Two" in html   # p2 not dropped despite no claims


def test_data_is_inlined_and_script_safe():
    # a value containing '</script>' must not break the embedded data block
    exp = _export()
    exp["professors"][0]["fields"]["recruiting"]["value"] = "closing </script> soon"
    html = db.build_dashboard(exp)
    assert "</script> soon" not in html            # neutralised
    assert "<\\/script> soon" in html
