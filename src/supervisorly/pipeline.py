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
import logging
import re
import time

from . import phases as phases_mod
from . import preflight
from .discover import ladder as _ladder
from .discover import openalex as _openalex
from .discover import orcid as orcid_mod
from .discover import ror as _ror
from .discover import roster as _roster
from .discover import sitecrawl
from .discover import websearch
from .ethics import optout as optout_mod
from .extract import chrome_prompt
from .extract import llm_claims
from .extract import llm_client
from .export import dashboard as dash
from .export import json_export as jx
from .fetch import browser_rung
from .fetch import pool as pool_mod
from .fetch import render as render_mod
from .fetch import walls
from .fetch.fetcher import Fetcher
from .fetch.normalize import content_hash, main_text
from .fetch.ratelimit import HostRateLimiter
from .fetch.snapshot import SnapshotStore
from .fetch.transport import Transport
from .model import claims, extraction_cache as xcache, runs
from .model.db import open_db, utcnow
from .score import scorer

# ExtractionCache key parts for the deterministic signal tier (cost §3b-i). The "prompt"
# and "model" are notional here — the point is a stable key so a warm re-scan skips work.
PROMPT_VERSION = "det-signal-v1"
MODEL_ID = "deterministic"
CACHE_SCHEMA_VERSION = "1"

_log = logging.getLogger(__name__)


# ── §4.1 progress events + cooperative stop ───────────────────────────────────
def _emit_progress(progress, event: tuple) -> None:
    """Fire one §4.1 progress event, never letting an observer break the scan.

    Progress is strictly advisory: a broken callback must not kill a multi-hour
    scan whose state is otherwise persisting fine, so every emit is guarded —
    log-and-continue. ``KeyboardInterrupt`` is a ``BaseException`` and is NOT
    caught here: Ctrl+C still interrupts the run (the state machine makes that
    safe — a fresh run with ``resume`` picks up the persisted work, D-029).
    """
    if progress is None:
        return
    try:
        progress(event)
    except Exception:
        _log.warning("progress callback raised on %r; continuing the scan",
                     event[0] if event else event, exc_info=True)


def _stop_requested(should_stop) -> bool:
    """Consult the cooperative-stop hook between targets.

    A RAISING hook is treated as "keep going": cancellation must be a deliberate
    ``True``, never the side effect of a buggy observer force-stopping a healthy
    run. ``KeyboardInterrupt`` propagates (same Ctrl+C reasoning as above)."""
    if should_stop is None:
        return False
    try:
        return bool(should_stop())
    except Exception:
        _log.warning("should_stop callback raised; continuing the scan", exc_info=True)
        return False


def _partial_warning_message(truncated: list[str]) -> str:
    """The §4.1 ``partial_warning`` payload for recorded PARTIAL markers — ASCII-only,
    so any console/log sink can render it (a marker derives from a URL or a
    user-supplied target name, which need not be ASCII)."""
    msg = (f"Coverage is PARTIAL - {len(truncated)} source(s) had more results than "
           f"were enumerated ({', '.join(truncated)}).")
    return msg.encode("ascii", "replace").decode("ascii")

# ── recruiting signal ─────────────────────────────────────────────────────────
# a recruiting-related sentence (candidate signal — not a classification). This is the KEYWORD
# alternation only — the sentence is found first and the keyword matched WITHIN it (see
# _first_sentence), so a long period-free blob can't trigger O(n²) backtracking on the old
# `[^.!?]*…[^.!?]*[.!?]` shape (live audit-5).
_RECRUIT = re.compile(
    r"\b(recruit\w*|looking for|accepting|seeking|opening|join (?:my|the|our) "
    r"(?:lab|group|team)|hiring|taking (?:new )?students?)\b",
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
                 r"(?:are|is)\s+due|(?:applications?|submissions?)\s+due|submit(?:s|ted|ting)?\b")
_CUE_RE = re.compile(rf"\b(?:{_DEADLINE_CUE})\b", re.IGNORECASE)
# A cue that is itself an application verb ("apply by", "applications/submissions due") is an
# application deadline by construction — no subject test needed. "submitted"/"submit" is NOT here:
# "Tax returns must be submitted by …" must stay non-application (decided by the subject test below).
_CUE_IS_APP = re.compile(r"appl|submiss", re.IGNORECASE)

# Deciding a dated deadline clause is an APPLICATION deadline (not a tuition/registration/event one
# that merely mentions a domain word). Fixed signal-tier grammar, NOT a generated per-query
# dictionary and NOT a closed list of a field's search terms (D-038 stands). A clause qualifies iff
# a "<domain> deadline" noun-phrase appears, OR the deadline cue's SUBJECT HEAD is an application
# word. The subject head is the last surviving token of the leading noun-phrase run — the run stops
# at the first grammatical boundary (a preposition/relative, a coordinator, an auxiliary/modal, an
# intransitive coordination verb, or a participle heading an object phrase). This is what stops a
# fee/deposit/surcharge due-date from being fabricated as a firm deadline (D-010/D-061) — crucially
# WITHOUT enumerating payment nouns: the harm is asymmetric, so a head that is not a *recognised*
# application word never yields a firm deadline (a genuine deadline may over-drop; a money date must
# never surface as one). Live audit-4 replaced the payment-list scheme, which leaked on any money
# noun outside the list ("application surcharge/bond/repayment is due") and on participial
# post-modifiers ("the deposit securing your PhD position is due").
_DOMAIN = r"phd|dphil|doctoral|postdocs?|postdoctoral|fellowships?|studentships?|scholarships?|positions?|vacanc(?:y|ies)"
_STRONG_APP = re.compile(r"^(?:applications?|applicants?|apply|admissions?|submissions?)$", re.IGNORECASE)
# The set of tokens that, as a subject/predicate HEAD, mark an application deadline.
_APP_HEAD = re.compile(rf"^(?:{_DOMAIN}|applications?|applicants?|apply|submissions?|admissions?)$",
                       re.IGNORECASE)
_DOMAIN_DEADLINE = re.compile(
    rf"\b(?:{_DOMAIN}|applications?|submissions?|admissions?|entry|programmes?|programs?|courses?|intake)"
    r"\s+deadline\b", re.IGNORECASE)

# Grammatical words that END the leading subject noun-phrase run: prepositions / relatives / the
# infinitive marker, coordinators, auxiliaries + modals + forms of be/have/do, and a few intransitive
# verbs that pair with a deadline cue ("applications OPEN … and close …"). This is English grammar,
# not a field-search dictionary (D-038). Anything after the head modifies it, so the head lies at the
# end of the run before the first of these.
_STOP_WORDS = frozenset("""
    for of to that which who whom whose including with from in on at by
    and but or nor
    is are was were be been being am has have had do does did
    must should shall will would can could may might
    open opens opened begin begins began start starts started
""".split())
# Leading tokens that are NOT a nominal head — determiners, possessives and personal pronouns. A run
# ending in one of these has no nominal subject (an imperative "Submit … by …" / "The deadline to …"),
# routed to the predicate/object test instead.
_NON_HEAD = frozenset("""
    the a an this that these those our your my his her its their
    no any all each every some you we they i he she it one
""".split())
# Adverbs / politeness words skipped between a subject and its verb ("applications TYPICALLY close",
# "PLEASE submit …") so they are never mistaken for the head. (``-ly`` adverbs are skipped by rule.)
_SKIP_WORDS = frozenset("please kindly also now then still already soon again once only".split())
# A participle heading an object phrase ("the deposit SECURING your place", "the fee CHARGED to your
# account") ends the subject — the head is the noun before it, not the domain word inside the object.
# Detected as an -ing/-ed token immediately followed by an object marker (determiner/possessive/prep).
_PARTICIPLE_OBJECT = frozenset("your our my his her its their the a an to for of with".split())
_WORD_RE = re.compile(r"[A-Za-z]+")


def _subject_head(clause: str, cue_start: int) -> str | None:
    """The head token (lower-cased) of the leading subject noun-phrase before the cue, or ``None``.

    ``None`` means the subject is empty or only determiners/pronouns (an imperative or a
    "The deadline to …" frame) — the caller then tests the predicate/object.
    """
    words = _WORD_RE.findall(clause[:cue_start])
    run: list[str] = []
    for i, w in enumerate(words):
        low = w.lower()
        if low in _STOP_WORDS:
            break
        if (low.endswith("ing") or low.endswith("ed")) and i + 1 < len(words) \
                and words[i + 1].lower() in _PARTICIPLE_OBJECT:
            break                                   # participle + object → subject ends before it
        if low.endswith("ly") or low in _SKIP_WORDS:
            continue                                # adverb / politeness word, not the head
        run.append(low)
    if not run or run[-1] in _NON_HEAD:
        return None
    return run[-1]


def _strong_app_in_head_position(text: str) -> bool:
    """True if a strong application word in ``text`` is a phrase HEAD — followed by a grammatical
    stop / another determiner / punctuation / end, not by a content noun it merely modifies.

    This qualifies the imperative object ("submit your APPLICATION by …") while refusing a
    pre-modifier of a money/other head ("submit your application FEE by …") — never a fabricated
    firm deadline from a fee due-date (D-010/D-061).
    """
    words = _WORD_RE.findall(text)
    for i, w in enumerate(words):
        if _STRONG_APP.match(w):
            nxt = words[i + 1].lower() if i + 1 < len(words) else None
            if nxt is None or nxt in _STOP_WORDS or nxt in _NON_HEAD:
                return True
    return False


