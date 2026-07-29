# P6 — Historical cycles *(what the deadline was last year)*

← [`README.md`](README.md) · [`00-invariants.md`](00-invariants.md) · gate: **SPIKE-6** in [`01-spikes.md`](01-spikes.md)

**Size: S · Risk: low.** Isolated — it can fail entirely and nothing else notices.

## Why this exists

Ahmed asked for *"the old versions of the acceptance"*. Reading the same admissions URL across
past years gives the **pattern** — *"applications have opened in May for the last four cycles"*
— which the dashboard already renders as `watch · projected` and distinguishes from a `firm`
published date.

Verified: the Wayback CDX API is free and open, and an institution the live ladder returned had
admissions pages archived from **2003 to 2023**.

**Gate**: SPIKE-6 must show **≥ 25%** of the admissions URLs P1 found have **≥ 3** archived
cycles.

---

## P6-1 · Archive client `[ ]`

**Files**: `src/supervisorly/discover/archive.py` *(new)*, `tests/test_archive.py` *(new)*

- [ ] P6-1.1 CDX query for a URL **P1 discovered** — never a URL we authored
      ([`00-invariants.md`](00-invariants.md) §2)
- [ ] P6-1.2 Fetch the snapshots, extract dates from each
- [ ] P6-1.3 **Fewer than 3 cycles → no projection.** Two points are not a pattern; report what
      was found and stop
- [ ] P6-1.4 A projection is labelled `watch · projected`, **never** `firm`
- [ ] P6-1.5 Archive slow or unavailable → skip. Historical enrichment is never load-bearing
- [ ] P6-1.6 Behind the `PHASES` flag; ledger row either way

**Acceptance** — a URL with two snapshots yields no projected date; one with four yields a
projected date that renders as `watch`, never as a published deadline.

**Review** `[ ]`

---

## Edge cases

| case | handling |
|---|---|
| Fewer than 3 archived cycles | No projection at all |
| Archive slow or down | Skip; never load-bearing |
| The archived page contradicts the live one | **The live page wins for "current".** The archive supplies only the pattern |
| Snapshots exist but contain no date | `searched_absent` for the pattern — honest, not a failure |
| The URL changed between cycles | Follow what CDX returns for that URL only; do not guess successors |

## The line

An archived page describes **the past**. It may inform a projection; it may never be presented
as the current deadline. The existing `firm` vs `watch · projected` distinction in the
dashboard is the mechanism — reuse it rather than inventing a new label.
