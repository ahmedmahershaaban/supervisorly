"""Wave D / B6-audit D1+D2: the consumer half of the D-064 browser seam.

An agent-read browser page (``ingest-page --entity ... --run ...``) now fills the
entity's signal fields through the pipeline's own extractors and evidence path, closes
its ``awaiting_human`` gap-fill tasks, and flips the run to ``finalized`` when no open
gaps remain (D-049) — the walled-social gap can finally close outside the classic
MD-grammar rung. No network — cassette scan + synthetic page text only.
"""

import sqlite3
from pathlib import Path

from supervisorly import pipeline
from supervisorly.cli import main
from supervisorly.fetch.browser_fill import fill_from_browser_page
from supervisorly.fetch.normalize import quote_in_snapshot
from supervisorly.fetch.snapshot import SnapshotStore
from supervisorly.fetch.transport import CassetteTransport
from supervisorly.model import claims, runs
from supervisorly.model.db import open_db

# A reachable homepage that advertises a walled X profile: fields are searched_absent,
# the social link is recorded, and an awaiting_human gap_fill task is minted (Phase L3).
HOME = ("<html><body><main><h1>Dr. W</h1>"
        "<p>My research is on graph theory.</p>"
        "<p>Follow me on X: https://x.com/drw for lab updates.</p>"
        "</main></body></html>")
WALLED_URL = "https://x.com/drw"
RECRUITING_TEXT = "Dr. W's profile. I am recruiting PhD students for 2026. DM me."
NO_SIGNAL_TEXT = "Dr. W's profile. Thoughts on graph theory and coffee."


def _walled_run(tmp_path):
    """A one-professor run with a walled-social awaiting_human gap; returns (db, run_id)."""
    tp = CassetteTransport()
    tp.record("https://u.edu/robots.txt", 200, "User-agent: *\nAllow: /\n")
    tp.record("https://u.edu/p", 200, HOME)
    db = tmp_path / "output" / "supervisorly.sqlite"
    db.parent.mkdir(parents=True)
    r = pipeline.run_offline({"intent_kind": "pre_phd", "resolved_topic_ids": ["T"]},
                             [{"id": "p", "name": "Dr. W", "url": "https://u.edu/p"}],
                             tp, db.parent / ".cache" / "snaps", db_path=db)
    assert r["export"]["run"]["status"] == "finalized_with_open_gaps"
    assert r["export"]["professors"][0]["fields"]["recruiting_signal"]["state"] == \
        "searched_absent"
    return db, r["run_id"]


def _staging(tmp_path, text):
    f = tmp_path / "browser_staging" / "page.txt"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(text, encoding="utf-8")
    return f


def _gap_tasks(db, run_id):
    conn = open_db(db)
    ts = [t for t in runs.tasks_for_run(conn, run_id) if t["stage"] == "gap_fill"]
    conn.close()
    return ts


# ── the end-to-end close: walled gap -> value claim -> task done -> run finalized ──
def test_ingest_page_fill_closes_a_walled_social_gap(tmp_path, capsys):
    db, run_id = _walled_run(tmp_path)
    f = _staging(tmp_path, RECRUITING_TEXT)
    rc = main(["ingest-page", "--url", WALLED_URL, "--file", str(f),
               "--db", str(db), "--entity", "professor:p", "--run", run_id])
    assert rc == 0
    out = capsys.readouterr().out
    out.encode("ascii")                                # console contract: ASCII-safe
    assert "filled recruiting_signal=value" in out
    assert "deadline=searched_absent" in out
    assert "1 gap(s) closed" in out and "run finalized" in out

    conn = open_db(db)
    # recruiting_signal is now a VALUE claim whose quote verifies against the browser
    # snapshot (D-010 intact), sourced from the walled page under tier agent_browser
    head = next(c for c in claims.claims_for(conn, "person", "p")
                if c["field"] == "recruiting_signal")
    assert head["state"] == "value" and "recruiting" in head["value"]
    assert head["source_url"] == WALLED_URL
    stored = SnapshotStore(db.parent / ".cache" / "snaps").load(head["snapshot_hash"])
    assert quote_in_snapshot(head["quote"], stored)
    tier = conn.execute("SELECT source_tier FROM web_source WHERE source_id=?",
                        (head["source_id"],)).fetchone()["source_tier"]
    assert tier == "agent_browser"
    # the advertised social link display value survives the fill
    social = next(c for c in claims.claims_for(conn, "person", "p")
                  if c["field"] == "social")
    assert social["state"] == "value" and social["value"] == WALLED_URL
    # the gap task closed and the run flipped to finalized
    assert runs.get_run(conn, run_id)["status"] == "finalized"
    conn.close()
    task = _gap_tasks(db, run_id)[0]
    assert task["status"] == "done" and "ingest-page" in (task["last_error"] or "")

    # a re-export shows the value and agrees on finalized (D-049 consistency)
    re = pipeline.reexport(db, [{"id": "p", "name": "Dr. W"}])
    assert re["export"]["run"]["status"] == "finalized"
    env = re["export"]["professors"][0]["fields"]["recruiting_signal"]
    assert env["state"] == "value" and "recruiting" in env["value"]


