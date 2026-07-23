"""Phase L6 — scheduled re-scan delta: a warm re-scan over unchanged pages issues ≈0 re-extraction
and reports an empty delta; a changed page shows up in the delta."""

from supervisorly import demo, pipeline
from supervisorly.export import delta


def _export_with(profs):
    return {"professors": profs}


def test_delta_reports_new_removed_and_changed():
    prev = _export_with([
        {"id": "a", "name": "Prof A", "fields": {"recruiting_signal": {"state": "searched_absent"}}},
        {"id": "b", "name": "Prof B", "fields": {"recruiting_signal": {"state": "value", "value": "x"}}},
    ])
    curr = _export_with([
        {"id": "a", "name": "Prof A", "fields": {"recruiting_signal": {"state": "value", "value": "recruiting!"}}},
        {"id": "c", "name": "Prof C", "fields": {"recruiting_signal": {"state": "value", "value": "y"}}},
    ])
    d = delta.compute_delta(prev, curr)
    assert d["new_professors"] == ["Prof C"]
    assert d["removed_professors"] == ["Prof B"]
    assert d["recruiting_changed"] == ["Prof A"]         # A's recruiting signal changed — review it
    assert "newly_recruiting" not in d                    # never asserts "now recruiting"
    assert any(c["field"] == "recruiting_signal" and c["professor"] == "Prof A"
               for c in d["changed_fields"])
    assert d["unchanged"] is False


def test_recruiting_highlight_is_a_review_signal_not_a_classification():
    # audit (live): recruiting_signal is a raw candidate, not open/closed. A negative sentence
    # appearing, or a closed->open change, is surfaced for REVIEW — never as a "now recruiting" claim.
    neg = delta.compute_delta(
        _export_with([{"id": "a", "name": "A", "fields": {"recruiting_signal": {"state": "searched_absent"}}}]),
        _export_with([{"id": "a", "name": "A", "fields": {"recruiting_signal": {
            "state": "value", "value": "I am not accepting students this year."}}}]))
    assert neg["recruiting_changed"] == ["A"] and "newly_recruiting" not in neg

    flip = delta.compute_delta(
        _export_with([{"id": "a", "name": "A", "fields": {"recruiting_signal": {
            "state": "value", "value": "Not currently accepting students."}}}]),
        _export_with([{"id": "a", "name": "A", "fields": {"recruiting_signal": {
            "state": "value", "value": "Now seeking PhD students for 2027."}}}]))
    assert flip["recruiting_changed"] == ["A"]            # closed->open change is caught (was missed)


def test_first_run_reports_everything_new():
    curr = _export_with([{"id": "a", "name": "Prof A", "fields": {}}])
    d = delta.compute_delta(None, curr)
    assert d["new_professors"] == ["Prof A"] and d["unchanged"] is False


def test_newly_published_deadline_is_highlighted():
    prev = _export_with([{"id": "a", "name": "A", "fields": {"deadline": {"state": "searched_absent"}}}])
    curr = _export_with([{"id": "a", "name": "A",
                          "fields": {"deadline": {"state": "value", "value": "2026-12-01"}}}])
    d = delta.compute_delta(prev, curr)
    assert d["newly_deadline"] == [{"professor": "A", "deadline": "2026-12-01"}]


def test_warm_rescan_delta_is_empty_and_cheap(tmp_path):
    """A scheduled re-scan over unchanged cassettes: ≈0 re-extraction (warm cache) + empty delta."""
    tp, targets, plan = demo.demo_fixture()
    db, snaps = tmp_path / "run.sqlite", tmp_path / "snaps"
    r1 = pipeline.run_offline(plan, targets, tp, snaps, db_path=db)
    r2 = pipeline.run_offline(plan, targets, tp, snaps, db_path=db)   # scheduled re-scan
    assert r2["stats"]["extractions"] == 0                # warm cache: nothing re-extracted
    assert delta.compute_delta(r1["export"], r2["export"])["unchanged"] is True


def test_changed_page_shows_in_delta(tmp_path):
    tp, targets, plan = demo.demo_fixture()
    db, snaps = tmp_path / "run.sqlite", tmp_path / "snaps"
    r1 = pipeline.run_offline(plan, targets, tp, snaps, db_path=db)
    # Ada's page changes its recruiting message → the re-scan should surface it
    tp.record("https://ca-uni.example/people/ada", 200,
              "<html><body><main><h1>Dr. Ada Placeholder</h1>"
              "<p>I am now recruiting three postdocs in reinforcement learning.</p>"
              "</main></body></html>")
    r2 = pipeline.run_offline(plan, targets, tp, snaps, db_path=db)
    d = delta.compute_delta(r1["export"], r2["export"])
    assert d["unchanged"] is False
    assert any(c["field"] == "recruiting_signal" and "reinforcement learning" in (c["value"] or "")
               for c in d["changed_fields"])
