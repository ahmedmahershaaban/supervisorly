# P4 — Deterministic triage *(the token gate)*

← [`README.md`](README.md) · [`00-invariants.md`](00-invariants.md) · gate: **SPIKE-4** in [`01-spikes.md`](01-spikes.md)

**Size: S · Risk: med** — the risk is entirely in the recall tuning.

## Why this exists

*"No dummy data, no context overload, be direct"* should be enforced in **code**, not requested
in a prompt. A page with no recruiting cue, no date near an application word and no supervision
term cannot produce a recruiting claim — sending it to a model to be told so spends tokens to
learn nothing.

This is what makes P5 affordable.

**Gate**: SPIKE-4 must show **recall ≥ 90%** on pages known to contain recruiting language.

---

# SPIKE-4 RESULT, 2026-07-29 — **INCONCLUSIVE. Not a miss; not measurable.** P4 is NOT built.

`tools/spikes/spike_triage.py` prototypes the triage rule from the shipped `pipeline.py`
regexes (as P4-1.2 directs) and labels each page with **the model triage exists to feed** —
not with the regexes under test, which would have measured them against themselves and
returned 100%.

**The judge found recruiting language on 0 pages, so recall has no denominator.** Reporting
that as "0% — MISS" would kill a phase that was never tested; the script now says
`NOT MEASURED` and exits distinctly.

| cohort | pages read | judged "recruiting" |
|---|---|---|
| GB · machine learning (with the render rung) | 16 | **0** |
| EG · cardiovascular disease | 4 | **0** |

**Why zero — measured, not guessed.** `tools/spikes/spike_page_supply.py` resolves each
shortlisted professor to the URL `pipeline._page_url_for` would deep-dive and classifies it.
For **GB · machine learning, 49 shortlisted**:

| | share |
|---|---|
| no page at all | **88%** |
| registry profile (ORCID/Publons — cannot state recruiting) | 12% |
| **a page the person controls** | **0%** |

A professor's own page is where "I am recruiting PhD students" lives. ORCID has no field for
it. So the deep-dive's page supply contains **nothing that could carry a recruiting claim**,
and triage has nothing to triage.

This is not a triage problem and P4 cannot fix it. It is the same supply problem as
[B-003](../BLOCKERS.md) (ORCID profile pages are the only lead), compounded by
[B-006](../BLOCKERS.md) (the institutions enumerated are often not universities). **P2 — the
directory rung — is the phase that would actually create this supply**, by finding staff
directory pages and, through them, real faculty pages.

**Two method notes worth keeping:**
- The first version of this spike skipped the render rung and reported 15 of 17 pages as
  "under 200 chars (JS app?)" — a blocker that was really its own measurement gap, since the
  deployed worker reaches 10 of 40 targets on the same cohort. **A spike that skips a rung the
  product has measures a product nobody ships.** It now builds the same `ChromiumRenderer`.
- The run also surfaced a real defect, now fixed: a rate-limited OpenAlex topic lookup
  returned `[]` and was indistinguishable from "no such topic", which makes `build_targets`
  enumerate *unfiltered* with no warning. See `tests/test_topic_resolution_honesty.py`.

**Re-run when P2 has shipped, or on a cohort with real faculty pages.** Until then this gate
cannot be evaluated and P4 must not be built on an assumption.

---

## P4-1 · The triage module `[!]` blocked — SPIKE-4 inconclusive: no page in the supply can carry a recruiting claim

**Files**: `src/supervisorly/extract/triage.py` *(new)*, `tests/test_triage.py` *(new)*

- [ ] P4-1.1 `triage(text) -> "candidate" | "empty" | "uncertain"`
- [ ] P4-1.2 Signals: recruiting cue, a date near an application word, a supervision term, a
      contact block. Reuse the existing regexes in `pipeline.py` — they are excellent at
      *"worth a closer look"* even where they are too blunt to be the extractor
- [ ] P4-1.3 **Tuned for recall, not precision.** When in doubt → `candidate`
- [ ] P4-1.4 **Non-Latin or unknown-language text → `uncertain`, which escalates to the model —
      never `empty`.** This is the rule that stops Arabic-language institutions returning
      nothing and reading as *"that country has no professors"*, which is exactly the failure
      D-038 exists to prevent
- [ ] P4-1.5 Skip counts recorded in the ledger (CC-1) so the miss rate is **measurable rather
      than assumed**

**Acceptance** — an Arabic page with recruiting language is never classified `empty`.

**Review** `[ ]`

---

## Edge cases

| case | handling |
|---|---|
| **False negatives are invisible** — a relevant page skipped never reaches the model and never appears anywhere | Tune for recall; log skip counts so the rate can be checked rather than trusted |
| **Non-English pages** — the cue lists are English | Uncertainty escalates to the model, never to the bin. No translation step is needed: models read Arabic natively |
| A page that is relevant but phrased with no cue at all | Accepted loss, and **measured** by SPIKE-4 rather than discovered later |

## What this phase must NOT do

- **Do not translate before triage.** Translation belongs to display only — see
  [`30-frontend.md`](30-frontend.md) T-1. Storing a translated quote would manufacture a
  sentence the page never contained.
- **Do not discard on a weak signal.** Weak signals order the queue; they never exclude from it.
