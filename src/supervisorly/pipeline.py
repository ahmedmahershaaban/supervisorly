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

import datetime
import re

from .ethics import optout as optout_mod
from .export import dashboard as dash
from .export import json_export as jx
from .fetch.fetcher import Fetcher
from .fetch.normalize import content_hash, main_text
from .fetch.snapshot import SnapshotStore
from .fetch.transport import Transport
from .model import claims, extraction_cache as xcache, runs
from .model.db import open_db, utcnow

# ExtractionCache key parts for the deterministic signal tier (cost §3b-i). The "prompt"
# and "model" are notional here — the point is a stable key so a warm re-scan skips work.
PROMPT_VERSION = "det-signal-v1"
MODEL_ID = "deterministic"
CACHE_SCHEMA_VERSION = "1"

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
# A date bound in a clause *other than* the deadline cue's makes it unsafe to call firm —
# e.g. "the deadline has passed, but the semester begins 1 September 2026" (D-061). Such a
# match is downgraded to a watch date, never shown as firm.
_NONFIRM = re.compile(
    r"\b(has\s+passed|passed|no\s+fixed|previous|but|however|semester\s+begins|"
    r"term\s+begins|classes\s+(?:begin|start)|intake\s+(?:starts|begins)|"
    r"academic\s+year\s+begins|starts?|began)\b|;",
    re.IGNORECASE,
)
_MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august",
     "september", "october", "november", "december"], start=1)}
_ORD = r"(?:st|nd|rd|th)?"          # optional ordinal suffix: 1st, 2nd, 3rd, 4th …
_ISO = re.compile(r"\b(20\d{2})-(\d{1,2})-(\d{1,2})\b")
_DMY = re.compile(rf"\b(\d{{1,2}}){_ORD}\s+([A-Za-z]+)\s+(20\d{{2}})\b")   # 1[st] December 2026
_MDY = re.compile(rf"\b([A-Za-z]+)\s+(\d{{1,2}}){_ORD},?\s+(20\d{{2}})\b") # December 1[st], 2026
_NUM = re.compile(r"\b(\d{1,2})/(\d{1,2})/(20\d{2})\b")                    # 01/12/2026 (numeric)


def _valid_date(y: int, mo: int, d: int) -> bool:
    """True iff (y, mo, d) is a real calendar day — rejects Feb 31, Apr 31, etc."""
    try:
        datetime.date(y, mo, d)
        return True
    except ValueError:
        return False

FIELD_DESCRIPTORS = [
    {"id": "recruiting_signal", "label": "Recruiting signal", "kind": "filter",
     "datatype": "string"},
    {"id": "deadline", "label": "Application deadline", "kind": "sort", "datatype": "date"},
]


def _normalize_date(text: str) -> tuple[str, bool] | None:
    """Deterministically parse the first full (day+month+year) date to ISO.

    Returns ``(iso, ambiguous)`` or ``None``. Requires all three parts — a bare month/season
    is never invented into a date, and an impossible calendar date (Feb 31) is rejected.
    ``ambiguous`` is True for a numeric ``dd/mm/yyyy`` date (locale-uncertain) so the caller
    can present it as a watch date rather than firm (D-061).
    """
    m = _ISO.search(text)
    if m:
        y, mo, d = (int(x) for x in m.groups())
        return (f"{y:04d}-{mo:02d}-{d:02d}", False) if _valid_date(y, mo, d) else None

    m = _DMY.search(text)
    if m and m.group(2).lower() in _MONTHS:
        d, mo, y = int(m.group(1)), _MONTHS[m.group(2).lower()], int(m.group(3))
        return (f"{y:04d}-{mo:02d}-{d:02d}", False) if _valid_date(y, mo, d) else None

    m = _MDY.search(text)
    if m and m.group(1).lower() in _MONTHS:
        mo, d, y = _MONTHS[m.group(1).lower()], int(m.group(2)), int(m.group(3))
        return (f"{y:04d}-{mo:02d}-{d:02d}", False) if _valid_date(y, mo, d) else None

    m = _NUM.search(text)
    if m:
        a, b, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        # Disambiguate by the >12 rule; if both are ≤12 the order is genuinely unknowable, so
        # we do NOT guess (a wrong deadline is worse than an honest absent one).
        if a > 12 and b <= 12:      # a is the day → dd/mm
            d, mo = a, b
        elif b > 12 and a <= 12:    # b is the day → mm/dd
            mo, d = a, b
        else:
            return None
        # numeric dates are inherently lower-confidence → flag ambiguous (watch, not firm)
        return (f"{y:04d}-{mo:02d}-{d:02d}", True) if _valid_date(y, mo, d) else None
    return None


