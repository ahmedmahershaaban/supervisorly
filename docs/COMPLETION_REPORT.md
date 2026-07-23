# Supervisorly v1 — Completion Report

> Status of this document: **complete.** The build, self-run, four-pass adversarial refine loop,
> and clean-room verification are all done and green (135 tests, exit 0). The Definition-of-Done
> checklist (§8) is fully checked.

Supervisorly is a Claude-Code **skill + agents + deterministic tools** that helps a student
find a research supervisor (pre-PhD/RA, master's, PhD, postdoc, mentor) in **any country**,
producing a filterable, evidence-backed dashboard in which **every displayed fact is a Claim
with a verbatim quote verified against a stored snapshot**. It is built to be a public,
open-source portfolio piece; engineering quality is a hard requirement.

Build branch: `build/v1`. Commit range: **`9f07e31` (round 0, design baseline) … this report's
commit** — 34 tracked commits (rounds A–AA plus the Q–Z refine rounds), one round per commit, each
leaving the suite green.

---

## 1 — What was built

**Deterministic layer (zero LLM calls, D-009), `src/supervisorly/`:**
- `model/` — SQLite is the source of truth (D-026): `schema.sql` (the pipeline-state entities +
  the Claim/WebSource/Conflict provenance spine with the four-state envelope and confidence
  enum), `db.py`, `runs.py` (Run/Task/Checkpoint state machine incl. `awaiting_human_input` /
  `finalized_with_open_gaps`, resume via `incomplete_tasks` / `target_stage_done`), `claims.py`
  (the anti-hallucination control — a value claim whose quote is not in its snapshot is rejected
  before storage, D-010 — plus supersession + the `live_value`/`live_reached` precedence guards),
  `extraction_cache.py` (per-entity warm-rescan cache), `units.py` (the LOGIN_WALL coverage note).
- `fetch/` — `robots.py` (fail-closed), `normalize.py` (`main_text`, the volatile-masked
  `content_hash`, and `quote_in_snapshot`), `transport.py` (cassette + lazy httpx behind a seam),
  `snapshot.py` (content-addressed), `ratelimit.py`, `backoff.py` (exp. backoff + jitter on
  429/5xx), `fetcher.py` (robots-gated → rate-limited → retrying → snapshot-storing).
- `discover/roster.py` — directory triage: OPEN / LOGIN_WALL (→ human rung) / NOT_FOUND.
- `score/scorer.py` — intent-aware gates (D-059), OpenAlex topic-ID overlap (D-058), works
  reconciliation before scoring (D-057); `score/programs.py` — program roll-up (D-031).
- `extract/` — `md_grammar.py` (the one shared Phase-3 grammar, D-051), `chrome_prompt.py`
  (the emitting half of the human rung).
- `export/` — `json_export.py` (four-state envelopes + PII/no-bare-email redaction, D-024) and
  `dashboard.py` (a single self-contained offline HTML: filter, **Deadlines** watch-date view,
  clickable evidence detail panel).
- `ethics/optout.py` (+ repo `optout.txt`), `preflight.py` (fail-loud credentials + honest
  sparse-coverage warning), `pipeline.py` (`run_offline` / `reexport`), `ingest.py`
  (md-ingester), `demo.py` (synthetic offline fixture), `cli.py` (`version`, `init-db`, `scan`).

**Claude-Code layer:** `.claude/skills/supervisorly/SKILL.md` (orchestrator) and five agent
contracts (`recruiting-analyst`, `eligibility-analyst`, `profile-synthesist`, `evidence-auditor`,
`adapter-author`).

---

## 2 — Test & eval results

`python -m pytest` → **135 passed** (exit 0), 22 files:

| Area | Files | Tests |
|---|---|---|
| State machine / DB / claims | state_machine, claims | 13 |
| Contracts (MD grammar, JSON export, skill/agents, chrome prompt) | md_grammar, json_export, skill_contracts, chrome_prompt | 19 |
| Fetch (normalize, fetcher, backoff) | fetch_normalize, fetcher, backoff | 18 |
| Scoring & program roll-up | scorer, programs | 9 |
| Dashboard | dashboard | 9 |
| Deadline parser | deadline_parse | 19 |
| Discovery / coverage | discovery | 5 |
| Genericity eval (3 shapes / 3 countries) + CLI | eval_genericity, cli | 9 |
| Self-run (offline, zero-hallucination) | selfrun | 4 |
| Warm cache / resume | warm_cache, resume | 8 |
| Ethics gates (optout, PII, LLM-free, corpus) | ethics, optout, preflight | 22 |

**Eval thresholds (D-063):** met — the genericity set exercises **≥3 directory shapes across ≥3
countries** plus a non-English page and a robots-blocked one, and asserts honest per-shape states
with **zero hallucinated facts** (every `value`'s quote re-verified present in its snapshot).

---

## 3 — Edge-case matrix coverage (goal §3 — all 18 rows have a passing test)

| Edge case | Where covered |
|---|---|
| Sparse OpenAlex/ROR country | `test_preflight` (warn, not block) |
| Login-walled directory | `test_discovery` (roster-enumerate, LOGIN_WALL, nothing scraped) |
| Department page not found | `test_discovery` (distinct NOT_FOUND coverage) |
| Non-Western split/merged name | `test_scorer` (works reconciled, not dropped) |
| Interdisciplinary field | `test_scorer` (topic-ID overlap) |
| Zero professors match | `test_eval_genericity` (coverage-gap note; "none matched" vs "nothing returned") |
| Student never returns Phase-3 MD | `test_resume` (finalized_with_open_gaps, resumable) |
| Run interrupted, resumed later | `test_resume` (resume: completed targets not re-fetched) |
| Monthly re-scan, nothing changed | `test_warm_cache` (cache hits, no duplicate claims) |
| Missing ROR/OpenAlex key | `test_preflight` (fail loud with exact fix) |
| Volatile page chrome | `test_fetch_normalize` (hash stable) |
| Blocked source | `test_selfrun` / `test_fetcher` / `test_discovery` |
| Rate-limit 429 / 5xx | `test_backoff` (bounded exp. backoff + jitter) |
| Non-English page | `test_eval_genericity` (German → honest searched_absent) |
| Projected/not-published deadline | `test_dashboard` / `test_deadline_parse` (watch date, never firm) |
| Intent postdoc vs pre_phd vs phd | `test_scorer` (intent-aware gates) |
| Two great profs, same dept | `test_programs` (roll-up to one application) |
| A field/country never imagined | `test_eval_genericity` (invented discipline still runs) |

---

## 4 — Governing-constraint compliance

- **Generate, don't look up (D-038):** no embedded university list or per-field keyword
  dictionary; genericity proven on an invented discipline. Test-guarded.
- **Corpus is methodology-only (D-035):** no source file references the corpus path; guarded by
  `test_ethics::test_corpus_path_is_never_referenced_in_code`.
- **Deterministic layer is LLM-free (D-009):** guarded by
  `test_ethics::test_deterministic_layer_has_no_llm_calls`.
- **Every field is a verified Claim (D-010):** enforced in `claims.record_claim`; the self-run
  re-verifies every exported value's quote against its snapshot.
- **Honest four states (D-022/037/046):** distinct in export + dashboard; a professor is never
  dropped for missing data; an absence never downgrades a reached field.
- **Public sources + human rung (D-039/043/044):** robots fail-closed; walled directories routed
  to the Phase-3 human rung; never defeats a login.
- **Ethics in code (D-005/019/023/024/032/053):** opt-out enforced at build **and** on re-export;
  no bare-email / email-list / mailto leaks; no LLM-judgements exported; no bulk-outreach path;
  scan output/DB/snapshots never committed. All test-guarded.

---

## 5 — Self-run (goal §4)

The offline cassette self-run (`test_selfrun`, `test_eval_genericity`, `scan --demo`) drives the
full pipeline with **no network and no credentials** and produces a valid four-state export + a
self-contained dashboard with **zero hallucinated facts**, blocked professors present (not
dropped), and firm-vs-watch deadlines rendered honestly. `scan --demo --out output/dashboard.html`
writes a runnable dashboard + sibling JSON.

**Credentialed live smoke test:** **skipped** (no ROR/OpenAlex credentials available in this
environment) — recorded as skipped per goal §7, never as passed.

---

## 6 — Adversarial refine loop (goal §5)

Three adversarial audit passes were run as verification workflows (each finding independently
re-verified against the running code before it counted):

- **Pass 1** — 6 dimensions → **10 confirmed findings** (2 high, 8 medium): deadline parser
  (ordinals/numeric/calendar-validity/clause-binding), reexport opt-out, build-time email
  redaction, dashboard firm-vs-watch, http(s)-only source links, parsed-date deadline sort,
  per-entity cache key, resume-without-refetch. Fixed in rounds **Q–U**, each with a regression test.
- **Pass 2** — focused on the fixes → **6 confirmed findings** (3 high, 2 medium, 1 low): the
  `applications open` mis-cue + nearest-cue date binding, claim supersession/no-clobber precedence,
  over-broad `_NONFIRM`, email-list redaction, mailto source_url. Fixed in rounds **V–X**.
- **Pass 3** — lean re-audit (regression hunt + fresh correctness + completeness) → **2 findings**,
  **both regressions from pass-2's own round-V change** (the completeness and PII/correctness
  dimensions returned clean): the standalone `close(s)` cue over-matching, and `_NONFIRM` applied
  sentence-wide after per-clause date binding. Fixed in round **Y**.
- **Pass 4** — a final focused verifier on round Y found **1** still-reachable defect: `closes? on`
  was *still* too broad (fabricated firm deadlines from "office hours close on…", "gym registration
  closes on…"). Fixed in round **Z** by dropping the ambiguous close cues entirely and keeping only
  application/submission-specific ones — the parser now structurally cannot fabricate a firm
  deadline from a non-application sentence.

**Loop outcome:** finding counts **10 → 6 → 2 → 1** across passes, converging to only self-inflicted
regressions from earlier fixes, each closed with a regression test. The deadline parser was the
recurring hot-spot (it is the one heuristic natural-language component); it is now conservative by
construction (application-only cues, calendar-validated dates, nearest-cue binding, clause-scoped
demotion, "never guess" on ambiguity). Every one of the 19 total findings has a passing regression
test.

## 7 — Clean-room verification (goal §4 step 6)

All generated/transient state was town down — `.venv`, `.pytest_cache`, `*.egg-info`, every
`__pycache__` — after confirming `git status` showed **no tracked generated state, no personal data,
no scan output** (only the committed code/docs/synthetic fixtures, plus this report). From that clean
checkout the documented install was run fresh (`python -m venv .venv` → `pip install -e ".[dev]"`) and
the offline cassette self-test re-run with nothing pre-warmed.

**Result — green.** The fresh `pip install -e ".[dev]"` succeeded on the first try; `python -m pytest`
→ **135 passed** (exit 0) with freshly-compiled bytecode; `python -m supervisorly scan --demo` → exit
0, writing `dashboard.html` + `dashboard.json` and printing an ASCII status line; `python -m
supervisorly version` → `Supervisorly 0.1.0`.

The clean-room run **caught one real bug the test suite had masked** (round AA): `scan --demo` crashed
on its final `print()` because a Unicode arrow can't encode on the default Windows console (cp1252) —
pytest captures stdout as UTF-8, so the unit test never hit it. Fixed (ASCII output) and guarded with a
regression assertion; the clean self-test then passed on the first try. This is exactly the class of
"works under test, breaks when actually run" defect the clean-room step exists to surface.

## 8 — Definition of Done

- [x] Every phase (A–J) meets its DoD. (Build log records each phase + DoD.)
- [x] All unit + integration + eval tests pass; eval thresholds met (≥3 shapes / ≥3 countries).
      **135 passed**, exit 0.
- [x] **Every edge case in §3 has a passing test** (18/18 — table above).
- [x] The self-run (§4) produces a correct, honest dashboard from cassettes with **zero hallucinated
      facts** and all four states rendering.
- [x] The adversarial self-audit (§5) returns **no open findings** — four passes (10 → 6 → 2 → 1),
      all 19 findings fixed with regression tests; the last pass's findings were self-inflicted
      regressions since closed, and the completeness/PII/correctness dimensions returned clean.
- [x] Ethics gates verified by tests: optout (build **and** re-export), robots (fail-closed),
      no-bare-emails (incl. lists + mailto), no-bulk-path, corpus-never-read, deterministic-LLM-free.
- [x] Cost/latency within budget; warm re-scan issues ~0 re-extraction (entity-keyed cache);
      deterministic layer is LLM-free.
- [x] Docs updated: `README.md` (install, credentials, two run modes, `scan --demo`), `BUILD_LOG.md`,
      this `COMPLETION_REPORT.md`.
- [x] **Clean-room verification passes:** all generated state wiped; fresh install + offline self-test
      green from a clean checkout (the one bug it surfaced is fixed and re-verified green).
- [x] `git status` shows **no scan output / no personal data** staged; `.gitignore` honoured; only
      code, docs, and synthetic fixtures survive the teardown.
- [x] A final **`docs/COMPLETION_REPORT.md`** (this file) with numbers, edge-case coverage, honest
      limitations, and exact run steps.

**All boxes checked — the goal is complete.**

### Credentialed live smoke test (goal §4 step 4) — **skipped**, not passed
No ROR/OpenAlex credentials are available in this environment, and the live discovery rungs are
contract-and-seam (not yet wired end to end). Per goal §7 this step is recorded as **skipped**, never
as passed. It is the natural next build increment (see §9).

## 9 — Known limitations (stated honestly)

- **Deterministic signal tiers are intentionally simple.** Recruiting detection is a regex over
  page text and deadline parsing handles the common ISO / spelled-month / ordinal / numeric
  shapes; genuinely locale-ambiguous numeric dates (e.g. `01/12/2026`) are deliberately **not
  guessed**. Nuanced classification is the LLM analysts' Stage-2 job (defined as agent contracts;
  the deterministic self-run exercises the no-LLM path only).
- **The live discovery ladder (ROR/OpenAlex/sitemap/CT-log rungs) is contract-and-seam, not yet
  wired end-to-end;** the offline pipeline runs against cassettes. A live scan needs the two
  credentials in the README and is the natural next build increment.
- **The dashboard is a vanilla-JS single file.** The React/JSX + virtualiser vendoring (D-048) is
  a later refinement; the current build already meets its DoD (self-contained, offline, four-state,
  deadline-aware, clickable, injection- and scheme-safe).

## 10 — How to run

```bash
python -m venv .venv && .venv/Scripts/activate      # (Windows; use source .venv/bin/activate elsewhere)
python -m pip install -e ".[dev]"
python -m pytest                                    # 135 passing
python -m supervisorly scan --demo --out output/dashboard.html   # offline synthetic demo
```
A live scan additionally needs `SUPERVISORLY_ROR_CLIENT_ID` and `SUPERVISORLY_OPENALEX_KEY`
(see `README.md`).
