"""Phase A DoD: the DB migrates and the Run/Task state machine round-trips —
including the awaiting_human_input pause (D-043) and the finalized_with_open_gaps
terminal state (D-049) — and resumability works via incomplete-task queries.
"""

import pytest

from supervisorly.model import runs
from supervisorly.model.db import SCHEMA_VERSION, migrate, open_db


def test_migrate_is_idempotent():
    conn = open_db()  # connect + migrate
    migrate(conn)     # second time must not error
    tables = {
        r["name"]
        for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    # every core table the later phases build on
    for t in ("run", "task", "checkpoint", "extraction_cache", "claim",
              "web_source", "conflict", "search_plan", "person", "unit", "institution"):
        assert t in tables, f"missing table {t}"
    # the recorded version tracks the current schema (v2 added the 'agent_browser'
    # web_source tier, D-064) — pinned to the constant, not a literal
    assert conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()[0] \
        == SCHEMA_VERSION


def test_run_lifecycle_including_terminal_states():
    conn = open_db()
    run_id = runs.create_run(conn, budget_tokens=100_000)
    assert runs.get_run(conn, run_id)["status"] == "planning"

    # normal progression
    for status in ("enumerating", "signalling", "deep_diving", "gap_filling"):
        runs.set_run_status(conn, run_id, status)
        assert runs.get_run(conn, run_id)["status"] == status
        assert runs.get_run(conn, run_id)["finalized_at"] is None

    # the human-in-the-loop pause (D-043) — not terminal
    runs.set_run_status(conn, run_id, "awaiting_human_input")
    assert runs.get_run(conn, run_id)["finalized_at"] is None

    # the common real terminal: student never returned the MD (D-049)
    runs.set_run_status(conn, run_id, "finalized_with_open_gaps")
    row = runs.get_run(conn, run_id)
    assert row["status"] == "finalized_with_open_gaps"
    assert row["finalized_at"] is not None  # a terminal state stamps finalized_at


def test_invalid_status_is_rejected():
    conn = open_db()
    run_id = runs.create_run(conn)
    with pytest.raises(runs.StateError):
        runs.set_run_status(conn, run_id, "definitely_not_a_status")
    with pytest.raises(runs.StateError):
        runs.add_task(conn, run_id, "person", "p1", stage="nonsense")


def test_resume_via_incomplete_tasks():
    conn = open_db()
    run_id = runs.create_run(conn)
    t_done = runs.add_task(conn, run_id, "person", "p1", stage="deep_dive")
    t_pending = runs.add_task(conn, run_id, "person", "p2", stage="deep_dive")
    t_await = runs.add_task(conn, run_id, "person", "p3", stage="gap_fill")

    runs.set_task_status(conn, t_done, "done")
    runs.set_task_status(conn, t_await, "awaiting_human", phase="human")

    # a resumed run picks up exactly the not-finished work
    incomplete = {t["task_id"] for t in runs.incomplete_tasks(conn, run_id)}
    assert incomplete == {t_pending, t_await}
    assert t_done not in incomplete

    # the awaiting task carries its human phase and a bumped attempt count
    runs.set_task_status(conn, t_pending, "blocked", last_error="404", bump_attempt=True)
    blocked = next(t for t in runs.tasks_for_run(conn, run_id) if t["task_id"] == t_pending)
    assert blocked["status"] == "blocked"
    assert blocked["attempts"] == 1
    assert blocked["last_error"] == "404"


def test_checkpoint_roundtrip():
    conn = open_db()
    run_id = runs.create_run(conn)
    runs.save_checkpoint(conn, run_id, stage="enumerate", cursor="inst_idx=3")
    runs.save_checkpoint(conn, run_id, stage="signal", cursor="page=2")
    latest = runs.latest_checkpoint(conn, run_id)
    assert latest["stage"] == "signal" and latest["cursor"] == "page=2"


def test_counts_merge():
    conn = open_db()
    run_id = runs.create_run(conn)
    runs.update_counts(conn, run_id, enumerated=400)
    runs.update_counts(conn, run_id, shortlisted=40, gaps_open=12)
    import json
    counts = json.loads(runs.get_run(conn, run_id)["counts_json"])
    assert counts == {"enumerated": 400, "shortlisted": 40, "gaps_open": 12}


def test_extraction_cache_unique_key():
    """The 4-tuple (snapshot_hash, prompt_version, model_id, schema_version) is unique
    — the dominant cost lever (cost §3b-i)."""
    conn = open_db()
    key = ("hashA", "p1", "claude-opus-4-8", "s1")
    conn.execute(
        "INSERT INTO extraction_cache(cache_id, snapshot_content_hash, prompt_version, "
        "model_id, schema_version, created_at) VALUES('c1',?,?,?,?, '2026-01-01')", key
    )
    import sqlite3
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO extraction_cache(cache_id, snapshot_content_hash, prompt_version, "
            "model_id, schema_version, created_at) VALUES('c2',?,?,?,?, '2026-01-02')", key
        )
