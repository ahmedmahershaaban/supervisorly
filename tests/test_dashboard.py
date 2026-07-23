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
    assert "\\u003c/script> soon" in html          # every '<' escaped as <


def test_inlined_data_escapes_comment_and_script_open():
    # audit (live): a value with '<!--' + '<script' must not break out of the DATA <script> block
    exp = _export()
    exp["professors"][0]["fields"]["recruiting"]["value"] = "use <!-- and <script here"
    html = db.build_dashboard(exp)
    assert "use <!-- and <script" not in html      # the raw dangerous sequence never survives
    assert "\\u003c!-- and \\u003cscript" in html  # escaped instead


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
    # both dates are present in the inlined data; sort is soonest-first by parsed date
    assert "2026-09-15" in html and "2026-12-01" in html
    assert "dateKey(a.when) - dateKey(b.when)" in html   # ascending sort by parsed date


def test_firm_badge_requires_an_official_confidence_not_the_default():
    # audit finding 8: only quoted_official/derived read as firm; null/unknown → watch (D-061)
    html = db.build_dashboard(_deadline_export())
    assert "FIRM_CONF" in html and "quoted_official" in html and "derived" in html
    assert "isFirm" in html and "isWatch" in html
    # the firm badge is gated on isFirm(...), so a missing/other confidence falls through to watch
    assert "isFirm(r.env)" in html


def test_source_links_are_scheme_guarded_against_javascript_urls():
    # audit finding 9: a javascript:/data: source_url must never become a clickable link
    html = db.build_dashboard(_deadline_export())
    assert "safeUrl" in html and "srcLink" in html
    assert "https?:" in html                       # only http(s) is linkified
    # source_url is never inlined directly into an href without going through srcLink/safeUrl
    assert 'href="\'+esc(env.source_url)' not in html


def test_deadline_view_sorts_by_parsed_date_not_lexicographically():
    # audit finding 10: sort by a parsed date key so non-ISO values order correctly
    html = db.build_dashboard(_deadline_export())
    assert "dateKey" in html and "Date.parse" in html
    assert "dateKey(a.when) - dateKey(b.when)" in html


def test_professor_detail_is_clickable_and_traceable():
    html = db.build_dashboard(_export())
    # rows carry an id and are keyboard-focusable buttons that open a detail panel
    assert 'role="button"' in html and "data-id=" in html
    assert "openDetail" in html and "closeDetail" in html
    # the detail panel shows the verbatim quote (traceability, D-010)
    assert "blockquote" in html
