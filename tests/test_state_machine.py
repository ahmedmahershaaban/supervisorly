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
    # web_source tier, D-064; v3 added the 'cancelled' run status) — pinned to the
    # constant, not a literal
    assert conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()[0] \
        == SCHEMA_VERSION


def test_cancelled_run_status_round_trips():
    # schema v3: the cooperative-stop terminal state is accepted by the CHECK and the
    # state machine, and stamps finalized_at like every terminal state (D-049)
    conn = open_db()
    run_id = runs.create_run(conn)
    runs.set_run_status(conn, run_id, "deep_diving")
    runs.set_run_status(conn, run_id, "cancelled")
    row = runs.get_run(conn, run_id)
    assert row["status"] == "cancelled"
    assert row["finalized_at"] is not None


# the run table's CHECK as of schema v2 — no 'cancelled'
_V2_RUN_DDL = """
CREATE TABLE run (
  run_id        TEXT PRIMARY KEY,
  plan_id       TEXT REFERENCES search_plan(plan_id),
  status        TEXT NOT NULL
    CHECK (status IN (
      'planning','enumerating','signalling','deep_diving','gap_filling',
      'awaiting_human_input','scoring','finalized','finalized_with_open_gaps','failed'
    )),
  budget_tokens INTEGER,
  budget_spent  INTEGER NOT NULL DEFAULT 0,
  counts_json   TEXT NOT NULL DEFAULT '{}',
  started_at    TEXT NOT NULL,
  updated_at    TEXT NOT NULL,
  finalized_at  TEXT
)
"""


def test_open_db_migrates_a_pre_cancelled_schema_db(tmp_path):
    # old DBs are unaffected on their data: the stale run CHECK is widened by an
    # in-place rebuild (the schema v2 web_source pattern), rows preserved
    import sqlite3
    path = tmp_path / "old.sqlite"
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    # no FK pragma here: the old fixture only needs the stale run table itself (its DDL
    # references search_plan, which this bare fixture doesn't create); open_db's own
    # connect re-enables enforcement for the migrated DB below
    conn.execute(_V2_RUN_DDL)
    conn.execute(
        "INSERT INTO run(run_id, status, counts_json, started_at, updated_at, finalized_at) "
        "VALUES('run_old1', 'finalized', '{}', '2026-01-01', '2026-01-01', '2026-01-01')")
    conn.commit()
    conn.close()

    conn = open_db(path)          # migrate: clean, no exception
    row = conn.execute("SELECT * FROM run WHERE run_id='run_old1'").fetchone()
    assert row is not None and row["status"] == "finalized"      # data preserved
    assert conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()[0] \
        == SCHEMA_VERSION
    # the widened CHECK accepts 'cancelled'; FK references to run still work
    runs.set_run_status(conn, "run_old1", "cancelled")
    task_id = runs.add_task(conn, "run_old1", "person", "p1", stage="deep_dive")
    assert runs.tasks_for_run(conn, "run_old1")[0]["task_id"] == task_id
    conn.close()
    open_db(path).close()         # re-open is idempotent — no rebuild loop


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


def test_a_task_carries_its_phase_and_its_failure():
    """What survives the checkpoint API's removal (round AM): task state IS the resume
    record. `runs.target_stage_done` reads it, and it is the only mechanism resume uses."""
    conn = open_db()
    run_id = runs.create_run(conn)
    t_done = runs.add_task(conn, run_id, "person", "p1", stage="deep_dive")
    t_pending = runs.add_task(conn, run_id, "person", "p2", stage="deep_dive")
    t_await = runs.add_task(conn, run_id, "person", "p3", stage="gap_fill")

    runs.set_task_status(conn, t_done, "done")
    runs.set_task_status(conn, t_await, "awaiting_human", phase="human")

    by_id = {t["task_id"]: t for t in runs.tasks_for_run(conn, run_id)}
    assert by_id[t_done]["status"] == "done"
    assert by_id[t_await]["status"] == "awaiting_human" and by_id[t_await]["phase"] == "human"

    # the pending task carries its failure and a bumped attempt count
    runs.set_task_status(conn, t_pending, "blocked", last_error="404", bump_attempt=True)
    blocked = next(t for t in runs.tasks_for_run(conn, run_id) if t["task_id"] == t_pending)
    assert blocked["status"] == "blocked"
    assert blocked["attempts"] == 1
    assert blocked["last_error"] == "404"


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
