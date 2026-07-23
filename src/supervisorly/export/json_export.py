"""The JSON export contract (D-046) — the system's interchange format.

The dashboard is a *view* over this JSON, and the student's Claude session reads it
to answer questions and edit the UI (D-041). Three parts:

1. **A per-field value envelope with an explicit state** — never a bare value. State is
   one of ``value / searched_absent / never_attempted / blocked``, derived
   deterministically from the claim store, so "no data" is honest, not a bug (D-022).
2. **A field-metadata descriptor** so the *generic* dashboard adapts to whatever fields
   the search produced instead of assuming fixed columns (D-038).
3. **The personal-data rules** — fields marked non-exportable (LLM judgements about
   people) and bare email lists never serialise (D-024).
"""

from __future__ import annotations

import re

VALID_STATES = {"value", "searched_absent", "never_attempted", "blocked"}
VALID_KINDS = {"filter", "sort", "facet", "score-input", "search", "display"}
SCHEMA_VERSION = "1"

# A contact email is personal data we never emit as a bare field (D-024). Email-typed fields
# are dropped at build like non-exportable ones; validate flags any that leak through.
_EMAIL_RE = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")


def _is_email_field(descriptor: dict) -> bool:
    return descriptor.get("datatype") == "email"

# required keys on a field descriptor
_DESCRIPTOR_KEYS = {"id", "label", "kind", "datatype"}
# keys carried by a value envelope
_ENVELOPE_KEYS = ("state", "value", "quote", "source_url", "snapshot_hash",
                  "observed_at", "confidence", "extractor")


class ExportError(ValueError):
    pass


def _best_claim(claims: list[dict], field_id: str) -> dict | None:
    """Most-recent, non-superseded claim for a field (the current head)."""
    candidates = [
        c for c in claims
        if c.get("field") == field_id and not c.get("superseded_by")
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda c: c.get("observed_at") or c.get("created_at") or "")


def _redact_pii(value):
    """Replace a value that *is* a bare email address with a safe placeholder (D-024).

    Applied at build so a bare contact email never serialises even when it arrives via the
    human rung (which bypasses the deterministic extractors). A merely *mentioned* email
    inside a sentence is left intact — only a whole-value address is redacted.
    """
    if isinstance(value, str) and _EMAIL_RE.fullmatch(value.strip()):
        return "[email redacted — see source]"
    return value


def _envelope(claim: dict | None) -> dict:
    """Turn a claim (or its absence) into a four-state value envelope."""
    if claim is None:
        return {"state": "never_attempted", "value": None, "quote": None,
                "source_url": None, "snapshot_hash": None, "observed_at": None,
                "confidence": None, "extractor": None}
    state = claim.get("state", "value")
    return {
        "state": state,
        "value": _redact_pii(claim.get("value")) if state == "value" else None,
        "quote": _redact_pii(claim.get("quote")),
        "source_url": claim.get("source_url"),
        "source_url": claim.get("source_url"),
        "snapshot_hash": claim.get("snapshot_hash"),
        "observed_at": claim.get("observed_at"),
        "confidence": claim.get("confidence"),
        "extractor": claim.get("extractor_agent"),
    }


def build_export(
    *,
    run_summary: dict,
    field_descriptors: list[dict],
    professors: list[dict],
    claims_by_entity: dict[str, list[dict]],
    generated_at: str,
) -> dict:
    """Assemble the export. ``field_descriptors`` may carry ``exportable: False`` to keep
    a field (e.g. an LLM judgement) out of the serialised output (D-024)."""
    # Drop non-exportable fields (LLM judgements) AND email-typed fields (D-024): a bare
    # contact email never serialises, by construction.
    exportable = [d for d in field_descriptors
                  if d.get("exportable", True) and not _is_email_field(d)]
    clean_descriptors = [{k: v for k, v in d.items() if k != "exportable"} for d in exportable]

    out_professors = []
    for prof in professors:
        claims = claims_by_entity.get(prof["id"], [])
        fields = {}
        for d in exportable:
            fields[d["id"]] = _envelope(_best_claim(claims, d["id"]))
        out_professors.append({"id": prof["id"], "name": prof.get("name"), "fields": fields})

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "run": run_summary,
        "fields": clean_descriptors,
        "professors": out_professors,
    }


def validate_export(obj: dict) -> list[str]:
    """Return a list of structural violations (empty = valid). Enforces the four-state
    envelope, the descriptor shape, and that no non-exportable field leaked in."""
    errors: list[str] = []
    if obj.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION!r}")
    descriptors = obj.get("fields")
    if not isinstance(descriptors, list):
        return errors + ["'fields' must be a list of descriptors"]

    declared_ids = set()
    for d in descriptors:
        missing = _DESCRIPTOR_KEYS - d.keys()
        if missing:
            errors.append(f"descriptor {d.get('id','?')} missing keys {sorted(missing)}")
        if d.get("kind") not in VALID_KINDS:
            errors.append(f"descriptor {d.get('id','?')} has invalid kind {d.get('kind')!r}")
        if "exportable" in d:
            errors.append(f"descriptor {d.get('id','?')} leaked internal 'exportable' flag")
        if _is_email_field(d):
            errors.append(f"descriptor {d.get('id','?')} is an email field — must not be "
                          "exported (D-024)")
        declared_ids.add(d.get("id"))

    for p in obj.get("professors", []):
        if "id" not in p:
            errors.append("professor missing id")
        fields = p.get("fields", {})
        for fid, env in fields.items():
            if fid not in declared_ids:
                errors.append(f"professor {p.get('id','?')} has undeclared/non-exportable "
                              f"field {fid!r}")
            st = env.get("state")
            if st not in VALID_STATES:
                errors.append(f"{p.get('id','?')}.{fid}: invalid state {st!r}")
            if st == "value" and env.get("value") is None:
                errors.append(f"{p.get('id','?')}.{fid}: state 'value' with null value")
            if st != "value" and env.get("value") is not None:
                errors.append(f"{p.get('id','?')}.{fid}: non-'value' state carries a value")
            if st == "value" and not env.get("source_url"):
                errors.append(f"{p.get('id','?')}.{fid}: a value must cite a source_url (D-010)")
            # a value that *is* a bare email address (not a sentence mentioning one) is PII
            # smuggled under a non-email datatype — reject it (D-024).
            val = env.get("value")
            if st == "value" and isinstance(val, str) and _EMAIL_RE.fullmatch(val.strip()):
                errors.append(f"{p.get('id','?')}.{fid}: a bare email address must not be "
                              "exported (D-024)")
    return errors