def test_reexport_cli_regenerates_the_dashboard_after_a_fill(tmp_path, capsys):
    db, run_id = _walled_run(tmp_path)
    f = _staging(tmp_path, RECRUITING_TEXT)
    main(["ingest-page", "--url", WALLED_URL, "--file", str(f),
          "--db", str(db), "--entity", "professor:p", "--run", run_id])
    capsys.readouterr()
    out_html = tmp_path / "output" / "dashboard.html"
    rc = main(["reexport", "--db", str(db), "--out", str(out_html)])
    assert rc == 0
    html = out_html.read_text(encoding="utf-8")
    assert "recruiting PhD students for 2026" in html
    assert out_html.with_suffix(".json").is_file()


def test_reexport_cli_missing_db_exits_2(tmp_path, capsys):
    rc = main(["reexport", "--db", str(tmp_path / "nope.sqlite"),
               "--out", str(tmp_path / "d.html")])
    assert rc == 2
    assert "database not found" in capsys.readouterr().out


# ── honest absence + the human-assisted protection ──────────────────────────────
def test_fill_records_searched_absent_when_the_page_lacks_signal(tmp_path):
    db, run_id = _walled_run(tmp_path)
    conn = open_db(db)
    res = fill_from_browser_page(conn, db.parent / ".cache" / "snaps", run_id=run_id,
                                 entity_kind="person", entity_id="p",
                                 final_url=WALLED_URL, text=NO_SIGNAL_TEXT)
    assert res["fields"] == {"recruiting_signal": "searched_absent",
                             "deadline": "searched_absent",
                             "students_signal": "searched_absent",
                             "industry_signal": "searched_absent"}
    # the read happened, so the gap still closes honestly (checked, found nothing)
    assert res["tasks_closed"] == 1 and res["run_status"] == "finalized"
    conn.close()


def test_fill_never_clobbers_a_human_assisted_value(tmp_path):
    db, run_id = _walled_run(tmp_path)
    conn = open_db(db)
    # the human rung already answered recruiting from the walled page (D-043)
    src = claims.record_web_source(conn, WALLED_URL, source_tier="human_assisted",
                                   robots_allowed=None)
    rec = claims.record_claim(
        conn, entity_kind="person", entity_id="p", field="recruiting_signal",
        value="Recruiting via the human rung.", quote="I am recruiting.",
        source_id=src, observed_at="2026-07-25",
        extractor_agent="human-assisted (Claude for Chrome)")
    assert rec.ok
    claims.supersede_prior(conn, "person", "p", "recruiting_signal", rec.claim_id)

    res = fill_from_browser_page(conn, db.parent / ".cache" / "snaps", run_id=run_id,
                                 entity_kind="person", entity_id="p",
                                 final_url=WALLED_URL, text=NO_SIGNAL_TEXT)
    assert res["fields"]["recruiting_signal"] == "kept_human"
    head = next(c for c in claims.claims_for(conn, "person", "p")
                if c["field"] == "recruiting_signal")
    assert head["state"] == "value" and "human rung" in head["value"]
    assert head["extractor_agent"].startswith("human-assisted")
    conn.close()


# ── D-010: a quote that is not in the browser text is rejected; nothing closes ──
def test_rejected_quote_leaves_field_unfilled_gap_open_and_status_unchanged(
        tmp_path, monkeypatch):
    db, run_id = _walled_run(tmp_path)
    # force a hallucinated extractor result (quote not in the snapshot) — the gate must
    # refuse it and the fill must fail loud rather than close the gap
    monkeypatch.setitem(
        pipeline._EXTRACTORS, "recruiting_signal",
        lambda html: ("recruiting", "fully funded positions for everyone", "inferred"))
    conn = open_db(db)
    res = fill_from_browser_page(conn, db.parent / ".cache" / "snaps", run_id=run_id,
                                 entity_kind="person", entity_id="p",
                                 final_url=WALLED_URL, text=NO_SIGNAL_TEXT)
    assert res["fields"]["recruiting_signal"] == "rejected"
    assert "D-010" in res["rejected"]["recruiting_signal"]
    assert res["tasks_closed"] == 0
    assert res["run_status"] == "finalized_with_open_gaps"
    head = next(c for c in claims.claims_for(conn, "person", "p")
                if c["field"] == "recruiting_signal")
    assert head["state"] == "searched_absent"          # the scan's honest head survives
    conn.close()
    assert _gap_tasks(db, run_id)[0]["status"] == "awaiting_human"


