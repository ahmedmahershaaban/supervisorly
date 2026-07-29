# P6 — Historical cycles *(what the deadline was last year)*

# SPIKE-6 RESULT, 2026-07-29 — **PASS (50%, gate 25%)**, but P6 is blocked upstream.

`tools/spikes/spike_wayback.py`, run against the admissions URLs **SPIKE-1's crawl actually
found** — P1 was never built, so there is no harvest to draw from, and the archive is queried
only for URLs discovery produced rather than any we authored (D-038).

| url | usable cycles |
|---|---|
| `asu.edu.eg/postgraduate` | **6** (2021–2026) |
| `aisegypt.com/admissions/application-help` | **5** (2022–2026) |
| `must.edu.eg/…/graduate-studies` | 1 |
| `ohi.edu.eg/training-courses` | 0 — not archived |

**2/4 = 50% have ≥ 3 cycles**, against a 25% gate. Cycles are counted **per year**
(`collapse=timestamp:4`) and only 2xx captures count: fifty captures in one busy year is one
cycle, and a 404 capture records that a URL existed, not a deadline anyone could read.

**So the archive is not the problem — but P6 still cannot be built.** P6 projects a next
deadline from past ones on *admissions pages P1 discovered*. P1 is `[!]` (SPIKE-1 = 0% on the
real cohort, cause upstream in [B-006](../BLOCKERS.md)). With no P1 there is no URL harvest to
project from; four hand-carried URLs from a spike are not a pipeline.

**This is a good state to be in**: when P1 lands, its URLs go straight into a projection whose
feasibility is already measured. Re-run then — 4 URLs is thin and the number is indicative.

P6-1 stays `[!]`, blocked on **P1**, not on its own gate.

---

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

## P6-1 · Archive client `[x]` — built as a primitive; no caller until P1 lands

**Files**: `src/supervisorly/discover/archive.py` *(new)*, `tests/test_archive.py` *(new)*

- [x] P6-1.1 CDX query for a URL **P1 discovered** — never a URL we authored
      ([`00-invariants.md`](00-invariants.md) §2). Anything that is not an `http(s)` URL is
      refused rather than normalised: a constructed guess arrives in exactly that shape.
- [x] P6-1.2 Fetch the snapshots, extract dates from each — *the dates are passed IN.* This
      module does not parse pages: the pipeline already has one date extractor and a second
      would be a second set of bugs.
- [x] P6-1.3 **Fewer than 3 cycles → no projection.** Two points are not a pattern; report what
      was found and stop
- [x] P6-1.4 A projection is labelled `watch · projected`, **never** `firm`
- [x] P6-1.5 Archive slow or unavailable → skip. Historical enrichment is never load-bearing
- [~] P6-1.6 Behind the `PHASES` flag; ledger row either way — **not yet**, and deliberately:
      `p6` stays in `PLANNED_PHASES` because a phase joins `OPTIONAL_PHASES` only when it has
      a **call site that can be skipped**. It has none until P1 supplies URLs. Listing it
      early would let `PHASES=p6` read as accepted while changing nothing, which is the exact
      failure the FLAG task exists to prevent.

**Acceptance** — a URL with two snapshots yields no projected date; one with four yields a
projected date that renders as `watch`, never as a published deadline. **Both pinned as tests.**

**Done, 2026-07-29.** Built for the same reason CC-3 was: SPIKE-6 passed its gate, and this
is the self-contained client that phase needs. It is exercised as a primitive, not wired in —
P1 has no admissions URLs to give it yet.

Three refusals worth keeping:
- **Only 2xx captures count as cycles.** A 404 capture proves the URL existed, not that a page
  was archived whose deadline could be read — counting it inflates the very history that gates
  the projection.
- **Enough captures but too few readable dates still refuses.** Otherwise "four cycles" would
  license projecting from two dates, sidestepping the 3-cycle rule through the back door.
- **A 429 is a failure, not an empty history.** The archive is a charity and throttles;
  reporting that as "no history" turns their rate limit into our claim about an institution.

**Review** `[R]`

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
