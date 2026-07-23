"""Unit (department/faculty) helpers — including the coverage note (D-052).

A unit's ``coverage_note`` is how the pipeline records *why* a directory yielded what it
did without pretending it yielded more: ``LOGIN_WALL`` (routed to the human rung),
``NOT_FOUND`` (searched for, genuinely absent), etc. This keeps "we couldn't reach it"
distinct from "there was nothing there" (D-046/D-060).
"""

from __future__ import annotations

import sqlite3

from .db import new_id


def upsert_unit(
    conn: sqlite3.Connection,
    *,
    institution_id: str | None = None,
    name: str | None = None,
    kind: str | None = None,
    directory_url: str | None = None,
    coverage_note: str | None = None,
) -> str:
    """Insert a unit and return its id. Nothing is keyed on the display name (D-030)."""
    unit_id = new_id("unit")
    conn.execute(
        "INSERT INTO unit(unit_id, institution_id, name, kind, directory_url, coverage_note) "
        "VALUES(?,?,?,?,?,?)",
        (unit_id, institution_id, name, kind, directory_url, coverage_note),
    )
    conn.commit()
    return unit_id


def set_unit_coverage(conn: sqlite3.Connection, unit_id: str, note: str) -> None:
    conn.execute("UPDATE unit SET coverage_note=? WHERE unit_id=?", (note, unit_id))
    conn.commit()


def get_unit(conn: sqlite3.Connection, unit_id: str) -> dict | None:
    row = conn.execute("SELECT * FROM unit WHERE unit_id=?", (unit_id,)).fetchone()
    return dict(row) if row else None
