# CC — Cross-cutting (do these first)

← back to [`README.md`](README.md) · invariants: [`00-invariants.md`](00-invariants.md)

Later phases depend on these. CC-1 and CC-3 in particular are prerequisites, not nice-to-haves.

---

## CC-1 · Phase ledger `[x]`

Every phase records attempted / reached / skipped-with-reason / cost, surfaced in the run
summary and the dashboard. This turns *"the dashboard looks thin"* into an answerable question
— the difference between this session's diagnosis taking ten minutes and taking an afternoon.

**Files**
- `src/supervisorly/model/runs.py`
- `src/supervisorly/pipeline.py`
- `src/supervisorly/export/json_export.py`
- `src/supervisorly/export/dashboard.py`
- `tests/test_phase_ledger.py` *(new)*

**Subtasks**
- [x] CC-1.1 `runs.record_phase(conn, run_id, phase, attempted, reached, skipped, reason, seconds, tokens=0)`
- [x] CC-1.2 A `phase_ledger` table, or reuse the `run_counts` JSON — **additive migration only**
      *(new table, schema v4; a new table IS additive, so `migrate` needed no rebuild path)*
- [x] CC-1.3 `_build_result` includes `ledger` in the export
- [x] CC-1.4 The dashboard's "How it works" panel renders it
- [x] CC-1.5 Tests: a phase that reached nothing still appears, with its reason

**Acceptance** — a run where P1 finds no admissions page shows
`P1 attempted 10 · reached 0 · skipped 10 (no admissions page found)`. Never absence.

**Done, 2026-07-29** (`176edf8`). Two decisions worth keeping:
- A skip with **no reason RAISES**. A blank "Why" cell reads to a student as "no reason"
  rather than "nobody recorded one" — which is the silence the table exists to remove.
- Rows order by `rowid`, not `created_at`: `utcnow()` is second-resolution, so timestamp
  ordering lets the ledger reshuffle between two reads of the same run.

Live rows today: `discovery`, `shortlist`, `optout`, `recent_works`, `deep_dive`, plus one
per flag-disabled phase. An opt-out is its own row, never folded into a skip count — D-023
makes that a *filtered result*, not a coverage gap.

**Review** `[R]` — invariants re-checked; `python -m pytest` green (907) with `TMPDIR`
outside the repo.

---

## CC-2 · Per-phase budgets `[ ]`

**Files**
- `src/supervisorly/fetch/budget.py` *(new)*
- `src/supervisorly/pipeline.py`
- `tests/test_budget.py` *(new)*

**Subtasks**
- [ ] CC-2.1 `Budget(fetches, seconds, tokens)` with `spend()` / `remaining()` / `exhausted()`
- [ ] CC-2.2 Each phase takes a budget; exhaustion **returns**, never raises
- [ ] CC-2.3 Exhaustion writes a ledger row with `reason="budget"`
- [ ] CC-2.4 Tests: an exhausted budget mid-phase leaves prior work intact and the run valid

**Acceptance** — cutting a budget to one fetch still produces a complete, honest dashboard.

**Review** `[ ]`

---

## CC-3 · Per-host concurrency, across **domains** `[ ]`

