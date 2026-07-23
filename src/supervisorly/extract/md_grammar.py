"""The one shared Phase-3 Markdown grammar (D-051).

This module is the **single source of truth** for the format the student returns
from Claude for Chrome. The ``chrome-prompt-generator`` embeds ``emit()``'s output
as its output contract; the ``md-ingester`` calls ``parse()``. Because both sides
call this one module, they can never drift.

Grammar (deliberately simple so Claude-for-Chrome produces it reliably and the
parser is deterministic — no YAML dependency):

    # Supervisorly — human retrieval
    target: person=<id>  name=<display name>
    retrieved_at: <ISO date>

    ## field: <field_name>
    value: <the value>                # omit when state is not 'value'
    quote: <verbatim supporting text>
    source_url: <url>
    observed_at: <ISO date>
    confidence: quoted_official        # optional
    note: <free text>                  # optional; used with searched_absent

Each ``## field:`` block becomes one Claim. A block with ``state: searched_absent``
records an honest "we looked, found nothing" (D-046) instead of a value.

Human-returned data is **not privileged** — every entry becomes a normal Claim with
``extractor = 'human-assisted (Claude for Chrome)'`` and full provenance (D-043).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field as dc_field

VALID_STATES = {"value", "searched_absent", "never_attempted", "blocked"}
VALID_CONFIDENCE = {"quoted_official", "derived", "inferred", "unconfirmed", "action_needed"}
VALID_TARGET_KINDS = {"person", "unit", "institution"}

# fields captured per block, in emit order
_ENTRY_KEYS = ("state", "value", "quote", "source_url", "observed_at", "confidence", "note")


class MDParseError(ValueError):
    """Raised on malformed human-return Markdown — surfaced, never swallowed."""


@dataclass
class MDEntry:
    field: str
    state: str = "value"
    value: str | None = None
    quote: str | None = None
    source_url: str | None = None
    observed_at: str | None = None
    confidence: str | None = None
    note: str | None = None

    def validate(self) -> None:
        if not self.field:
            raise MDParseError("entry with empty field name")
        if self.state not in VALID_STATES:
            raise MDParseError(f"{self.field}: invalid state {self.state!r}")
        if self.confidence is not None and self.confidence not in VALID_CONFIDENCE:
            raise MDParseError(f"{self.field}: invalid confidence {self.confidence!r}")
        if self.state == "value" and self.value is None:
            raise MDParseError(f"{self.field}: state 'value' requires a value")
        if self.state == "value" and not self.source_url:
            raise MDParseError(f"{self.field}: a value must cite a source_url (D-010)")


@dataclass
class MDDocument:
    target_kind: str
    target_ref: str
    target_name: str | None = None
    retrieved_at: str | None = None
    entries: list[MDEntry] = dc_field(default_factory=list)


_TARGET_RE = re.compile(r"^target:\s*(\w+)=(\S+)(?:\s+name=(.*))?\s*$")
_FIELD_HDR_RE = re.compile(r"^##\s*field:\s*(.+?)\s*$")
_KV_RE = re.compile(r"^(\w+):\s?(.*)$")


def parse(text: str) -> MDDocument:
    """Parse the grammar into an ``MDDocument``. Raises ``MDParseError`` on anything
    malformed rather than guessing."""
    lines = text.splitlines()
    target_kind = target_ref = target_name = retrieved_at = None
    entries: list[MDEntry] = []
    current: dict | None = None

    def flush() -> None:
        nonlocal current
        if current is not None:
            e = MDEntry(**current)
            e.validate()
            entries.append(e)
            current = None

    for raw in lines:
        line = raw.rstrip()
        if not line or line.startswith("#") and not line.startswith("## field:"):
            # skip blank lines and the top title / comment headings
            continue
        m = _FIELD_HDR_RE.match(line)
        if m:
            flush()
            current = {"field": m.group(1)}
            continue
        if current is None:
            # header region — look for target / retrieved_at
            t = _TARGET_RE.match(line)
            if t:
                target_kind, target_ref = t.group(1), t.group(2)
                target_name = (t.group(3) or "").strip() or None
                continue
            kv = _KV_RE.match(line)
            if kv and kv.group(1) == "retrieved_at":
                retrieved_at = kv.group(2).strip() or None
            continue
        # inside a field block
        kv = _KV_RE.match(line)
        if not kv:
            raise MDParseError(f"unparseable line in field {current['field']!r}: {line!r}")
        key, val = kv.group(1), kv.group(2)
        if key not in _ENTRY_KEYS:
            raise MDParseError(f"unknown key {key!r} in field {current['field']!r}")
        current[key] = val.strip() if key != "quote" else val  # keep quote verbatim
    flush()

    if target_kind is None:
        raise MDParseError("missing 'target:' header")
    if target_kind not in VALID_TARGET_KINDS:
        raise MDParseError(f"invalid target kind {target_kind!r}")
    if not entries:
        raise MDParseError("no field blocks found")
    return MDDocument(target_kind, target_ref, target_name, retrieved_at, entries)


def emit(doc: MDDocument) -> str:
    """Render an ``MDDocument`` back to the grammar. ``parse(emit(doc)) == doc``.
    This is exactly what the chrome-prompt-generator shows the student as the
    required output shape."""
    out = ["# Supervisorly — human retrieval"]
    name = f"  name={doc.target_name}" if doc.target_name else ""
    out.append(f"target: {doc.target_kind}={doc.target_ref}{name}")
    if doc.retrieved_at:
        out.append(f"retrieved_at: {doc.retrieved_at}")
    for e in doc.entries:
        out.append("")
        out.append(f"## field: {e.field}")
        for key in _ENTRY_KEYS:
            v = getattr(e, key)
            if v is None:
                continue
            if key == "state" and v == "value":
                continue  # 'value' is the default; omit for cleanliness
            out.append(f"{key}: {v}")
    return "\n".join(out) + "\n"


def to_claim_dicts(doc: MDDocument) -> list[dict]:
    """Map a parsed document to Claim-shaped dicts (extractor = human-assisted, D-043)."""
    claims = []
    for e in doc.entries:
        claims.append({
            "entity_kind": doc.target_kind,
            "entity_id": doc.target_ref,
            "field": e.field,
            "state": e.state,
            "value": e.value,
            "quote": e.quote,
            "source_url": e.source_url,
            "observed_at": e.observed_at or doc.retrieved_at,
            "confidence": e.confidence,
            "extractor_agent": "human-assisted (Claude for Chrome)",
            "note": e.note,
        })
    return claims
