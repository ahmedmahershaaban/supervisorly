"""Phase L6 — scheduled re-scan delta: a warm re-scan over unchanged pages issues ≈0 re-extraction
and reports an empty delta; a changed page shows up in the delta."""

from supervisorly import demo, pipeline
from supervisorly.export import delta
from supervisorly.fetch.transport import CassetteTransport
from supervisorly.model import claims
from supervisorly.model.db import open_db


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


def test_deadline_watch_to_firm_confidence_flip_is_surfaced():
    """Regression (audit): state/value-only comparison reported a watch->firm confidence
    flip (inferred -> quoted_official, same date) as unchanged, while the dashboard badge
    flipped to FIRM (dashboard.py FIRM_CONF) — the event a re-scan exists to surface."""
    prev = _export_with([{"id": "a", "name": "A", "fields": {"deadline": {
        "state": "value", "value": "2026-12-01", "confidence": "inferred"}}}])
    curr = _export_with([{"id": "a", "name": "A", "fields": {"deadline": {
        "state": "value", "value": "2026-12-01", "confidence": "quoted_official"}}}])
    d = delta.compute_delta(prev, curr)
    assert d["unchanged"] is False
    assert any(c["field"] == "deadline" for c in d["changed_fields"])
    assert d["newly_deadline"] == [{"professor": "A", "deadline": "2026-12-01"}]


def test_vanished_field_is_surfaced_as_a_removal():
    """Regression (audit): only curr field keys were iterated, so a field present in prev
    but gone from curr was silently dropped from the delta."""
    prev = _export_with([{"id": "a", "name": "A", "fields": {
        "deadline": {"state": "value", "value": "2026-12-01"}}}])
    curr = _export_with([{"id": "a", "name": "A", "fields": {}}])
    d = delta.compute_delta(prev, curr)
    assert d["unchanged"] is False
    assert any(c["field"] == "deadline" and c["from_state"] == "value"
               and c["to_state"] is None for c in d["changed_fields"])


def test_schema_version_mismatch_is_reported_and_per_field_diff_skipped():
    """Regression (audit): schema_version was never compared — a schema-wide field
    addition flooded phantom from_state: None changes. Report the mismatch instead."""
    prev = {"schema_version": "1", "professors": [
        {"id": "a", "name": "A", "fields": {"deadline": {"state": "searched_absent"}}}]}
    curr = {"schema_version": "2", "professors": [
        {"id": "a", "name": "A", "fields": {"deadline": {"state": "searched_absent"},
                                            "new_field": {"state": "never_attempted"}}}]}
    d = delta.compute_delta(prev, curr)
    assert d["schema_mismatch"] == {"previous": "1", "current": "2"}
    assert d["changed_fields"] == []            # no phantom per-field noise
    assert d["unchanged"] is True
    # same schema → the new field IS surfaced (once), not hidden
    prev["schema_version"] = "2"
    d2 = delta.compute_delta(prev, curr)
    assert d2["schema_mismatch"] is None
    assert any(c["field"] == "new_field" for c in d2["changed_fields"])


def test_rename_is_surfaced():
    prev = _export_with([{"id": "a", "name": "Prof Old", "fields": {}}])
    curr = _export_with([{"id": "a", "name": "Prof New", "fields": {}}])
    d = delta.compute_delta(prev, curr)
    assert d["renamed"] == [{"id": "a", "from": "Prof Old", "to": "Prof New"}]
    assert d["unchanged"] is False


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


_V1 = ("<html><body><main><p>I am recruiting a PhD student for 2027.</p>"
       "<p>My research is on graphs.</p></main></body></html>")
_V2 = ("<html><body><main><p>My research is on graphs and networks.</p>"
       "</main></body></html>")   # the recruiting sentence is genuinely REMOVED


def _two_scan(tmp_path):
    tp = CassetteTransport()
    tp.record("https://u.edu/robots.txt", 200, "User-agent: *\nAllow: /\n")
    tp.record("https://u.edu/p", 200, _V1)
    db, snaps = tmp_path / "run.sqlite", tmp_path / "snaps"
    plan = {"intent_kind": "pre_phd", "resolved_topic_ids": ["T"]}
    tgt = [{"id": "p", "name": "Prof Y", "url": "https://u.edu/p"}]
    r1 = pipeline.run_offline(plan, tgt, tp, snaps, db_path=db)
    return tp, db, snaps, plan, tgt, r1


def test_verified_removal_supersedes_a_stale_deterministic_value(tmp_path):
    """live audit-5: a successful 200 re-fetch with a NEW content hash whose re-extraction
    affirmatively finds nothing is a verified removal — record searched_absent (superseding the
    stale deterministic value) so the delta surfaces it. The old guard returned early on ANY live
    value, so the removal stayed invisible forever."""
    tp, db, snaps, plan, tgt, r1 = _two_scan(tmp_path)
    assert r1["export"]["professors"][0]["fields"]["recruiting_signal"]["state"] == "value"

    tp.record("https://u.edu/p", 200, _V2)
    r2 = pipeline.run_offline(plan, tgt, tp, snaps, db_path=db)
    env = r2["export"]["professors"][0]["fields"]["recruiting_signal"]
    assert env["state"] == "searched_absent"        # not the stale value, not never_attempted

    d = delta.compute_delta(r1["export"], r2["export"])
    assert d["unchanged"] is False
    assert any(c["field"] == "recruiting_signal" and c["from_state"] == "value"
               and c["to_state"] == "searched_absent" for c in d["changed_fields"])
    # exactly one live head — the absence superseded the stale value (append-only history kept)
    heads = [c for c in claims.claims_for(open_db(db), "person", "p")
             if c["field"] == "recruiting_signal"]
    assert len(heads) == 1 and heads[0]["state"] == "searched_absent"


def test_human_assisted_value_survives_the_same_verified_absence_rescan(tmp_path):
    """Companion to the above: the guard still protects the HUMAN rung's answer (D-043) — a
    re-fetch finding nothing must never clobber a human-assisted value (test_resume.py:113's
    principle, on the successful-refetch path)."""
    tp, db, snaps, plan, tgt, r1 = _two_scan(tmp_path)
    conn = open_db(db)
    rec = claims.record_claim(
        conn, entity_kind="person", entity_id="p", field="deadline",
        value="2027-01-15", extractor_agent="human-assisted (Claude for Chrome)")
    assert rec.ok                                    # human values need no snapshot quote (D-043)
    claims.supersede_prior(conn, "person", "p", "deadline", rec.claim_id)
    conn.close()

    tp.record("https://u.edu/p", 200, _V2)
    r2 = pipeline.run_offline(plan, tgt, tp, snaps, db_path=db)
    env = r2["export"]["professors"][0]["fields"]["deadline"]
    assert env["state"] == "value" and env["value"] == "2027-01-15"   # not downgraded to absent
