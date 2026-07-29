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


def _is_pii_email(value) -> bool:
    """True if ``value`` is PII we must not serialise (D-024): a bare single address, or a
    *list* of 2+ addresses. A single email merely *mentioned inside a sentence* is allowed
    (a legitimate recruiting quote), so it is not flagged."""
    if not isinstance(value, str):
        return False
    emails = _EMAIL_RE.findall(value)
    return len(emails) >= 2 or (len(emails) == 1 and bool(_EMAIL_RE.fullmatch(value.strip())))


def _redact_pii(value):
    """Redact a value that is a bare email / email list to a safe placeholder (D-024).

    Applied at build so contact emails never serialise even via the human rung (which bypasses
    the deterministic extractors). A single email inside a sentence is left intact.
    """
    return "[email redacted — see source]" if _is_pii_email(value) else value


def _redact_profile(profile: dict) -> dict:
    """Run the same PII pass over registry metadata that claim values already get (D-024).

    The profile block is machine-supplied rather than page-scraped, which makes it *likelier*
    to be trusted blindly, not less — so it is redacted on the same terms as everything else
    rather than exempted for coming from an API. Strings are checked directly; the recent-works
    list is checked title by title, because a redaction pass that only walks the top level of a
    structure is a redaction pass with a hole in it.
    """
    out = {}
    for k, v in profile.items():
        if isinstance(v, str):
            out[k] = _redact_url(v) if k.endswith("url") else _redact_pii(v)
        elif isinstance(v, list):
            out[k] = [
                {ik: (_redact_pii(iv) if isinstance(iv, str) else iv) for ik, iv in item.items()}
                if isinstance(item, dict)
                else (_redact_pii(item) if isinstance(item, str) else item)
                for item in v
            ]
        else:
            out[k] = v
    return out


def _redact_url(url):
    """Strip any email embedded in a source_url (e.g. ``mailto:prof@uni.edu``) so it can't leak
    into the JSON, while keeping the field truthy so a value still cites a source (D-010/D-024)."""
    if isinstance(url, str) and _EMAIL_RE.search(url):
        return _EMAIL_RE.sub("[email]", url)
    return url


def _envelope(claim: dict | None) -> dict:
    """Turn a claim (or its absence) into a four-state value envelope."""
    if claim is None:
        return {"state": "never_attempted", "value": None, "quote": None,
                "source_url": None, "snapshot_hash": None, "observed_at": None,
                "confidence": None, "extractor": None}
    state = claim.get("state", "value")
    env = {
        "state": state,
        "value": _redact_pii(claim.get("value")) if state == "value" else None,
        "quote": _redact_pii(claim.get("quote")),
        "source_url": _redact_url(claim.get("source_url")),
        "snapshot_hash": claim.get("snapshot_hash"),
        "observed_at": claim.get("observed_at"),
        "confidence": claim.get("confidence"),
        "extractor": claim.get("extractor_agent"),
    }
    # T-1: a display translation travels BESIDE the verbatim quote, and only when one exists.
    # `quote` above is still the source-language sentence the D-010 gate verified — these keys
    # never replace it, and their absence is what makes the dashboard's marker meaningful.
    if claim.get("quote_translated"):
        env["quote_translated"] = _redact_pii(claim.get("quote_translated"))
        env["translated_by"] = claim.get("translated_by")
    return env


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
        out_prof = {"id": prof["id"], "name": _redact_pii(prof.get("name")),
                    "fields": fields}
        if prof.get("profile"):
            # Registry metadata from the discovery APIs (institution, output, citations,
            # ORCID, recent works). Deliberately a SEPARATE key from `fields`: `fields` is
            # the quote-gated evidence surface (D-010) and nothing may enter it without a
            # verified quote, while this is openly labelled as what OpenAlex/ROR said about
            # the person. Same redaction pass as the name, so a record that somehow carries
            # an address cannot ride out through the new key (D-005/D-032).
            out_prof["profile"] = _redact_profile(prof["profile"])
        if prof.get("resolution"):
            # Named-target identity honesty label (verified / unverified / unchecked) —
            # an optional per-professor field, so an unconfirmed OpenAlex match is never
            # presented as confirmed identity in the durable artifacts (D-010).
            out_prof["identity_resolution"] = prof["resolution"]
        out_professors.append(out_prof)

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
        # an email-shaped id/name is PII, not an identifier (D-024). Flag-only: the id is
        # the join key for claims_by_entity and delta — redacting it here would desync them.
        for key in ("id", "name"):
            if _is_pii_email(p.get(key)):
                errors.append(f"professor {key} {p.get(key)!r} is a bare email — "
                              "personal data must not be exported (D-024)")
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
            # a bare email / email list smuggled under a non-email datatype is PII (D-024)
            if st == "value" and _is_pii_email(env.get("value")):
                errors.append(f"{p.get('id','?')}.{fid}: a bare email must not be "
                              "exported (D-024)")
            # …and a source_url must not carry a contact address (e.g. mailto:) into the JSON
            src = env.get("source_url")
            if isinstance(src, str) and _EMAIL_RE.search(src):
                errors.append(f"{p.get('id','?')}.{fid}: source_url leaks an email (D-024)")
    return errors
