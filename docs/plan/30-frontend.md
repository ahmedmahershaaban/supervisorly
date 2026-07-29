# FE — Front-end workstream, and T-1 translation display

← [`README.md`](README.md) · [`00-invariants.md`](00-invariants.md)

**Size: M · Risk: low.** The student's experience as one thing rather than fragments.
Independent of the harvest chain except where noted, so it can run in parallel.

**Primary files**
- `src/supervisorly/export/webapp.py` — the 5-step wizard
- `src/supervisorly/export/dashboard.py` — the result page
- tests: `tests/test_webapp*.py`, `tests/test_dashboard*.py`
- real-browser harness: `tools/e2e/record_flow.js` — **extend it for every new surface**

---

## FE-1 · Past searches on step 1 `[ ]` — *(the UI half of CC-4)*

- [ ] FE-1.1 Panel above the email field: past searches with field, country, date, status
- [ ] FE-1.2 "Open" re-enters step 5 for a finished job; "Start fresh" clears the form only
- [ ] FE-1.3 An expired job (7-day TTL) says so and offers "run it again" — **never an error**
- [ ] FE-1.4 On a first visit the panel is absent entirely — no empty box

**Review** `[ ]`

## FE-2 · Step 2 polish `[ ]`

- [ ] FE-2.1 Live cost preview — *"N fields × M phrasings ≈ K lookups"*
- [ ] FE-2.2 **Warn, never block**, above a large phrasing total. The cap was removed on purpose
- [ ] FE-2.3 Keyboard path end to end: type → Enter adds → Tab → Understand
- [ ] FE-2.4 Plan rows remember open/closed across re-renders — already true; pin it in a test

**Review** `[ ]`

## FE-3 · Progress that explains itself `[ ]`

- [ ] FE-3.1 Phase names in the student's words for each new phase (P0/P1/P2/P5)
- [ ] FE-3.2 Ledger surfaced live — *"read 4 of 12 admissions pages"*
- [ ] FE-3.3 A long phase shows **what it is waiting on**, not a spinner

**Depends on** CC-1. **Review** `[ ]`

## FE-4 · The professor modal, final shape `[ ]`

- [ ] FE-4.1 Identity: name, current role + department (P0), institution
- [ ] FE-4.2 Former appointments collapsed and labelled
- [ ] FE-4.3 Admissions block inherited from the institution, **with its scope and source shown**
- [ ] FE-4.4 Evidence fields with quote, source link, confidence
- [ ] FE-4.5 Translation marker + hover (T-1); the original is always reachable
- [ ] FE-4.6 "Is this them?" confirmation for `unverified` matches (P2-3)
- [ ] FE-4.7 Actions for blocked rows — shipped; keep working

**Review** `[ ]`

## FE-5 · Optional model key `[ ]` — *(the UI half of P7)*

- [ ] FE-5.1 Collapsed "Use my own model key (optional)" on step 1
- [ ] FE-5.2 Plain statement: **stays in this browser, sent only to Google, never to us**
- [ ] FE-5.3 "Test key" button — one cheap call, clear pass/fail
- [ ] FE-5.4 Clearing it is one click and immediate

**Review** `[ ]`

## FE-6 · Accessibility and honesty sweep `[ ]`

- [ ] FE-6.1 Every new control keyboard-reachable, labelled, focus-visible
- [ ] FE-6.2 `prefers-reduced-motion` respected by any new animation
- [ ] FE-6.3 **No new state renders blank** — every empty says *which* empty it is
- [ ] FE-6.4 `tools/e2e/record_flow.js` extended to assert each new surface

**Review** `[ ]`

---

# T-1 · Translation display *(Ahmed's icon)*

**Files**: `src/supervisorly/export/dashboard.py`, `src/supervisorly/export/json_export.py`,
`tests/test_translation_display.py` *(new)*

Ahmed asked for a marker showing a page was machine-translated, so a student knows the result
depends on that translation and should check the page before relying on it. Adopted — with the
evidence chain intact.

**The constraint that shapes it**: the quote must be verbatim in the stored snapshot. Translate
the page, store an English quote, and we have manufactured a sentence the page never contained.
That is fabricating evidence, with good intentions.

| layer | language |
|---|---|
| **snapshot** | the original, always |
| **quote** | original, verbatim — the gate verifies against it |
| **value** | may be normalised English (`open for PhD 2027`) |
| **translation** | display only, labelled |

**Subtasks**
- [ ] T-1.1 Snapshot and quote stay in the source language; the gate verifies against the original
- [ ] T-1.2 Optional `quote_translated` + `translated_by` travel **beside** the quote, never
      replacing it
- [ ] T-1.3 Dashboard shows a **translation icon**; hover explains it is machine-translated and
      that the original should be checked before relying on it
- [ ] T-1.4 The original sentence is **always reachable** from the UI
- [ ] T-1.5 Tests: a translated quote never satisfies the gate; the icon appears only when a
      translation exists

**Note** — no translation step is needed for *extraction*. Models read Arabic natively;
translation was only ever required for the English regex triage, and P4-1.4 already handles
that by escalating uncertain pages to the model instead of binning them.

**Acceptance** — an Arabic page yields an Arabic quote that verifies, an English display
translation, and a visible marker that it was translated.

**Review** `[ ]`
