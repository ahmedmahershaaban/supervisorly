"""Database connection and idempotent migration.

SQLite is the source of truth (D-026). One file, real joins, an append-only
claim history. The schema lives in ``schema.sql`` and is applied with
``IF NOT EXISTS`` semantics so ``migrate`` can run any number of times.
The one exception is the ``web_source.source_tier`` CHECK (schema v2, D-064):
CHECKs can't be ALTERed, so a stale table is rebuilt atomically in place (one
transaction, foreign keys off during the rebuild), data preserved.
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


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def _apply_schema(conn: sqlite3.Connection) -> None:
    """schema.sql statement by statement. Unlike ``executescript`` (which issues an
    implicit COMMIT first), this is safe to run inside an open transaction."""
    # strip "--" comments first: some span text containing ';', which would
    # otherwise be mistaken for a statement boundary
    sql = "\n".join(line.split("--", 1)[0] for line in _load_schema().splitlines())
    for stmt in sql.split(";"):
        if stmt.strip():
            conn.execute(stmt)


def _rebuild_web_source(conn: sqlite3.Connection) -> None:
    """SQLite's documented table-rebuild procedure: foreign_keys OFF, then
    rename-aside / recreate / copy / drop inside ONE transaction, foreign_keys back ON.

    foreign_keys must be OFF before the rename for two reasons (legacy_alter_table
    does NOT do this — it only suppresses the rewrite for triggers/views): with FK
    enforcement on, the rename rewrites claim.source_id's FK clause to the temp name,
    and the final DROP then fails on the referencing claim rows. The whole sequence is
    one transaction so a crash can never leave the table half-rebuilt; a leftover
    ``web_source_old`` from a pre-fix crash is recovered (rows merged back, never
    orphaned) instead of being silently stranded. PRAGMA foreign_keys is a no-op
    inside a transaction, so it is toggled OUTSIDE the BEGIN/COMMIT."""
    conn.execute("PRAGMA foreign_keys=OFF")
    try:
        conn.execute("BEGIN IMMEDIATE")
        try:
            # the index follows the rename and would still exist (on the old table),
            # making CREATE INDEX IF NOT EXISTS a silent no-op — drop it first.
            conn.execute("DROP INDEX IF EXISTS idx_web_source_hash")
            if _web_source_check_is_stale(conn):
                conn.execute("ALTER TABLE web_source RENAME TO web_source_old")
            if _table_exists(conn, "web_source_old"):
                _apply_schema(conn)         # recreates web_source with the new CHECK
                # OR IGNORE: a recovered web_source may already hold post-crash rows
                conn.execute(
                    "INSERT OR IGNORE INTO web_source SELECT * FROM web_source_old")
                conn.execute("DROP TABLE web_source_old")
            dangling = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' "
                "AND sql LIKE '%web_source_old%'").fetchone()
            if dangling:
                # a crashed pre-fix rebuild rewrote other tables' stored FK clauses to
                # the temp name — repair the DDL, then bump schema_version to force a
                # re-parse (this connection caches the old schema otherwise)
                conn.execute("PRAGMA writable_schema=ON")
                conn.execute(
                    "UPDATE sqlite_master "
                    "SET sql=replace(sql, 'web_source_old', 'web_source') "
                    "WHERE type='table' AND sql LIKE '%web_source_old%'")
                conn.execute("PRAGMA writable_schema=OFF")
                v = conn.execute("PRAGMA schema_version").fetchone()[0]
                conn.execute(f"PRAGMA schema_version={v + 1}")
            conn.commit()
        except Exception:
            conn.rollback()                 # nothing half-applies; retry is safe
            raise
    finally:
        conn.execute("PRAGMA foreign_keys=ON")


def migrate(conn: sqlite3.Connection) -> None:
    """Apply the schema. Idempotent — safe to call on every startup. A leftover
    ``web_source_old`` means an earlier rebuild crashed mid-way; it is recovered
    (completed and its rows merged back) rather than skipped."""
    if _web_source_check_is_stale(conn) or _table_exists(conn, "web_source_old"):
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