def _is_application_deadline(clause: str) -> bool:
    """True if the clause's deadline attaches to an application, not a fee/tuition/event date.

    A "<application/domain> deadline" noun-phrase always qualifies, as does an application cue
    ("apply by …", "applications due …"). Otherwise the deadline cue's SUBJECT HEAD must be a
    recognised application word — so "the application fee/surcharge is due", "the deposit securing
    your PhD position is due" and "course registration for PhD students is due" (heads: fee /
    surcharge / deposit / registration) do NOT qualify, while "Applications close" / "PhD
    studentship closes" do. With no nominal subject (an imperative "Submit your application by …")
    a strong application word standing as a predicate head qualifies it.
    """
    if _DOMAIN_DEADLINE.search(clause):
        return True
    cue = _CUE_RE.search(clause)
    if not cue:
        return False
    if _CUE_IS_APP.search(cue.group(0)):
        return True
    head = _subject_head(clause, cue.start())
    if head is not None:
        return bool(_APP_HEAD.match(head))
    return _strong_app_in_head_position(clause[cue.end():])
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
# common abbreviations map to the same indices — real pages write "15 Jan 2027", "30 Sept 2026",
# "Apply by Feb 28, 2027" (live audit-3: full-only names silently dropped very common deadlines).
_MONTHS.update({"jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7,
                "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12})
_ORD = r"(?:st|nd|rd|th)?"          # optional ordinal suffix: 1st, 2nd, 3rd, 4th …
_ISO = re.compile(r"\b(20\d{2})-(\d{1,2})-(\d{1,2})\b")
# ``\.?`` tolerates a trailing period on an abbreviated month ("1 Dec. 2026"); the month word is
# validated against _MONTHS in _iso_from_match, so a non-month word still yields None.
_DMY = re.compile(rf"\b(\d{{1,2}}){_ORD}\s+([A-Za-z]+)\.?\s+(20\d{{2}})\b")   # 1[st] Dec[.] 2026
_MDY = re.compile(rf"\b([A-Za-z]+)\.?\s+(\d{{1,2}}){_ORD},?\s+(20\d{{2}})\b") # Dec[.] 1[st], 2026
_NUM = re.compile(r"\b(\d{1,2})/(\d{1,2})/(20\d{2})\b")                    # 01/12/2026 (numeric)
# The period after an abbreviated month ("1 Dec. 2026") otherwise reads as a sentence terminator to
# _sentences and splits the date in half — strip it before sentence-splitting (live audit-3).
# The strip is for ANALYSIS only: it rewrites the text, so a quote taken from the stripped text is
# not verbatim in the snapshot and the D-010 quote gate rejects the claim (live audit-5). The
# deadline extractor therefore maps its matched sentence back to the unstripped text for the quote.
_ABBR_MONTH_DOT = re.compile(r"\b(jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec)\.", re.IGNORECASE)


def _strip_month_dots(text: str) -> tuple[str, list[int]]:
    """``text`` with abbreviated-month dots removed, plus a monotonic stripped→raw index map.

    The transform only ever DELETES the "." after a month abbreviation, so ``idx[i]`` is the raw
    position of stripped character ``i`` — the raw slice of a stripped span is verbatim page text.
    """
    out: list[str] = []
    idx: list[int] = []
    pos = 0
    for m in _ABBR_MONTH_DOT.finditer(text):
        dot = m.end() - 1                       # the "." the match ends on
        out.append(text[pos:dot])
        idx.extend(range(pos, dot))
        pos = m.end()                           # skip the dot itself
    out.append(text[pos:])
    idx.extend(range(pos, len(text)))
    return "".join(out), idx


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
    {"id": "students_signal", "label": "Students / lab members", "kind": "filter",
     "datatype": "string"},
    {"id": "industry_signal", "label": "Industry / collaborations", "kind": "filter",
     "datatype": "string"},
    {"id": "social", "label": "Advertised social profile", "kind": "display",
     "datatype": "string"},
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


def _sentence_spans(text: str):
    """Yield ``(sentence, start, end)`` — the same split as ``_sentences`` but with offsets."""
    pos = 0
    for m in re.finditer(r"(?<=[.!?])\s+", text):
        yield text[pos:m.start()], pos, m.start()
        pos = m.end()
    yield text[pos:], pos, len(text)


# Split a sentence into subject-bearing clauses on ``;`` and on a coordinating conjunction
# (and/but/or). A conjunction is NOT a clause break when either (a) a deadline cue verb follows it —
# a coordinated VERB sharing the prior subject ("applications open on X and close on Y") — or (b) the
# left coordinand is a short bare noun-phrase with no cue/date of its own — coordinated SUBJECTS
# sharing one downstream cue ("Applications and supporting documents are due by X"), live audit-4
# finding 2. Appositive commas ("…, including the studentship, …") are not split either.
_CONJ_SPLIT = re.compile(r"(;|\s+(?:and|but|or)\s+)", re.IGNORECASE)
_COORD_VERB_AFTER = re.compile(
    r"^(?:closes?|closing|due|deadline|submits?|submitted|apply|opens?)\b", re.IGNORECASE)


def _is_bare_subject(text: str) -> bool:
    """A left coordinand that is a short subject noun-phrase with no cue/date of its own — so its
    coordinating conjunction joins two SUBJECTS of one downstream cue, not two clauses."""
    t = text.strip()
    if _CUE_RE.search(t) or _dates_in(t):
        return False
    return len(_WORD_RE.findall(t)) <= 4


def _clauses(sentence: str):
    """Yield the clauses of a sentence (split on ``;`` and clause-level conjunctions), dates whole."""
    masked = _DATE_COMMA.sub(lambda m: m.group(1) + "\x00" + m.group(2), sentence)
    parts = _CONJ_SPLIT.split(masked)
    current = parts[0]
    for i in range(1, len(parts), 2):
        delim = parts[i]
        nxt = parts[i + 1] if i + 1 < len(parts) else ""
        break_here = True
        if delim.strip() != ";":                       # a coordinating conjunction, not a semicolon
            after = nxt.lstrip()
            if _COORD_VERB_AFTER.match(after) or _is_bare_subject(current):
                break_here = False                     # coordinated verb / coordinated subject
        if break_here:
            if current.strip():
                yield current.replace("\x00", ",")
            current = nxt
        else:
            current = current + delim + nxt
    if current.strip():
        yield current.replace("\x00", ",")


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
    return _first_sentence(_RECRUIT, html)


def extract_deadline(html: str):
    """Return (iso_date, quote, confidence) for an application deadline, or None.

    A date qualifies only when a deadline **verb cue**, an **application-context** word, and a
    full date all share ONE clause — so the date, the deadline, and the subject genuinely belong
    together. ``confidence`` is ``quoted_official`` for a firm spelled-out date, or ``inferred``
    (a *watch* date, D-061) when the clause is projected ("usually"/"each year"), the date is
    numeric/locale-ambiguous, or a strong signal ties the date to another event. Within the
    clause the date nearest the cue is chosen (so "…and close on 1 Dec" binds the close date).

    The abbreviated-month dot is stripped for ANALYSIS only; the returned quote is the VERBATIM
    slice of the unstripped text ("Dec." keeps its period), so the D-010 quote gate accepts it.
    """
    raw = main_text(html)
    stripped, idx = _strip_month_dots(raw)
    for sentence, start, end in _sentence_spans(stripped):
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
            quote = raw[idx[start]:idx[end - 1] + 1].strip() if end > start else ""
            return iso, quote, ("inferred" if projected else "quoted_official")
    return None


# ── the extra collectors the author asked for (students / companies / social) ─────────────────
# Each is a deterministic candidate signal quoted from the professor's own public page — the LLM
# synthesist confirms/structures it in Stage 2 (D-009/D-021). Walled social CONTENT (a recruiting
# post on X/LinkedIn) is never fetched here — only an *advertised* link in the visible text is
# recorded; the actual walled page goes to the human rung (D-039/043). Like _RECRUIT these are
# KEYWORD alternations matched within one sentence at a time (live audit-5: the old
# `[^.!?]*…[^.!?]*[.!?]` shape was O(n²) on period-free text).
_STUDENTS = re.compile(
    r"\b(current\s+(?:phd\s+)?(?:students?|members?)|lab\s+members?|group\s+members?|"
    r"team\s+members?|alumni|former\s+students?|advisees?|graduated?\s+students?|"
    r"phd\s+students?\s+in\s+(?:my|the)\s+(?:group|lab))\b",
    re.IGNORECASE,
)
_INDUSTRY = re.compile(
    r"\b(industry\s+(?:partner\w*|collaborat\w*|experience|funding)|"
    r"in\s+collaboration\s+with|collaborat\w*\s+with|partnered?\s+with|"
    r"consult\w*\s+(?:for|at)|funded\s+by|sponsored\s+by)\b",
    re.IGNORECASE,
)
_SOCIAL_URL = re.compile(
    r"https?://(?:www\.)?(?:twitter\.com|x\.com|linkedin\.com/in|github\.com|"
    r"[a-z0-9.-]*mastodon[a-z0-9.-]*|bsky\.app)/[^\s\"'<>)]+",
    re.IGNORECASE,
)
# Walled social hosts — an advertised link here points to a page the tool must NOT scrape
# (D-039/044), so the link is recorded AND reading the walled page becomes a human-rung task.
# This host set is page-classification structure (an enum of source types, allowed under D-038 —
# the same class as the login-wall marker phrases), not a per-field search-term dictionary.
# github.com / bsky.app / mastodon are deliberately absent: D-044 marks those tool-fetchable.
#: Profile hosts that advertise a researcher but refuse machines. Fetching one can only end
#: in a 403 or a login page, so they are routed to the human rung and never scraped
#: (D-039/D-043/D-044) — a rule about *how* a source is reached, unaffected by
#: [D-072](../../docs/DECISIONS.md#d-072) unlocking documented APIs.
#:
#: Each entry was measured, not assumed (2026-07-28, plain GET with the project user-agent):
#:   researchgate.net  403, and its robots.txt is SELECTIVE — so the robots gate ALLOWS
#:                     /profile/ and the wall is only discovered by being refused. This is
#:                     the one that must be listed here, because nothing else stops it.
#:   scholar.google.*  302 away, robots.txt Disallow: /
#:   academia.edu      403, robots.txt Disallow: /
#: ORCID resolution surfaced a real ResearchGate profile URL as a professor's only page,
#: which is how the gap was found.
#: ONE definition, in ``fetch/walls.py``, shared with the server-side renderer. It used to
#: live here while the renderer relied on its own weaker guard ("a non-2xx is a refusal") —
#: and a real ResearchGate profile walked straight through it, because that host answers 403
#: to a plain client and 200 to Chromium. Two copies of a refusal rule is two chances to
#: disagree, and the permissive copy is the one that ends up on the network.
_WALLED_SOCIAL = walls.WALLED_HOSTS


def _first_sentence(rx, html):
    """First sentence containing the keyword, verbatim — first match wins, bounded work per
    sentence (the same approach the deadline extractor uses)."""
    for sentence in _sentences(main_text(html)):
        if rx.search(sentence):
            s = sentence.strip()
            return s, s, "quoted_official"
    return None


def extract_students_signal(html: str):
    """A sentence naming the professor's students / lab members / alumni, or None."""
    return _first_sentence(_STUDENTS, html)


def extract_industry_signal(html: str):
    """A sentence naming an industry collaboration / company / sponsor, or None."""
    return _first_sentence(_INDUSTRY, html)


def extract_social(html: str):
    """An advertised social/profile URL in the page's visible text, or None.

    Only the *link* is recorded (public). The walled page it points to (e.g. a recruiting post on
    X) is NEVER fetched here — it is routed to the human rung (D-039/043)."""
    m = _SOCIAL_URL.search(main_text(html))
    if not m:
        return None
    url = m.group(0).rstrip(".,);")
    return url, url, "quoted_official"


# field_id → extractor. Adding a field is adding a row here + a descriptor above (D-038).
_EXTRACTORS = {
    "recruiting_signal": extract_recruiting_signal,
    "deadline": extract_deadline,
    "students_signal": extract_students_signal,
    "industry_signal": extract_industry_signal,
    "social": extract_social,
}


def _crawl_more(conn, pid, entry_url, fetcher, snaps, *, filled, stats, complete=None,
                max_pages=sitecrawl.MAX_PAGES):
    """Walk a few pages out from the professor's own page, looking for the fields still empty.

    **Why the entry page is usually not enough.** Rung 7 finds the page a professor controls,
    and that page is typically a staff card — title, email, publications. "I am recruiting PhD
    students for 2027" lives one click away on *Join the group* or *Vacancies*. Reading only
    the entry point measurably finds nothing.

    Bounded by ``sitecrawl`` (depth 2, same host, 20 pages, link-text filtered) and bounded
    again here: the walk **stops as soon as every field has an answer**, so a professor whose
    staff card already says everything costs one extra request, not twenty.

    Politeness is not re-implemented — pages come through the ordinary ``Fetcher``, so robots,
    rate limiting, snapshots and the ``--ignore-robots`` override all keep their single
    definition. A page this walk cannot read is simply a branch that ends.
    """
    want = [f for f in _EXTRACTORS if f not in filled]
    if not want or not entry_url:
        return

    def fetch(u):
        res = fetcher.fetch(u)
        return (bool(res and res.ok), snaps.load(res.snapshot_hash) if res and res.ok else "")

    pages, truncated = sitecrawl.crawl(entry_url, fetch, max_pages=max_pages)
    if truncated:
        stats["crawl_truncated"] = stats.get("crawl_truncated", 0) + 1
    for page_url, html in pages[1:]:                  # [0] is the entry page, already read
        if not want:
            break
        stats["crawl_pages"] = stats.get("crawl_pages", 0) + 1
        src_id = claims.record_web_source(
            conn, page_url, snapshot_hash=content_hash(html), http_status=200,
            source_tier=_source_tier(page_url),
            robots_allowed=fetcher.robots_verdict(page_url),
        )
        still: list[str] = []
        for field in want:
            found = _EXTRACTORS[field](html)
            if not found:
                still.append(field)
                continue
            # A value found here is a real find on a real page — record it, and do NOT record
            # an absence for the fields this page happens not to mention. The entry page
            # already recorded the honest `searched_absent`; a second absence per crawled page
            # would bury it under noise without adding a fact.
            rec = _record_evidence(conn, pid, field, found, src_id=src_id,
                                   snapshot_hash=content_hash(html), html=html)
            if rec and rec.ok:
                stats["crawl_claims"] = stats.get("crawl_claims", 0) + 1
            else:
                still.append(field)
        if complete is not None and still:
            _model_claims(conn, pid, html=html, url=page_url, src_id=src_id,
                          snapshot_hash=content_hash(html), complete=complete,
                          filled=set(_EXTRACTORS) - set(still), stats=stats)
        want = still


def _model_claims(conn, pid, *, html, url, src_id, snapshot_hash, complete, filled, stats):
    """The D-073 pass: let a model point at sentences the regexes could not shape-match.

    **It fills gaps; it never overrules a regex.** Where a deterministic extractor already
    found a value that value stands — it is free, reproducible, and was quote-gated too, and
    a model that disagrees about a date it can also see is not evidence of anything. So
    ``filled`` is subtracted from the fields we ask about, which also shrinks the prompt.

    Everything the model returns is a *proposal* until ``llm_claims.verify`` finds its quote
    verbatim in this snapshot, and ``record_claim`` then applies the identical gate a second
    time on the way into the database. A hallucinated deadline cannot survive either pass.

    Rejections are counted rather than swallowed (D-073 bound 6): a model whose quotes stop
    matching is a signal worth seeing, not a quiet fade back to an empty dashboard.
    """
    fields = tuple(f for f in llm_claims.PROPOSABLE_FIELDS if f not in filled)
    if not fields:
        return
    text = main_text(html)[:llm_claims.MAX_PAGE_CHARS]
    try:
        raw = complete(llm_claims.build_prompt(text, url, fields=fields))
    except Exception:                      # noqa: BLE001 — fail-closed by design (D-068/D-073)
        stats["model_unavailable"] = stats.get("model_unavailable", 0) + 1
        return
    kept, dropped = llm_claims.verify(llm_claims.parse_proposals(raw, fields=fields), html)
    stats["model_proposals"] = stats.get("model_proposals", 0) + len(kept) + len(dropped)
    stats["model_rejected"] = stats.get("model_rejected", 0) + len(dropped)
    for p in kept:
        rec = claims.record_claim(
            conn, entity_kind="person", entity_id=pid, field=p.field,
            value=p.value, quote=p.quote, source_id=src_id, snapshot_hash=snapshot_hash,
            snapshot_html=html, observed_at=utcnow(), extractor_agent="model",
            # `derived`, not `quoted_official`: the SENTENCE is official and verbatim, but the
            # reading of it — "this means recruiting" — is the model's. A regex that matched a
            # literal cue earns `quoted_official`; an interpretation of prose does not, and
            # flattening the two would hide which cells a model decided.
            confidence="derived",
        )
        if rec.ok:
            claims.supersede_prior(conn, "person", pid, p.field, rec.claim_id)
            stats["model_claims"] = stats.get("model_claims", 0) + 1


def _record_evidence(conn, pid, field, found, *, src_id, snapshot_hash, html):
    """Record one field's deterministic result with correct precedence.

    A fresh **value** supersedes prior heads (freshest evidence wins). An **absence**
    (``searched_absent``) never clobbers a **human-assisted** value (D-043/D-046/D-049) — a
    re-scan that finds nothing does not erase the human rung's answer. It DOES supersede a stale
    *deterministic* value: reaching the page again and affirmatively finding nothing is a
    verified removal, not a transient failure, and the delta must surface it (live audit-5).
    Absences also supersede prior *non-value* heads so they don't pile up.
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
    if claims.live_value_is_human(conn, "person", pid, field):
        return None                       # keep the human-rung answer; never downgrade to absent
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


# Known third-party aggregators — a page there is not the professor's own official page (D-047).
_AGGREGATORS = re.compile(
    r"(researchgate\.net|academia\.edu|linkedin\.com|scholar\.google|semanticscholar\.org|"
    r"orcid\.org|twitter\.com|x\.com)", re.IGNORECASE)


def _source_tier(url: str | None) -> str:
    """Coarse trust tier for a fetched page — an aggregator is ``community_unverified``, an
    institutional/personal page is ``official_institutional`` (don't over-claim provenance)."""
    return "community_unverified" if _AGGREGATORS.search(url or "") else "official_institutional"


def _target_open_gap(conn, pid) -> bool:
    """True if the target still has an open gap for the human rung: any field ``blocked``
    (unreached), or an advertised **walled** social page the tool recorded but must not scrape —
    reading it is a human-rung task (D-039/044), so the run cannot claim ``finalized`` while a
    known walled recruiting source went unchecked (Phase L3).

    The walled-social condition is discharged when its human-rung read task is no longer
    incomplete — i.e. the browser-fill consumer (``fetch.browser_fill``, the D-064 consumer
    half) ingested the walled page and closed the task. Until then the task is the durable
    record that the check is still owed, so a walled link alone keeps the gap open exactly
    as before."""
    cs = claims.claims_for(conn, "person", pid)
    if any(c.get("state") == "blocked" for c in cs):
        return True
    walled_advertised = any(
        c.get("field") == "social" and c.get("state") == "value"
        and isinstance(c.get("value"), str) and _WALLED_SOCIAL.search(c["value"])
        for c in cs)
    if not walled_advertised:
        return False
    placeholders = ",".join("?" * len(runs.INCOMPLETE_TASK_STATUSES))
    row = conn.execute(
        f"SELECT 1 FROM task WHERE target_kind='person' AND target_ref=? AND stage='gap_fill' "
        f"AND status IN ({placeholders}) LIMIT 1",
        (pid, *sorted(runs.INCOMPLETE_TASK_STATUSES)),
    ).fetchone()
    return row is not None


# ── the consumer half of the D-064 browser seam ───────────────────────────────
# Minimal public wrappers over the deep-dive's private machinery, so the browser-fill
# consumer (``fetch.browser_fill``) runs the SAME extractors / evidence path / gap
# computation as ``_process_targets`` instead of duplicating them.

#: The signal fields a browser-ingested page fills. ``social`` is deliberately absent:
#: the advertised-profile link is a display value recorded from the professor's own page,
#: not something re-extracted off the walled page itself.
BROWSER_FILL_FIELDS = ("recruiting_signal", "deadline", "students_signal", "industry_signal")


def run_signal_extractors(html: str) -> dict:
    """The deep-dive's deterministic signal extractors over a page, field_id → result.

    Each value is ``(value, quote, confidence)`` or ``None`` — the same functions and
    semantics ``_process_targets`` uses (``_EXTRACTORS``), restricted to
    ``BROWSER_FILL_FIELDS``."""
    return {field: _EXTRACTORS[field](html) for field in BROWSER_FILL_FIELDS}


def record_field_evidence(conn, pid, field, found, *, src_id, snapshot_hash, html):
    """Public ``_record_evidence``: one field's deterministic result with the deep-dive's
    precedence (a value supersedes; an absence never clobbers a human-assisted value)."""
    return _record_evidence(conn, pid, field, found, src_id=src_id,
                            snapshot_hash=snapshot_hash, html=html)


def recompute_run_status(conn, run_id) -> str:
    """``finalized`` vs ``finalized_with_open_gaps`` from current claim/task state (D-049).

    The same computation ``run_offline``/``reexport`` derive their status from —
    ``_target_open_gap`` over the run's person targets — so a gap closed by the browser
    fill flips the run to ``finalized`` exactly the way a re-export would see it."""
    rows = conn.execute(
        "SELECT DISTINCT target_ref FROM task WHERE run_id=? AND target_kind='person'",
        (run_id,)).fetchall()
    gaps = sum(1 for r in rows if _target_open_gap(conn, r["target_ref"]))
    return "finalized_with_open_gaps" if gaps else "finalized"


# ── the D-056 shortlist gate ──────────────────────────────────────────────────
#: Default deep-dive shortlist size (D-056): only the top-N by research fit get the
#: expensive per-page deep-dive; every enumerated professor still appears in the export.
DEFAULT_SHORTLIST_SIZE = 40


def _topic_overlap(target: dict, topic_ids: list[str]) -> int:
    """How many of the plan's resolved topic ids appear in the target's own topics."""
    own = set(target.get("topic_ids") or [])
    return sum(1 for t in topic_ids if t in own)


def _apply_shortlist(targets: list[dict], exempt_keys: set, topic_ids: list[str],
                     size: int) -> list[dict]:
    """D-056: rank ``targets`` deterministically and deep-dive only the top ``size``.

    Ranking key: topic overlap with the plan's resolved topics (desc), tie-broken by
    works_count (desc); Python's stable sort keeps discovery order beyond that. Targets
    whose key is in ``exempt_keys`` (named ``--targets`` professors, D-066) are NEVER
    gated — the user asked for them by name. The non-shortlisted are NOT dropped: the
    caller still exports them (fields ``never_attempted`` — an honest "not checked yet").

    A plan with NO resolved topic ids still gets gated: every overlap is then 0 and the
    ranking falls back to works_count alone. Passing all targets through ungated in that
    case would re-open the very defect this gate fixes (6,123 discovered targets → a 2+
    hour deep-dive), so the bounded-by-default behavior is the safer option.
    """
    gated = [t for t in targets
             if (t.get("openalex_id") or t.get("id")) not in exempt_keys]
    if len(gated) <= size:
        return list(targets)
    ranked = sorted(gated, key=lambda t: (-_topic_overlap(t, topic_ids),
                                          -int(t.get("works_count") or 0)))
    keep = {id(t) for t in ranked[:size]}
    return [t for t in targets
            if id(t) in keep or (t.get("openalex_id") or t.get("id")) in exempt_keys]


def _process_targets(conn, run_id, targets, fetcher, snaps, *, stats, resume,
                     progress=None, should_stop=None, orcid_client=None,
                     renderer=None, render_all=False, complete=None, search=None,
                     crawl=False) -> int:
    """Deep-dive each target (fetch → extract → claim) — the shared core of run_offline/run_live.

    Returns the gap count (targets with any still-``blocked`` field or an unchecked walled social
    page), derived from claim state so the run status can never contradict the exported cells
    (D-046/D-049). A target with no page URL (e.g. an OpenAlex professor with no discoverable
    homepage) is an honest open gap for the human rung, never a fabricated value.

    Emits the §4.1 ``("deep_dive_progress", i, k)`` event after every target (i = 1-based
    count done, k = total; a resume-skipped target counts as done). Between targets it
    consults ``should_stop()``: on True it stops cleanly at that checkpoint and marks
    ``stats["cancelled"]`` — the untouched targets keep every field ``never_attempted``
    (an honest "not checked yet"), their completed siblings' claims persist, and the
    caller reports the run ``cancelled`` instead of a finalized status.
    """
    urls, prerendered = _prerender_batch(conn, targets, renderer, orcid_client,
                                         stats=stats, resume=resume, render_all=render_all,
                                         search=search)
    total = len(targets)
    for i, t in enumerate(targets, 1):
        _deep_dive_one(conn, run_id, t, fetcher, snaps, stats=stats, resume=resume,
                       orcid_client=orcid_client, renderer=renderer, render_all=render_all,
                       url_override=urls.get(t["id"]), prerendered=prerendered,
                       complete=complete, search=search, crawl=crawl)
        _emit_progress(progress, ("deep_dive_progress", i, total))
        if _stop_requested(should_stop):
            stats["cancelled"] = True
            break
    return sum(1 for t in targets if _target_open_gap(conn, t["id"]))


def _prerender_batch(conn, targets, renderer, orcid_client, *, stats, resume, render_all,
                     search=None):
    """Resolve every deep-dive URL and render them all concurrently, once, before the loop.

    Returns ``(url_by_target_id, page_by_url)``. Both are empty when render-all is off or the
    renderer cannot batch, and the run then behaves exactly as it did before.

    **Why this exists.** ``BatchRenderer`` was built as a primitive with no production caller,
    because a deep dive that renders one page in twenty has nothing to be concurrent about.
    Render-all changes that: now every target wants a browser, so the serial loop would pay
    one page-load latency per professor, in sequence. Rendering them as a batch is the same
    pages, the same refusal gate, the same politeness — ``HostPool`` keeps one host strictly
    serial (CC-3.3/CC-3.4) — just not one-at-a-time across *different* hosts.

    **The URL is resolved here, not twice.** ``_page_url_for`` can ask ORCID's API for a
    professor's real page, so calling it in both this pass and the loop would double those
    requests. It is called once and the answer handed to the loop.

    Resume-skipped targets are neither resolved nor rendered: a resumed run must not pay for
    work whose whole point is that it is already done.
    """
    if not render_all or renderer is None or not hasattr(renderer, "render_many"):
        return {}, {}
    urls: dict[str, str] = {}
    for t in targets:
        if resume and runs.target_stage_done(conn, "person", t["id"], "deep_dive"):
            continue
        url = _page_url_for(t, orcid_client, stats, search)
        if url:
            urls[t["id"]] = url
    if not urls:
        return urls, {}
    pages = renderer.render_many(urls.values())
    stats["render_batch_size"] = len(pages)
    return urls, pages


def _page_url_for(t: dict, orcid_client, stats, search=None) -> str | None:
    """The page to deep-dive — resolving an ORCID profile URL to the professor's real page.

    ``ladder._author_url`` falls back to the author's ORCID profile because OpenAlex almost
    never carries a homepage. But that profile is a JavaScript app whose HTML holds no
    record, so fetching it can only ever produce ``blocked`` — measured at 52 of 52 targets,
    a whole run with zero facts (`BLOCKERS.md` B-003). Asking ORCID's public API for the
    record's researcher URLs is the same fact from a machine-readable endpoint (D-072).

    Walled hosts are skipped rather than fetched: a ResearchGate or LinkedIn URL is a real
    recruiting source the tool must NOT scrape (D-039/D-043/D-044), and the existing
    ``walled_social`` path already routes advertised ones to the human rung.

    When the record lists no usable page we fall back to **the ORCID profile itself**. That
    reverses an optimisation D-072 added, and the reversal is the point: D-072 skipped this
    fetch because the profile "is known in advance to be walled", which was true while the
    only reader was an HTTP client. With the render rung (D-073) it is no longer true — the
    profile is public, robots-allowed, and merely needs JavaScript, and a browser reads it
    (measured: 29,109 characters for a real Cairo professor). Skipping it now would mean
    refusing to open the one page the new capability exists to open.

    The cost of being wrong is bounded and unchanged: with no renderer available the fetch
    returns the JavaScript shell, the wall detector fires, and the target is `blocked` exactly
    as it was before — one wasted request, never a fabricated fact.
    """
    url = t.get("url")
    if orcid_client is not None and t.get("url_kind") == "orcid":
        for candidate in orcid_client.researcher_urls(t.get("orcid") or url):
            if _WALLED_SOCIAL.search(candidate):
                continue
            stats["orcid_resolved"] = stats.get("orcid_resolved", 0) + 1
            return candidate
    # Rung 7 (last resort): we are about to deep-dive nothing, or a registry profile that
    # measurably never carries a recruiting sentence. One generated query per professor can
    # find the page they actually control — 88% of a real shortlist had none on record.
    # Absent a search key this is None and the target keeps exactly today's fate.
    if search is not None and (not url or t.get("url_kind") == "orcid"):
        names = t.get("institution_names") or []
        hits = search(t.get("name") or "", names[0] if names else None)
        if hits:
            stats["search_resolved"] = stats.get("search_resolved", 0) + 1
            return hits[0]
    return url


def _render_page(conn, snaps, url, res, renderer, stats, prerendered=None, robots_allowed=True):
    """Render a JavaScript page and store it as a snapshot, or None if it stays unreadable.

    Returns ``(html, source_id, snapshot_hash)`` so the caller cites what it actually read.

    ``prerendered`` is the batch produced by ``_prerender_batch`` before the loop started. A
    URL present there has already been through the browser — and through the *same*
    ``_refusal`` gate, because ``BatchRenderer`` inherits it — so we use that page instead of
    driving a second browser for it. A URL that is present but maps to ``None`` was tried and
    failed; it is not retried serially, or a batch of 200 dead URLs would be paid for twice.

    The rendered text goes through the SAME wall detector that sent us here. A login page
    renders perfectly well — it is a real page, it just is not the professor's — so without
    this second check "render it" would quietly become "defeat it", which is the one thing
    D-039/D-043 forbid. Provenance is recorded truthfully as a server-side read: robots WAS
    consulted, and the host's normal tier applies (an institutional page is no less
    institutional for having been rendered).
    """
    if prerendered is not None and url in prerendered:
        page = prerendered[url]
        stats["render_batched"] = stats.get("render_batched", 0) + 1
    elif renderer is None:
        return None
    else:
        page = renderer.render(url)
    if page is None:
        return None
    ingested = browser_rung.ingest_page(
        conn, snaps.root, final_url=page.final_url, text=page.text, title=page.title,
        source_tier=_source_tier(page.final_url or url), robots_allowed=robots_allowed,
    )
    html = snaps.load(ingested["snapshot_hash"])
    if _roster.detect_login_wall(html):
        stats["render_still_walled"] = stats.get("render_still_walled", 0) + 1
        return None
    stats["rendered"] = stats.get("rendered", 0) + 1
    return html, ingested["source_id"], ingested["snapshot_hash"]


def _deep_dive_one(conn, run_id, t, fetcher, snaps, *, stats, resume,
                   orcid_client=None, renderer=None, render_all=False,
                   url_override=None, prerendered=None, complete=None, search=None,
                   crawl=False) -> None:
    """One target of ``_process_targets``: fetch → extract → claim (semantics per its docstring).

    ``render_all`` promotes Chromium from fallback to main reader — see the comment at the
    render decision below. It never changes what a *failure* means: a page that fetched fine
    and merely could not be rendered keeps its fetched text, because the alternative is
    reporting our own missing browser as the site's wall.
    """
    pid = t["id"]
    if resume and runs.target_stage_done(conn, "person", pid, "deep_dive"):
        stats["resumed_skipped"] += 1
        return
    task = runs.add_task(conn, run_id, "person", pid, stage="deep_dive")
    url = (url_override if url_override is not None
           else _page_url_for(t, orcid_client, stats, search))
    res = fetcher.fetch(url) if url else None
    src_id_override = snapshot_hash_override = None
    if res is not None and res.ok:
        html = snaps.load(res.snapshot_hash)
        walled = _roster.detect_login_wall(html)
        if walled or render_all:
            # Two very different reasons to start a browser, and they must not share a fate.
            #
            # WALLED — a robots-allowed 200 whose text is not the professor's content. Two
            # different things land here:
            #   * a LOGIN or bot wall  — a refusal; goes to the human rung untouched.
            #   * a JAVASCRIPT SHELL   — the page said yes and then needed a browser. That is
            #                            our reader's limit, not a wall (D-073).
            # So try rendering, then apply the SAME wall detector to what came back: if the
            # rendered text still looks like a wall, it was a wall, and nothing was defeated.
            #
            # RENDER_ALL — Chromium is the main reader, not the fallback. The HTTP read only
            # ever sees what the server sent; anything a script writes into the page is
            # invisible to it, and a page does not have to look broken for that to cost us a
            # sentence. So we render whether or not the fetched text tripped the detector.
            rendered = _render_page(conn, snaps, url, res, renderer, stats, prerendered,
                                    robots_allowed=fetcher.robots_verdict(url))
            if rendered is not None:
                html, src_id_override, snapshot_hash_override = rendered
            elif walled:
                for field in _EXTRACTORS:
                    _record_blocked(conn, pid, field)
                runs.set_task_status(conn, task, "blocked",
                                     last_error="login/bot wall — routed to the human rung")
                return
            else:
                # Render-all asked for a browser and did not get one — no Playwright, a
                # timeout, a robots refusal on the redirect. The page itself was fine, so
                # falling back to the fetched HTML loses nothing that was ever there. Marking
                # it blocked here would invent a wall out of our own missing dependency.
                stats["render_fallback"] = stats.get("render_fallback", 0) + 1
        chash = content_hash(html)
        if xcache.lookup(conn, "person", pid, chash, PROMPT_VERSION, MODEL_ID,
                         CACHE_SCHEMA_VERSION):
            stats["cache_hits"] += 1
            runs.set_task_status(conn, task, "done")
            return
        # When the page was rendered, the evidence must cite the RENDERED snapshot: that is
        # the text the quote was found in, and a quote verified against one snapshot while
        # citing another is exactly the provenance break D-010 exists to prevent.
        if src_id_override is not None:
            src_id, evidence_hash = src_id_override, snapshot_hash_override
        else:
            src_id = claims.record_web_source(
                conn, res.final_url or url, snapshot_hash=res.snapshot_hash, http_status=200,
                source_tier=_source_tier(res.final_url or url),
                # The real verdict, not the fact that we fetched it. On an ordinary run these
                # are the same; under --ignore-robots they are not, and the export must carry
                # the one that is true.
                robots_allowed=fetcher.robots_verdict(res.final_url or url),
            )
            evidence_hash = res.snapshot_hash
        claim_ids: list[str] = []
        walled_social = None
        filled: set[str] = set()
        for field, extractor in _EXTRACTORS.items():
            found = extractor(html)
            if found:
                filled.add(field)
            rec = _record_evidence(conn, pid, field, found, src_id=src_id,
                                   snapshot_hash=evidence_hash, html=html)
            if rec and rec.ok:
                claim_ids.append(rec.claim_id)
            if field == "social" and found and _WALLED_SOCIAL.search(found[0]):
                walled_social = found[0]
        if complete is not None:
            # D-073: the regexes have had their turn and `filled` says where they landed. The
            # model is asked only about what is left, and only about this page.
            _model_claims(conn, pid, html=html, url=res.final_url or url, src_id=src_id,
                          snapshot_hash=evidence_hash, complete=complete,
                          filled=filled, stats=stats)
        if crawl:
            # The staff card rarely says whether they are recruiting; the page it links to
            # does. Bounded hard, and skipped entirely once every field has an answer.
            _crawl_more(conn, pid, res.final_url or url, fetcher, snaps,
                        filled={f for f in _EXTRACTORS if claims.live_value(
                            conn, "person", pid, f)},
                        stats=stats, complete=complete)
        if walled_social:
            # An advertised walled social page (X/Twitter/LinkedIn) is a known recruiting
            # source the tool must NOT scrape (D-039/044): mint an awaiting_human task for it
            # (the roster.route_directory pattern, Phase L3 DoD) — the target stays an open
            # gap via _target_open_gap, so the run finalizes WITH open gaps, not `finalized`.
            walled_task = runs.add_task(conn, run_id, "person", pid,
                                        stage="gap_fill", phase="human")
            runs.set_task_status(
                conn, walled_task, "awaiting_human",
                last_error=f"walled social page advertised ({walled_social}) — "
                           "read it by hand and return it via the Phase-3 MD grammar")
        xcache.record(conn, "person", pid, chash, PROMPT_VERSION, MODEL_ID,
                      CACHE_SCHEMA_VERSION, claim_ids)
        stats["extractions"] += 1
        runs.set_task_status(conn, task, "done")
    else:
        for field in _EXTRACTORS:
            _record_blocked(conn, pid, field)
        if res is not None:
            err = res.error
        elif t.get("url_kind") == "orcid":
            # Distinct from "no page url": the target HAS an ORCID, its public record was
            # read, and it simply lists no page we may fetch. Saying so keeps the human-rung
            # note actionable — the reader knows the registry was checked, not skipped.
            err = "ORCID record lists no fetchable researcher URL — open for the human rung"
        else:
            err = "no page url — open for the human rung"
        runs.set_task_status(conn, task, "blocked", last_error=err)


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
    # Cassettes are synthetic — no real host to be polite to, so neither the backoff nor the
    # per-host rate limiter should actually sleep (keeps the offline suite fast).
    fetcher = Fetcher(transport, snaps, sleep=lambda _s: None,
                      rate_limiter=HostRateLimiter(min_interval=0.0))

    # Opt-out is enforced BEFORE any fetch: a suppressed person is never even requested (D-023).
    optout = optout_mod.load_optout(optout_path)
    targets, opted_out = optout_mod.filter_targets(targets, optout)

    run_id = runs.create_run(conn)
    runs.set_run_status(conn, run_id, "deep_diving")

    stats = {"extractions": 0, "cache_hits": 0, "opted_out": opted_out, "resumed_skipped": 0}
    _t_dive = time.monotonic()
    gaps = _process_targets(conn, run_id, targets, fetcher, snaps, stats=stats, resume=resume)
    # CC-1: the offline path explains itself on the same terms as a live one. A cassette run
    # is the path every test exercises, so a ledger that only existed on the live path would
    # be the one part of the pipeline nothing verifies.
    if opted_out:
        runs.record_phase(conn, run_id, "optout", attempted=opted_out, reached=0,
                          skipped=opted_out,
                          reason="on the opt-out list — never requested (D-023)")
    runs.record_phase(
        conn, run_id, "deep_dive", attempted=len(targets),
        reached=max(len(targets) - gaps, 0), skipped=gaps,
        reason=("page blocked, walled or absent — open for the human rung" if gaps else None),
        seconds=time.monotonic() - _t_dive,
    )
    status = "finalized_with_open_gaps" if gaps else "finalized"
    runs.set_run_status(conn, run_id, status)
    return _build_result(conn, run_id, status, targets, stats=stats, gaps=gaps,
                         plan_intents=_ladder.plan_intents(plan))


def run_live(plan: dict, transport: Transport, snap_root, *, email: str,
             openalex_key=None, db_path=None, optout_path=None, resume=False,
             rate_limit: float = 1.0, backoff_sleep=None,
             targets_override: list[dict] | None = None,
             targets_truncated: list[str] | None = None,
             shortlist_size: int = DEFAULT_SHORTLIST_SIZE,
             max_institutions: int | None = None,
             progress=None, should_stop=None,
             phase_flags: "phases_mod.PhaseFlags | None" = None,
             render_all: bool = False,
             concurrency: int = pool_mod.DEFAULT_MAX_CONCURRENT,
             obey_robots: bool = True, crawl: bool = False) -> dict:
    """A **live** scan: preflight → discovery ladder (ROR + OpenAlex) → the *same* fetch → extract
    → claim → score → export → dashboard pipeline as ``run_offline`` (D-028), now from **discovered**
    targets rather than hand-fed ones.

    Requires a contact email (fails loud without one, D-019/023); ROR is keyless, the OpenAlex
    premium ``openalex_key`` is optional. The ``transport`` serves both the open-API JSON (ROR/
    OpenAlex, via the clients) and the professor pages (via the robots-gated ``Fetcher``) — one seam,
    so a live run is exactly the cassette-tested path with httpx swapped in.

    ``targets_override`` (D-066 ``--targets``) holds named-professor targets already resolved via
    OpenAlex author search. With a plan country they are UNIONED with the ladder's targets (deduped
    by OpenAlex id — nobody double-deep-dived); with NO plan country the country/discovery ladder
    is skipped entirely and the named targets are deep-dived directly through the same
    ``_process_targets`` path.

    The **shortlist gate** (D-056) bounds the deep-dive: ladder targets are ranked by topic
    overlap with the plan's resolved topics (works_count breaks ties) and only the top
    ``shortlist_size`` are deep-dived. The rest are NOT dropped — they stay enumerated and are
    exported with every field ``never_attempted`` (honest "not checked yet"), and the coverage
    line states the split plainly. Named targets (``targets_override``) always bypass the gate.

    ``targets_truncated`` carries the truncation markers (``author-search@…`` / ``author@…``)
    recorded by the CLI-side client that resolved ``targets_override`` — those lookups happened
    before run_live existed, so without this hand-off a lookup FAILURE would vanish and the run
    would read as complete (D-037).

    ``max_institutions`` (the §4.3 scale control) caps the ladder's institution scan to the
    first N of the ROR enumeration, with an honest warning when the cap cuts (D-037); the
    explicit parameter wins, else the plan's own ``max_institutions`` is honored — 0/unset
    means all (current behavior).

    ``progress`` (§4.1) is an optional callable fired with a structured event tuple at each
    phase transition — ``("enumerated", n_targets, n_institutions)`` after the ladder,
    ``("deep_dive_start", k)`` after the shortlist gate (k = targets actually deep-dived,
    post-gate, post-opt-out), ``("deep_dive_progress", i, k)`` per target, a
    ``("partial_warning", msg)`` alongside the warnings channel when a PARTIAL marker is
    recorded (msg ASCII), and ``("scoring",)`` / ``("exported",)`` around the export build.
    The default ``None`` is exactly today's behavior with zero overhead; a raising callback
    is logged and ignored — an observer must never kill a scan.

    ``should_stop`` is an optional callable consulted between deep-dive targets. On True the
    run stops cleanly at that checkpoint: the run is marked ``cancelled`` (never a finalized
    status — cancelled wins over the open-gaps audit), the partial results are exported
    honestly through the same ``_build_result`` path (untouched targets stay
    ``never_attempted``), and the result carries ``stats["cancelled"] = True``.
    Completed-target claims persist, so a fresh run with ``resume=True`` skips them and
    finishes the remainder (D-029). A raising hook means "keep going".

    ``phase_flags`` (plan FLAG) decides which gated phases may run. It defaults to reading
    the ``PHASES`` environment variable — **server configuration, never a request
    parameter** (the D-068 rule): a student's browser must not be able to switch on a phase
    that is off because it is not ready. Read exactly once, here, so no scan can take two
    different code paths inside one run. Every phase a flag turns off writes a CC-1 ledger
    row saying so: off must be *visible*, never silent, which is the whole reason the flag
    and the ledger landed together.
    """
    preflight.require_credentials({preflight.CONTACT_EMAIL_ENV: email})
    flags = phase_flags if phase_flags is not None else phases_mod.PhaseFlags.from_env()
    ror_client = _ror.RorClient(transport, email=email)
    oa_client = _openalex.OpenAlexClient(transport, email=email, key=openalex_key)
    country = plan.get("country") or (plan.get("countries") or [None])[0]
    targets_truncated = list(targets_truncated or [])
    # CC-1 timing starts before the ladder, which runs before the run row exists — the
    # ledger rows are written just after ``create_run`` with the elapsed time carried across.
    _t_discovery = time.monotonic()

    if targets_override is not None and not country:
        # named-professor run: no country/field scope, so the discovery ladder is skipped —
        # nothing to enumerate. Truncation markers from the CLI-side author lookups still
        # surface via ``targets_truncated`` (D-037). Named targets are never gated (D-066).
        disc = {"plan": dict(plan), "institutions": [], "targets": list(targets_override),
                "truncated": sorted(set(oa_client.truncated_sources) | set(targets_truncated)),
                "warnings": []}
        warnings: list[str] = []
        exempt_keys = {t.get("openalex_id") or t.get("id") for t in targets_override}
    else:
        disc = _ladder.build_targets(plan, ror_client, oa_client,
                                     max_institutions=(max_institutions
                                                       or plan.get("max_institutions")
                                                       or None))
        exempt_keys = set()
        if targets_override:
            seen = {t.get("openalex_id") or t.get("id") for t in disc["targets"]}
            for t in targets_override:
                key = t.get("openalex_id") or t.get("id")
                exempt_keys.add(key)        # named targets bypass the shortlist gate (D-066)
                if key not in seen:
                    seen.add(key)
                    disc["targets"].append(t)
            disc["truncated"] = sorted(set(disc["truncated"]) | set(oa_client.truncated_sources))
        if targets_truncated:
            # CLI-side --targets lookup failures merge into the SAME PARTIAL coverage the
            # ladder's own markers produce — even when every named target failed to resolve
            # (targets_override empty), a vanished target must never read as "none dropped".
            disc["truncated"] = sorted(set(disc["truncated"]) | set(targets_truncated))
        # D-060 (Phase L0 DoD): the sparse-country preflight warns and continues — never blocks.
        # Feed it the real discovery stats and surface its warnings (plus the ladder's) in the run
        # stats + coverage line; the CLI prints them.
        warnings = preflight.coverage_preflight({
            "country": country,
            "ror_institutions": len(disc["institutions"]),
            "openalex_works": sum(int(t.get("works_count") or 0) for t in disc["targets"]),
        }) + list(disc.get("warnings", []))

    _emit_progress(progress, ("enumerated", len(disc["targets"]),
                              len(disc["institutions"])))
    _discovery_seconds = time.monotonic() - _t_discovery

    conn = open_db(db_path) if db_path is not None else open_db()
    snaps = SnapshotStore(snap_root)
    # Polite by default for a real run (per-host min-interval + real backoff sleep); tests pass
    # rate_limit=0 + a no-op backoff_sleep so the cassette suite stays fast.
    fetcher = Fetcher(transport, snaps, sleep=backoff_sleep or time.sleep,
                      rate_limiter=HostRateLimiter(min_interval=rate_limit),
                      obey_robots=obey_robots)
    optout = optout_mod.load_optout(optout_path)
    targets, opted_out = optout_mod.filter_targets(disc["targets"], optout)
    # The D-056 shortlist gate, AFTER the opt-out filter (a suppressed person must not burn a
    # shortlist slot): only the top ``shortlist_size`` ladder targets are deep-dived; the rest
    # stay in ``targets`` and are exported with fields ``never_attempted`` — listed, unchecked.
    deep_dive = _apply_shortlist(targets, exempt_keys,
                                 disc["plan"].get("resolved_topic_ids") or [],
                                 shortlist_size)
    _emit_progress(progress, ("deep_dive_start", len(deep_dive)))

    run_id = runs.create_run(conn)
    runs.set_run_status(conn, run_id, "deep_diving")
    stats = {"extractions": 0, "cache_hits": 0, "opted_out": opted_out, "resumed_skipped": 0,
             "discovered": len(disc["targets"]), "institutions": len(disc["institutions"]),
             "truncated": disc.get("truncated", []), "warnings": warnings}
    if not obey_robots:
        # Recorded on the RUN, not just printed. A run that ignored robots must still say so
        # long after the console scrollback is gone — the warning rides the result (D-037) and
        # the phase row keeps it in the database for any later re-export (D-019).
        stats["warnings"].append(
            "robots.txt was NOT obeyed on this run (--ignore-robots). Pages a site asked "
            "machines not to read may have been read. Per-source provenance still records "
            "what robots actually said.")
        runs.record_phase(conn, run_id, "robots_override", attempted=0, reached=0, skipped=0,
                          reason="--ignore-robots: robots.txt consulted for provenance, "
                                 "not enforced")
    if len(deep_dive) < len(targets):
        stats["shortlisted"] = len(deep_dive)
        stats["unchecked"] = len(targets) - len(deep_dive)
    # Persist the discovery truncation markers on the run so a later human-rung re-export can still
    # emit the PARTIAL coverage line instead of implicitly claiming completeness (D-037, audit-3 #7).
    if stats["truncated"]:
        runs.update_counts(conn, run_id, truncated=stats["truncated"])
        # the same PARTIAL disclosure the coverage line carries, as a §4.1 event (D-037)
        _emit_progress(progress, ("partial_warning",
                                  _partial_warning_message(stats["truncated"])))

    # ── CC-1 ledger: discovery and the shortlist gate ─────────────────────────
    # Written here rather than at the end so a run that dies mid-deep-dive still leaves
    # behind what discovery actually did. A ledger that only survives a clean finish is a
    # ledger that is absent exactly when it is needed.
    runs.record_phase(
        conn, run_id, "discovery",
        attempted=len(disc["institutions"]),
        reached=len(disc["targets"]),
        skipped=len(disc.get("truncated") or []),
        reason=(f"{len(disc['truncated'])} source(s) had more results than were "
                f"enumerated ({', '.join(disc['truncated'])})"
                if disc.get("truncated") else None),
        seconds=_discovery_seconds,
    )
    runs.record_phase(
        conn, run_id, "shortlist",
        attempted=len(targets),
        reached=len(deep_dive),
        skipped=len(targets) - len(deep_dive),
        reason=(f"outside the top {shortlist_size} by topic fit — listed, unchecked "
                "(never_attempted)" if len(deep_dive) < len(targets) else None),
    )
    if opted_out:
        # An opt-out is a filtered result, never a coverage gap (D-023) — so it is its own
        # row rather than folded into the shortlist's skip count, which would misreport a
        # person's own choice as a limit of the scan.
        runs.record_phase(conn, run_id, "optout", attempted=opted_out, reached=0,
                          skipped=opted_out,
                          reason="on the opt-out list — never requested (D-023)")

    # ── FLAG: an off phase is SKIPPED AND SAID SO ─────────────────────────────
    # The single place off-rows are written, so each phase's own call site is just
    # ``if flags.is_on(...)`` and cannot forget to explain itself. The skipped count is the
    # shortlist size because every gated phase here is shortlist-scoped: "p0 skipped 40" is
    # the honest shape of what an off flag actually cost this run.
    for _off in flags.off():
        runs.record_phase(conn, run_id, _off, attempted=0, reached=0,
                          skipped=len(deep_dive), reason=flags.off_reason(_off))
    if flags.unknown or flags.not_yet_built:
        # A typo'd flag that silently does nothing is how "I turned it on" and "it is on"
        # drift apart. Zero counts: nothing was skipped BECAUSE of this — it is a
        # configuration note, and inflating a skip count to carry it would be a lie about
        # coverage. record_phase permits a reason without a skip for exactly this case.
        runs.record_phase(
            conn, run_id, "phase_flags", attempted=0, reached=0, skipped=0,
            reason=(f"{phases_mod.PHASES_ENV} names "
                    + "; ".join(filter(None, [
                        (f"{', '.join(flags.not_yet_built)} — recognised but not built yet"
                         if flags.not_yet_built else ""),
                        (f"{', '.join(flags.unknown)} — not a phase"
                         if flags.unknown else "")]))))

    # What the professor has actually been publishing — the single most useful thing a
    # student weighing a supervisor can see, and the one signal that survives a blocked
    # deep-dive. `works_by_author` shipped with the OpenAlex client and was never called.
    _t_works = time.monotonic()
    _works = _attach_recent_works(deep_dive, oa_client)
    runs.record_phase(conn, run_id, "recent_works", seconds=time.monotonic() - _t_works,
                      **_works)
    # Live runs only: resolves an ORCID profile URL to the professor's real page (D-072).
    # Built here rather than inside the deep-dive so the offline/demo path stays network-free
    # and every existing cassette test keeps passing unchanged (D-011/D-063).
    # Server-side rendering (D-073), live runs only. It asks the FETCHER's robots question so
    # both readers share one cached answer per host — two robots caches is two chances to
    # disagree, and the permissive one wins. Absent Playwright this is inert: `render()`
    # returns None and every page takes exactly the path it takes today.
    # ``BatchRenderer`` IS a ``ChromiumRenderer`` — it adds ``render_many`` and inherits the
    # single-page path unchanged, so this is the old object plus a batch entry point. The
    # sync browser inside it is created lazily, so a run whose pages were all pre-rendered
    # never launches a second one.
    renderer = render_mod.BatchRenderer(fetcher.robots_allows, max_concurrent=concurrency)
    # D-073, live runs only. ``None`` when no extraction key is configured, and that is the
    # default: the deep dive then runs on the deterministic extractors exactly as before.
    # Built once per run so "is a model available" is answered at the top, not per page.
    complete = llm_client.completer_from_env()
    # Rung 7, live runs only. ``None`` without a search key, and that is the default: the
    # deep dive then aims at exactly the URLs it aims at today.
    search = websearch.search if websearch.configured() else None
    _t_dive = time.monotonic()
    try:
        gaps = _process_targets(conn, run_id, deep_dive, fetcher, snaps, stats=stats,
                                resume=resume, progress=progress, should_stop=should_stop,
                                orcid_client=orcid_mod.OrcidClient(transport),
                                renderer=renderer, render_all=render_all, complete=complete,
                                search=search, crawl=crawl)
    finally:
        # One browser for the whole run; leaking it would outlive the scan inside a container
        # that then gets reused for the next job.
        renderer.close()
    # ``gaps`` counts targets with at least one blocked field, so reached is the complement:
    # the ones whose deep-dive produced something readable. A cancelled run records what it
    # got through rather than nothing — a stopped scan still did work, and hiding that would
    # make cancel look like failure.
    runs.record_phase(
        conn, run_id, "deep_dive",
        attempted=len(deep_dive),
        reached=max(len(deep_dive) - gaps, 0),
        skipped=gaps,
        reason=("page blocked, walled or absent — open for the human rung" if gaps else None),
        seconds=time.monotonic() - _t_dive,
    )
    if stats.get("rendered"):
        stats["render_note"] = (f"{stats['rendered']} page(s) needed a browser to read")
    if stats.get("cancelled"):
        # cancelled wins the status audit: a stopped run NEVER reports a finalized
        # status, whatever the gap count of the processed targets says.
        status = "cancelled"
    else:
        status = "finalized_with_open_gaps" if gaps else "finalized"
    runs.set_run_status(conn, run_id, status)
    _emit_progress(progress, ("scoring",))
    # a cancelled run exports its partials through the same honest path (D-046 four-state
    # model: untouched targets are never_attempted, never silently "checked").
    result = _build_result(conn, run_id, status, targets, stats=stats, gaps=gaps,
                           plan_topic_ids=plan.get("resolved_topic_ids") or (),
                           plan_intents=_ladder.plan_intents(plan))
    _emit_progress(progress, ("exported",))
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
    gaps = sum(1 for t in targets if _target_open_gap(conn, t["id"]))
    status = "finalized_with_open_gaps" if gaps else "finalized"
    latest = conn.execute(
        "SELECT run_id FROM run ORDER BY started_at DESC, rowid DESC LIMIT 1"
    ).fetchone()
    run_id = latest["run_id"] if latest else "reexport"
    # Re-read the discovery truncation markers persisted on the run (D-037): the resume path must not
    # silently claim completeness for a run whose discovery was PARTIAL (audit-3 finding 7).
    truncated = runs.get_counts(conn, run_id).get("truncated", []) if latest else []
    if latest:
        runs.set_run_status(conn, run_id, status)
    return _build_result(
        conn, run_id, status, targets,
        stats={"extractions": 0, "cache_hits": 0, "opted_out": opted_out, "reexport": True,
               "truncated": truncated},
        gaps=gaps,
    )


#: How many recent works to carry per professor. Enough to read activity and recency at a
#: glance; small enough that the payload stays a dashboard, not a bibliography.
RECENT_WORKS_LIMIT = 8


def _attach_recent_works(targets: list[dict], oa) -> dict:
    """Attach each shortlisted professor's recent publications, newest first.

    Only the SHORTLISTED targets — one OpenAlex call each, so this is bounded by the same
    gate that bounds the deep-dive, never by the enumerated count.

    Failure here is never fatal and never silent-but-wrong: a professor whose works lookup
    fails simply carries none, exactly as if OpenAlex had returned an empty list. That is
    honest emptiness (D-037) — the alternative, failing the scan because a *supplementary*
    signal was unavailable, would trade the whole result for a nice-to-have.

    Returns the CC-1 ledger counts for this phase. It returns them rather than writing the
    row itself so the function keeps no database handle: the phase that *does* the work and
    the phase that *records* it stay separable, which is what let this be tested without a
    connection at all.
    """
    attempted = reached = 0
    no_author_id = 0
    for t in targets:
        author_id = t.get("openalex_id")
        if not author_id:
            # Not a failure — this target never had an OpenAlex identity to look up. Counted
            # separately so "we could not ask" never reads as "we asked and got nothing".
            no_author_id += 1
            continue
        attempted += 1
        # Marked BEFORE the call, and left marked whatever happens. The modal shows a works
        # COUNT from the registry, so an empty publications list next to "4 works" reads as a
        # bug unless the page can say which it is: not looked up (outside the shortlist) or
        # looked up and nothing came back. Same four-state honesty as the evidence cells —
        # a number with no explanation is the failure, not the empty list.
        t["works_checked"] = True
        try:
            works = oa.works_by_author(author_id)
        except Exception:                          # noqa: BLE001 — see docstring
            continue
        ranked = sorted(works, key=lambda w: (w.get("year") or 0), reverse=True)
        t["recent_works"] = [
            {"title": w.get("title"), "year": w.get("year")}
            for w in ranked[:RECENT_WORKS_LIMIT] if w.get("title")
        ]
        if t["recent_works"]:
            reached += 1
    # Deliberately emits NO progress event. The §4.1 phase vocabulary is consumed by the CLI
    # printer, the job-store event mapper and the web page's phase labels, and a new verb
    # would have to be taught to all three — a large surface for a step that adds a few
    # seconds inside a phase the student is already watching. It stays silent until the
    # phase list is revised for its own reasons.
    return {"attempted": attempted + no_author_id, "reached": reached,
            "skipped": no_author_id,
            "reason": (f"{no_author_id} target(s) carry no OpenAlex id to look up"
                       if no_author_id else None)}


def _profile_for(t: dict, plan_topic_ids) -> dict:
    """The registry facts the enumeration already fetched, kept instead of thrown away.

    Every one of these came from OpenAlex/ROR during discovery and was then DISCARDED — the
    exported professor carried only ``id`` and ``name``. So a run whose deep-dive was blocked
    showed a student a row of "awaiting your browser" and nothing else, while the tool was
    already holding the person's institution, output, citation count and ORCID.

    These are **registry metadata, not evidence claims**, and the export keeps that line
    sharp ([D-010](../../docs/DECISIONS.md#d-010)): the five evidence fields are quote-gated
    and stay quote-gated, while this block is labelled with the API it came from and carries
    no quote because it is not a claim about recruiting. Mixing the two would let unverified
    text sit next to verified text with the same authority, which is the failure D-010
    exists to prevent. `name` already travelled this way, so the precedent is the schema's,
    not a new one.
    """
    own_topics = list(t.get("topic_ids") or [])
    prof = {
        "institutions": [n for n in (t.get("institution_names") or []) if n],
        "works_count": int(t.get("works_count") or 0),
        "cited_by_count": int(t.get("cited_by_count") or 0),
        "topics_total": len(own_topics),
        "topic_overlap": _topic_overlap(t, list(plan_topic_ids or [])),
        "orcid": t.get("orcid"),
        "openalex_id": t.get("openalex_id"),
        # Which page the deep-dive aimed at, and what KIND it was. `url_kind` is the honest
        # part: "orcid" means the only lead was a registry profile, which is why a blocked
        # row is blocked. Without it the student cannot tell "we found no page" from "the
        # page we found refused us".
        "page_url": t.get("url"),
        "page_url_kind": t.get("url_kind"),
    }
    if t.get("recent_works"):
        prof["recent_works"] = t["recent_works"]
    if t.get("works_checked"):
        prof["works_checked"] = True
    return prof


def _anchor_links(t: dict) -> list[str]:
    """Where a human should start looking for this professor — best lead first."""
    seen, out = set(), []
    for u in (t.get("url"), t.get("orcid"), t.get("openalex_id")):
        if u and u not in seen:
            seen.add(u)
            out.append(u)
    return out


def _human_prompt_for(t: dict, blocked_fields: list[str]) -> str | None:
    """The ready-to-paste D-043 prompt for one professor's open gaps, or None.

    Built with ``chrome_prompt.generate_prompt`` — the same function the CLI uses, which
    embeds the required output shape by emitting a worked example through ``md_grammar``,
    the module the ingester parses. Re-creating that shape in the dashboard's JavaScript
    would have been easier and would have re-introduced exactly the drift that design
    exists to prevent: two hand-written copies of a grammar, one of which is not tested
    against the parser.

    Only generated for professors who actually have blocked fields, so the payload is
    bounded by the shortlist rather than by the enumerated count.
    """
    if not blocked_fields:
        return None
    try:
        return chrome_prompt.generate_prompt(
            target_kind="person", target_ref=str(t.get("id") or ""),
            target_name=t.get("name"), missing_fields=blocked_fields,
            anchor_links=_anchor_links(t))
    except ValueError:
        return None


#: Counters that answer "which rungs actually ran", surfaced on the export's ``run.rungs``.
#: Every one is about the tool, not about a person — how many pages we rendered, how many
#: links we followed, how many searches resolved. A student reading a thin dashboard and an
#: operator debugging a scan need the same answer, and it must survive in the artifact rather
#: than only in a console that has already scrolled away.
_RUNG_COUNTERS = (
    "rendered", "render_batched", "render_fallback", "render_still_walled", "render_batch_size",
    "crawl_pages", "crawl_claims", "crawl_truncated",
    "search_resolved", "orcid_resolved",
    "model_proposals", "model_claims", "model_rejected", "model_unavailable",
    "extractions", "cache_hits", "resumed_skipped",
)


def _match_rating(t: dict, plan_topic_ids, claims_for_target) -> dict:
    """A 0–100 match rating for one professor, with its components shown.

    **``score/scorer.py`` was built, tested and called by nothing** — so every professor was
    exported unranked, and "why is this person in my list" had no answer beyond the order they
    happened to arrive in. This wires it.

    Two rules keep it honest:

    * **Every enumerated professor is rated, not only the deep-dived ones.** Rating uses
      registry facts (topics, output) that discovery already fetched for everyone, so a
      professor outside the shortlist still gets a place in the order. That is what makes the
      shortlist a budget rather than a verdict.
    * **The rating is not a claim about the person.** It is our arithmetic on our own inputs,
      so it is labelled ``match`` and kept out of the quote-gated ``fields`` block entirely.
      D-024 bars *evaluative judgements about people* — "this professor is a good supervisor"
      — and this is not one: it says how well their published topics overlap the ones the
      student ticked, and shows the components so the number can be argued with.
    """
    recruiting = 1.0 if any(c.get("field") == "recruiting_signal" and c.get("state") == "value"
                            for c in claims_for_target) else 0.0
    funding = 1.0 if any(c.get("field") == "industry_signal" and c.get("state") == "value"
                         for c in claims_for_target) else 0.0
    fit = scorer.score_professor(
        {"topic_ids": list(t.get("topic_ids") or []),
         "works_count": int(t.get("works_count") or 0),
         "recruiting": recruiting, "funding": funding,
         "evidence_count": sum(1 for c in claims_for_target if c.get("state") == "value")},
        {"resolved_topic_ids": list(plan_topic_ids or [])})
    return {
        "percent": round(fit.score_total * 100),
        "tier": fit.tier,
        "components": {k: round(v * 100) for k, v in fit.components.items()},
        "evidence_count": fit.evidence_count,
    }


def _build_result(conn, run_id, status, targets, *, stats, gaps,
                  plan_topic_ids=(), plan_intents=()) -> dict:
    """Assemble the export + dashboard from the persisted claims (no fetching here)."""
    professors = []
    for t in targets:
        p = {"id": t["id"], "name": t.get("name"), "profile": _profile_for(t, plan_topic_ids)}
        if t.get("resolution"):
            # named-target identity honesty label (verified/unverified/unchecked) — it must
            # travel into the durable artifacts, not just the console (D-010).
            p["resolution"] = t["resolution"]
        professors.append(p)
    claims_by_entity = {t["id"]: claims.claims_for(conn, "person", t["id"]) for t in targets}
    # Rate EVERY professor and order by it. Previously the export preserved discovery order,
    # so a student scrolling 493 rows had no signal about which to read first — and the scorer
    # that could have told them shipped uncalled.
    by_target = {t["id"]: t for t in targets}
    for p in professors:
        p["match"] = _match_rating(by_target[p["id"]], plan_topic_ids,
                                   claims_by_entity.get(p["id"], []))
    professors.sort(key=lambda p: (-p["match"]["percent"], p.get("name") or ""))
    # A `blocked` cell told the student "awaiting your browser" and then gave them nothing to
    # do about it — a dead end, which D-070 says a terminal state must never be. Attach the
    # generated D-043 prompt to exactly the professors who have open gaps, so the dashboard
    # can offer a real action instead of an instruction.
    by_id = {t["id"]: t for t in targets}
    for p in professors:
        blocked = sorted({c["field"] for c in claims_by_entity.get(p["id"], [])
                          if c.get("state") == "blocked" and not c.get("superseded_by")})
        prompt = _human_prompt_for(by_id[p["id"]], blocked)
        if prompt:
            p["profile"]["blocked_fields"] = blocked
            p["profile"]["human_prompt"] = prompt
    enumerated = len(targets)
    # Honest coverage line so the empty-state can tell "sources returned nothing" apart
    # from "found people, none matched" (edge-case matrix / D-046). The deterministic
    # pipeline never drops a professor, so zero here means discovery surfaced no one —
    # UNLESS the opt-out list removed them, which is a filtered result and must say so
    # (an opt-out is never a "coverage gap").
    opted_out = (stats or {}).get("opted_out") or 0
    if enumerated == 0 and opted_out:
        coverage = (f"{opted_out} professor(s) removed by the opt-out list; "
                    "none remain to scan.")
    elif enumerated == 0:
        coverage = ("No sources returned any professors for this search — this is a coverage "
                    "gap, not a filtered result.")
    else:
        coverage = f"{enumerated} professor(s) enumerated; none were dropped for missing data."
        shortlisted = (stats or {}).get("shortlisted")
        if shortlisted is not None:
            # the D-056 gate bounded the deep-dive — state the split plainly, never let the
            # unchecked remainder read as "checked and found nothing" (D-046).
            coverage += (f" Deep-dived the top {shortlisted} by topic fit; the remaining "
                         f"{stats['unchecked']} stay listed, unchecked (never_attempted).")
    if gaps:
        coverage += f" {gaps} target(s) have open gaps for the human rung."
    truncated = (stats or {}).get("truncated")
    if truncated:
        # never claim completeness while a source hit its page cap (D-037)
        coverage += (f" Coverage is PARTIAL — {len(truncated)} source(s) had more results than "
                     f"were enumerated ({', '.join(truncated)}).")
    for w in (stats or {}).get("warnings", []):
        # sparse-coverage preflight + discovery-scope warnings (D-060) reach the dashboard too
        coverage += f" Warning: {w}"
    # CC-1: what each phase attempted, reached and skipped — and why. It travels in the
    # export rather than only in the logs because the person who needs it most is the
    # student looking at a thin dashboard, not an operator with `gcloud logging read`.
    # An empty list is a real answer too: no phase recorded anything.
    ledger = runs.phase_ledger(conn, run_id)
    export = jx.build_export(
        run_summary={"run_id": run_id, "status": status,
                     "counts": {"enumerated": enumerated}, "coverage": coverage,
                     "ledger": ledger,
                     # WHICH RUNGS ACTUALLY FIRED. `--progress` prints phases, so a run that
                     # rendered every page and one that rendered none look identical, and the
                     # artifact carried no way to tell them apart either — a real scan had to
                     # be diagnosed by noticing every source host was orcid.org. These are
                     # counters about OUR OWN machinery, never about a person, so they carry
                     # no personal data and export freely (D-024 is about judgements).
                     "rungs": {k: v for k, v in (stats or {}).items()
                               if k in _RUNG_COUNTERS and v},
                     # MI-4.2: which supervision levels the student said they were open to,
                     # so the dashboard can pre-tick those filter chips. A preference, not a
                     # claim about anyone — it never gates what is recorded or exported.
                     "intents": list(plan_intents or ())},
        field_descriptors=FIELD_DESCRIPTORS,
        professors=professors,
        claims_by_entity=claims_by_entity,
        generated_at=utcnow(),
    )
    return {"run_id": run_id, "export": export, "html": dash.build_dashboard(export),
            "stats": stats}
