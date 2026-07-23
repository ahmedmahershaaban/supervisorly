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

from . import preflight
from .discover import ladder as _ladder
from .discover import openalex as _openalex
from .discover import ror as _ror
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
# A date is read as a deadline only when a deadline **verb cue**, an **application-context**
# word, AND a full date all share ONE CLAUSE. Working per-clause (not per-sentence) is what
# stops a real "office hours close on 1 Dec; applications … 15 Jan" from binding the wrong
# (office-hours) date, and stops "rent is due by 1 Dec" / "the library closes on 1 Dec" from
# fabricating a firm application deadline at all. A clause that doesn't satisfy all three is an
# honest miss (searched_absent), never a guessed firm date (D-010/D-061).
_DEADLINE_CUE = (r"deadline|apply\s+by|closes?\b|closing\s+date|due\s+by|"
                 r"(?:are|is)\s+due|(?:applications?|submissions?)\s+due|submit(?:ted)?\s+by")
_CUE_RE = re.compile(rf"\b(?:{_DEADLINE_CUE})\b", re.IGNORECASE)

# Deciding a dated deadline clause is an APPLICATION deadline (not a tuition/registration/event
# one that merely mentions a domain word). Like the recruiting regex this is a fixed signal-tier
# heuristic, not a generated per-query dictionary (D-038 stands). A clause qualifies if:
#   (A) a strong application noun is present (applications/applicants/apply/admissions/submissions),
#   (B) a "<domain> deadline" phrase appears (application/PhD/fellowship/… deadline), or
#   (C) a domain word is the SUBJECT of the cue verb — directly before close/due/submitted — so
#       "PhD studentship closes 1 Dec" counts but "…for the PhD program are due by 1 Dec" (subject
#       = tuition/fees) does not. Tying context to the cue's subject is what stops the fabrication.
_DOMAIN = r"phd|dphil|doctoral|postdocs?|postdoctoral|fellowships?|studentships?|scholarships?|positions?|vacanc(?:y|ies)"
_STRONG_APP = re.compile(r"\b(?:applications?|applicants?|apply|admissions?|submissions?)\b", re.IGNORECASE)
_DOMAIN_DEADLINE = re.compile(
    rf"\b(?:{_DOMAIN}|applications?|submissions?|admissions?|entry|programmes?|programs?|courses?|intake)"
    r"\s+deadline\b", re.IGNORECASE)
_DOMAIN_SUBJECT = re.compile(
    rf"\b(?:{_DOMAIN})\s+(?:closes?\b|closing\b|(?:are|is)\s+due|due\s+by|submit(?:ted)?\s+by)",
    re.IGNORECASE)


def _is_application_deadline(clause: str) -> bool:
    """True if the clause's deadline plausibly attaches to an application (not a tuition/event one)."""
    return bool(_STRONG_APP.search(clause)
                or _DOMAIN_DEADLINE.search(clause)
                or _DOMAIN_SUBJECT.search(clause))
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


# mask a comma that sits *inside* a "…D[st], YYYY" date so clause-splitting doesn't cut the date
_DATE_COMMA = re.compile(r"(\d(?:st|nd|rd|th)?)\s*,(\s*20\d{2})")


def _sentences(text: str):
    """Split text into sentences on terminal punctuation (bounded work per sentence)."""
    return re.split(r"(?<=[.!?])\s+", text)


def _clauses(sentence: str):
    """Yield the clauses of a sentence (split on ``;`` and clause commas), keeping dates whole."""
    masked = _DATE_COMMA.sub(lambda m: m.group(1) + "\x00" + m.group(2), sentence)
    for part in re.split(r"[;,]", masked):
        yield part.replace("\x00", ",")


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
    """Return (iso_date, quote, confidence) for an application deadline, or None.

    A date qualifies only when a deadline **verb cue**, an **application-context** word, and a
    full date all share ONE clause — so the date, the deadline, and the subject genuinely belong
    together. ``confidence`` is ``quoted_official`` for a firm spelled-out date, or ``inferred``
    (a *watch* date, D-061) when the clause is projected ("usually"/"each year"), the date is
    numeric/locale-ambiguous, or a strong signal ties the date to another event. Within the
    clause the date nearest the cue is chosen (so "…and close on 1 Dec" binds the close date).
    """
    for sentence in _sentences(main_text(html)):
        if not _CUE_RE.search(sentence):        # cheap prefilter before the per-clause work
            continue
        for clause in _clauses(sentence):
            cue = _CUE_RE.search(clause)
            if not cue or not _is_application_deadline(clause):
                continue
            dates = _dates_in(clause)
            if not dates:
                continue
            iso, ambiguous, _pos = min(dates, key=lambda dp: abs(dp[2] - cue.start()))
            projected = (ambiguous
                         or bool(_PROJECTED.search(clause))
                         or bool(_NONFIRM.search(clause)))
            return iso, sentence.strip(), ("inferred" if projected else "quoted_official")
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


