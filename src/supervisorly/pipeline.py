"""End-to-end scan orchestration (the deterministic path).

``run_offline`` ties the pieces together — fetch → deterministic signal extraction →
quote-verified claim → export → dashboard — with **no LLM and no network** (cassettes).
This is what the self-run exercises: a full run that, by construction, cannot hallucinate
(every value claim's quote is lifted verbatim from the page and re-verified against the
snapshot, D-010).

The signal tier here is regexes over normalised text — legitimately no-LLM (the design's
"signal tier"). Classifying a candidate sentence into recruiting *state* is the LLM
recruiting-analyst's Stage-2 job; the deterministic tier only surfaces the candidate. The
deadline tier likewise only surfaces a dated sentence and marks it firm vs *projected*
(a watch date, D-061) from unambiguous cue words — it never guesses a date.

Extraction is **field-driven**: each field descriptor names a deterministic extractor.
A blocked page marks *every* field ``blocked`` (honest — we reached nothing), never
``never_attempted``; a reachable page that lacks a field records ``searched_absent``.
"""

from __future__ import annotations

import re

from .export import dashboard as dash
from .export import json_export as jx
from .fetch.fetcher import Fetcher
from .fetch.normalize import main_text
from .fetch.snapshot import SnapshotStore
from .fetch.transport import Transport
from .model import claims, runs
from .model.db import open_db, utcnow

# ── recruiting signal ─────────────────────────────────────────────────────────
# a recruiting-related sentence (candidate signal — not a classification)
_RECRUIT = re.compile(
    r"[^.!?]*\b(recruit\w*|looking for|accepting|seeking|opening|join (?:my|the|our) "
    r"(?:lab|group|team)|hiring|taking (?:new )?students?)\b[^.!?]*[.!?]",
    re.IGNORECASE,
)

# ── deadline signal (D-061) ───────────────────────────────────────────────────
_DEADLINE_CUE = (r"deadline|applications?\s+(?:close|open|due|are\s+due)|apply\s+by|"
                 r"closing\s+date|submit(?:ted)?\s+by|due\s+by")
# a sentence carrying a deadline cue (a date is required separately, below)
_DEADLINE = re.compile(rf"[^.!?]*\b(?:{_DEADLINE_CUE})\b[^.!?]*[.!?]", re.IGNORECASE)
# cue words that make a date *projected*, not a published/firm deadline (→ watch date)
_PROJECTED = re.compile(
    r"\b(typically|usually|generally|normally|around|about|each\s+year|every\s+year|"
    r"annually|rolling|expected|projected|anticipated|likely)\b",
    re.IGNORECASE,
)
_MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august",
     "september", "october", "november", "december"], start=1)}
_ISO = re.compile(r"\b(20\d{2})-(\d{1,2})-(\d{1,2})\b")
_DMY = re.compile(r"\b(\d{1,2})\s+([A-Za-z]+)\s+(20\d{2})\b")          # 1 December 2026
_MDY = re.compile(r"\b([A-Za-z]+)\s+(\d{1,2}),?\s+(20\d{2})\b")        # December 1, 2026

FIELD_DESCRIPTORS = [
    {"id": "recruiting_signal", "label": "Recruiting signal", "kind": "filter",
     "datatype": "string"},
    {"id": "deadline", "label": "Application deadline", "kind": "sort", "datatype": "date"},
]


def _normalize_date(text: str) -> str | None:
    """Deterministically parse the first full (day+month+year) date to ISO, else None.

    Requires all three parts — a bare month/season is not a date and must not be invented.
    """
    m = _ISO.search(text)
    if m:
        y, mo, d = (int(x) for x in m.groups())
    else:
        m = _DMY.search(text)
        if m and m.group(2).lower() in _MONTHS:
            d, mo, y = int(m.group(1)), _MONTHS[m.group(2).lower()], int(m.group(3))
        else:
            m = _MDY.search(text)
            if m and m.group(1).lower() in _MONTHS:
                mo, d, y = _MONTHS[m.group(1).lower()], int(m.group(2)), int(m.group(3))
            else:
                return None
    if not (1 <= mo <= 12 and 1 <= d <= 31):
        return None
    return f"{y:04d}-{mo:02d}-{d:02d}"


