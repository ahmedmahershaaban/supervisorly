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

## P4-1 · The triage module `[ ]`

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
