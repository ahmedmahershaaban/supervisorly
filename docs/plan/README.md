# Supervisorly — implementation plan

The **index**. Each task area is its own file; open only what you are working on.

Written 2026-07-29 to be executed by another engineer or model.

## Read first, once

| file | what it is |
|---|---|
| [`GOALS.md`](GOALS.md) | **paste-ready `/goal` strings**, one per shippable slice |
| [`00-invariants.md`](00-invariants.md) | the seven checks every task must pass before it is `[R]` |
| [`01-spikes.md`](01-spikes.md) | measure before building — thresholds per phase |
| [`../PLAN_HARVEST.md`](../PLAN_HARVEST.md) | **why** the plan is shaped this way |
| [`../PLAN_HARVEST_REVIEW.md`](../PLAN_HARVEST_REVIEW.md) | edge cases and failure handling |
| [`../DECISIONS.md`](../DECISIONS.md) | **binding.** Never contradict a locked decision |

## The work

| file | tasks | size | risk |
|---|---|---|---|
| [`10-cross-cutting.md`](10-cross-cutting.md) | CC-1…CC-5, FLAG | S–M | low–med |
| [`20-p0-orcid.md`](20-p0-orcid.md) | P0-1…P0-3 | S | low |
| [`21-p1-admissions.md`](21-p1-admissions.md) | P1-1…P1-3 | **L** | **high** |
| [`22-p4-triage.md`](22-p4-triage.md) | P4-1 | S | med |
| [`23-p5-model.md`](23-p5-model.md) | P5-1…P5-2 | M | med |
| [`24-p2-directory.md`](24-p2-directory.md) | P2-1…P2-3 | **L** | **high** |
| [`25-p6-archive.md`](25-p6-archive.md) | P6-1 | S | low |
| [`26-p7-byo-key.md`](26-p7-byo-key.md) | P7-1 | S | low |
| [`30-frontend.md`](30-frontend.md) | FE-1…FE-6, T-1 | M | low |
| [`31-multi-intent.md`](31-multi-intent.md) | MI-1…MI-5 | M | low–med |
| [`90-ops-deploy.md`](90-ops-deploy.md) | OPS-1…OPS-7 + what is out of scope | — | — |

## Order

```
10 cross-cutting  →  SPIKE-0 → 20 P0  →  SPIKE-1 → CC-5 → 21 P1
                  →  SPIKE-4 → 22 P4  →  SPIKE-5 → 23 P5
                  →  31 T-1  →  CC-4  →  SPIKE-2 → 24 P2
                  →  SPIKE-6 → 25 P6  →  26 P7
```

[`30-frontend.md`](30-frontend.md), [`31-multi-intent.md`](31-multi-intent.md) and
[`26-p7-byo-key.md`](26-p7-byo-key.md) are independent of the harvest chain and can run in
parallel if someone is on the front end. MI-3 alone waits on P5.

## Marks

`[ ]` todo · `[~]` in progress · `[x]` done · `[R]` reviewed · `[!]` blocked (say why)

A task is **not done** until its tests pass, the full suite is green, and the seven invariants
in [`00-invariants.md`](00-invariants.md) have been re-checked.

## Status board

Update this line as phases land, so anyone opening the folder sees the state in one glance.

```
CC ■▢■▢■+FLAG■   P0 ✗   P1 ✗   P4 ▢   P5 ▢   P2 ▢   P6 ▢   P7 ▢   FE ▢   T ▢   MI ■■!■■
```

`■` done · `▢` todo · `!` blocked on another phase · `✗` **spike missed, not built**

| | state | as of |
|---|---|---|
| CC-1 phase ledger | `[R]` shipped, live | 2026-07-29 |
| CC-3 host pool | `[R]` shipped (primitive; P1/P2 are its callers) | 2026-07-29 |
| CC-5 PDF extraction | `[R]` shipped | 2026-07-29 |
| FLAG phase flags | `[R]` shipped, live | 2026-07-29 |
| MI-1, MI-2, MI-4, MI-5 | `[R]` shipped, live | 2026-07-29 |
| MI-3 | `[!]` blocked on P5 — no extraction call to aim yet | |
| CC-2 / CC-4 | todo | |
| **P0 ORCID employments** | **`[!]` SPIKE-0 = 22%, gate is 30% — not built** | 2026-07-29 |
| **P1 admissions** | **`[!]` SPIKE-1 = 0% on the real cohort — not built** | 2026-07-29 |

> ### ⚠ Read [B-006](../BLOCKERS.md) before planning anything else
>
> SPIKE-1 measured 0%, but **not because admissions pages are hard to find** — Ain Shams and
> Misr University both expose a postgraduate page one hop from the homepage. It measured 0%
> because the institutions a scan currently surfaces are not universities. Education-typed
> institutions in the enumeration: **41/97 Egypt, 5/100 Canada, 1/98 Germany.** A German
> student's scan enumerates professors at a clinical-drug-research company.
>
> This plausibly also limits P2 and P4/P5. It needs a product decision, and re-running any
> institution-dependent spike before it is resolved measures the wrong cohort again.

Deployed at tag `web-v20`; last verified by `tools/e2e/record_flow.js` **44/44** against a
real scan of 428 professors.

**Read [`20-p0-orcid.md`](20-p0-orcid.md) before touching P0.** The binding constraint turned
out not to be employments at all: 55% of shortlisted professors carry no ORCID on their
OpenAlex record. Nothing in the P0 tasks as written can move that.

**The level filter currently has nothing to filter on.** `supervises` is only populated once
P5 ships, so every professor is `unknown` and the chips say so out loud rather than looking
broken. That is designed behaviour — but it does mean MI-4's real value arrives with P5, and
the two are worth demoing together.

## Where the numbers went

There is no **P3** task file: P3 (capture page text, not DOM) is **already shipped** —
`src/supervisorly/extract/page_extract.js` and `src/supervisorly/fetch/browser_rung.py`.
Phase numbers match [`../PLAN_HARVEST.md`](../PLAN_HARVEST.md); the gap is deliberate.