def extract_recruiting_signal(html: str):
    """Return (value, quote, confidence) for the first recruiting-related sentence, or None."""
    m = _RECRUIT.search(main_text(html))
    if not m:
        return None
    sentence = m.group(0).strip()
    return sentence, sentence, "quoted_official"


def extract_deadline(html: str):
    """Return (iso_date, quote, confidence) for a dated deadline sentence, or None.

    ``confidence`` is ``quoted_official`` for a firm, published date and ``inferred`` for a
    *projected* one (cue words like "usually"/"each year") — the dashboard shows the latter
    as a watch date, never firm (D-061).
    """
    text = main_text(html)
    for m in _DEADLINE.finditer(text):
        sentence = m.group(0).strip()
        iso = _normalize_date(sentence)
        if iso:
            projected = bool(_PROJECTED.search(sentence))
            return iso, sentence, ("inferred" if projected else "quoted_official")
    return None


# field_id → extractor. Adding a field is adding a row here + a descriptor above (D-038).
_EXTRACTORS = {
    "recruiting_signal": extract_recruiting_signal,
    "deadline": extract_deadline,
}


def run_offline(plan: dict, targets: list[dict], transport: Transport, snap_root,
                *, db_path=None) -> dict:
    """Run a deterministic scan over ``targets`` (each {id, name, url}) using cassettes.

    Returns {run_id, export, html}. The run always finalises with a dashboard — it never
    blocks on the human rung (D-049). Pass ``db_path`` to persist the store across runs
    (used by the warm-cache path)."""
    conn = open_db(db_path) if db_path is not None else open_db()
    snaps = SnapshotStore(snap_root)
    fetcher = Fetcher(transport, snaps)

    run_id = runs.create_run(conn)
    runs.set_run_status(conn, run_id, "deep_diving")

    for t in targets:
        pid = t["id"]
        task = runs.add_task(conn, run_id, "person", pid, stage="deep_dive")
        res = fetcher.fetch(t["url"])
        if res.ok:
            html = snaps.load(res.snapshot_hash)
            src_id = claims.record_web_source(
                conn, t["url"], snapshot_hash=res.snapshot_hash, http_status=200,
                source_tier="official_institutional", robots_allowed=True,
            )
            for field, extractor in _EXTRACTORS.items():
                found = extractor(html)
                if found:
                    value, quote, confidence = found
                    claims.record_claim(
                        conn, entity_kind="person", entity_id=pid, field=field,
                        value=value, quote=quote, source_id=src_id,
                        snapshot_hash=res.snapshot_hash, snapshot_html=html,
                        observed_at=utcnow(), extractor_agent="deterministic",
                        confidence=confidence,
                    )
                else:
                    claims.record_claim(
                        conn, entity_kind="person", entity_id=pid, field=field,
                        state="searched_absent", source_id=src_id,
                        extractor_agent="deterministic",
                    )
            runs.set_task_status(conn, task, "done")
        else:
            # a failed/blocked source is an honest 'blocked' state on every field —
            # we reached nothing, which is not the same as 'never attempted'.
            for field in _EXTRACTORS:
                claims.record_claim(
                    conn, entity_kind="person", entity_id=pid, field=field,
                    state="blocked", extractor_agent="deterministic",
                )
            runs.set_task_status(conn, task, "blocked", last_error=res.error)

    runs.set_run_status(conn, run_id, "finalized")

    professors = [{"id": t["id"], "name": t.get("name")} for t in targets]
    claims_by_entity = {t["id"]: claims.claims_for(conn, "person", t["id"]) for t in targets}
    enumerated = len(targets)
    # Honest coverage line so the empty-state can tell "sources returned nothing" apart
    # from "found people, none matched" (edge-case matrix / D-046). The deterministic
    # pipeline never drops a professor, so zero here means discovery surfaced no one.
    coverage = ("No sources returned any professors for this search — this is a coverage "
                "gap, not a filtered result." if enumerated == 0
                else f"{enumerated} professor(s) enumerated; none were dropped for missing data.")
    export = jx.build_export(
        run_summary={"run_id": run_id, "status": "finalized",
                     "counts": {"enumerated": enumerated}, "coverage": coverage},
        field_descriptors=FIELD_DESCRIPTORS,
        professors=professors,
        claims_by_entity=claims_by_entity,
        generated_at=utcnow(),
    )
    return {"run_id": run_id, "export": export, "html": dash.build_dashboard(export)}
