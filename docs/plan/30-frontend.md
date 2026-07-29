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

## FE-1 · Past searches on step 1 `[x]` — *(the UI half of CC-4)*

- [x] FE-1.1 Panel above the email field: past searches with ~~field, country,~~ date, status
      — **field and country are NOT stored**, see below
- [x] FE-1.2 "Open" re-enters step 5 for a finished job; "Start fresh" clears the form only
- [x] FE-1.3 An expired job (7-day TTL) says so and offers "run it again" — **never an error**
- [x] FE-1.4 On a first visit the panel is absent entirely — no empty box

**Done, 2026-07-29, with one deliberate reduction.** CC-4.1 asks for "job ids + field /
country / date" in `localStorage`; [D-069](../DECISIONS.md#d-069) says "no localStorage /
cookies for **plan** or email", and the field and country *are* the plan. A locked decision
outranks a plan task, so the list stores **the job id and the date only** and the conflict is
recorded as **[B-008](../BLOCKERS.md)** for Ahmed rather than resolved in favour of the nicer
label. The cost is real and stated there: rows read `29 July 2026, 14:05 · 7a3df6…`.

- Remembered at **scan start**, not completion — a scan the student walked away from mid-run
  is exactly the one they need the id for later.
- `pastOpen` re-enters step 5 and lets the normal poller decide what the job *is* now. Two
  places deciding job state is how they drift apart.
- Expiry is a 404/410 from the status endpoint, rendered as an explanation and a "run it
  again" button — a terminal state is never a dead end (D-070).
- Every storage call is wrapped: private mode, disabled storage and corrupt JSON all degrade
  to "no past searches". A convenience feature must never be able to fail a scan.

**Review** `[R]`

## FE-2 · Step 2 polish `[x]`

- [x] FE-2.1 Live cost preview — *"N fields × M phrasings ≈ K lookups"*
- [x] FE-2.2 **Warn, never block**, above a large phrasing total. The cap was removed on purpose
- [x] FE-2.3 Keyboard path end to end: type → Enter adds → Tab → Understand *(already shipped;
      Enter adds rather than submits, so a second field stays reachable from the keyboard)*
- [x] FE-2.4 Plan rows remember open/closed across re-renders — already true; pin it in a test

**Done, 2026-07-29.** The preview counts **topic lookups**, not requests: `/api/map` carries
every phrasing in ONE request (B-001), so "requests" would understate a wide search by a
factor of 50 and "lookups" is what actually gets spent. The warning above `COST_WARN_AT`
says the search *will still run* — D-074 removed the field cap on purpose, and a refusal would
make someone hide part of their own research. The e2e asserts the preview exists **and** that
it contains no blocking language.

**Review** `[R]`

## FE-3 · Progress that explains itself `[~]` — partially blocked

- [!] FE-3.1 Phase names in the student's words for each new phase (P0/P1/P2/P5) — **none of
      those phases is built** (P0 ✗, P1 ✗, P4/P5 ?, P2 not started), so there are no new phase
      names to translate. The §4.1 phase table already covers every phase that exists.
- [!] FE-3.2 Ledger surfaced live — *"read 4 of 12 admissions pages"*. The CC-1 ledger is
      written and **exported**, and the dashboard renders it after the run; surfacing it
      *during* a run needs the worker to stream ledger rows into the job document, which no
      phase currently produces rows for beyond the five that already exist.
- [x] FE-3.3 A long phase shows **what it is waiting on**, not a spinner *(shipped: the §4.2
      slow state names the phase and the target count, and the bar is indeterminate ONLY
      before the first count arrives — never a faked percentage)*

**Depends on** CC-1 *(done)* and on the phases themselves *(not built)*. **Review** `[ ]`

## FE-4 · The professor modal, final shape `[~]` — blocked on the phases that feed it

- [!] FE-4.1 Identity: name, current role + department (P0), institution — **P0 not built**
      (SPIKE-0 = 22%). Name and institution already show.
- [!] FE-4.2 Former appointments collapsed and labelled — same, needs P0's data
- [!] FE-4.3 Admissions block inherited from the institution, with scope and source —
      **P1 not built** (SPIKE-1 = 0% on the real cohort)
