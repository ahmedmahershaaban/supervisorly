# P5 — Model extraction *(batched, quote-gated)*

> ## SPIKE-5 NOT RUN, 2026-07-29 — blocked behind SPIKE-4, which is inconclusive.
>
> SPIKE-5 asks what share of **model proposals survive the quote gate** on 20 real pages. It
> needs pages that could produce a proposal. [`22-p4-triage.md`](22-p4-triage.md) measured the
> deep-dive's actual page supply for GB · machine learning: **0% of 49 shortlisted professors
> resolve to a page they control** — 88% resolve to no page at all and 12% to an ORCID or
> Publons profile, which has no field in which a person could say they take students.
>
> Running SPIKE-5 against that supply would measure the model on registry profiles and report
> a number about nothing. P5-1 and P5-2 stay `[ ]` and unbuilt.
>
> **Prerequisite: P2 (the directory rung)**, which is what would create a supply of real
> faculty pages — see [`24-p2-directory.md`](24-p2-directory.md) and B-003/B-006.
>
> *(Secondary, and temporary: OpenAlex's free daily budget was exhausted during this session
> — `429 "Insufficient budget… Resets at midnight UTC"` — so no ladder-dependent spike could
> be re-run afterwards. That is a scheduling constraint, not the reason SPIKE-5 is blocked.)*

---

← [`README.md`](README.md) · [`00-invariants.md`](00-invariants.md) · gate: **SPIKE-5** in [`01-spikes.md`](01-spikes.md)

**Size: M · Risk: med.** The contract is already written and tested — `extract/llm_claims.py`
exists and **nothing calls it**. This phase is mostly batching and wiring.

## Why this exists

The regexes are cue lists. They find `"I am accepting PhD students"` and miss
`"I will be reviewing applications for the 2027 intake"`. Measured: a rendered ORCID page with
**27,357 characters of biography** produced `searched_absent` on all five fields.

The model is needed to **read**, not to extract.

**Gate**: SPIKE-5 must show **≥ 60%** of proposals surviving the quote gate. A low rate means
the prompt or the batching is wrong — not that the pages are empty.

---

## P5-1 · Batching `[ ]`

**Files**: `src/supervisorly/extract/llm_claims.py`, `tests/test_llm_claims.py`

- [ ] P5-1.1 `build_batch_prompt(pages)` — several pages per call, one array back, each item
      carrying its page id
- [ ] P5-1.2 Batch by **bytes, not page count** — one enormous page must not silently truncate
      its neighbours out of the request
- [ ] P5-1.3 A proposal naming an unknown page id is **dropped**
- [ ] P5-1.4 Per-page failure isolation — one bad page costs itself only
- [ ] P5-1.5 **All quotes in a batch rejected → log a signal.** Model degradation is otherwise
      indistinguishable from "these pages had nothing"
- [ ] P5-1.6 **Isolated context per batch** — no conversation history, no accumulated
      transcript. Cost stays linear and a long scan cannot drag a growing context behind it

**Review** `[ ]`

---

## P5-2 · Wire it in `[ ]`

**Files**: `src/supervisorly/pipeline.py`, `firebase/_core.py`

- [ ] P5-2.1 Runs after P4, on `candidate` **and** `uncertain` pages only
- [ ] P5-2.2 Every proposal goes through `claims.record_claim` — **the gate is not
      re-implemented**, it is reused
- [ ] P5-2.3 Token budget (CC-2); exhaustion truncates and **reports** —
      *"N pages not read (budget)"* — never fails the run
- [ ] P5-2.4 Fail-closed: no key, any error → the deterministic results stand alone
- [ ] P5-2.5 Behind the `PHASES` flag (see FLAG in [`10-cross-cutting.md`](10-cross-cutting.md))

**Acceptance** — with the model disabled the scan produces exactly today's output. With it
enabled, **every added claim carries a verbatim quote** found in its snapshot.

**Review** `[ ]`

---

## Edge cases

| case | handling |
|---|---|
| Provider 429 / 5xx / timeout | Retry with backoff, then fail closed **for that batch only**; its pages stay `searched_absent` and the scan continues |
| Batch exceeds the context window | Batch by bytes; split rather than truncate |
| Every quote rejected | Log it as a signal — see P5-1.5 |
| **Prompt injection in page content** | Bounded, not eliminated. The entity is fixed by **which page we fetched** and is never chosen by the model, so injected text cannot move a claim onto a different professor. Quoted injection is reported as *"this page says X"* with the quote and URL shown — which is what a reader can check |
| Cost runaway on a large scan | Hard per-scan token budget; truncate and report |
| Same page, different answers on re-run | Already handled — the conflicts table records disagreement rather than overwriting (D-010) |

## The line this phase must not cross

A model **proposes**. It never *is* the evidence. Anything whose quote is not verbatim in the
stored snapshot is dropped **before** it can become a claim — so a hallucinated deadline dies
at the gate rather than in front of a student.

The quote stays in the **source language**; only the `value` may be normalised.
