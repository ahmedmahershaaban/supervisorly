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
import time

from . import preflight
from .discover import ladder as _ladder
from .discover import openalex as _openalex
from .discover import ror as _ror
from .discover import roster as _roster
from .ethics import optout as optout_mod
from .export import dashboard as dash
from .export import json_export as jx
from .fetch.fetcher import Fetcher
from .fetch.normalize import content_hash, main_text
from .fetch.ratelimit import HostRateLimiter
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
_WALLED_SOCIAL = re.compile(
    r"^https?://(?:www\.)?(?:twitter\.com|x\.com|linkedin\.com)/", re.IGNORECASE)


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


def _process_targets(conn, run_id, targets, fetcher, snaps, *, stats, resume) -> int:
    """Deep-dive each target (fetch → extract → claim) — the shared core of run_offline/run_live.

    Returns the gap count (targets with any still-``blocked`` field or an unchecked walled social
    page), derived from claim state so the run status can never contradict the exported cells
    (D-046/D-049). A target with no page URL (e.g. an OpenAlex professor with no discoverable
    homepage) is an honest open gap for the human rung, never a fabricated value.
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
            if _roster.detect_login_wall(html):
                # a robots-allowed 200 that is really a login/JS/bot wall — its chrome text is NOT
                # the professor's content, so never extract it; mark blocked → the human rung
                # (D-039/D-044). This is what keeps a wall from being silently defeated.
                for field in _EXTRACTORS:
                    _record_blocked(conn, pid, field)
                runs.set_task_status(conn, task, "blocked",
                                     last_error="login/bot wall — routed to the human rung")
                continue
            chash = content_hash(html)
            if xcache.lookup(conn, "person", pid, chash, PROMPT_VERSION, MODEL_ID,
                             CACHE_SCHEMA_VERSION):
                stats["cache_hits"] += 1
                runs.set_task_status(conn, task, "done")
                continue
            src_id = claims.record_web_source(
                conn, res.final_url or url, snapshot_hash=res.snapshot_hash, http_status=200,
                source_tier=_source_tier(res.final_url or url), robots_allowed=True,
            )
            claim_ids: list[str] = []
            walled_social = None
            for field, extractor in _EXTRACTORS.items():
                found = extractor(html)
                rec = _record_evidence(conn, pid, field, found, src_id=src_id,
                                       snapshot_hash=res.snapshot_hash, html=html)
                if rec and rec.ok:
                    claim_ids.append(rec.claim_id)
                if field == "social" and found and _WALLED_SOCIAL.search(found[0]):
                    walled_social = found[0]
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
            err = res.error if res is not None else "no page url — open for the human rung"
            runs.set_task_status(conn, task, "blocked", last_error=err)

    return sum(1 for t in targets if _target_open_gap(conn, t["id"]))


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
    gaps = _process_targets(conn, run_id, targets, fetcher, snaps, stats=stats, resume=resume)
    status = "finalized_with_open_gaps" if gaps else "finalized"
    runs.set_run_status(conn, run_id, status)
    return _build_result(conn, run_id, status, targets, stats=stats, gaps=gaps)


def run_live(plan: dict, transport: Transport, snap_root, *, email: str,
             openalex_key=None, db_path=None, optout_path=None, resume=False,
             rate_limit: float = 1.0, backoff_sleep=None,
             targets_override: list[dict] | None = None,
             targets_truncated: list[str] | None = None,
             shortlist_size: int = DEFAULT_SHORTLIST_SIZE) -> dict:
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
    """
    preflight.require_credentials({preflight.CONTACT_EMAIL_ENV: email})
    ror_client = _ror.RorClient(transport, email=email)
    oa_client = _openalex.OpenAlexClient(transport, email=email, key=openalex_key)
    country = plan.get("country") or (plan.get("countries") or [None])[0]
    targets_truncated = list(targets_truncated or [])

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
        disc = _ladder.build_targets(plan, ror_client, oa_client)
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

    conn = open_db(db_path) if db_path is not None else open_db()
    snaps = SnapshotStore(snap_root)
    # Polite by default for a real run (per-host min-interval + real backoff sleep); tests pass
    # rate_limit=0 + a no-op backoff_sleep so the cassette suite stays fast.
    fetcher = Fetcher(transport, snaps, sleep=backoff_sleep or time.sleep,
                      rate_limiter=HostRateLimiter(min_interval=rate_limit))
    optout = optout_mod.load_optout(optout_path)
    targets, opted_out = optout_mod.filter_targets(disc["targets"], optout)
    # The D-056 shortlist gate, AFTER the opt-out filter (a suppressed person must not burn a
    # shortlist slot): only the top ``shortlist_size`` ladder targets are deep-dived; the rest
    # stay in ``targets`` and are exported with fields ``never_attempted`` — listed, unchecked.
    deep_dive = _apply_shortlist(targets, exempt_keys,
                                 disc["plan"].get("resolved_topic_ids") or [],
                                 shortlist_size)

    run_id = runs.create_run(conn)
    runs.set_run_status(conn, run_id, "deep_diving")
    stats = {"extractions": 0, "cache_hits": 0, "opted_out": opted_out, "resumed_skipped": 0,
             "discovered": len(disc["targets"]), "institutions": len(disc["institutions"]),
             "truncated": disc.get("truncated", []), "warnings": warnings}
    if len(deep_dive) < len(targets):
        stats["shortlisted"] = len(deep_dive)
        stats["unchecked"] = len(targets) - len(deep_dive)
    # Persist the discovery truncation markers on the run so a later human-rung re-export can still
    # emit the PARTIAL coverage line instead of implicitly claiming completeness (D-037, audit-3 #7).
    if stats["truncated"]:
        runs.update_counts(conn, run_id, truncated=stats["truncated"])
    gaps = _process_targets(conn, run_id, deep_dive, fetcher, snaps, stats=stats, resume=resume)
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


def _build_result(conn, run_id, status, targets, *, stats, gaps) -> dict:
    """Assemble the export + dashboard from the persisted claims (no fetching here)."""
    professors = []
    for t in targets:
        p = {"id": t["id"], "name": t.get("name")}
        if t.get("resolution"):
            # named-target identity honesty label (verified/unverified/unchecked) — it must
            # travel into the durable artifacts, not just the console (D-010).
            p["resolution"] = t["resolution"]
        professors.append(p)
    claims_by_entity = {t["id"]: claims.claims_for(conn, "person", t["id"]) for t in targets}
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