- [x] FE-4.4 Evidence fields with quote, source link, confidence *(shipped)*
- [x] FE-4.5 Translation marker + hover (T-1); the original is always reachable
- [!] FE-4.6 "Is this them?" confirmation for `unverified` matches — **P2-3 not started**
- [x] FE-4.7 Actions for blocked rows — shipped; verified still working (e2e, 54/54)

Four of seven need data no shipped phase produces. Building the UI for them now would be
rendering empty blocks and calling it done.

**Review** `[ ]` — reopen with P0/P1/P2

## FE-5 · Optional model key `[x]` — *(the UI half of P7)*

- [x] FE-5.1 Collapsed "Use my own model key (optional)" on step 1
- [x] FE-5.2 Plain statement: **stays in this browser, sent only to Google, never to us**
- [x] FE-5.3 "Test key" button — one cheap call, clear pass/fail
- [x] FE-5.4 Clearing it is one click and immediate

**Done, 2026-07-29.** The promise is enforced structurally, not just written on the panel:
the key never enters `state` (which is what gets serialised into a plan), tests assert no
line touching the key mentions `api(` or `/api/`, the POSTed plan carries no key-shaped field,
and a separate test reads the D-071 beacon's body and fails if it can reach the key at all —
that beacon is the real leak path, since it posts error text to us.

`Test key` calls Google **directly from the browser**, deliberately not through our API:
proxying it would be exactly what the panel promises never happens. It fails **soft** — a
blocked or offline request says nothing about the key, and the product does not need one.

The e2e asserts the panel's shape and its promise, and never pastes a real key: a test that
did would be putting a credential into a screencast.

**Review** `[R]`

## FE-6 · Accessibility and honesty sweep `[x]`

- [x] FE-6.1 Every new control keyboard-reachable, labelled, focus-visible *(the chips, the
      past-search Open/Forget buttons, the key panel and its inputs, the translation marker —
      all `:focus-visible` outlined; the marker carries `tabindex` + `aria-label`, because a
      `title` alone is invisible to a keyboard or screen-reader user)*
- [x] FE-6.2 `prefers-reduced-motion` respected by any new animation *(no new animation was
      added — the existing `reducedMotion()` guard still covers everything that moves)*
- [x] FE-6.3 **No new state renders blank** — the level filter says which empty it is, the
      expired job explains itself and offers a re-run, the past-searches panel is absent
      rather than empty on a first visit, and the ledger names its zero-reach phases
- [x] FE-6.4 `tools/e2e/record_flow.js` extended to assert each new surface

**Review** `[R]` — 54/54 against production, up from 33 at the start of this work.

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
- [x] T-1.1 Snapshot and quote stay in the source language; the gate verifies against the original
- [x] T-1.2 Optional `quote_translated` + `translated_by` travel **beside** the quote, never
      replacing it
- [x] T-1.3 Dashboard shows a **translation icon**; hover explains it is machine-translated and
      that the original should be checked before relying on it
- [x] T-1.4 The original sentence is **always reachable** from the UI
- [x] T-1.5 Tests: a translated quote never satisfies the gate; the icon appears only when a
      translation exists

**Done, 2026-07-29** (schema v5 — two nullable columns on `claim`).

- **The gate reads `quote`, never `quote_translated`.** The snapshot is in the page's own
  language, so a translation cannot appear in it; a gate that fell back to the translation
  would turn an English sentence no page ever contained into verified evidence. That is the
  one test in this file that is about D-010 rather than presentation.
- The export keys are **absent, not null**, when there is no translation — their presence is
  what makes the marker meaningful.
- Adding columns needed `_add_missing_columns` in `db.py`: `CREATE TABLE IF NOT EXISTS` is a
  no-op on an existing table, so a new column in `schema.sql` reaches a *new* database and
  never an old one, and a plain `ALTER` in that file is not idempotent.
- Nothing produces translations yet — P5 would. This is the display contract and the gate
  boundary, landed ahead of it so the boundary exists before anything can cross it.

**Note** — no translation step is needed for *extraction*. Models read Arabic natively;
translation was only ever required for the English regex triage, and P4-1.4 already handles
that by escalating uncertain pages to the model instead of binning them.

**Acceptance** — an Arabic page yields an Arabic quote that verifies, an English display
translation, and a visible marker that it was translated.

**Review** `[ ]`
