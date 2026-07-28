"""Turn a model's reading of a page into claims the quote gate can check (D-073).

**Why this exists.** The regex extractors can only match shapes someone anticipated. A page
that says "I will be reviewing applications from students interested in joining the group for
the 2027 intake" means *recruiting*, and no pattern short of a language model gets there. The
hosted product has no judgement layer at all — that is why its dashboards are empty — while
the CLI has five agents doing exactly this work.

**The line this module draws, and the whole reason it is safe.** The model does not produce
facts. It produces *proposals*, each of which must carry a quote **copied verbatim from the
page**. Every proposal is then checked against the stored snapshot with
``normalize.quote_in_snapshot`` — the SAME function ``claims.record_claim`` uses (D-010/D-047)
— and anything whose quote is not literally present is dropped before it can become a claim.

So the model's power is bounded to *pointing at text that already exists*. It can be wrong
about what a sentence means; it cannot invent a deadline, a professor, or a recruiting status,
because the sentence it cites has to be on the page. A hallucination dies here, not in front
of a student.

Deliberately NOT reimplementing the check: this module imports the gate rather than writing
its own comparison. A second, slightly-different implementation of a security check is how
gates grow holes — the one place quote-matching is defined stays the only place.

**Fail-closed** (the D-068 pattern): unusable output, a missing key, a timeout, or an error
yields an EMPTY proposal list and the scan continues on the deterministic extractors alone.
Nobody's search dies because a model was unavailable.

This module makes no network call of its own. The caller injects a ``complete(prompt) -> str``
callable, which is what keeps it unit-testable with no key and keeps the offline/demo path
(D-011/D-063) network-free.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from ..fetch.normalize import quote_in_snapshot

#: Hard caps. A page cannot cause an unbounded amount of work or storage, and a model cannot
#: bury a bad proposal in a flood of good ones.
MAX_PROPOSALS = 12
MAX_VALUE_CHARS = 200
MAX_QUOTE_CHARS = 400
#: How much page text the model is shown. Mirrors the in-page cap in ``page_extract.js`` so a
#: browser snapshot and a fetcher snapshot are read on the same terms.
MAX_PAGE_CHARS = 12_000

#: The fields a proposal may target. An unknown field name is dropped rather than stored:
#: the export's column vocabulary is fixed in code, and a model must not be able to add to it.
PROPOSABLE_FIELDS = (
    "recruiting_signal",
    "deadline",
    "students_signal",
    "industry_signal",
    "supervises",
)

#: What a professor may be said to supervise — the same vocabulary as the student's
#: ``intent_kind`` (``cli.PLAN_INTENT_KINDS``), so "I want a PhD supervisor" can be matched
#: against "this person takes PhD students" without a translation step in between.
SUPERVISION_LEVELS = ("training", "pre_master", "pre_phd", "mentor", "master", "phd", "postdoc")


@dataclass(frozen=True)
class Proposal:
    """One (field, value, quote) the model proposes. Not yet a claim — see ``verify``."""
    field: str
    value: str
    quote: str


def build_prompt(page_text: str, url: str, *, fields=PROPOSABLE_FIELDS) -> str:
    """The extraction prompt, generated per page (D-038 — generated, never looked up).

    Two properties matter more than wording. First, it asks for a **verbatim quote** per
    field and says plainly that anything else is discarded — telling the model the rule that
    the code enforces anyway makes it cooperate with the gate instead of fighting it. Second,
    it makes **absence a valid answer**: without that, a model asked to fill five fields will
    fill five fields, and honest emptiness (D-037) is the thing this product sells.
    """
    text = (page_text or "")[:MAX_PAGE_CHARS]
    return (
        "You are reading ONE web page belonging to, or describing, an academic. Extract only "
        "what this page actually says about supervising and recruiting students.\n\n"
        f"PAGE URL: {url}\n"
        "PAGE TEXT (verbatim, may be truncated):\n"
        "-----\n" + text + "\n-----\n\n"
        "Return STRICT JSON: an object with one key \"claims\", whose value is a list of "
        "objects, each with exactly:\n"
        '  "field": one of ' + ", ".join(fields) + "\n"
        '  "value": a short answer (<= 200 chars). For "supervises", use only these words, '
        "comma separated: " + ", ".join(SUPERVISION_LEVELS) + "\n"
        '  "quote": text copied EXACTLY, character for character, from PAGE TEXT above\n\n'
        "RULES\n"
        "1. Every claim MUST have a quote copied verbatim from PAGE TEXT. A quote that is "
        "not found in the page is discarded automatically, and the claim with it.\n"
        "2. Do NOT paraphrase, translate, correct spelling, or fix punctuation inside a "
        "quote. Copy the characters.\n"
        "3. If the page does not say something, OMIT that field. Returning fewer claims is "
        "correct and expected. An empty list is a valid, useful answer.\n"
        "4. Never infer from the person's title, seniority, or field. Only from the text.\n"
        "5. Output JSON only. No commentary, no markdown fence.\n"
    )


def parse_proposals(raw: str, *, fields=PROPOSABLE_FIELDS) -> list[Proposal]:
    """Parse the model's reply into proposals, discarding anything malformed.

    Every branch here fails toward *fewer* proposals, never toward a permissive one: unusable
    JSON, a wrong shape, an unknown field, a missing quote and an over-long value all drop the
    item rather than repairing it. Repairing model output is how a strict contract becomes a
    suggestion.
    """
    if not raw or not isinstance(raw, str):
        return []
    body = raw.strip()
    # Tolerate a markdown fence, since models add one despite being told not to. This is
    # formatting, not content — stripping it does not repair a malformed claim.
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", body, re.S)
    if fence:
        body = fence.group(1).strip()
    try:
        data = json.loads(body)
    except (ValueError, TypeError):
        return []
    items = data.get("claims") if isinstance(data, dict) else data
    if not isinstance(items, list):
        return []

    out: list[Proposal] = []
    seen: set[tuple[str, str]] = set()
    for item in items:
        if len(out) >= MAX_PROPOSALS:
            break
        if not isinstance(item, dict):
            continue
        field = item.get("field")
        value = item.get("value")
        quote = item.get("quote")
        if field not in fields:
            continue
        if not isinstance(value, str) or not isinstance(quote, str):
            continue
        value, quote = value.strip(), quote.strip()
        if not value or not quote:
            continue
        if len(value) > MAX_VALUE_CHARS or len(quote) > MAX_QUOTE_CHARS:
            continue
        if field == "supervises":
            value = _clean_levels(value)
            if not value:
                continue
        key = (field, value.lower())
        if key in seen:
            continue
        seen.add(key)
        out.append(Proposal(field=field, value=value, quote=quote))
    return out


def _clean_levels(value: str) -> str:
    """Keep only recognised supervision levels, in the canonical order.

    A model asked for an enum will still occasionally answer "PhD students" or "doctoral".
    Unrecognised words are dropped rather than mapped, because mapping them is a dictionary of
    a field's terms, which D-038 forbids — and because a level nobody can match against an
    ``intent_kind`` is worth less than an honest omission.
    """
    words = {w.strip().lower().replace("-", "_").replace(" ", "_")
             for w in value.split(",") if w.strip()}
    return ", ".join(lvl for lvl in SUPERVISION_LEVELS if lvl in words)


def verify(proposals: list[Proposal], snapshot_html: str) -> tuple[list[Proposal], list[tuple[Proposal, str]]]:
    """Split proposals into those whose quote is really on the page and those that are not.

    ``record_claim`` applies this same gate again when the claim is stored, and that second
    application is the one that actually protects the database. This pass exists so a rejected
    proposal can be COUNTED and reported rather than vanishing silently — a model whose quotes
    stop matching is a signal worth seeing, not a quiet degradation to an empty dashboard.
    """
    kept: list[Proposal] = []
    dropped: list[tuple[Proposal, str]] = []
    for p in proposals:
        if quote_in_snapshot(p.quote, snapshot_html):
            kept.append(p)
        else:
            dropped.append((p, "quote not found in snapshot"))
    return kept, dropped


def propose(page_text: str, url: str, snapshot_html: str, complete) -> tuple[list[Proposal], list[tuple[Proposal, str]]]:
    """Full step: prompt → model → parse → verify. Never raises.

    ``complete`` is any callable taking the prompt and returning the model's text. Injecting
    it keeps this module free of transport, keys and retries, and lets the tests run the whole
    contract with no network (D-011/D-063).
    """
    try:
        raw = complete(build_prompt(page_text, url))
    except Exception:                      # noqa: BLE001 — fail-closed by design (D-068)
        return [], []
    return verify(parse_proposals(raw), snapshot_html)
