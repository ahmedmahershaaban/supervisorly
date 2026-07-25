"""The browser ingest seam (D-064) — where agent-driven Chrome pages enter the engine.

The agent drives Chrome via chrome-devtools-mcp; in-page JS (``extract/page_extract.js``)
produces cleaned, capped main text; this module stores that TEXT as a normal
content-addressed snapshot and records its provenance. The Python layer stays LLM-free
(D-009) and never sees raw HTML/DOM — a browser page is just another snapshot, so the
existing extractors and the D-010 quote gate run unchanged.

The text is wrapped in a minimal HTML shell before storage so the snapshot is
byte-compatible with the fetcher's format and ``normalize.main_text`` round-trips it
faithfully (an escaped ``<`` in the text can never be misparsed as a tag).

Provenance honesty: the source is recorded under the FINAL url with tier
``agent_browser`` and ``robots_allowed=None`` — the browser tier is the human-session
tier; robots was never consulted (same convention as ``human_assisted`` in ingest.py).
"""

from __future__ import annotations

import sqlite3
from html import escape
from pathlib import Path

from ..model import claims
from .snapshot import SnapshotStore

SOURCE_TIER = "agent_browser"


def _wrap_as_snapshot(text: str, title: str | None) -> str:
    """Minimal HTML shell around the extracted text, entity-escaped, so the stored
    snapshot feeds ``normalize.main_text`` / the D-010 quote gate exactly like a
    fetcher-produced snapshot does."""
    head = f"<title>{escape(title)}</title>" if title else ""
    return f"<html><head>{head}</head><body><main>{escape(text)}</main></body></html>"


def ingest_page(
    conn: sqlite3.Connection,
    snap_root: str | Path,
    *,
    final_url: str,
    text: str,
    title: str | None = None,
) -> dict:
    """Store browser-extracted main text as a snapshot and record its web source.

    Returns ``{"snapshot_hash", "source_id", "bytes", "final_url"}``.
    Raises ``ValueError`` on a blank url or empty/whitespace-only text — there is
    nothing verifiable to store (the CLI turns this into exit 2).
    """
    if not final_url or not final_url.strip():
        raise ValueError("final_url is required (provenance cites the FINAL url)")
    if not text or not text.strip():
        raise ValueError("empty page text — nothing to ingest")

    snaps = SnapshotStore(snap_root)
    snapshot_hash = snaps.store(_wrap_as_snapshot(text, title))
    source_id = claims.record_web_source(
        conn, final_url, snapshot_hash=snapshot_hash,
        source_tier=SOURCE_TIER, robots_allowed=None,   # robots not consulted (honesty)
    )
    return {
        "snapshot_hash": snapshot_hash,
        "source_id": source_id,
        "bytes": len(text.encode("utf-8")),
        "final_url": final_url,
    }