The unit is the **host/domain**, not the institution *(Ahmed's correction, 2026-07-29)*. One
university spans a main site, a scholar subdomain and faculty subdomains; sources span domains
belonging to no institution at all. Twenty concurrent means twenty **distinct hosts**.

**Files**
- `src/supervisorly/fetch/pool.py` *(new)*
- `src/supervisorly/fetch/ratelimit.py`
- `src/supervisorly/fetch/render.py`
- `tests/test_pool.py` *(new)*

**Subtasks**
- [ ] CC-3.1 `HostPool(max_concurrent=10)` — N workers, **at most one in-flight request per host**
- [ ] CC-3.2 Queue keyed by registrable domain; a host already in flight is **deferred, not dropped**
- [ ] CC-3.3 `ChromiumRenderer` acquires and releases pages through the pool
- [ ] CC-3.4 **Async page pool, not threads** — Playwright's sync API is bound to its creating
      thread, so threads buy contention rather than speed
- [ ] CC-3.5 Tests: 20 URLs across 3 hosts never issue two concurrent requests to one host

**Acceptance** — a 20-URL burst against one host serialises; across 20 hosts it parallelises.
Start at 8–10 concurrent pages (~1–2 GB against the worker's 4 GiB) and measure before raising.

**Review** `[ ]`

---

## CC-4 · Sessions the student can re-open `[ ]`

*(Ahmed, 2026-07-29.)* A finished result is kept and re-openable from the UI; starting a new
search never deletes an old one.

**Files**
- `src/supervisorly/export/webapp.py`
- `tests/test_sessions.py` *(new)*

**Subtasks**
- [ ] CC-4.1 Keep a **local list** of past job ids + field / country / date in `localStorage`
- [ ] CC-4.2 "Your past searches" panel on step 1 — open one, or start fresh
- [ ] CC-4.3 Starting a new scan **never** clears the list
- [ ] CC-4.4 A job past its 7-day TTL shows as expired **with the reason**, not as an error
- [ ] CC-4.5 "Forget this search" removes it locally — their device, their choice
- [ ] CC-4.6 Tests: the list survives a new scan; expired entries degrade honestly

**Constraint** — the job id **is** the access token (D-069). The list is local only, never
server-side, and jobs stay unlistable.

**Review** `[ ]`

---

## CC-5 · PDF text extraction `[x]`

Verified gap: the engine cannot see PDFs **at all**, and admissions information is frequently
PDF-only. Today such a page contributes nothing and says nothing about why.

**Files**
- `src/supervisorly/fetch/pdf.py` *(new)*
- `src/supervisorly/fetch/fetcher.py`
- `firebase/requirements.txt`
- `tests/test_pdf.py` *(new)*

**Subtasks**
- [x] CC-5.1 `extract_pdf_text(data) -> str | None` via `pypdf`, wrapped as a snapshot exactly
      like HTML so the quote gate is unchanged
- [x] CC-5.2 Detect `application/pdf` by **content-type and magic bytes**
- [x] CC-5.3 No text layer (scanned) → `blocked`, reason `"scanned PDF — no text layer"`
- [x] CC-5.4 Size cap — a 200 MB PDF must not be downloaded
- [x] CC-5.5 Tests: a text PDF extracts; a scanned PDF blocks with the reason; oversize refused

**Note** — code extracts the text; a model only *reads* it. Do not ask a model to do the
extraction.

**Done, 2026-07-29.** It needed a **transport change**, which the task did not anticipate:
`Response` carried only `text`, so a PDF body could not be recovered at all (binary decoded
as UTF-8 is destroyed) and the magic-byte sniff had nothing to look at. `Response` now also
carries `content: bytes`.

- **CC-5.4 required streaming.** `client.get()` downloads the whole body before returning, so
  a cap checked afterwards has already paid the cost. The live transport uses
  `client.stream()` with *two* guards: `Content-Length` up front for the honest case, and a
  running byte count for a chunked response that never declared its size. Either alone has a
  hole. Refusal is a state (`Response.oversize`), never an exception.
- **The `<pre>` envelope is load-bearing, not cosmetic.** `normalize.main_text` runs an HTML
  parser, so raw PDF prose containing `<` or `&` would be silently eaten — and a quote taken
  from that page would then fail against its own snapshot, so the gate would discard a *true*
  claim. Extracted text is escaped into `<pre>…</pre>` and stored like any other snapshot;
  the D-010 gate is untouched.
- `None` from `extract_pdf_text` means "nothing to read"; it must never become `""`, which
  reads as "we read it and it said nothing".
- `pypdf` is declared in **`pyproject.toml`**, not only in `firebase/requirements.txt`: the
  worker installs the package from the release tarball, so a dependency missing from that
  list is missing in production while every local test passes — the `page_extract.js` shape.
- Verified live as well as on cassettes: a real PDF over the network extracted, and a 500-byte
  cap refused a real response at 0 bytes downloaded. Cassettes cannot exercise the streaming
  path at all, which is exactly how a production-only break would have hidden.

**Review** `[R]` — invariants re-checked; `python -m pytest` green (982) with `TMPDIR`
outside the repo.

---

## FLAG · Shipping a half-finished phase safely `[x]`

Every phase lands behind a flag, default **off**, so the branch is always deployable and a bad
phase is one config change from gone.

**Files**
- `src/supervisorly/pipeline.py`
- `firebase/_core.py`, `firebase/worker.py`
- `tests/test_phase_flags.py` *(new)*

**Subtasks**
- [x] FLAG-1 `PHASES` env var, comma-separated (`"p0,p1"`), read once at worker start
- [x] FLAG-2 A phase not listed is skipped **and writes a ledger row saying so** — off must be
      visible, never silent
- [x] FLAG-3 Flags are **server config only**, never a request parameter (the D-068 rule)
- [x] FLAG-4 Test: with every phase off, output is byte-identical to today's

**Why** — the render rung shipped and did nothing for two deploys because a separate change had
quietly removed its input. A flag plus a ledger row makes that state legible instead of
requiring log archaeology.

**Done, 2026-07-29** (`5838759`), `src/supervisorly/phases.py`. Notes for whoever adds the
next phase:
- **`OPTIONAL_PHASES` lists only a phase that has a skippable call site.** It is `("p0",)`
  today and P0 is *not built* (SPIKE-0 missed), so nothing is gated yet in practice. Adding a
  name early would let `PHASES=p2` read as accepted while changing nothing — the exact
  failure this task exists to prevent. `PLANNED_PHASES` holds the rest and answers
  "recognised, not built yet", which is a different thing from "not a phase".
- **Off-rows are written in one place** in `run_live`, so each phase's call site is just
  `if flags.is_on(...)` and cannot forget to explain itself.
- **FLAG-4 read precisely**: the *evidence* output (professors, fields, envelopes, coverage)
  is byte-identical with everything off. The ledger gains rows — that is FLAG-2's whole
  point, and the two subtasks would otherwise contradict each other.
- The volatile-field list both byte-comparison tests need lives in `tests/helpers_export.py`.

**Review** `[R]` — invariants re-checked; `python -m pytest` green (926) with `TMPDIR`
outside the repo.
