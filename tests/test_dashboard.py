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


def _deadline_export():
    """An export with a date-typed field: one firm (officially quoted) deadline and one
    projected/watch date (inferred), plus a professor with no deadline at all."""
    return jx.build_export(
        run_summary={"run_id": "run_d", "status": "finalized"},
        field_descriptors=[
            {"id": "deadline", "label": "Application deadline", "kind": "sort", "datatype": "date"},
        ],
        professors=[{"id": "p1", "name": "Firm Prof"},
                    {"id": "p2", "name": "Watch Prof"},
                    {"id": "p3", "name": "No Deadline Prof"}],
        claims_by_entity={
            "p1": [{"field": "deadline", "state": "value", "value": "2026-12-01",
                    "quote": "Applications close 1 December 2026.",
                    "source_url": "https://p1/", "observed_at": "2026-07-20",
                    "confidence": "quoted_official"}],
            "p2": [{"field": "deadline", "state": "value", "value": "2026-09-15",
                    "quote": "Applications typically open each autumn.",
                    "source_url": "https://p2/", "observed_at": "2026-07-20",
                    "confidence": "inferred"}],
            "p3": [],
        },
        generated_at="2026-07-23T00:00:00+00:00",
    )


def test_deadline_view_present_and_distinguishes_firm_from_watch():
    html = db.build_dashboard(_deadline_export())
    # the view toggle and renderer exist
    assert 'id="vDeadlines"' in html and "renderDeadlines" in html
    # firm vs projected are separate, styled classes (D-061 — projected shown as watch)
    assert "badge firm" in html and "badge watch" in html
    # the honesty note that watch dates are not published deadlines
    assert "not published deadlines" in html.lower()
    # both dates are present in the inlined data; sort is soonest-first in code
    assert "2026-09-15" in html and "2026-12-01" in html
    assert "when < b.when" in html                 # ascending sort by date


def test_watch_date_is_driven_by_confidence_not_guessed():
    # the projected/watch classification keys on inferred/unconfirmed/action_needed only
    html = db.build_dashboard(_deadline_export())
    assert "WATCH_CONF" in html
    for conf in ("inferred", "unconfirmed", "action_needed"):
        assert conf in html


def test_professor_detail_is_clickable_and_traceable():
    html = db.build_dashboard(_export())
    # rows carry an id and are keyboard-focusable buttons that open a detail panel
    assert 'role="button"' in html and "data-id=" in html
    assert "openDetail" in html and "closeDetail" in html
    # the detail panel shows the verbatim quote (traceability, D-010)
    assert "blockquote" in html
