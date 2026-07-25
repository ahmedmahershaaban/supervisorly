"""Database connection and idempotent migration.

SQLite is the source of truth (D-026). One file, real joins, an append-only
claim history. The schema lives in ``schema.sql`` and is applied with
``IF NOT EXISTS`` semantics so ``migrate`` can run any number of times.
The one exception is the ``web_source.source_tier`` CHECK (schema v2, D-064):
CHECKs can't be ALTERed, so a stale table is rebuilt in place, data preserved.
"""

from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone
from importlib import resources
from pathlib import Path

SCHEMA_VERSION = "2"


def new_id(prefix: str) -> str:
    """A stable internal id. Nothing is ever keyed on a display name (D-030)."""
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def utcnow() -> str:
    """ISO-8601 UTC timestamp — every claim and state change is point-in-time."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _load_schema() -> str:
    return resources.files("supervisorly.model").joinpath("schema.sql").read_text(
        encoding="utf-8"
    )


def connect(path: str | Path = ":memory:") -> sqlite3.Connection:
    """Open a connection with foreign keys on and dict-like rows."""
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _web_source_check_is_stale(conn: sqlite3.Connection) -> bool:
    """True if an existing web_source table predates the 'agent_browser' tier (D-064).

    CHECK constraints can't be ALTERed, and CREATE TABLE IF NOT EXISTS leaves the old
    constraint in place — a v1 DB would reject 'agent_browser' inserts. Detectable from
    the stored DDL."""
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='web_source'"
    ).fetchone()
    return row is not None and "'agent_browser'" not in row["sql"]


def _rebuild_web_source(conn: sqlite3.Connection) -> None:
    """Standard SQLite table rebuild: rename aside, recreate from schema.sql (new CHECK),
    copy rows back, drop the old table. legacy_alter_table keeps the rename from
    rewriting claim.source_id's FK to point at the about-to-be-dropped table."""
    # the index follows the rename and would still exist (on the old table), making
    # CREATE INDEX IF NOT EXISTS a silent no-op for the new table — drop it first.
    conn.execute("DROP INDEX IF EXISTS idx_web_source_hash")
    conn.execute("PRAGMA legacy_alter_table=ON")
    conn.execute("ALTER TABLE web_source RENAME TO web_source_old")
    conn.execute("PRAGMA legacy_alter_table=OFF")
    conn.executescript(_load_schema())          # recreates web_source with the new CHECK
    conn.execute("INSERT INTO web_source SELECT * FROM web_source_old")
    conn.execute("DROP TABLE web_source_old")


def migrate(conn: sqlite3.Connection) -> None:
    """Apply the schema. Idempotent — safe to call on every startup."""
    if _web_source_check_is_stale(conn):
        _rebuild_web_source(conn)
    conn.executescript(_load_schema())
    conn.execute(
        "INSERT INTO meta(key, value) VALUES('schema_version', ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (SCHEMA_VERSION,),
    )
    conn.commit()


def open_db(path: str | Path = ":memory:") -> sqlite3.Connection:
    """Connect and migrate in one step."""
    conn = connect(path)
    migrate(conn)
    return conn
