"""The opt-out suppression list, enforced at build (D-023/032/053).

Anyone can ask to be excluded. ``optout.txt`` lists opaque identifiers — a homepage URL, an
ORCID, an OpenAlex id, or an internal id — one per line (``#`` comments allowed). Before a
professor is ever fetched or exported, if **any** of their identifiers matches the list they
are dropped entirely: not scored, not shown, not stored in the output. Enforcement runs at the
start of a scan (so an opted-out person isn't even fetched) and is guarded by a failing test.

The shipped ``optout.txt`` is empty (a template) — it must never contain real personal data in
the repo; real suppression lists are supplied at deploy time.
"""

from __future__ import annotations

from pathlib import Path

# Identifier keys on a target/professor that an opt-out entry may match.
_ID_KEYS = ("id", "url", "homepage", "orcid", "openalex_id", "ror_id", "name")


def _norm(s: str) -> str:
    return s.strip().lower().rstrip("/")


def load_optout(path: str | Path | None) -> set[str]:
    """Load normalised opt-out identifiers from ``path`` (missing/None → empty set)."""
    if not path:
        return set()
    p = Path(path)
    if not p.exists():
        return set()
    out: set[str] = set()
    for line in p.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        out.add(_norm(s))
    return out


def identifiers_of(target: dict) -> set[str]:
    """The set of normalised identifiers a target exposes for opt-out matching."""
    return {_norm(str(target[k])) for k in _ID_KEYS if target.get(k)}


def is_opted_out(target: dict, optout: set[str]) -> bool:
    return bool(optout) and bool(identifiers_of(target) & optout)


def filter_targets(targets: list[dict], optout: set[str]) -> tuple[list[dict], int]:
    """Return (kept_targets, removed_count). An opted-out target is never processed."""
    if not optout:
        return list(targets), 0
    kept = [t for t in targets if not is_opted_out(t, optout)]
    return kept, len(targets) - len(kept)
