"""The ExtractionCache (cost §3b-i) — the dominant cost lever.

If the *normalised* page content and the extraction parameters are unchanged, the
extraction is **not re-run**: a monthly re-scan of a professor whose page didn't
meaningfully change issues ~zero LLM calls and creates no duplicate claims. The key is the
4-tuple (content hash, prompt version, model id, schema version) — a genuine content change
changes the hash and forces a fresh extraction; volatile chrome (a "last updated" line, a
hit counter) is masked out of the hash so it does *not* (see ``fetch.normalize``).
"""

from __future__ import annotations

import json
import sqlite3

from .db import new_id, utcnow


def lookup(conn: sqlite3.Connection, entity_kind: str, entity_id: str, content_hash: str,
           prompt_version: str, model_id: str, schema_version: str) -> dict | None:
    """Return the cached extraction row for this (entity + content + params) key, or None.

    A hit means "this content was already extracted **for this entity**" — not merely that
    the bytes were seen for someone else (see the table comment / audit finding 7).
    """
    row = conn.execute(
        "SELECT * FROM extraction_cache WHERE entity_kind=? AND entity_id=? AND "
        "snapshot_content_hash=? AND prompt_version=? AND model_id=? AND schema_version=?",
        (entity_kind, entity_id, content_hash, prompt_version, model_id, schema_version),
    ).fetchone()
    return dict(row) if row else None


def record(conn: sqlite3.Connection, entity_kind: str, entity_id: str, content_hash: str,
           prompt_version: str, model_id: str, schema_version: str,
           claim_ids: list[str]) -> str:
    """Record that this extraction ran for this entity, pointing at the claims it produced.

    ``INSERT OR IGNORE`` so a concurrent/duplicate write can't violate the UNIQUE key.
    """
    cache_id = new_id("xcache")
    conn.execute(
        "INSERT OR IGNORE INTO extraction_cache(cache_id, entity_kind, entity_id, "
        "snapshot_content_hash, prompt_version, model_id, schema_version, result_refs_json, "
        "created_at) VALUES(?,?,?,?,?,?,?,?,?)",
        (cache_id, entity_kind, entity_id, content_hash, prompt_version, model_id,
         schema_version, json.dumps(claim_ids), utcnow()),
    )
    conn.commit()
    return cache_id
