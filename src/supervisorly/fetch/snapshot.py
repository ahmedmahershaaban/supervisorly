"""Content-addressed snapshot store.

Snapshots (raw fetched HTML) live on the filesystem, keyed by the normalised
``content_hash`` — never as blobs in the DB (D-026), and never committed (D-005).
Quote verification re-opens the snapshot, not the live page, so a quote stays
checkable after the page changes.
"""

from __future__ import annotations

from pathlib import Path

from .normalize import content_hash


class SnapshotStore:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, h: str) -> Path:
        return self.root / f"{h}.html"

    def exists(self, h: str) -> bool:
        return self._path(h).exists()

    def store(self, html: str) -> str:
        """Store raw html under its content hash; return the hash. Identical content
        (ignoring volatile chrome) dedupes to the same file."""
        h = content_hash(html)
        p = self._path(h)
        if not p.exists():
            p.write_text(html, encoding="utf-8")
        return h

    def load(self, h: str) -> str:
        return self._path(h).read_text(encoding="utf-8")