def extract_recruiting_signal(html: str):
    """Return (value, quote, confidence) for the first recruiting-related sentence, or None."""
    m = _RECRUIT.search(main_text(html))
    if not m:
        return None
    sentence = m.group(0).strip()
    return sentence, sentence, "quoted_official"


def extract_deadline(html: str):
    """Return (iso_date, quote, confidence) for a dated deadline sentence, or None.

    ``confidence`` is ``quoted_official`` only for a firm, published, spelled-out date whose
    cue owns it; it is ``inferred`` (a *watch* date, D-061) when the sentence is projected
    ("usually"/"each year"), the date is numeric/locale-ambiguous, or the date sits in a
    different clause than the cue ("deadline has passed, but term begins 1 September 2026").
    """
    text = main_text(html)
    for m in _DEADLINE.finditer(text):
        sentence = m.group(0).strip()
        nd = _normalize_date(sentence)
        if nd:
            iso, ambiguous = nd
            projected = (ambiguous
                         or bool(_PROJECTED.search(sentence))
                         or bool(_NONFIRM.search(sentence)))
            return iso, sentence, ("inferred" if projected else "quoted_official")
    return None


# field_id → extractor. Adding a field is adding a row here + a descriptor above (D-038).
_EXTRACTORS = {
    "recruiting_signal": extract_recruiting_signal,
    "deadline": extract_deadline,
}


def run_offline(plan: dict, targets: list[dict], transport: Transport, snap_root,
                *, db_path=None, optout_path=None, resume=False) -> dict:
    """Run a deterministic scan over ``targets`` (each {id, name, url}) using cassettes.

    Returns {run_id, export, html}. The run always finalises with a dashboard — it never
    blocks on the human rung (D-049). Pass ``db_path`` to persist the store across runs
    (used by the warm-cache path); ``optout_path`` to enforce the suppression list (D-023);
    ``resume=True`` to skip (not re-fetch) any target already deep-dived in a prior run whose
    state persists in ``db_path`` (D-029)."""
    conn = open_db(db_path) if db_path is not None else open_db()
    snaps = SnapshotStore(snap_root)
    # Offline cassettes never rate-limit us, so any retry needn't actually sleep.
    fetcher = Fetcher(transport, snaps, sleep=lambda _s: None)

    # Opt-out is enforced BEFORE any fetch: a suppressed person is never even requested (D-023).
    optout = optout_mod.load_optout(optout_path)
    targets, opted_out = optout_mod.filter_targets(targets, optout)

    run_id = runs.create_run(conn)
    runs.set_run_status(conn, run_id, "deep_diving")

    stats = {"extractions": 0, "cache_hits": 0, "opted_out": opted_out, "resumed_skipped": 0}
    gaps = 0
    for t in targets:
        pid = t["id"]
        # Resume: a target already deep-dived in a prior run is not re-fetched — its claims
        # are already persisted. This is what makes an interrupted scan cheap to finish (D-029).
        if resume and runs.target_stage_done(conn, "person", pid, "deep_dive"):
            stats["resumed_skipped"] += 1
            continue
        task = runs.add_task(conn, run_id, "person", pid, stage="deep_dive")
        res = fetcher.fetch(t["url"])
        if res.ok:
            html = snaps.load(res.snapshot_hash)
            chash = content_hash(html)
            if xcache.lookup(conn, "person", pid, chash, PROMPT_VERSION, MODEL_ID,
                             CACHE_SCHEMA_VERSION):
                # warm re-scan: this exact content was already extracted — reuse the
                # claims from the prior run, do no work, create no duplicates (cost §3b-i).
                stats["cache_hits"] += 1
                runs.set_task_status(conn, task, "done")
                continue
            src_id = claims.record_web_source(
                conn, t["url"], snapshot_hash=res.snapshot_hash, http_status=200,
                source_tier="official_institutional", robots_allowed=True,
            )
            claim_ids: list[str] = []
            for field, extractor in _EXTRACTORS.items():
                found = extractor(html)
                if found:
                    value, quote, confidence = found
                    rec = claims.record_claim(
                        conn, entity_kind="person", entity_id=pid, field=field,
                        value=value, quote=quote, source_id=src_id,
                        snapshot_hash=res.snapshot_hash, snapshot_html=html,
                        observed_at=utcnow(), extractor_agent="deterministic",
                        confidence=confidence,
                    )
                else:
                    rec = claims.record_claim(
                        conn, entity_kind="person", entity_id=pid, field=field,
                        state="searched_absent", source_id=src_id,
                        extractor_agent="deterministic",
                    )
                if rec.ok:
                    claim_ids.append(rec.claim_id)
            xcache.record(conn, "person", pid, chash, PROMPT_VERSION, MODEL_ID,
                          CACHE_SCHEMA_VERSION, claim_ids)
            stats["extractions"] += 1
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
            gaps += 1

    # An unreached (blocked) target is an open gap the human rung can later fill (D-049).
    status = "finalized_with_open_gaps" if gaps else "finalized"
    runs.set_run_status(conn, run_id, status)

    result = _build_result(conn, run_id, status, targets, stats=stats, gaps=gaps)
    return result


