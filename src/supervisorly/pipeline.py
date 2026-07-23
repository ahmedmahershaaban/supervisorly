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
# Cues are deliberately kept to **application/submission** contexts. Broader "close" cues
# ("applications open" round 2; bare "close(s)" round 3; "close(s) on" / "registration closes"
# round 4) all fabricated firm deadlines from unrelated sentences ("office hours close on
# Fridays", "the library closes on 1 Dec", "gym registration closes on 1 Dec"). A miss here is
# an honest `searched_absent` the LLM analyst can resolve later; a fabricated firm date is not
# (D-010/D-061 — never guess). So "…and close on 1 Dec" without an application subject is missed.
_DEADLINE_CUE = (r"deadline|applications?\s+(?:close|due|are\s+due)|submissions?\s+(?:close|due)|"
                 r"apply\s+by|closing\s+date|submit(?:ted)?\s+by|due\s+by")
# a sentence carrying a deadline cue (a date is required separately, below)
_DEADLINE = re.compile(rf"[^.!?]*\b(?:{_DEADLINE_CUE})\b[^.!?]*[.!?]", re.IGNORECASE)
# where the cue sits, so the date can be bound to *its* clause (not blindly the first date)
_CUE_RE = re.compile(rf"\b(?:{_DEADLINE_CUE})\b", re.IGNORECASE)
# cue words that make a date *projected*, not a published/firm deadline (→ watch date)
_PROJECTED = re.compile(
    r"\b(typically|usually|generally|normally|around|about|each\s+year|every\s+year|"
    r"annually|rolling|expected|projected|anticipated|likely)\b",
    re.IGNORECASE,
)
# STRONG signals that the parsed date belongs to some other event than the deadline (a term
# start, a passed round) → downgrade to a watch date, never firm (D-061). Kept deliberately
# narrow: generic tokens ("but", ";", bare "start") wrongly demoted real firm deadlines
# whose date sits in the cue's own clause (audit round 2).
_NONFIRM = re.compile(
    r"\b(has\s+passed|deadline\s+has\s+passed|no\s+fixed|next\s+intake|previous\s+round|"
    r"semester\s+begins|term\s+begins|classes\s+(?:begin|start)|"
    r"intake\s+(?:starts|begins)|academic\s+year\s+begins)\b",
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


_DATE_RXS = (("iso", _ISO), ("dmy", _DMY), ("mdy", _MDY), ("num", _NUM))


def _iso_from_match(kind: str, m: re.Match) -> tuple[str, bool] | None:
    """Turn one date-regex match into ``(iso, ambiguous)`` or None if invalid/unparseable.

    An impossible calendar date (Feb 31) is rejected; a numeric ``dd/mm`` date is flagged
    ``ambiguous`` (locale-uncertain → watch); a truly ambiguous numeric (both parts ≤12) is
    not guessed.
    """
    if kind == "iso":
        y, mo, d = (int(x) for x in m.groups())
        ambiguous = False
    elif kind == "dmy":
        if m.group(2).lower() not in _MONTHS:
            return None
        d, mo, y = int(m.group(1)), _MONTHS[m.group(2).lower()], int(m.group(3))
        ambiguous = False
    elif kind == "mdy":
        if m.group(1).lower() not in _MONTHS:
            return None
        mo, d, y = _MONTHS[m.group(1).lower()], int(m.group(2)), int(m.group(3))
        ambiguous = False
    else:  # numeric dd/mm/yyyy — disambiguate by the >12 rule, else don't guess
        a, b, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if a > 12 and b <= 12:
            d, mo = a, b
        elif b > 12 and a <= 12:
            mo, d = a, b
        else:
            return None
        ambiguous = True
    if not _valid_date(y, mo, d):
        return None
    return f"{y:04d}-{mo:02d}-{d:02d}", ambiguous


def _clause_containing(sentence: str, pos: int) -> str:
    """Return the clause (split on ``,``/``;``) that contains character ``pos``.

    Used so a "belongs to another event" signal only downgrades the deadline when it shares
    the date's clause — a strong phrase in a separate, dateless clause must not demote a firm,
    cue-owned date (audit round 3).
    """
    seps = [m.start() for m in re.finditer(r"[;,]", sentence)]
    starts = [0] + [s + 1 for s in seps]
    ends = seps + [len(sentence)]
    for st, en in zip(starts, ends):
        if st <= pos < en:
            return sentence[st:en]
    return sentence


def _dates_in(text: str) -> list[tuple[str, bool, int]]:
    """Every valid full (day+month+year) date in ``text`` as (iso, ambiguous, position)."""
    out = []
    for kind, rx in _DATE_RXS:
        for m in rx.finditer(text):
            parsed = _iso_from_match(kind, m)
            if parsed:
                out.append((parsed[0], parsed[1], m.start()))
    return out


def _normalize_date(text: str) -> tuple[str, bool] | None:
    """First valid full date in ``text`` as ``(iso, ambiguous)``, else None.

    Requires all three parts — a bare month/season is never invented, and an impossible
    calendar date (Feb 31) is rejected.
    """
    dates = _dates_in(text)
    if not dates:
        return None
    dates.sort(key=lambda x: x[2])
    return dates[0][0], dates[0][1]


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
    ("usually"/"each year"), the date is numeric/locale-ambiguous, or a strong signal says the
    date belongs to another event ("deadline has passed, but term begins 1 September 2026").
    The date is bound to the one **nearest the cue**, so a sentence that states both an opening
    and a closing date yields the closing (deadline) date, not the opening one.
    """
    text = main_text(html)
    for m in _DEADLINE.finditer(text):
        sentence = m.group(0).strip()
        dates = _dates_in(sentence)
        if not dates:
            continue
        cue = _CUE_RE.search(sentence)
        cue_pos = cue.start() if cue else 0
        iso, ambiguous, date_pos = min(dates, key=lambda dp: abs(dp[2] - cue_pos))
        # _PROJECTED ("usually"/"each year") applies anywhere; a strong "other-event" signal
        # only demotes when it shares the *date's* clause (not a separate, dateless one).
        projected = (ambiguous
                     or bool(_PROJECTED.search(sentence))
                     or bool(_NONFIRM.search(_clause_containing(sentence, date_pos))))
        return iso, sentence, ("inferred" if projected else "quoted_official")
    return None


# field_id → extractor. Adding a field is adding a row here + a descriptor above (D-038).
_EXTRACTORS = {
    "recruiting_signal": extract_recruiting_signal,
    "deadline": extract_deadline,
}


def _record_evidence(conn, pid, field, found, *, src_id, snapshot_hash, html):
    """Record one field's deterministic result with correct precedence.

    A fresh **value** supersedes prior heads (freshest evidence wins). An **absence**
    (``searched_absent``) never clobbers a live value we already hold — e.g. a human-rung
    answer — so a re-scan that finds nothing does not erase real data (D-046/D-049); otherwise
    it is recorded and supersedes prior *non-value* heads so absences don't pile up.
    """
    if found:
        value, quote, confidence = found
        rec = claims.record_claim(
            conn, entity_kind="person", entity_id=pid, field=field,
            value=value, quote=quote, source_id=src_id, snapshot_hash=snapshot_hash,
            snapshot_html=html, observed_at=utcnow(), extractor_agent="deterministic",
            confidence=confidence,
        )
        if rec.ok:
            claims.supersede_prior(conn, "person", pid, field, rec.claim_id)
        return rec
    if claims.live_value(conn, "person", pid, field):
        return None                       # keep the real value; don't downgrade to absent
    rec = claims.record_claim(
        conn, entity_kind="person", entity_id=pid, field=field,
        state="searched_absent", source_id=src_id, extractor_agent="deterministic",
    )
    if rec.ok:
        claims.supersede_prior(conn, "person", pid, field, rec.claim_id)
    return rec


def _record_blocked(conn, pid, field):
    """Record a blocked field — but never downgrade an already-reached field, and dedupe blocked."""
    if claims.live_reached(conn, "person", pid, field):
        return None                       # already reached (value/absent); a failed re-fetch can't erase it
    rec = claims.record_claim(
        conn, entity_kind="person", entity_id=pid, field=field,
        state="blocked", extractor_agent="deterministic",
    )
    if rec.ok:
        claims.supersede_prior(conn, "person", pid, field, rec.claim_id)
    return rec


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
                rec = _record_evidence(conn, pid, field, extractor(html), src_id=src_id,
                                       snapshot_hash=res.snapshot_hash, html=html)
                if rec and rec.ok:
                    claim_ids.append(rec.claim_id)
            xcache.record(conn, "person", pid, chash, PROMPT_VERSION, MODEL_ID,
                          CACHE_SCHEMA_VERSION, claim_ids)
            stats["extractions"] += 1
            runs.set_task_status(conn, task, "done")
        else:
            # a failed/blocked source is an honest 'blocked' state on every field — we reached
            # nothing (not 'never attempted'), but a failed re-fetch never erases evidence we
            # already hold (e.g. a human-rung answer).
            for field in _EXTRACTORS:
                _record_blocked(conn, pid, field)
            runs.set_task_status(conn, task, "blocked", last_error=res.error)

    # An open gap is a field still 'blocked' after this run — derived from claim state so the
    # run status can never contradict the exported cells (D-046/D-049). Matches reexport().
    gaps = sum(
        1 for t in targets
        if any(c.get("state") == "blocked"
               for c in claims.claims_for(conn, "person", t["id"]))
    )
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
