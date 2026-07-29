# P2 — Directory rung *(find the professor's page at all)*

← [`README.md`](README.md) · [`00-invariants.md`](00-invariants.md) · gate: **SPIKE-2** in [`01-spikes.md`](01-spikes.md)

**Size: L · Risk: HIGH.** The expensive, unglamorous grind — and it contains the single most
dangerous failure in the plan (P2-3).

## Why this exists

The bottleneck behind every thin dashboard: **we have no pages to read.**

| | |
|---|---|
| OpenAlex authors carrying a homepage | 0 / 50 |
| ORCID records carrying a researcher URL | 0 / 11 |
| professors with any readable page | 3 / 24 |

`roster.classify_directory` and `roster.route_directory` exist and **nothing calls them**.

**Gate**: SPIKE-2 must show **≥ 30%** of institutions expose a reachable people directory.

## Honest scope

Per-institution work in the tail, and it will **never** cover Cairo University — its TLS chain
is broken at the server and its scholar subdomain 403s bots. Say so rather than appear to fail.

---

## P2-1 · Bounded crawler `[ ]`

**Files**: `src/supervisorly/discover/crawl.py` *(new)*, `tests/test_crawl.py` *(new)*

- [ ] P2-1.1 Frontier with depth cap, page cap and a visited set
- [ ] P2-1.2 URL normalisation — strip fragments, drop volatile query params, normalise
      trailing slash
- [ ] P2-1.3 **Dedupe by content hash as well as URL** — session ids serve one page at many
      addresses (`fetch/normalize.content_hash` already exists)
- [ ] P2-1.4 Per-URL-**pattern** cap — kills `?page=1..1000` traps
- [ ] P2-1.5 Redirect-loop and soft-404 guards (a 200 whose body says "not found")
- [ ] P2-1.6 **Weak signals order the queue; they never exclude from it.** Link text and URL
      shape may decide what to visit *first* — a scheduling hint that costs nothing when wrong.
      They may never decide what to *skip*, which would turn an unreliable signal into a
      silent gap
- [ ] P2-1.7 robots + per-host serial via CC-3
- [ ] P2-1.8 Budget exhaustion reports what went unvisited (CC-1/CC-2)

**Review** `[ ]`

---

## P2-2 · Page-kind classification `[ ]`

**Files**: `src/supervisorly/discover/roster.py`, `tests/test_roster_classify.py` *(new)*

- [ ] P2-2.1 `classify_page_kind(text, links) -> "roster" | "person" | "other"` —
      **deterministic first**: thirty short internal links with person-shaped anchor text is a
      roster, and recognising that needs **counting, not judgement**
- [ ] P2-2.2 Model only for the genuinely ambiguous remainder (P5)

**Note** — the existing `classify_directory` answers *"could we read this page"*
(OPEN / LOGIN_WALL / NOT_FOUND), **not** *"is this a directory of people"*. The content
classifier is new work.

**Review** `[ ]`

---

## P2-3 · Identity matching + student confirmation `[ ]`

**The most dangerous failure in the plan.** Attributing another person's page to a professor is
worse than finding nothing — it is a confident wrong answer.

Ahmed's answer, adopted: automated matching cannot reliably separate *"M. A. Hassan"* from
*"Mohamed A. Hassan"*; a person looking at the page can, in two seconds. **So ask them.**

**Files**: `src/supervisorly/discover/ladder.py`, `src/supervisorly/export/dashboard.py`,
`tests/test_identity_match.py` *(new)*

- [ ] P2-3.1 Match requires surname + initial + institution agreement → `verified`
- [ ] P2-3.2 Anything weaker → `unverified`. **Two people sharing a name at one institution →
      refuse outright** and mark ambiguous — a coin flip here is indistinguishable from a lie
- [ ] P2-3.3 Modal shows an unverified candidate as **"Is this them?" plus a link to the page**
- [ ] P2-3.4 The student's confirmation is **recorded as evidence** — dated, with extractor
      `student-confirmed`. A human check is provenance
- [ ] P2-3.5 An unconfirmed match is **never presented as a finding** in the export or the
      dashboard — it appears as a candidate awaiting confirmation, which is a different thing

**Reuses** the existing `resolution: verified / unverified / unchecked` machinery.

**Review** `[ ]`

---

## Edge cases

| case | handling |
|---|---|
| Crawl explosion — calendars, pagination, session ids, faceted search | P2-1.2 → P2-1.4 |
| Directory behind a search form (POST) or a "Load more" button | Take what rendered; report the rest as unreached |
| Directory is a JS app | The render rung handles it (shipped) |
| Site in a language we have no cues for | Classification escalates to the model (P4-1.4) |
| Institution unreachable (broken TLS, bot-wall) | Ledger row with the reason; never a silent zero |