def reexport(db_path, targets: list[dict], *, optout_path=None) -> dict:
    """Rebuild the export + dashboard from persisted claims — **without any fetching** (D-029).

    This is the resume path: after the human rung fills gaps (``ingest.ingest_md``), the run
    re-exports from the database and snapshots already on disk. It constructs no transport and
    no fetcher, so nothing can be re-fetched; a field still ``blocked`` keeps the run
    ``finalized_with_open_gaps``, otherwise it becomes ``finalized`` (D-049).

    Opt-out is enforced here too (D-023): a person suppressed *after* their claims were stored
    must not survive into the re-exported output, so the suppression list is applied before the
    export is built — not only on the initial fetch path.
    """
    conn = open_db(db_path)
    optout = optout_mod.load_optout(optout_path)
    targets, opted_out = optout_mod.filter_targets(targets, optout)
    gaps = sum(
        1 for t in targets
        if any(c.get("state") == "blocked"
               for c in claims.claims_for(conn, "person", t["id"]))
    )
    status = "finalized_with_open_gaps" if gaps else "finalized"
    latest = conn.execute(
        "SELECT run_id FROM run ORDER BY started_at DESC, rowid DESC LIMIT 1"
    ).fetchone()
    run_id = latest["run_id"] if latest else "reexport"
    if latest:
        runs.set_run_status(conn, run_id, status)
    return _build_result(
        conn, run_id, status, targets,
        stats={"extractions": 0, "cache_hits": 0, "opted_out": opted_out, "reexport": True},
        gaps=gaps,
    )


def _build_result(conn, run_id, status, targets, *, stats, gaps) -> dict:
    """Assemble the export + dashboard from the persisted claims (no fetching here)."""
    professors = [{"id": t["id"], "name": t.get("name")} for t in targets]
    claims_by_entity = {t["id"]: claims.claims_for(conn, "person", t["id"]) for t in targets}
    enumerated = len(targets)
    # Honest coverage line so the empty-state can tell "sources returned nothing" apart
    # from "found people, none matched" (edge-case matrix / D-046). The deterministic
    # pipeline never drops a professor, so zero here means discovery surfaced no one.
    coverage = ("No sources returned any professors for this search — this is a coverage "
                "gap, not a filtered result." if enumerated == 0
                else f"{enumerated} professor(s) enumerated; none were dropped for missing data.")
    if gaps:
        coverage += f" {gaps} target(s) are blocked and open for the human rung."
    export = jx.build_export(
        run_summary={"run_id": run_id, "status": status,
                     "counts": {"enumerated": enumerated}, "coverage": coverage},
        field_descriptors=FIELD_DESCRIPTORS,
        professors=professors,
        claims_by_entity=claims_by_entity,
        generated_at=utcnow(),
    )
    return {"run_id": run_id, "export": export, "html": dash.build_dashboard(export),
            "stats": stats}
