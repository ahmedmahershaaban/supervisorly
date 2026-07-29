# Implementation plan — phases, tasks, subtasks

Written 2026-07-29 to be executed by another engineer or model. Companions:
[PLAN_HARVEST.md](PLAN_HARVEST.md) (why) and
[PLAN_HARVEST_REVIEW.md](PLAN_HARVEST_REVIEW.md) (edge cases). This file is the *what* and
*where*.

## How to use this document

- Work **top to bottom**. Cross-cutting tasks (CC) come first because later phases depend on
  them. Phases are ordered by value per unit of effort, not by number.
- Every phase opens with a **SPIKE**. A spike is a throwaway script under `tools/spikes/`,
  never product code, that measures the real yield on ~10 institutions the live ladder
  returns. **If the spike misses its threshold, stop and re-plan** — do not build the phase.
  This exists because three confident estimates in one session (90%, 24%, "fixes the blocked
  rows") were 0%, 0/11 and 3/24 in reality.
- Marks: `[ ]` todo · `[~]` in progress · `[x]` done · `[R]` reviewed · `[!]` blocked (say why)
- A task is **not done until its tests pass and the full suite is green.**

## Invariants — check these on EVERY task before marking `[R]`

1. **D-010 quote gate** — no claim without a verbatim quote found in its stored snapshot. The
   quote is in the **source language**; the value may be normalised.
2. **D-038** — no authored URL, no institution list, no path dictionary. `tests/test_no_seed_urls.py`
   must stay green.
3. **Failure is a state, not an exception** — `blocked` / `searched_absent` / `never_attempted`
   with a reason. Nothing raises across a phase boundary.
4. **No cross-session cache** of page or institution data (Ahmed, 2026-07-29). Within one run,
   fetch each URL once.
5. **Per-host politeness** — robots checked, `HostRateLimiter` interval respected,
   abort-on-challenge honoured, **never two concurrent requests to the same host**.
6. **Coverage honesty** — every phase reports what it did not reach.
7. **Suite green**, and `python -m pytest` run with `TMPDIR` outside the repo.

---

# CC — Cross-cutting (do these first)

## CC-1 · Phase ledger `[ ]`

Every phase records attempted / reached / skipped-with-reason / cost, surfaced in the run
summary and the dashboard. Turns "the dashboard looks thin" into an answerable question.

**Files**: `src/supervisorly/model/runs.py`, `src/supervisorly/pipeline.py`,
`src/supervisorly/export/json_export.py`, `src/supervisorly/export/dashboard.py`,
`tests/test_phase_ledger.py` (new)

- [ ] CC-1.1 `runs.record_phase(conn, run_id, phase, attempted, reached, skipped, reason, seconds, tokens=0)`
- [ ] CC-1.2 A `phase_ledger` table (or reuse `run_counts` JSON) — additive migration only
- [ ] CC-1.3 `_build_result` includes `ledger` in the export
- [ ] CC-1.4 Dashboard "How it works" panel renders the ledger
- [ ] CC-1.5 Tests: a phase that reached nothing still appears with its reason
- **Acceptance**: a run where P1 finds no admissions page shows `P1 attempted 10, reached 0,
  skipped 10 (no admissions page found)` — never absence.
- **Review** `[ ]`

## CC-2 · Per-phase budgets `[ ]`

**Files**: `src/supervisorly/pipeline.py`, `src/supervisorly/fetch/budget.py` (new),
`tests/test_budget.py` (new)

- [ ] CC-2.1 `Budget(fetches, seconds, tokens)` with `spend()` / `remaining()` / `exhausted()`
- [ ] CC-2.2 Each phase takes a budget; exhaustion **returns**, never raises
- [ ] CC-2.3 Exhaustion writes a ledger row with `reason="budget"`
- [ ] CC-2.4 Tests: exhausted budget mid-phase leaves prior work intact and the run valid
- **Acceptance**: killing a budget to 1 fetch still produces a complete, honest dashboard.
- **Review** `[ ]`

## CC-3 · Per-host concurrency, across **domains** `[ ]`

Correction on the record: the unit is the **host/domain**, not the institution. One university
spans several domains, and sources span domains that belong to no institution.

**Files**: `src/supervisorly/fetch/ratelimit.py`, `src/supervisorly/fetch/pool.py` (new),
`src/supervisorly/fetch/render.py`, `tests/test_pool.py` (new)

- [ ] CC-3.1 `HostPool(max_concurrent=10)` — N workers, **at most one in-flight request per host**
- [ ] CC-3.2 Queue keyed by registrable domain; a host already in flight is deferred, not dropped
- [ ] CC-3.3 `ChromiumRenderer` accepts a pool; pages are acquired/released through it
- [ ] CC-3.4 Async page pool (**not threads** — Playwright's sync API is bound to its creating thread)
- [ ] CC-3.5 Tests: 20 URLs across 3 hosts never issue 2 concurrent requests to one host
- **Acceptance**: a 20-URL burst against one host serialises; across 20 hosts it parallelises.
- **Review** `[ ]`

## CC-4 · Sessions the student can re-open `[ ]`

Ahmed, 2026-07-29: a finished result is kept and re-openable from the UI; starting a new search
never deletes an old one.

**Files**: `src/supervisorly/export/webapp.py`, `firebase/_core.py`, `src/supervisorly/webapi.py`,
`tests/test_sessions.py` (new)

- [ ] CC-4.1 Page keeps a **local list** of past job ids + field/country/date in `localStorage`
- [ ] CC-4.2 "Your past searches" panel on step 1 — open, or start fresh
- [ ] CC-4.3 Starting a new scan **never** clears the list
- [ ] CC-4.4 A job whose 7-day TTL expired shows as expired with the reason, not as an error
- [ ] CC-4.5 "Forget this search" removes it locally (their device, their choice)
- [ ] CC-4.6 Tests: list survives a new scan; expired entries degrade honestly
- **Note**: the id **is** the access token (D-069) — the list is local only, never server-side,
  and jobs stay unlistable.
- **Review** `[ ]`

## CC-5 · PDF text extraction `[ ]`

Verified gap: the engine cannot see PDFs at all, and admissions info is frequently PDF-only.

**Files**: `src/supervisorly/fetch/pdf.py` (new), `src/supervisorly/fetch/fetcher.py`,
`firebase/requirements.txt`, `tests/test_pdf.py` (new)

- [ ] CC-5.1 `extract_pdf_text(bytes) -> str | None` via `pypdf`; wrapped as a snapshot exactly
      like HTML so the quote gate is unchanged
- [ ] CC-5.2 Detect `application/pdf` by content-type **and** magic bytes
- [ ] CC-5.3 No text layer (scanned) → `blocked`, reason `"scanned PDF — no text layer"`
- [ ] CC-5.4 Size cap; a 200 MB PDF must not be downloaded
- [ ] CC-5.5 Tests: text PDF extracts; scanned PDF blocks with the reason; oversize refused
- **Review** `[ ]`

---

# P0 — ORCID employments *(cheapest real content)*

### SPIKE-0 `[ ]` — `tools/spikes/spike_orcid_employments.py`
Of shortlisted professors from a live scan, how many have an ORCID with a **current**
employment (no `end-date`)? **Threshold: ≥ 30%.** Below that, P0 is cosmetic — re-plan.

## P0-1 · ORCID employments client `[ ]`
**Files**: `src/supervisorly/discover/orcid.py`, `tests/test_orcid.py`

- [ ] P0-1.1 `employments_url(orcid_id)` → `/v3.0/{id}/employments`
- [ ] P0-1.2 Parse `<employment:employment-summary>` → organisation, role-title, department,
      start/end date (namespace-aware, mirroring the researcher-urls parser)
- [ ] P0-1.3 **Split current vs past** on `end-date` presence — a former post shown as current
      is a correctness bug
- [ ] P0-1.4 Keep **all** concurrent appointments; never pick one
- [ ] P0-1.5 Failure/`404`/unparseable → `[]` + `failed_lookups`, never raises
- [ ] P0-1.6 Tests: end-dated is past; two concurrent both kept; malformed XML is empty not fatal
- **Review** `[ ]`

## P0-2 · Wire into the pipeline `[ ]`
**Files**: `src/supervisorly/pipeline.py`, `tests/test_profile_export.py`

- [ ] P0-2.1 `_attach_employments(targets, orcid_client)` beside `_attach_recent_works`
- [ ] P0-2.2 Shortlist only; one call per professor; `works_checked`-style attempted flag
- [ ] P0-2.3 `_profile_for` carries `employments_current` / `employments_past`
- [ ] P0-2.4 Ledger row via CC-1
- **Review** `[ ]`

## P0-3 · Show it `[ ]`
**Files**: `src/supervisorly/export/dashboard.py`, `src/supervisorly/export/json_export.py`,
`tests/test_dashboard_actions.py`

- [ ] P0-3.1 Modal: role + department + organisation, current first
- [ ] P0-3.2 Past appointments collapsed, labelled "former"
- [ ] P0-3.3 Source line: "from their ORCID record" — registry metadata, **not** quote-verified
      evidence (the existing disclaimer discipline)
- [ ] P0-3.4 Redaction pass covers the new fields (`_redact_profile`)
- **Acceptance**: a professor with a current post shows role + department; one with only a
  former post never shows it as current.
- **Review** `[ ]`

---

# P1 — Institution admissions pages *(biggest yield per fetch)*

### SPIKE-1 `[ ]` — `tools/spikes/spike_admissions.py`
For ~10 institutions the ladder returns: can an admissions/graduate page be **found by
following the site's own links within 3 hops**, and is it HTML (not PDF)? Record: found,
HTML vs PDF, language, whether a date is present. **Threshold: ≥ 40% found.**

## P1-1 · Institution-scoped claims `[ ]`
Claims are person-scoped today. Deadlines belong to an institution/faculty/programme.

**Files**: `src/supervisorly/model/schema.sql`, `src/supervisorly/model/claims.py`,
`tests/test_claims_institution.py` (new)

- [ ] P1-1.1 Confirm `entity_kind` supports `"institution"` (it is already a column) — additive
      migration only, no rewrite of existing rows
- [ ] P1-1.2 **Scope field** on the claim: `institution` / `faculty` / `programme` + the scope's
      own name
- [ ] P1-1.3 Tests: an institution-scope claim never silently becomes a person claim
- **Review** `[ ]`

## P1-2 · Find the admissions pages `[ ]`
**Files**: `src/supervisorly/discover/admissions.py` (new), `tests/test_admissions.py` (new)

- [ ] P1-2.1 Start from the institution URL the ladder discovered; **extract links**, never
      guess paths (D-038)
- [ ] P1-2.2 Classify a **fetched** page as admissions-relevant from its text
- [ ] P1-2.3 Depth ≤ 3, page budget per institution, robots, per-host serial (CC-3)
- [ ] P1-2.4 PDF → CC-5
- [ ] P1-2.5 Non-English → do **not** skip; hand to triage/model (P4/P5)
- **Review** `[ ]`

## P1-3 · Extract and scope the facts `[ ]`
**Files**: `src/supervisorly/pipeline.py`, `src/supervisorly/export/*`

- [ ] P1-3.1 Deadline / eligibility / language / funding at the **narrowest scope discovered**
- [ ] P1-3.2 **Past dates are historical**, never live deadlines — compare against today
- [ ] P1-3.3 Undeterminable programme level → refuse the claim (wrong level is worse than none)
- [ ] P1-3.4 Professors inherit with the **institution named as the source** and the scope shown
- [ ] P1-3.5 Tests: a faculty-scope deadline never leaks to another faculty; a past date never
      renders as current
- **Acceptance**: an institution deadline appears on its professors, labelled with its scope and
  source, and is never presented as the professor's own statement.
- **Review** `[ ]`

---

# P4 — Deterministic triage *(before any model spend)*

### SPIKE-4 `[ ]` — `tools/spikes/spike_triage.py`
On ~20 pages known to contain recruiting language, what share does triage keep (**recall**)?
And on 20 known-irrelevant pages, what share does it drop? **Threshold: recall ≥ 90%.**

## P4-1 · The triage module `[ ]`
**Files**: `src/supervisorly/extract/triage.py` (new), `tests/test_triage.py` (new)

- [ ] P4-1.1 `triage(text) -> "candidate" | "empty" | "uncertain"`
- [ ] P4-1.2 Signals: recruiting cue, date near an application word, supervision term, contact block
- [ ] P4-1.3 **Tuned for recall** — when in doubt, `candidate`
- [ ] P4-1.4 **Non-Latin / unknown-language text → `uncertain`, which escalates to the model**,
      never `empty`. This is the rule that stops Arabic sites reading as "no professors here"
- [ ] P4-1.5 Skip counts recorded in the ledger so the miss rate is measurable
- **Review** `[ ]`

---

# P5 — Model extraction *(batched)*

### SPIKE-5 `[ ]` — `tools/spikes/spike_llm_yield.py`
On 20 real pages, what share of proposals survive the quote gate, and what does a batch cost?
**Threshold: ≥ 60% survive.** A low rate means the prompt or the batching is wrong.

## P5-1 · Batching `[ ]`
**Files**: `src/supervisorly/extract/llm_claims.py`, `tests/test_llm_claims.py`

- [ ] P5-1.1 `build_batch_prompt(pages)` — several pages, one array back, each item carrying its
      page id
- [ ] P5-1.2 Batch by **bytes**, not page count
- [ ] P5-1.3 A proposal naming an unknown page id is dropped
- [ ] P5-1.4 Per-page failure isolation — one bad page costs itself only
- [ ] P5-1.5 **All quotes rejected in a batch → log a signal** (model degradation is otherwise
      indistinguishable from "these pages had nothing")
- **Review** `[ ]`

## P5-2 · Wire it in `[ ]`
**Files**: `src/supervisorly/pipeline.py`, `firebase/_core.py`

- [ ] P5-2.1 Runs after P4, on `candidate` + `uncertain` only
- [ ] P5-2.2 Every proposal through `claims.record_claim` — the gate is not re-implemented
- [ ] P5-2.3 Token budget (CC-2); exhaustion truncates and reports
- [ ] P5-2.4 Fail-closed: no key / any error → deterministic results stand alone
- **Acceptance**: with the model disabled the scan produces exactly today's output; with it
  enabled, every added claim carries a verbatim quote.
- **Review** `[ ]`

---

# P2 — Directory rung *(the expensive grind)*

### SPIKE-2 `[ ]` — `tools/spikes/spike_directory.py`
For ~10 institutions: is a people directory reachable within 3 hops by following links, and can
a named professor be located in it? **Threshold: ≥ 30%.**

## P2-1 · Bounded crawler `[ ]`
**Files**: `src/supervisorly/discover/crawl.py` (new), `tests/test_crawl.py` (new)

- [ ] P2-1.1 Frontier with depth cap, page cap, visited set
- [ ] P2-1.2 URL normalisation (strip fragments, sort/strip volatile query params, trailing slash)
- [ ] P2-1.3 **Dedupe by content hash as well as URL** (session ids serve one page at many URLs)
- [ ] P2-1.4 Per-URL-pattern cap — kills `?page=1..1000` traps
- [ ] P2-1.5 Redirect-loop and soft-404 guards
- [ ] P2-1.6 **Weak signals order the queue; they never exclude from it**
- [ ] P2-1.7 Robots + per-host serial via CC-3
- **Review** `[ ]`

## P2-2 · Directory + person-page classification `[ ]`
**Files**: `src/supervisorly/discover/roster.py`, `tests/test_roster_classify.py` (new)

- [ ] P2-2.1 `classify_page_kind(text, links) -> "roster" | "person" | "other"` — **deterministic
      first**: thirty short internal links with person-shaped anchors is a roster (counting, not
      judgement). Note: existing `classify_directory` answers *reachability*, not kind
- [ ] P2-2.2 Model only for the ambiguous remainder
- **Review** `[ ]`

## P2-3 · Identity matching + student confirmation `[ ]`
The most dangerous failure in the plan. Ahmed's answer: let the student confirm.

**Files**: `src/supervisorly/discover/ladder.py`, `src/supervisorly/export/dashboard.py`,
`tests/test_identity_match.py` (new)

- [ ] P2-3.1 Match requires surname + initial + institution agreement → `verified`
- [ ] P2-3.2 Weaker → `unverified`; **two people sharing a name at one institution → refuse**
- [ ] P2-3.3 Modal shows an unverified candidate as **"Is this them?" + a link to the page**
- [ ] P2-3.4 Confirmation is **recorded as evidence**, dated, extractor `student-confirmed`
- [ ] P2-3.5 An unconfirmed match is **never presented as a finding** in export or dashboard
- **Review** `[ ]`

---

# P6 — Historical cycles

### SPIKE-6 `[ ]` — `tools/spikes/spike_wayback.py`
For admissions URLs P1 found: how many have **≥ 3** archived cycles? **Threshold: ≥ 25%.**

## P6-1 · Archive client `[ ]`
**Files**: `src/supervisorly/discover/archive.py` (new), `tests/test_archive.py` (new)

- [ ] P6-1.1 CDX query for a URL P1 discovered — never a URL we authored
- [ ] P6-1.2 Fetch snapshots, extract dates
- [ ] P6-1.3 **Fewer than 3 cycles → no projection.** Two points are not a pattern
- [ ] P6-1.4 Projection labelled `watch · projected`, never `firm`
- [ ] P6-1.5 Archive slow/down → skip; never load-bearing
- **Review** `[ ]`

---

# P7 — Bring your own key

**CORS verified 2026-07-29**: preflight 200, `allow-origin` echoes our origin, `allow-headers`
includes `x-goog-api-key`. The browser can call Gemini directly.

## P7-1 · Key in the page, never on the server `[ ]`
**Files**: `src/supervisorly/export/webapp.py`, `tests/test_byo_key.py` (new)

- [ ] P7-1.1 Optional key field on step 1; stored in `localStorage` only
- [ ] P7-1.2 Expansion calls Gemini **directly from the browser** when a key is present
- [ ] P7-1.3 Key is **never** sent to our API, never logged, never in an error message
- [ ] P7-1.4 Invalid/revoked/quota-exhausted → fail closed to the student's own words
- [ ] P7-1.5 Tests: no code path posts the key to our origin; the D-071 beacon cannot carry it
- **Review** `[ ]`

---

# T — Translation display *(Ahmed's icon)*

## T-1 · Show a translation without weakening the evidence `[ ]`
**Files**: `src/supervisorly/export/dashboard.py`, `src/supervisorly/export/json_export.py`,
`tests/test_translation_display.py` (new)

- [ ] T-1.1 Snapshot and quote stay in the **source language**; the gate verifies against the
      original
- [ ] T-1.2 An optional `quote_translated` + `translated_by` travels **beside** the quote, never
      replacing it
- [ ] T-1.3 Dashboard shows a **translation icon**; hover explains it is machine-translated and
      that the original should be checked before relying on it — Ahmed's wording
- [ ] T-1.4 The original sentence is always reachable from the UI
- [ ] T-1.5 Tests: a translated quote never satisfies the gate; the icon appears only when a
      translation exists
- **Acceptance**: an Arabic page yields an Arabic quote that verifies, an English display
  translation, and a visible marker that it was translated.
- **Review** `[ ]`

---

## Suggested order

`CC-1 → CC-2 → CC-3 → SPIKE-0 → P0 → SPIKE-1 → CC-5 → P1 → SPIKE-4 → P4 → SPIKE-5 → P5 → T-1
→ CC-4 → SPIKE-2 → P2 → SPIKE-6 → P6 → P7`

CC-4 (sessions) and P7 (BYO key) are independent of the harvest chain and can be pulled forward
if the front end is being worked on separately.

## Definition of done, per task

1. Code + tests written; the tests describe the **property**, not the implementation
2. `python -m pytest` green (`TMPDIR` outside the repo)
3. The seven invariants re-checked
4. A ledger row exists if the task touches a phase
5. One commit, message saying what changed, what was run, and the result
6. Mark `[R]` only after the above

---
---

# Part 2 — the gaps Part 1 left open

Part 1 was a backend skeleton. This part adds what another engineer would otherwise have to
ask for: the front end as one coherent workstream, how to ship a phase safely, how to deploy
it, and rough sizing.

**On the numbering**: there is no P3 task list because P3 (capture page text, not DOM) is
**already shipped** — `extract/page_extract.js` + `fetch/browser_rung.py`. The gap in the
numbers is deliberate; the phase numbers match PLAN_HARVEST.md.

---

# FE — Front-end workstream

The student's experience as one thing rather than fragments. Independent of the harvest chain
except where noted, so this can run in parallel.

**Primary files**: `src/supervisorly/export/webapp.py` (the wizard) and
`src/supervisorly/export/dashboard.py` (the result). Both are generated pages; tests are
`tests/test_webapp*.py` and `tests/test_dashboard*.py`, and the real-browser harness is
`tools/e2e/record_flow.js`.

## FE-1 · Past searches on step 1 `[ ]` — *(= CC-4, shown here for the front-end view)*
- [ ] FE-1.1 Panel above the email field: past searches with field, country, date, status
- [ ] FE-1.2 "Open" re-enters step 5 for a finished job; "Start fresh" clears the form only
- [ ] FE-1.3 Expired (7-day TTL) rows say so and offer "run it again", never an error
- [ ] FE-1.4 On a first visit the panel is absent entirely — no empty box
- **Review** `[ ]`

## FE-2 · Step 2 polish `[ ]`
- [ ] FE-2.1 Live cost preview: "N fields x M phrasings — about K lookups"
- [ ] FE-2.2 Warn (never block) above a sensible phrasing total; the cap was removed on purpose
- [ ] FE-2.3 Keyboard path end to end: type, Enter adds, Tab, Understand
- [ ] FE-2.4 Plan rows remember open/closed across re-renders (already true — pin it in a test)
- **Review** `[ ]`

## FE-3 · Progress that explains itself `[ ]`
- [ ] FE-3.1 Phase names in the student's words for each phase added (P0/P1/P2/P5)
- [ ] FE-3.2 Ledger surfaced live: "read 4 of 12 admissions pages"
- [ ] FE-3.3 A long phase shows what it is waiting on, not a spinner
- **Depends on**: CC-1
- **Review** `[ ]`

## FE-4 · The professor modal, final shape `[ ]`
- [ ] FE-4.1 Identity block: name, current role + department (P0), institution
- [ ] FE-4.2 Former appointments collapsed and labelled
- [ ] FE-4.3 Admissions block inherited from the institution, **with its scope and source shown**
- [ ] FE-4.4 Evidence fields with quote, source link, confidence
- [ ] FE-4.5 Translation marker + hover (T-1); the original is always reachable
- [ ] FE-4.6 "Is this them?" confirmation for `unverified` matches (P2-3)
- [ ] FE-4.7 Actions for blocked rows (shipped — keep working)
- **Review** `[ ]`

## FE-5 · Optional model key `[ ]` — *(= P7, front-end view)*
- [ ] FE-5.1 Collapsed "Use my own model key (optional)" on step 1
- [ ] FE-5.2 Plain statement: stays in this browser, sent only to Google, never to us
- [ ] FE-5.3 "Test key" button — one cheap call, clear pass/fail
- [ ] FE-5.4 Clearing it is one click and immediate
- **Review** `[ ]`

## FE-6 · Accessibility and honesty sweep `[ ]`
- [ ] FE-6.1 Every new control keyboard-reachable, labelled, focus-visible
- [ ] FE-6.2 `prefers-reduced-motion` respected by any new animation
- [ ] FE-6.3 No new state renders blank — every empty says which empty it is
- [ ] FE-6.4 `tools/e2e/record_flow.js` extended to assert each new surface
- **Review** `[ ]`

---

# FLAG — Shipping a half-finished phase safely

Every phase lands behind a flag, default **off**, so the main branch is always deployable and a
bad phase is one config change from gone.

**Files**: `src/supervisorly/pipeline.py`, `firebase/_core.py`, `firebase/worker.py`

- [ ] FLAG-1 `PHASES` env var, comma-separated (`"p0,p1"`), read once at worker start
- [ ] FLAG-2 A phase not listed is skipped **and writes a ledger row saying so** — off must be
      visible, never silent
- [ ] FLAG-3 Flags are server config only, never a request parameter (the D-068 rule)
- [ ] FLAG-4 Test: with every phase off, output is byte-identical to today's
- **Why this exists**: the render rung shipped and did nothing for two deploys because a
  separate change had quietly removed its input. A flag plus a ledger row makes that state
  legible instead of requiring log archaeology.
- **Review** `[ ]`

---

# OPS — Deploying a phase (learned the hard way, twice)

`firebase deploy` **does not rebuild the worker.** The Functions tier and the Cloud Run Job are
separate images, and the scan pipeline lives in the worker. Deploying one and testing the other
has cost this project two full cycles.

For any change under `src/supervisorly/**`:

- [ ] OPS-1 Commit, then `git tag -a web-vN` and push the tag
- [ ] OPS-2 Point `firebase/requirements.txt` at the new tag — the package installs **from the
      tag**, never from disk
- [ ] OPS-3 Deploy Functions: `firebase deploy --only functions`
- [ ] OPS-4 Deploy the worker: stage `Dockerfile.worker`, `requirements.txt`, `main.py`,
      `_core.py`, `worker.py` into a scratch dir, then `gcloud run jobs deploy` with
      `--memory 4Gi --cpu 2`
- [ ] OPS-5 **Verify both**: `python tools/verify_deploy.py` for the page, and confirm the
      worker image **digest changed** — an unchanged sha256 means the scanner did not change
- [ ] OPS-6 Run one real scan; check `python tools/logs.py job <id>` and the new ledger rows
- [ ] OPS-7 Any new runtime data file (`*.js`, `*.sql`, …) must be added to `pyproject.toml`
      `package-data`. A file present in the repo and absent from the wheel fails **only in
      production** — exactly how `page_extract.js` went missing

---

# SIZE — rough effort, for sequencing

| task | size | risk | notes |
|---|---|---|---|
| CC-1 ledger | S | low | additive |
| CC-2 budgets | S | low | |
| CC-3 domain pool | **M** | **med** | async rewrite of the render path |
| CC-4 sessions | S | low | localStorage only |
| CC-5 PDF | S | low | `pypdf` plus a size cap |
| P0 ORCID employments | S | low | mirrors the shipped researcher-urls work |
| P1 admissions | **L** | **high** | new scope model, crawl, extraction |
| P4 triage | S | med | recall tuning is the risk |
| P5 model extraction | M | med | contract already written and tested |
| P2 directory rung | **L** | **high** | crawl traps plus identity matching |
| P6 archive | S | low | isolated |
| P7 BYO key | S | low | CORS already verified |
| T-1 translation | S | low | display only |
| FE-1…6 | M | low | spread across the above |

Two tasks carry most of the risk — **P1 and P2** — which is why both are gated by spikes.

---

# What is deliberately NOT in this plan

- **No cross-session caching** of page or institution data (Ahmed, 2026-07-29)
- **No installed coding agent** on the student's machine
- **No path or institution dictionaries** — `tests/test_no_seed_urls.py` enforces it
- **No translated quotes** — translation is display-only (T-1)
- **No Stage 4** (`recent_collaborators`) — still open as BLOCKERS B-002 and needs a decision
  before any code is written
