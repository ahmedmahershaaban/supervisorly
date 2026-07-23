"""Database connection and idempotent migration.

SQLite is the source of truth (D-026). One file, real joins, an append-only
claim history. The schema lives in ``schema.sql`` and is applied with
``IF NOT EXISTS`` semantics so ``migrate`` can run any number of times.
"""

from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone
from importlib import resources
from pathlib import Path

SCHEMA_VERSION = "1"


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


def migrate(conn: sqlite3.Connection) -> None:
    """Apply the schema. Idempotent — safe to call on every startup."""
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