def test_fill_unknown_run_or_non_person_kind_is_a_value_error(tmp_path):
    db, run_id = _walled_run(tmp_path)
    conn = open_db(db)
    import pytest
    with pytest.raises(ValueError, match="no such run"):
        fill_from_browser_page(conn, tmp_path / "snaps", run_id="run_nope",
                               entity_kind="person", entity_id="p",
                               final_url=WALLED_URL, text=RECRUITING_TEXT)
    with pytest.raises(ValueError, match="entity kind"):
        fill_from_browser_page(conn, tmp_path / "snaps", run_id=run_id,
                               entity_kind="university", entity_id="p",
                               final_url=WALLED_URL, text=RECRUITING_TEXT)
    conn.close()


# ── CLI validation: bad fill invocations are a loud exit 2 (D-002) ───────────────
def test_cli_entity_without_run_exits_2(tmp_path, capsys):
    db, _run_id = _walled_run(tmp_path)
    f = _staging(tmp_path, RECRUITING_TEXT)
    rc = main(["ingest-page", "--url", WALLED_URL, "--file", str(f),
               "--db", str(db), "--entity", "professor:p"])
    assert rc == 2
    assert "--entity and --run must be given together" in capsys.readouterr().out


def test_cli_bad_entity_format_exits_2(tmp_path, capsys):
    db, run_id = _walled_run(tmp_path)
    f = _staging(tmp_path, RECRUITING_TEXT)
    rc = main(["ingest-page", "--url", WALLED_URL, "--file", str(f),
               "--db", str(db), "--entity", "professorp", "--run", run_id])
    assert rc == 2
    assert "invalid --entity" in capsys.readouterr().out


def test_cli_unknown_entity_kind_exits_2(tmp_path, capsys):
    db, run_id = _walled_run(tmp_path)
    f = _staging(tmp_path, RECRUITING_TEXT)
    rc = main(["ingest-page", "--url", WALLED_URL, "--file", str(f),
               "--db", str(db), "--entity", "company:acme", "--run", run_id])
    assert rc == 2
    assert "kind must be" in capsys.readouterr().out


def test_cli_unknown_run_exits_2(tmp_path, capsys):
    db, _run_id = _walled_run(tmp_path)
    f = _staging(tmp_path, RECRUITING_TEXT)
    rc = main(["ingest-page", "--url", WALLED_URL, "--file", str(f),
               "--db", str(db), "--entity", "professor:p", "--run", "run_nope"])
    assert rc == 2
    assert "unknown --run" in capsys.readouterr().out


def test_cli_unknown_entity_exits_2(tmp_path, capsys):
    db, run_id = _walled_run(tmp_path)
    f = _staging(tmp_path, RECRUITING_TEXT)
    rc = main(["ingest-page", "--url", WALLED_URL, "--file", str(f),
               "--db", str(db), "--entity", "professor:nobody", "--run", run_id])
    assert rc == 2
    assert "unknown --entity" in capsys.readouterr().out


# ── store-only mode is unchanged, and D2: the default db moved to output/ ───────
def test_cli_store_only_mode_without_entity_is_unchanged(tmp_path, capsys):
    f = _staging(tmp_path, RECRUITING_TEXT)
    db = tmp_path / "r.sqlite"
    rc = main(["ingest-page", "--url", WALLED_URL, "--file", str(f), "--db", str(db)])
    assert rc == 0
    out = capsys.readouterr().out
    assert out.startswith("ingested ") and "filled" not in out
    conn = sqlite3.connect(db)
    assert conn.execute("SELECT COUNT(*) FROM claim").fetchone()[0] == 0
    conn.close()


def test_cli_ingest_page_default_db_is_output_supervisorly_sqlite(tmp_path, monkeypatch,
                                                                  capsys):
    """B6-audit D2: the old default (./supervisorly.sqlite) put ingested pages in a store
    the documented scan (--out output/...) never reads. The default now matches it.
    (No prior test pinned the old default; this new test pins the new one.)"""
    monkeypatch.chdir(tmp_path)
    f = _staging(tmp_path, RECRUITING_TEXT)
    rc = main(["ingest-page", "--url", WALLED_URL, "--file", str(f)])
    assert rc == 0
    assert (tmp_path / "output" / "supervisorly.sqlite").is_file()
    assert (tmp_path / "output" / ".cache" / "snaps").is_dir()
    assert not (tmp_path / "supervisorly.sqlite").exists()
