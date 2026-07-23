"""Run / Task / Checkpoint state machine (D-029, D-049).

Resumability comes from ``SELECT`` on persisted state, never from an agent
remembering where it was. Every prior session in the corpus died at context
exhaustion mid-run; this is the fix.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any, Iterable

from .db import new_id, utcnow

# ── valid states (mirror the CHECK constraints in schema.sql) ─────────────────
RUN_STATUSES = {
    "planning", "enumerating", "signalling", "deep_diving", "gap_filling",
    "awaiting_human_input", "scoring", "finalized", "finalized_with_open_gaps",
    "failed",
}
# A run is over exactly when it reaches one of these (D-049).
TERMINAL_RUN_STATUSES = {"finalized", "finalized_with_open_gaps", "failed"}

TASK_STAGES = {"enumerate", "signal", "deep_dive", "gap_fill", "roster_enumerate"}
TASK_PHASES = {"structured", "browse", "human"}
TASK_STATUSES = {"pending", "running", "done", "blocked", "awaiting_human", "abandoned"}
# Work that a resumed run must still pick up.
INCOMPLETE_TASK_STATUSES = {"pending", "running", "blocked", "awaiting_human"}


class StateError(ValueError):
    """Raised on an invalid status/stage/phase — a guard, not a silent write."""


# ── Run ───────────────────────────────────────────────────────────────────────
def create_run(
    conn: sqlite3.Connection,
    plan_id: str | None = None,
    budget_tokens: int | None = None,
) -> str:
    run_id = new_id("run")
    now = utcnow()
    conn.execute(
        "INSERT INTO run(run_id, plan_id, status, budget_tokens, started_at, updated_at) "
        "VALUES(?,?,?,?,?,?)",
        (run_id, plan_id, "planning", budget_tokens, now, now),
    )
    conn.commit()
    return run_id


def set_run_status(conn: sqlite3.Connection, run_id: str, status: str) -> None:
    if status not in RUN_STATUSES:
        raise StateError(f"unknown run status: {status!r}")
    now = utcnow()
    finalized = now if status in TERMINAL_RUN_STATUSES else None
    conn.execute(
        "UPDATE run SET status=?, updated_at=?, "
        "finalized_at=COALESCE(?, finalized_at) WHERE run_id=?",
        (status, now, finalized, run_id),
    )
    conn.commit()


def update_counts(conn: sqlite3.Connection, run_id: str, **counts: int) -> None:
    """Merge into the run's counts_json (enumerated/shortlisted/deep_dived/gaps_open)."""
    row = conn.execute("SELECT counts_json FROM run WHERE run_id=?", (run_id,)).fetchone()
    if row is None:
        raise StateError(f"no such run: {run_id}")
    current = json.loads(row["counts_json"])
    current.update(counts)
    conn.execute(
        "UPDATE run SET counts_json=?, updated_at=? WHERE run_id=?",
        (json.dumps(current), utcnow(), run_id),
    )
    conn.commit()


def get_run(conn: sqlite3.Connection, run_id: str) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM run WHERE run_id=?", (run_id,)).fetchone()
    return dict(row) if row else None


# ── Task ──────────────────────────────────────────────────────────────────────
def add_task(
    conn: sqlite3.Connection,
    run_id: str,
    target_kind: str,
    target_ref: str,
    stage: str,
    phase: str = "structured",
) -> str:
    if stage not in TASK_STAGES:
        raise StateError(f"unknown task stage: {stage!r}")
    if phase not in TASK_PHASES:
        raise StateError(f"unknown task phase: {phase!r}")
    task_id = new_id("task")
    conn.execute(
        "INSERT INTO task(task_id, run_id, target_kind, target_ref, stage, phase, "
        "status, updated_at) VALUES(?,?,?,?,?,?,?,?)",
        (task_id, run_id, target_kind, target_ref, stage, phase, "pending", utcnow()),
    )
    conn.commit()
    return task_id


def set_task_status(
    conn: sqlite3.Connection,
    task_id: str,
    status: str,
    phase: str | None = None,
    last_error: str | None = None,
    bump_attempt: bool = False,
) -> None:
    if status not in TASK_STATUSES:
        raise StateError(f"unknown task status: {status!r}")
    if phase is not None and phase not in TASK_PHASES:
        raise StateError(f"unknown task phase: {phase!r}")
    conn.execute(
        "UPDATE task SET status=?, "
        "phase=COALESCE(?, phase), "
        "last_error=?, "
        "attempts=attempts + ?, "
        "updated_at=? WHERE task_id=?",
        (status, phase, last_error, 1 if bump_attempt else 0, utcnow(), task_id),
    )
    conn.commit()


def incomplete_tasks(conn: sqlite3.Connection, run_id: str) -> list[dict[str, Any]]:
    """Tasks a resumed run must still do — the heart of resumability (D-029)."""
    placeholders = ",".join("?" * len(INCOMPLETE_TASK_STATUSES))
    rows = conn.execute(
        f"SELECT * FROM task WHERE run_id=? AND status IN ({placeholders}) "
        "ORDER BY updated_at",
        (run_id, *sorted(INCOMPLETE_TASK_STATUSES)),
    ).fetchall()
    return [dict(r) for r in rows]


def tasks_for_run(conn: sqlite3.Connection, run_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM task WHERE run_id=? ORDER BY updated_at", (run_id,)
    ).fetchall()
    return [dict(r) for r in rows]


# ── Checkpoint ────────────────────────────────────────────────────────────────
def save_checkpoint(
    conn: sqlite3.Connection, run_id: str, stage: str, cursor: str | None = None
) -> str:
    cid = new_id("ckpt")
    conn.execute(
        "INSERT INTO checkpoint(checkpoint_id, run_id, stage, cursor, created_at) "
        "VALUES(?,?,?,?,?)",
        (cid, run_id, stage, cursor, utcnow()),
    )
    conn.commit()
    return cid


def latest_checkpoint(conn: sqlite3.Connection, run_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM checkpoint WHERE run_id=? ORDER BY created_at DESC, rowid DESC "
        "LIMIT 1",
        (run_id,),
    ).fetchone()
    return dict(row) if row else None