def _process_targets(conn, run_id, targets, fetcher, snaps, *, stats, resume) -> int:
    """Deep-dive each target (fetch → extract → claim) — the shared core of run_offline/run_live.

    Returns the gap count (targets with any still-``blocked`` field), derived from claim state so
    the run status can never contradict the exported cells (D-046/D-049). A target with no page URL
    (e.g. an OpenAlex professor with no discoverable homepage) is an honest open gap for the human
    rung, never a fabricated value.
    """
    for t in targets:
        pid = t["id"]
        if resume and runs.target_stage_done(conn, "person", pid, "deep_dive"):
            stats["resumed_skipped"] += 1
            continue
        task = runs.add_task(conn, run_id, "person", pid, stage="deep_dive")
        url = t.get("url")
        res = fetcher.fetch(url) if url else None
        if res is not None and res.ok:
            html = snaps.load(res.snapshot_hash)
            chash = content_hash(html)
            if xcache.lookup(conn, "person", pid, chash, PROMPT_VERSION, MODEL_ID,
                             CACHE_SCHEMA_VERSION):
                stats["cache_hits"] += 1
                runs.set_task_status(conn, task, "done")
                continue
            src_id = claims.record_web_source(
                conn, url, snapshot_hash=res.snapshot_hash, http_status=200,
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
            for field in _EXTRACTORS:
                _record_blocked(conn, pid, field)
            err = res.error if res is not None else "no page url — open for the human rung"
            runs.set_task_status(conn, task, "blocked", last_error=err)

    return sum(
        1 for t in targets
        if any(c.get("state") == "blocked"
               for c in claims.claims_for(conn, "person", t["id"]))
    )


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
    gaps = _process_targets(conn, run_id, targets, fetcher, snaps, stats=stats, resume=resume)
    status = "finalized_with_open_gaps" if gaps else "finalized"
    runs.set_run_status(conn, run_id, status)
    return _build_result(conn, run_id, status, targets, stats=stats, gaps=gaps)


def run_live(plan: dict, transport: Transport, snap_root, *, email: str,
             openalex_key=None, db_path=None, optout_path=None, resume=False) -> dict:
    """A **live** scan: preflight → discovery ladder (ROR + OpenAlex) → the *same* fetch → extract
    → claim → score → export → dashboard pipeline as ``run_offline`` (D-028), now from **discovered**
    targets rather than hand-fed ones.

    Requires a contact email (fails loud without one, D-019/023); ROR is keyless, the OpenAlex
    premium ``openalex_key`` is optional. The ``transport`` serves both the open-API JSON (ROR/
    OpenAlex, via the clients) and the professor pages (via the robots-gated ``Fetcher``) — one seam,
    so a live run is exactly the cassette-tested path with httpx swapped in.
    """
    preflight.require_credentials({preflight.CONTACT_EMAIL_ENV: email})
    ror_client = _ror.RorClient(transport, email=email)
    oa_client = _openalex.OpenAlexClient(transport, email=email, key=openalex_key)
    disc = _ladder.build_targets(plan, ror_client, oa_client)

    conn = open_db(db_path) if db_path is not None else open_db()
    snaps = SnapshotStore(snap_root)
    fetcher = Fetcher(transport, snaps)                 # real backoff/sleep for live politeness
    optout = optout_mod.load_optout(optout_path)
    targets, opted_out = optout_mod.filter_targets(disc["targets"], optout)

    run_id = runs.create_run(conn)
    runs.set_run_status(conn, run_id, "deep_diving")
    stats = {"extractions": 0, "cache_hits": 0, "opted_out": opted_out, "resumed_skipped": 0,
             "discovered": len(disc["targets"]), "institutions": len(disc["institutions"])}
    gaps = _process_targets(conn, run_id, targets, fetcher, snaps, stats=stats, resume=resume)
    status = "finalized_with_open_gaps" if gaps else "finalized"
    runs.set_run_status(conn, run_id, status)
    return _build_result(conn, run_id, status, targets, stats=stats, gaps=gaps)


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
