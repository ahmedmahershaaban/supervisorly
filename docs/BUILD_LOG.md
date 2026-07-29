# Build log

One short entry per milestone: what was built, what was run, what passed, what changed.
Newest at the bottom. Branches, in order: `build/v1` → `build/browser` → `build/web`.

---

## round 0 — design baseline (commit `9f07e31`)

The completed `docs/` design set, integrity-checked. No code. Starting point for implementation.

## round A — scaffold + schema (Phase A)

**Built:**
- `pyproject.toml` — package `supervisorly`, src layout, `[dev]` = pytest, module + console entry.
- `src/supervisorly/` — `__init__` (PRODUCT_NAME, version), `__main__` (`python -m supervisorly`),
  `cli.py` (`version`, `init-db`).
- `src/supervisorly/model/` — `schema.sql` (SQLite source of truth, D-026): the pipeline-state
  entities (Run/Task/Checkpoint/ExtractionCache/SearchPlan), the provenance spine
  (Claim/WebSource/Conflict) with the four-state envelope (D-046) and confidence enum (D-047), and
  spine stubs (Institution/Unit/Person). CHECK constraints encode the design's enums.
  `db.py` (connect + idempotent migrate), `runs.py` (Run/Task/Checkpoint state machine, D-029/D-049).
- `tests/` — `test_state_machine.py`, `test_cli.py`.
- `README.md`, this log; `.gitignore` extended to never commit `*.sqlite` (D-005).

**Ran:** `python -m pytest` → **9 passed** in a clean `.venv`. CLI `version` and `init-db` (incl.
nested-path) smoke-tested.

**Fixed (self-test caught it):** `init-db` failed with "unable to open database file" when the
parent directory didn't exist — sqlite3 won't create it. Now creates parents; regression test added.

**Environment note:** on this Windows machine, `pip install -e .` into the **global** Python 3.12
fails writing the `supervisorly.exe` console script into `C:\Python312\Scripts` (a permissions/path
quirk). Resolved by using a project **`.venv`** — the venv's Scripts dir is writable, install is
clean, and `python -m supervisorly` works regardless. The venv is the documented install path
(README) and what the clean-room verification (§4 step 6) will use.

**DoD (Phase A):** met — DB migrates idempotently; Run/Task state machine round-trips through
`awaiting_human_input` and `finalized_with_open_gaps`; resume via `incomplete_tasks`; the
ExtractionCache 4-tuple is unique.

## round B1 — Phase-3 Markdown grammar (commit `0f524d7`)

**Built:** `extract/md_grammar.py` — the single source of truth for the human-return format
(D-051): `parse`, `emit` (lossless), `to_claim_dicts` (extractor=human-assisted, D-043). A value
must cite a `source_url` (D-010); `searched_absent` records honest nulls (D-046). Contract doc.
**Ran:** pytest → **16 passed**. **DoD:** met — fixture round-trips losslessly; malformed input
fails loud.

## round B2 — JSON export contract (commit pending)

**Built:** `export/json_export.py` — `build_export` (claims → four-state envelopes + generic
field descriptors) and `validate_export` (D-046). Judgement/PII fields (`exportable: false`)
never serialise (D-024); every `value` cites a source (D-010); a professor with no claims is
still exported, all fields `never_attempted` (D-037). Contract doc.
**Ran:** pytest → **22 passed**. **DoD (Phase B contracts):** met — MD round-trips into claims;
the JSON validates against a worked example and rejects leaks.

## round C1 — fetch primitives: normalisation, cache hash, quote verification, robots (commit pending)

**Built:** `fetch/normalize.py` — `main_text` (faithful content, keeps dates, for quote
verification), `content_hash` (volatile tokens masked → stable cache key, cost §3b-i),
`quote_in_snapshot` (the anti-hallucination primitive, D-010). `fetch/robots.py` — `is_allowed`,
fail-closed (D-019/D-039), honest User-Agent. Pure stdlib (no HTML-parser dep) — testable offline.
**Ran:** pytest → **29 passed**, incl. the edge-case-matrix rows: *content hash stable across
volatile chrome* and *quote-in-snapshot rejects a fabricated quote*.

## round C2 — fetcher + cassette transport + snapshot store (commit pending)

**Built:** `fetch/transport.py` (Transport seam; `CassetteTransport` for offline determinism +
lazy httpx live transport), `fetch/snapshot.py` (content-addressed store, never in DB/committed —
D-026/D-005), `fetch/ratelimit.py` (per-host min-interval, injectable clock/sleep), `fetch/fetcher.py`
(robots-gated → rate-limited → snapshot-storing; blocked/404 marked, never a harder retry — D-039).
**Also fixed (self-review caught):** `content_hash` masked *all* ISO dates, so a changed application
deadline wouldn't invalidate the cache (would go stale, breaking D-061). Now masks only chrome
timestamps (last-updated/counters/copyright/clock); regression test added.
**Ran:** pytest → **35 passed**, incl. edge-case rows *404 marked not crashed*, *robots-blocked not
fetched*, *missing robots fails closed*, *deadline change invalidates cache*.
**DoD (Phase C):** substantially met — the fetch layer runs offline on cassettes with robots + rate
limit + snapshots. Remaining C work (the discovery ladder rungs) folds into Phase D wiring.

## round D1 — claim recorder (commit `07ca05f`)

`model/claims.py` — quote-in-snapshot enforced for tool/LLM value claims (hallucination rejected
before storage, D-010); four states; human-assisted accepted without snapshot (D-043). pytest → 41.

## round B3 — SKILL.md + agent contracts (commit pending)

**Built:** `.claude/skills/supervisorly/SKILL.md` (the orchestrator: intent→SearchPlan→confirm→
tiers/phases→dashboard, with the D-055 vocabulary crosswalk and the governing rules), and the five
agent definition files (`recruiting-analyst`, `eligibility-analyst`, `profile-synthesist`,
`evidence-auditor`, `adapter-author`) with frontmatter + contracts (inputs, task, output = write
claims / return status, never prose). `tests/test_skill_contracts.py` guards their structure.
**Ran:** pytest → **44 passed**. **DoD (Phase B):** complete — contracts (MD, JSON) + SKILL + agents
all written and validated.

## round E — scoring: intent gates, topic-ID match, works reconciliation (commit pending)

**Built:** `score/scorer.py` — `gates_for`/`evaluate_eligibility` (intent-aware, D-059; only
`quoted_official`/`derived` failing facts block — D-047; unreliable facts sort not gate — D-023),
`topic_match` (deterministic OpenAlex topic-ID overlap, interdisciplinary-safe, D-058),
`reconcile_works` + `score_professor` (fragmented non-Western profiles reconciled before scoring so
they aren't wrongly dropped; disambiguation risk lowers score *confidence* not activity — D-057),
re-weightable weights + tier bands.
**Ran:** pytest → **49 passed**, incl DoD rows: *pre_phd not gated on PhD rules*, *fragmented
profile reconciled not dropped*, *topic-ID interdisciplinary match*, *re-weightable*.

## round G1 — chrome-prompt-generator: the emitting half of the human rung (commit pending)

**Built:** `extract/chrome_prompt.py` — `generate_prompt` builds the ready-to-paste Claude-for-Chrome
prompt for a professor's open gaps (ethics/provenance preamble, target, anchor links, the specific
missing fields), and embeds the required output shape by calling `md_grammar.emit` — the **same
module** the ingester parses (D-051), so the two halves can't drift. Consolidated per professor (D-032).
**Ran:** pytest → **52 passed**, incl. the seam guarantee: *the generated example parses under the
real grammar*. The human rung is now complete on both ends (generator + ingester share one grammar).

**Remaining phases:** F (dashboard: four-state HTML+JSX, deadline view), G2 (orchestration glue:
end-to-end scan driver on cassettes tying discovery→fetch→extract→score→export; roster-enumeration),
H (hand-labelled cassette eval set + golden-path integration), I (self-run), J (refine), then
clean-room verify.

---

### Status at earlier checkpoint
10 rounds, 52 tests. Foundation + contracts + fetch + provenance + scoring + human-rung emit half.

## round F — self-contained dashboard (commit `12c7173`)
`export/dashboard.py` — single-file HTML, four states distinct, no CDN/offline, script-safe. pytest → 56.

## round G2+I — end-to-end pipeline + the self-run (commit pending)

**Built:** `pipeline.py` `run_offline` — fetch → deterministic regex signal extraction → quote-verified
claim → export → dashboard, no LLM / no network (cassettes). Added `claims.record_web_source` +
`claims_for` join so claims resolve their `source_url`. `tests/test_selfrun.py` = **the self-run**
(goal §4): a full offline scan produces a valid export with value/searched_absent/blocked across 3
professors (nobody dropped) and a self-contained dashboard, and asserts **zero hallucinated facts**
(every value's quote re-verified present in its snapshot).
**Fixed (self-run caught):** value claims weren't citing a source_url → export rejected them (D-010);
now the pipeline records a `web_source` and the claim references it.
**Ran:** pytest → **60 passed**. **DoD Phase I:** core met — the offline self-run is green with zero
hallucinations and the four states rendering.

**Remaining:** H (broaden the eval set to ≥3 directory shapes/≥3 countries per D-063; wire `scan` into
the CLI), roster-enumeration (D-052, minor), J (adversarial refine loop + COMPLETION_REPORT),
clean-room verify.

## round H — genericity eval set + `scan` CLI (commit pending)

**Built:** `demo.py` — a fully **synthetic** offline fixture (invented names, `example` domains, no
real person — D-035): three directory *shapes* (`<main><p>`, `<section><ul><li>`, nested
`<div class=bio>`) across three countries, plus a **non-English** (German) page and a **robots-blocked**
one — the D-063 genericity bar. `cli.py` gains `scan --demo --out` (writes dashboard `.html` + export
`.json`, creating parent + `.cache/snaps`). `tests/test_eval_genericity.py` asserts, across all shapes:
valid export, every professor present (nobody dropped), honest per-shape states (three `value`,
German → `searched_absent`, blocked → `blocked`), **zero hallucinations** (each value's quote
re-verified in its snapshot), the **zero-result** edge case (empty targets → valid empty export +
"no professors" dashboard, not a crash), and the CLI writing both files.
**Fixed (self-test caught):** the AU demo page originally read *"No openings are advertised"* — a
*negative* recruiting statement. The deterministic English signal tier correctly returns
`searched_absent` on it (it surfaces positive candidates only; negatives are the LLM analyst's Stage-2
call), which contradicted a test expecting `value`. Rather than weaken the tier, the demo's AU page
now carries a genuine positive in the third markup shape ("accepting a new PhD student"), so the demo
cleanly shows shape-diversity detection and the German page remains the honest-absent example.
**Ran:** pytest → **65 passed** (exit 0). **DoD (Phase H):** met — genericity holds across ≥3 shapes /
≥3 countries, non-English is honest not guessed, blocked isn't dropped, zero-result is graceful, and
`scan --demo` is a runnable end-to-end entry point.

## round I — deadline/urgency view + clickable detail + deadline extraction (commit pending)

Closes the two Phase-F gaps the docstring promised but the code lacked: the **deadline view**
(D-061) and **clickable professor detail** (goal §4 step 2).

**Built:**
- `export/dashboard.py`: a **Deadlines** view ("what closes soon") over any date-typed field,
  sorted soonest-first, that renders a *projected* date (envelope confidence
  inferred/unconfirmed/action_needed) as a **watch** badge — visually distinct from a **firm**
  officially-quoted one — with an on-page note that watch dates are not published deadlines
  (D-061: never shown as firm). A keyboard-accessible **detail panel**: clicking a professor
  (row or deadline card) opens an aside listing every field with value, **verbatim quote**,
  source link, and confidence — so every displayed fact is traceable (D-010). Still one
  self-contained offline file, script-injection-safe.
- `pipeline.py`: extraction is now **field-driven** (`_EXTRACTORS`: field_id → deterministic
  extractor) so a blocked page marks *every* field `blocked` (not `never_attempted`) and adding
  a field is one row + one descriptor (D-038). New `extract_deadline` finds a dated deadline
  sentence and marks it firm vs *projected* from unambiguous cue words ("usually"/"each year");
  `_normalize_date` parses ISO / "1 December 2026" / "December 1, 2026" to ISO deterministically
  and **requires day+month+year** — a bare month is never invented into a date.
- `demo.py`: Ada carries a firm published deadline, Ben a projected one → the demo deadline view
  shows a real firm + watch pair.

**Ran:** pytest → **69 passed** (exit 0), incl. `test_deadline_view_present_and_distinguishes_firm_from_watch`,
`test_watch_date_is_driven_by_confidence_not_guessed`, `test_professor_detail_is_clickable_and_traceable`,
and `test_demo_deadlines_firm_vs_projected` (Ada firm 2026-12-01 / Ben watch 2026-09-15, both parsed
not guessed; Cara searched_absent; Eve blocked). **DoD (Phase F):** now fully met — four states +
deadline sort + clickable detail all present; edge-case row *projected deadline → watch date* covered
through the real pipeline.

## round K — preflight: fail-loud credentials + honest sparse-coverage warning (commit pending)

Two edge-case rows (D-014/020 missing keys; D-060 sparse country) as one small module.

**Built:** `preflight.py` — `require_credentials(env)` **raises** `MissingCredentials` naming each
missing var (`SUPERVISORLY_ROR_CLIENT_ID`, `SUPERVISORLY_OPENALEX_KEY`) *and how to get it*, and
points at `--demo` (never runs silently on throttled anonymous tiers, D-020). `coverage_preflight(stats)`
returns **warnings and never raises** — a thin OpenAlex/ROR country is stated up front and the run
continues (D-060). `env` is injected, so both are testable without touching the process environment;
the offline demo path never calls `require_credentials`.
**Ran:** pytest → **75 passed** (exit 0), incl. missing/partial/complete credentials, sparse-warns-not-blocks,
well-covered-is-quiet, and *the offline demo needs no credentials*.

## round L — directory triage: roster-enumeration, LOGIN_WALL, distinct coverage (commit pending)

Three edge-case rows (login-walled directory; department not found; zero-result distinction)
via a new `discover` package + a run-level coverage note.

**Built:**
- `discover/roster.py` — `classify_directory` sorts a directory fetch into **OPEN /
  LOGIN_WALL / NOT_FOUND**. A robots `Disallow` *or* a login/bot wall in the page →
  LOGIN_WALL; `route_directory` then enqueues a `roster_enumerate` **human** task
  (`awaiting_human`) and marks the unit `LOGIN_WALL` — it **never reads or scrapes** the
  walled content (D-039/044/052). A 404/unreachable dir → `NOT_FOUND`, a *distinct* coverage
  gap, no human task. `detect_login_wall` is deliberately conservative so a real roster isn't
  mislabelled.
- `model/units.py` — `upsert_unit` / `set_unit_coverage` / `get_unit` (the `coverage_note`
  spine, D-052).
- `pipeline.py` + `dashboard.py` — the run now carries an honest **coverage line** so the
  empty-state tells *"sources returned nothing"* (a coverage gap) apart from *"found people,
  none matched"* (a filter) — the deterministic pipeline never drops a professor, so zero
  means discovery surfaced no one (D-046).
**Ran:** pytest → **80 passed** (exit 0), incl. three-way classification, *login-wall routes to
the human rung and scrapes nothing* (asserts no person tasks created), *not-found is distinct
coverage with no human task*, and the zero-result coverage-gap note.

## round M1 — polite backoff on 429/5xx (commit pending)

Edge-case row *rate-limit 429 / 5xx → exponential backoff + jitter; never retries harder*.

**Built:** `fetch/backoff.py` — `RetryPolicy` with exponential (`base*2**attempt`), **capped**
delays plus injectable jitter; `RETRY_STATUSES = {429,500,502,503,504}`. `fetch/fetcher.py`
now retries those (and transient transport errors) up to `max_retries`, waiting the policy
delay each time, then **gives up** and returns a marked result — it never escalates to a login
or a faster loop (D-039/044). `FetchResult.attempts` records how many hits it took. The offline
pipeline injects a no-op sleep (cassettes never rate-limit). Sleep + jitter are injected, so the
tests are deterministic.
**Fixed (self-test caught):** the jitter test asserted on `slept` **without calling `fetch()`** —
it was green only by accident of an empty list; added the missing call so it actually exercises
the retry (now asserts `[1.5]`).
**Ran:** pytest → **85 passed** (exit 0): retries-then-succeeds (`[1.0, 2.0]`), gives-up-after-max
(exactly 3 waits, non-decreasing, ≤ cap, attempts=4), delays-capped (`[10,15,15]`), jitter bounded,
and *404 is not retried*.

## round M2 — warm-rescan ExtractionCache (commit pending)

Edge-case row *monthly re-scan, nothing changed → ~zero re-extraction; normalised-hash cache hits*.

**Built:** `model/extraction_cache.py` — `lookup`/`record` over the 4-tuple (content-hash, prompt,
model, schema). `pipeline.run_offline` now takes an optional persistent `db_path`, hashes each page's
normalised content, and on a cache hit **reuses the prior run's claims** — no fresh extraction, no
duplicate claims (cost §3b-i). It also now finalises `finalized_with_open_gaps` when a target was
blocked (D-049), appends that to the coverage line, and returns `stats {extractions, cache_hits}`.
Export/dashboard assembly refactored into `_build_result` (shared with the resume path to come).
**Ran:** pytest → **87 passed** (exit 0): a cold run extracts every reachable page (`cache_hits==0`);
the warm re-scan does `extractions==0`, `cache_hits≥4`, **adds no duplicate claims**, and yields an
identical honest export; a genuine content change **busts** the cache and re-extracts only that page.

## round M3 — the human rung, end to end: md-ingester + no-fetch re-export (commit pending)

Edge-case rows *student never returns Phase-3 MD* and *run resumed later, nothing re-fetched* —
completing Phase G's DoD.

**Built:**
- `ingest.py` — `ingest_md(conn, md_text)` parses a Phase-3 return in the shared grammar
  (`extract.md_grammar`) and records each block as a normal, provenance-carrying Claim
  (`extractor = 'human-assisted (Claude for Chrome)'`, its walled `source_url` logged as a
  `human_assisted` web source). Human data is not privileged (D-043).
- `model/claims.py` — `supersede_prior`: a filled field **supersedes** the earlier head
  (typically the `blocked` placeholder), so the gap closes and `claims_for` returns the human
  answer as the single live head — history kept (append-only).
- `pipeline.reexport(db_path, targets)` — rebuilds the export + dashboard from the DB + disk
  snapshots and **constructs no transport or fetcher**, so nothing can be re-fetched (D-029);
  it re-derives `finalized` vs `finalized_with_open_gaps` from whether any field is still
  blocked (D-049).
**Ran:** pytest → **89 passed** (exit 0): an abandoned Phase-3 still finalises a dashboard
(`finalized_with_open_gaps`, the walled prof present + `blocked`, not dropped); the MD return
records 2 claims, and `reexport` flips the run to `finalized`, shows the human value with its
`x.com` source, keeps the export valid — while a **counting transport proves zero re-fetches**.

## round N — program roll-up + genericity of an unimagined field (commit pending)

Closes the last two edge-case rows (D-031 roll-up; D-038 arbitrary field/country).

**Built:** `score/programs.py` — `group_by_program` rolls shortlisted professors up to their
shared graduate program so the student **applies and pays once** per program, not per professor
(D-031); a professor with no known program stays its own singleton group (no invented shared
program). Pure, order-preserving, no model call.
**Tests:** `test_programs.py` (same-program roll-up, different-programs-separate, no-program-solo,
order preserved) and a genericity test that an **invented discipline** ("quantum basket weaving")
in a novel markup shape still runs and extracts honestly — proving there is no embedded field
dictionary (D-038).
**Ran:** pytest → **94 passed** (exit 0). **All 18 edge-case-matrix rows now have a passing test.**

## round O — ethics gates in code: opt-out, no-bare-email, LLM-free, corpus-never-read (commit pending)

The §6 DoD requires these as *tested* gates, not prose. Closed the remaining ones.

**Built:**
- `ethics/optout.py` + repo `optout.txt` (empty template) — the **opt-out suppression list**
  (D-023/032/053). `run_offline(..., optout_path=)` drops a matched person **before any fetch**
  (never requested, scored, shown, or stored); identifiers matched: id/url/homepage/orcid/
  openalex/ror/name, case-insensitive, trailing-slash-insensitive.
- `export/json_export.py` — the **no-bare-email** rule (D-024): an `email`-typed field is dropped
  at build like a non-exportable one; `validate_export` flags a leaked email descriptor **and** a
  value that *is* a bare address (while leaving an email merely *mentioned inside a sentence*
  alone, so real recruiting quotes aren't false-positived).
**Tests:**
- `test_optout.py` — the required *failing test*: suppressing Ada by URL removes her from the
  export (and the counterfactual shows she's present without it); parsing ignores comments/blanks.
- `test_ethics.py` — email-field dropped at build; validate rejects a leaked email descriptor and a
  bare-email value; an incidental in-sentence email is **not** flagged; the **deterministic layer
  is LLM-free** (scans discover/fetch/model/score/export/pipeline/ingest for model markers); the
  **methodology corpus path is never referenced** in code (D-035); **no bulk-outreach** helpers exist.
**Ran:** pytest → **105 passed** (exit 0). Ethics gates (optout, robots, no-bare-emails,
no-bulk-path, corpus-never-read, LLM-free) are now all test-guarded.

## round P — README run-modes/credentials + CLI `--optout` (commit pending)

Docs DoD: honest install incl. required credentials, the two run modes, and `scan --demo`.

**Built:** `README.md` — a **Run a scan** section (offline `scan --demo` vs live), the credential
**env-var names** in a table (`SUPERVISORLY_ROR_CLIENT_ID`, `SUPERVISORLY_OPENALEX_KEY`) with where
to get them, the dashboard's deadline/detail/four-state behaviour, and an **Opt-out** section.
`cli.py` — `scan --optout <path>` wired through to `run_offline(optout_path=...)` so the documented
flow works. **Ran:** pytest (CLI) → green; full suite still **105 passed**.

---

# Phase J — adversarial self-audit (goal §5) and the fixes it drove

A 6-dimension adversarial audit (correctness/provenance, edge-cases, ethics, genericity,
performance/cost, UX-honesty) ran as a verification workflow: each auditor read the real source;
an independent skeptic then had to *refute* each finding against the code before it counted.
**10 findings survived verification** (2 high, 8 medium). Each is fixed below with a regression
test; the loop repeats until the audit is clean.

## round Q — refine: deadline parser correctness + genericity (findings 2, 3, 4) (commit pending)

**Fixed in `pipeline.py`:**
- **(genericity, high)** `_normalize_date` now recognises **ordinal** dates ("1st December 2026",
  "December 1st, 2026") and **numeric** `dd/mm/yyyy` (disambiguated by the >12 rule); a real dated
  deadline is no longer mis-recorded as `searched_absent`. A genuinely ambiguous numeric date
  (both parts ≤12) is **not guessed** — honesty over a coin-flip (D-046).
- **(correctness, medium)** impossible calendar dates (Feb 31, Apr 31, `2026-02-30`) are rejected
  via `datetime.date` validation — never invented into a `quoted_official` value (D-010/D-061).
- **(correctness, medium)** a date bound in a *different clause* than the deadline cue
  ("deadline has passed, but term begins 1 September 2026"; "no fixed deadline; year begins …")
  is downgraded to a **watch** date via `_NONFIRM` — never shown as firm (D-061). Numeric dates
  are watch too (locale-uncertain).
**Ran:** `tests/test_deadline_parse.py` (8 new) + full suite → **113 passed** (exit 0). The demo's
firm/watch pair and all prior deadline tests still hold.

## round R — refine: human-rung parity guards (findings 6, 8, 9, 10) (commit pending)

Values arriving via the human rung bypass the deterministic extractors, so the same honesty/PII/
safety guards are now enforced at **build and render** time.

**Fixed:**
- **(ethics, medium — finding 6)** `json_export._redact_pii` redacts a value/quote that *is* a bare
  email at **build** (the shipping path never called `validate_export`); a mentioned-in-a-sentence
  email is left intact (D-024).
- **(UX-honesty, medium — finding 8)** `dashboard.py` firm/watch now keys on `FIRM_CONF =
  {quoted_official, derived}`: a `null`/unknown confidence (reachable when the human rung omits the
  optional field) renders **watch**, never firm (D-061).
- **(UX-honesty, medium — finding 9)** `srcLink`/`safeUrl` only linkify an `http(s)` `source_url`;
  a `javascript:`/`data:` URL (possible via the human rung) is shown as inert text, never a live
  link — closing an XSS vector `esc()` didn't cover.
- **(UX-honesty, medium — finding 10)** the Deadlines view now sorts by a **parsed date key**
  (`Date.parse`, unparseable → last) instead of lexicographically, so a non-ISO human-returned date
  ("March 1, 2026") orders correctly in a "what closes soon" view.
**Ran:** full suite → **116 passed** (exit 0), incl. new tests for redaction, firm-requires-official-
confidence, scheme-guarded source links, and parsed-date sort; stale `WATCH_CONF`/lexicographic-sort
assertions updated.

## round S — refine: opt-out on the resume/re-export path (finding 1) (commit pending)

**Fixed (ethics, high — finding 1):** `pipeline.reexport` now takes `optout_path` and applies
`load_optout` + `filter_targets` before building the export, so a person who opts out **after** their
claims were stored is dropped from the re-exported dashboard/JSON — opt-out was previously enforced
only on `run_offline`'s fetch path (D-023/D-053). **Ran:** `tests/test_optout.py::
test_reexport_resume_path_also_honours_optout` (Ada opts out after round 1 → absent from re-export,
name nowhere in the JSON, `opted_out == 1`) + full suite → **117 passed** (exit 0).

## round T — refine: ExtractionCache keyed per-entity (finding 7) (commit pending)

**Fixed (performance/honesty, medium — finding 7):** the extraction cache was keyed on content
only, so two professors with byte-identical pages collided — the second got a cache hit, recorded
no claims, and was dishonestly shown `never_attempted` for a page that *was* fetched (violating
D-022/037/046). `extraction_cache` now includes `entity_kind`+`entity_id` in its UNIQUE key and
`lookup`/`record` take the entity, so a hit means "already extracted **for this professor**". Warm
re-scan (same entity, same content) still hits; cross-entity identical content no longer collides.
**Ran:** `test_identical_content_across_professors_does_not_drop_the_second` (both → `value`,
`extractions==2`) + full suite → **118 passed** (exit 0).

## round U — refine: resume-without-refetch (finding 5) (commit pending)

**Fixed (edge-case/cost, medium — finding 5):** `run_offline` re-fetched every target on each call,
so the edge row *"run interrupted mid-Stage-2, resumed later → nothing re-fetched (D-029)"* was
neither implemented nor tested. Added `runs.target_stage_done` and a `run_offline(resume=True)` path
that **skips (does not re-fetch)** any target whose deep-dive Task is already `done` in the persisted
DB; its claims are reused from storage, and `stats["resumed_skipped"]` records how many. **Ran:**
`test_resume_does_not_refetch_already_completed_targets` (a counting transport proves p1/p2 are not
re-requested on resume while a newly-added p3 is; all three present in the export) + full suite →
**119 passed** (exit 0). **The adversarial audit's 10 findings are now all fixed with regression tests.**

---

# Phase J — second-pass audit (goal §5 loop) and its fixes

A leaner second audit over the changed surfaces (+ a completeness critic) surfaced **6 more
verified findings** — mostly *adjacent* issues the first fixes exposed. Fixing each below.

## round V — refine²: deadline cue/clause binding (findings 1, 4) (commit pending)

**Fixed in `pipeline.py`:**
- **(finding 1, high)** `"applications open"` was a deadline cue, so an *opening* date was emitted
  as a firm deadline. Removed `open` from the cue; the date is now bound to the one **nearest the
  cue** (refactored `_iso_from_match`/`_dates_in`), so *"applications open 1 Oct … and close 1 Dec"*
  yields the **close** date, and an opening-only sentence yields **no** deadline. Added standalone
  `close(s)` as a cue (a deadline sentence already requires a date, so "…and close on 1 Dec" is caught).
- **(finding 4, medium)** `_NONFIRM` matched the whole sentence with generic tokens (`but`, `;`,
  bare `start`), wrongly demoting firm deadlines in the cue's own clause. Tightened to **strong**
  signals only (`has passed`, `no fixed`, `semester/term/academic-year begins`, `next intake`), so
  *"due by 1 Dec 2026, but decisions come in March"* and *"deadline to start your application is
  1 Dec 2026"* stay **firm**, while *"deadline has passed, but term begins 1 Sep"* stays **watch**.
**Ran:** `test_deadline_parse.py` (+8 new: open-only→none, open+close→close, date-before-cue,
`but`/`start`/`;` stay firm) + full suite → **125 passed** (exit 0).

## round W — refine²: claim supersession + no-clobber precedence (findings 2, 3) (commit pending)

**Fixed in `pipeline.py` + `model/claims.py`:**
- **(finding 2, high)** the deterministic recording never superseded prior heads, so a
  previously-blocked target re-fetched on resume ended with **two live heads** (blocked + value)
  → a later `reexport` reported a phantom open gap on a filled target. `_record_evidence` now
  supersedes prior heads when it writes a value.
- **(finding 3, high)** a monthly re-scan re-recorded `blocked` for a still-walled professor and,
  because a blocked claim has no `observed_at`, `_best_claim` picked it over an earlier human value
  → the sourced human answer silently reverted to `blocked`. New precedence: an **absence never
  downgrades a reached field** — `_record_blocked` skips when `claims.live_reached` (value or
  searched_absent) is true; `_record_evidence` skips a `searched_absent` when a live value exists.
- Run **gaps are now derived from claim state** (like `reexport`), so the run status can never
  contradict the exported cells (D-046/D-049).
**Ran:** `test_monthly_rescan_does_not_clobber_a_human_filled_value` (value survives; one live head)
and `test_retried_blocked_target_supersedes_its_blocked_claims` (blocked→value on resume, single
head, reexport agrees `finalized`) + full suite → **127 passed** (exit 0).

## round X — refine²: email-list + mailto PII redaction (findings 5, 6) (commit pending)

**Fixed in `export/json_export.py`:**
- **(finding 5, medium)** a bare email **list** ("a@b.com, c@d.com") slipped past the `fullmatch`
  guard. New `_is_pii_email` redacts a bare single address **or any value carrying 2+ addresses**,
  while still allowing a single email *mentioned in a sentence* (the design-intended recruiting
  quote). Applied in both `_redact_pii` (build) and `validate_export` (D-024).
- **(finding 6, low)** an email embedded in a `source_url` (`mailto:prof@uni.edu`) serialised into
  the JSON. `_redact_url` strips it (`mailto:[email]`) while keeping the field truthy so a value
  still cites a source (D-010); `validate_export` now also flags an email-bearing `source_url`.
- Removed a **duplicate `source_url` key** in `_envelope` (slipped in during round R).
**Ran:** `test_bare_email_list_is_redacted_at_build`, `test_email_in_a_mailto_source_url_is_stripped`,
`test_single_incidental_email_in_a_sentence_still_allowed` + full suite → **130 passed** (exit 0).
**All 6 second-pass findings are fixed with regression tests.**

## round Y — refine³: fix two regressions my round-V fix introduced (commit pending)

A lean third audit pass (regression hunt + fresh correctness + completeness) returned **2 findings,
both regressions from round V** (completeness + PII dimensions came back clean).

**Fixed in `pipeline.py`:**
- **(finding 1, high)** the standalone `\bcloses?\b` cue over-matched everyday "close" ("close to
  campus", "close collaborator", "office hours close") + an incidental date → fabricated firm
  deadlines. Constrained it to real deadline contexts: `close(s) on <date>`, or
  `registration/submissions/applications close(s)`; a bare "close" is no longer a cue.
- **(finding 2, low)** `_NONFIRM` ran over the whole sentence while the date is bound per-clause,
  so a strong phrase in a **dateless other clause** ("deadline is 1 Dec 2026; the spring semester
  begins later") wrongly demoted a firm deadline. New `_clause_containing` scopes `_NONFIRM` to the
  bound date's clause; `_PROJECTED` still applies sentence-wide.
**Ran:** `test_deadline_parse.py` (+4: incidental "close" → none; constrained close still works;
dateless-clause stays firm; same-clause still demotes) + full suite → **134 passed** (exit 0).

## round Z — refine⁴: constrain deadline cues to application contexts (commit pending)

A final focused verification of round Y found one **still-reachable** defect: `closes?\s+on` was
*still* too broad — it fabricated firm deadlines from *"Office hours close on Fridays; the term
started 1 September 2024."* (binding the unrelated term-start date) and *"gym registration closes
on 1 December 2026."* (the `_clause_containing`/`_NONFIRM` scoping itself held up under every stress
test).

**Fixed (correctness/honesty, high):** dropped the ambiguous close cues (`closes? on`,
`registration/submissions closes`) and kept only **application/submission-specific** cues
(`deadline`, `applications close/due`, `submissions close/due`, `apply by`, `closing date`,
`submit by`, `due by`). A "close" without an application subject is now an **honest miss**
(`searched_absent`) the LLM analyst can resolve later — a fabricated firm date is not (D-010/D-061).
The combined *"…and close on 1 Dec"* test was corrected to assert this honest miss (a *more*
conservative spec, not a weakened one).
**Ran:** `test_deadline_parse.py` (application phrasings still firm; office-hours/library/gym
"close on" → none) + full suite → **135 passed** (exit 0). **Audit trend 10 → 6 → 2 → 1; the parser
now never fabricates a firm deadline from a non-application sentence.**

---

# Clean-room verification (goal §4 step 6)

Tore down all generated/transient state (`.venv`, `.pytest_cache`, `*.egg-info`, every
`__pycache__`); confirmed `git status` showed **no tracked generated state, no personal data, no
scan output**. Recreated the venv fresh and ran `pip install -e ".[dev]"` (succeeded), then re-ran
the offline self-test from the clean checkout.

## round AA — clean-room caught a portability bug the tests missed (commit pending)

**Fixed (portability):** `scan --demo` wrote the dashboard + JSON correctly but then **crashed on
its final `print()`** — it used a Unicode arrow (`→`) that the default Windows console codec
(cp1252) can't encode, so the command exited 1 *after* doing its work. pytest captures stdout as
UTF-8, so the unit test never hit it; running the real CLI on a cp1252 console did. Replaced the
arrow with ASCII `->` and **added a regression assertion** (`test_cli_scan_demo_writes_dashboard`
now captures the CLI output and asserts it is `cp1252`-encodable / ASCII).
**Ran (from the fresh venv):** `python -m pytest` → **135 passed** (exit 0) on the first try;
`python -m supervisorly scan --demo` → exit 0, writes `dashboard.html` + `.json`, prints an
ASCII line. Clean-room **green**.

## round BB — refine⁵: gate deadlines on application context (post-report verifier finding)

A final closing verifier (run *after* the report was drafted) found the round-Z fix was
**incomplete**: I anchored the `close`/`due` cues to an application subject but left `due by`,
`closing date`, and `submit(ted) by` unanchored, so *"Rent is due by 1 December 2026"*, *"Tax
returns must be submitted by 1 December 2026"*, and *"The store's closing date is 1 December
2026"* still fabricated firm deadlines. (The export/dashboard/claims honesty sweep came back
clean.)

**Fixed (correctness/honesty, high):** split the guard into a **verb cue** (for locating the
date's clause) plus a required **`_APP_CONTEXT`** word (`applications?/applicants?/apply/
submissions?/admissions?`) anywhere in the sentence — a deadline-shaped sentence with no
application context is now an honest miss, never a firm date (D-010/D-061). This design also
*correctly* binds the combined *"Applications open 1 Oct … and close on 1 Dec"* to the **close**
date (the verb owns its clause) — the round-2 intent, now achieved safely.
**Ran:** `test_deadline_parse.py` (+ rent/tax/store/payment → none; submitted-by/submission-
deadline/apply-by with context → firm; combined open+close → close date) + full suite →
**136 passed** (exit 0).

## round CC — refine⁶: clause-level deadline extraction (root-cause rewrite)

Another closing verifier found three issues in the deadline tier — a sign to fix root causes,
not patch symptoms. Rewrote `extract_deadline` to work **per clause** instead of per sentence.

**Fixed:**
- **(compound-sentence mis-binding, high)** nearest-cue binding bound the leftmost cue's date
  regardless of where the application subject sat, so *"Office hours close on 1 Dec; applications …
  15 Jan"* fabricated the office-hours date as the deadline. Now a deadline requires the **verb
  cue + application-context + date in ONE clause** (`_sentences` → `_clauses`, protecting
  date-internal commas), so the compound case correctly binds **15 Jan**.
- **(recall, medium)** expanded the domain context to the subjects a supervisor-seeker's deadline
  attaches to (phd/doctoral/postdoc/fellowship/studentship/position/…), so *"The PhD deadline is
  1 Dec 2026"* and *"The position closes on 1 Dec 2026"* are found — still a fixed signal-tier
  heuristic, not a generated search dictionary (D-038 stands).
- **(O(n²) blow-up, medium)** dropped the `[^.!?]*cue[^.!?]*` `finditer` that was quadratic on
  unpunctuated text (~78s at 40 KB); the sentence/clause iteration is linear — **96 KB now parses
  in 0.077s**.
Sentences whose only date is a semester/academic-year start (a different event) now correctly
**miss** (honest `searched_absent`) instead of surfacing a mis-bound watch date.
**Ran:** `test_deadline_parse.py` (+ compound-sentence binds the application clause; phd/position
phrasings; long-unpunctuated perf; semester-start dates → miss) + full suite → **139 passed** (exit 0).

## round DD — refine⁷: subject-aware application-deadline gate

The clause-level verifier found the `_APP_CONTEXT` bag-of-words check accepted any clause where a
domain word appeared *anywhere*, so *"Tuition and fees for the PhD program are due by 1 Dec"* (and
course-registration / insurance / deposit / orientation / symposium variants) fabricated firm
application deadlines — the domain word sat in a modifier, not the cue's subject.

**Fixed (correctness/honesty, high):** replaced the presence check with `_is_application_deadline`
tying context to the cue's subject — a clause qualifies only via (A) a **strong application noun**
(applications/applicants/apply/admissions/submissions), (B) a **`<domain> deadline`** phrase, or
(C) a **domain word directly before the cue verb** ("PhD studentship closes"). *"…for the PhD
program are due by…"* (subject = tuition/fees) no longer qualifies.
**Ran:** `test_deadline_parse.py` (+ 7 tuition/registration/insurance/… → none; phd/position/
studentship phrasings still firm) + full suite → **140 passed** (exit 0).

**Deadline tier — stopping point & known limitation.** Across rounds I/Q/V/Y/Z/BB/CC/DD the
deterministic deadline tier was hardened until it no longer fabricates a firm deadline from the
realistic non-application patterns adversarial verification could find (rent/tax/office-hours/
tuition/registration/…), parses in linear time, and binds compound sentences to the application
clause. It remains a **best-effort signal tier**: perfect grammatical subject-attribution is beyond
a regex, so a rare construction (e.g. "RSVP for the admissions open house closes …", via the strong
noun "admissions") can still surface. Per the design (D-009/D-021) the **LLM recruiting/eligibility
analyst does the real classification in Stage 2**; the deterministic tier only surfaces a
quote-verified candidate. Further refinement is delegated to that layer rather than chased in regex.

## COMPLETION — goal met (offline engine)

All phases (A–J) met their DoD; 18/18 edge-case rows have passing tests; the offline self-run is
hallucination-free; the four-pass adversarial audit (10 → 6 → 2 → 1) is closed with all 19 findings
fixed + regression-tested; ethics gates are all test-guarded; clean-room verification is green from a
fresh checkout. **135 tests pass (exit 0).** See `docs/COMPLETION_REPORT.md` for the full sign-off.
The only step recorded **skipped** (never passed) is the credentialed live smoke test — no
ROR/OpenAlex keys in this environment; it is the natural next build increment.

---

# LIVE build (branch `build/live`) — goal: docs/LIVE_IMPLEMENTATION_GOAL.md

Reuses the green offline engine; adds the real front door + collectors + Atlas front-end. Each
round is a tracked commit leaving the suite green.

## round L0 — ROR + OpenAlex clients behind the transport seam (commit pending)

**Built:** `discover/ror.py` (keyless ROR client: country → `{ror_id,name,country_code,homepage,
types}`; open API, polite email only) and `discover/openalex.py` (free OpenAlex client with the
`mailto` polite-pool param + optional premium `api_key`: `topic_ids`, `authors_by_institution` →
professor-target dicts, `works_by_author` → activity). Both take the injected `Transport` (cassette-
testable), with module-level URL builders so tests record the exact request URL. Nothing dropped for
missing data (honest `None`/`[]`); LLM-free (D-009).
**Ran:** `tests/test_discover_clients.py` (6) — ROR maps + honest-empty-homepage + error→[]; OpenAlex
topic-ids, authors→targets, works, premium-key-in-query — and the ethics LLM-free scan (now covers
`discover/`). Full suite → **148 passed** (exit 0). **DoD (Phase L0):** clients round-trip cassettes
into typed results, no live network in tests. (Preflight fail-loud on a missing contact email already
lands via `preflight.require_credentials`; the live entry wiring is L2/L8.)

## round L1 — discovery ladder: SearchPlan → professor targets (commit pending)

**Built:** `discover/openalex.py` gains `institution_by_ror` (ROR id → OpenAlex institution id).
`discover/ladder.py` — Round 1, generate-don't-look-up (D-038): `resolve_topic_ids` (field →
OpenAlex topic IDs, D-058), `select_institutions` (ROR by country, honouring `university_mode`
all/prioritise/only, D-045), `enumerate_professors` (OpenAlex authors-by-institution → targets,
**reconciled/de-duped by identity** so a split profile is one target not two, D-057; topics unioned,
works = max), and `build_targets` tying them together. Login-walled institutional pages are left for
the deep-dive fetcher + human rung, never scraped here.
**Ran:** `tests/test_discover_ladder.py` (5): enumerate+dedupe (Ada at two institutions → one target,
topics unioned), topic-ids-from-field, `only`/`prioritise` scope, `all` default. Full suite →
**153 passed** (exit 0). **DoD (Phase L1, Round 1):** targets enumerated with nobody duplicated/dropped;
scope modes honoured; identities reconciled — all on cassettes, no network.

## round L2 — the live driver `pipeline.run_live` (commit pending)

**Built:** refactored the per-target deep-dive loop out of `run_offline` into a shared
`_process_targets` (fetch → extract → claim → gap-derive), so `run_offline` and the new `run_live`
share one proven core (D-046/D-049 gap logic unchanged). `run_live(plan, transport, snap_root, *,
email, openalex_key=None, db_path, optout_path, resume)`: **fails loud without a contact email**
(D-019/023) → builds the ROR + OpenAlex clients on the injected transport → runs the ladder
(Round 1) → feeds discovered targets through the same fetch/extract/claim/export/dashboard path.
One transport serves both the open-API JSON and the professor pages (robots-gated `Fetcher`), so a
live run is the cassette-tested path with httpx swapped in; a professor with no discoverable homepage
is an honest **blocked** open gap (human rung), never a fabricated value.
**Ran:** `tests/test_run_live.py` (4): discovers 3 professors across 2 institutions → valid export,
nobody dropped; honest states (2 value, 1 blocked → `finalized_with_open_gaps`); **zero hallucinations**
(quotes re-verified in snapshots); **fails loud** without an email. Offline pipeline tests
(selfrun/warm_cache/resume) still green after the refactor. Full suite → **157 passed** (exit 0).
**DoD (Phase L2):** `run_live` runs end-to-end on cassettes and produces the same honest,
hallucination-free four-state dashboard as `run_offline`, now from discovered targets.

## round L3 — extra collectors: students / industry / advertised social (commit pending)

**Built:** three field-driven extractors on the professor's own public page (D-038 field-driven), each
a quote-verified candidate signal (the LLM synthesist confirms/structures in Stage 2, D-009/021):
`extract_students_signal` (current members / lab / alumni / advisees — deliberately NOT "recruiting
students", which is future), `extract_industry_signal` (collaborations / partners / funders /
sponsors), `extract_social` (an *advertised* social/profile link in the visible text — twitter/x/
linkedin/github/mastodon/bsky). **Only the social LINK is recorded; the walled page it points to is
never fetched — that's the human rung (D-039/043).** Added to `_EXTRACTORS` + `FIELD_DESCRIPTORS`,
so they flow through both `run_offline` and `run_live` as generic, filterable columns; absent → honest
`searched_absent`.
**Ran:** `tests/test_collectors.py` (6): each extractor value/None, "recruiting students" not read as a
roster, rich page → all three `value` (quote-verified, social = the bare link), bare page → all
`searched_absent`. **Fixed (regression):** the walled `eve` now has 3 more fields her MD doesn't fill,
so the resume re-export is honestly `finalized_with_open_gaps` (assertion corrected). Full suite →
**163 passed** (exit 0). **DoD (Phase L3):** sourced student/company/social claims where present,
honest `searched_absent` where not; walled social never scraped.

## round L4 — university + professor ranking (commit pending)

**Built:** `score/ranking.py` — reuses `score_professor` (intent gates D-059, topic-ID overlap D-058,
works reconciliation D-057) and adds `rank_professors` (best-first) + `rank_universities` (D-031
roll-up: aggregate members' fit + recruiting-fraction + activity into a transparent, **re-weightable**
`university_score`, with `confidence` lowered — never faked — for sparse institutions). Deterministic,
LLM-free.
**Ran:** `tests/test_ranking.py` (6): professors ordered best-first; universities aggregated + ordered;
re-weightable (fit-heavy vs recruiting-heavy differ); sparse university confidence not inflated;
fragmented profile reconciled not dropped; **pre_phd not gated on PhD-admission rules**. Full suite →
**169 passed** (exit 0). **DoD (Phase L4):** met.

## round L5 — university scope (all / prioritise / only) — met via L1

The scope form is already implemented and tested in the ladder: `select_institutions` honours
`university_mode` all/prioritise/only + `universities_json` (`tests/test_discover_ladder.py`
`only`/`prioritise`/`all`). Surfacing it as a CLI/skill flag is Phase L8. No new code this round.

## round L6 — scheduled re-scan delta + test-speed fix (commit pending)

**Built:** `export/delta.py` — `compute_delta(previous, current)` over two export dicts: new/removed
professors + changed fields, with the two the student cares about highlighted (**newly_recruiting**,
**newly_deadline**). Pure, no fetch, no LLM; a first run reports everything new.
**Fixed (perf, self-test caught):** the internal `Fetcher`'s per-host rate limiter used a real 1s
sleep, so the growing set of fetch-heavy cassette tests pushed the suite past 2 min. Cassettes are
synthetic — no host to be polite to — so `run_offline`/`run_live` now inject a no-wait rate limiter
(`min_interval=0`); **real live politeness is applied on the httpx fetcher wired in L8**. Suite time
2 min+ → **~21 s**.
**Ran:** `tests/test_delta.py` (5): new/removed/changed + highlights; first-run-all-new; newly-published
deadline; warm re-scan → `extractions==0` + empty delta; changed page shows in delta. Full suite →
**174 passed** (exit 0, ~21 s). **DoD (Phase L6):** re-scan ≈0 re-extraction + honest delta. (The
Task-Scheduler/cron recipe is documented with the CLI in L8.)

## round L7 — dashboard recreated in the Atlas design language + diagram engine (commit pending)

**Built:** rewrote `export/dashboard.py` in the hifi **"Supervisorly Atlas — Living"** language while
keeping every honesty/safety contract (and its test hook): the bioluminescent tokens (void `#05070c`,
the tissue-type kind palette, amber accent, teal focus), Space Grotesk + Space Mono (named with a
faithful system fallback — **no external font, no CDN, stays self-contained**), the decorative
background + scan line, and a **cell drawer** for professor detail (value + verbatim quote + source +
confidence, D-010). Added the **diagram engine** ("how diagrams appear"): glowing cell nodes
(halo/membrane/nucleus, sized by kind) + **cubic-bezier filaments** (bowed by a deterministic
`hash%2`, 4 stacked SVG elements: soft glow + base + animated light-packet dashes `omFlow` + arrowhead),
**highlight-connected** on hover/focus, and **recompute on resize** — driving a "How it works"
specimen (plan → discover → fetch → verify → score → dashboard, with the human-rung escalation).
`prefers-reduced-motion` disables all animation; injection- and URL-scheme-safe.
**Ran:** `tests/test_dashboard.py` (all prior hooks preserved: four states, firm/watch, safe links,
script-safe, no CDN, clickable detail) + `tests/test_dashboard_atlas.py` (5: tokens/type, self-contained
fonts, cells-and-filaments engine, how-it-works view + reduced-motion, cell drawer). Full suite →
**184 passed** (exit 0). **DoD (Phase L7):** the results dashboard + a how-it-works diagram render in
the Atlas language, self-contained/offline, reduced-motion-aware, four-states + deadline + cell-drawer
detail working, filaments recompute on resize.

## round L8 — CLI + SKILL orchestration (commit pending)

**Built:** the `scan` CLI now has a full **live path** — flags `--country --field --intent
--universities --university-mode --email --openalex-key --optout --resume --out`. It fails loud
without a contact email (ROR keyless, OpenAlex free), needs `--country`+`--field`, builds the httpx
transport with a polite `mailto` User-Agent, and runs `run_live`. Refactored the write-and-report into
`_write_result`. `run_live` gained `rate_limit`/`backoff_sleep` (polite defaults for real runs; tests
pass fast values). `SKILL.md` gained a **live orchestration** section (intent → SearchPlan → confirm →
Stage-1 enumerate → Stage-2 deep-dive incl. students/companies/social → score/rank → dashboard).
`README.md` gained a **live scan** command + a **scheduled re-scans** recipe (cron + Windows Task
Scheduler, using `--resume`).
**Ran:** `tests/test_cli_live.py` (3): fail-loud without email, needs country+field, and a **full live
run via a patched transport** (offline) → writes dashboard+JSON, ASCII output, `recruiting_signal`
value. Full suite → **182 passed** (exit 0). **DoD (Phase L8):** the live flags work; the skill
documents the flow; scheduling recipe documented. (Earlier L7 log said 184 — the accurate count then
was 179; recorded here for the trail.)

## round L9 -- live discovery wired + adversarial refine loop (section 5)

**Built:** the real discovery front door on the existing engine -- `discover/ror.py` (keyless ROR
country->institutions, paginated), `discover/openalex.py` (free OpenAlex topics/institutions/authors/
works, `mailto` polite pool, optional premium key), `discover/ladder.py` (Round-1 select-institutions
with all/prioritise/only scope + word-boundary matching, enumerate + reconcile professors),
`pipeline.run_live` (preflight -> clients -> ladder -> shared `_process_targets` deep-dive), the extra
collectors (`extract_students_signal`/`extract_industry_signal`/`extract_social`), `score/ranking.py`
(professor + university roll-up, re-weightable), `export/delta.py` (scheduled-rescan "what changed").

**Refine loop (section 5) -- three adversarial audit passes, each finding fixed with a regression test:**
- **Pass 1 (rounds L9b-L9g)** -- 9 confirmed findings fixed: deadline payment-exclusion; login-wall
  detection wired into the deep-dive; discovery pagination + truncation marker + word-boundary scope;
  dashboard `_inline_json` script-injection escape; unanchored `.cache/`/`snaps/` gitignore; ranking
  independence (roll up from independent axes, no double-count); delta recruiting-highlight relabeled
  to `recruiting_changed` (a review signal, never "now recruiting"). -> 195 passed.
- **Pass 2 (round L9h, commit `cc587b2`)** -- 6 confirmed findings fixed: (1/4/5) the `please enable
  javascript` marker false-positived on content-rich pages shipping a `<noscript>` fallback ->
  discarded real signals; split into strong `_WALL_MARKERS` (fire anywhere) + `_JS_WALL` that is a
  wall only when `main_text` is near-empty (a genuine JS shell, floor 30 chars). (2/6) the `_PAYMENT`
  guard was co-occurrence-based -> a payment noun with an adjacent domain word fabricated a firm
  deadline, while a real "Applications close" beside a fee word was over-dropped; made it subject-tied
  via `_PAYMENT_HEAD`. (3) a mid-pagination fetch failure returned partial results with **no**
  truncation marker -> false completeness; both clients now mark PARTIAL on the not-data early return.
  -> 202 passed (+7 regression tests).
- **Pass 3 (attempted)** -- the third independent multi-agent audit **could not run: all 3 finder
  agents errored on a session usage limit** (0 ran). Per section 7 that is **not** a "zero findings"
  result, so I did not treat it as convergence. Substituted an **in-loop adversarial probe** of the
  L9h areas (`scratchpad/probe_l9h.py`, real code), which reproduced one residual defect ->
- **Round L9i (commit `272ed0c`)** -- `_PAYMENT_NOUNS` listed a bare `deposit`, so `\bdeposit\b` missed
  the plural "Deposits" and "Deposits for PhD applicants are due 1 Dec" fabricated a firm deadline;
  made every payment noun plural-tolerant. Regression cases added. -> probe 0 failures; **202 passed**.

**Pass 3 (rerun, after the usage-limit reset) -- 10 confirmed findings.** The full three-finder
multi-agent audit ran and reproduced 10 defects, all in the L9h areas -- my L9h fixes were
architecturally fragile (a 64-char payment window; a length-based JS-wall floor). Fixed by
principled redesigns across three rounds, each a per-round commit leaving the suite green:
- **Round L9j (commit `2ebc21d`)** -- redesigned the deadline subject-detection: replaced the
  fragile fixed-width payment window with a subject-HEAD model (the cue's subject = head of the
  leading noun-phrase; English compounds are head-final). Also: abbreviated months
  (`15 Jan 2027`, `1 Dec. 2026`) via an `_ABBR_MONTH_DOT` pre-strip; appositive commas no longer
  sever subject from cue; conjunction-aware clause split. Closes findings 1,2,6,8,9,10. -> 206.
- **Round L9k (commit `514acb8`)** -- robust wall detection: bot-challenge interstitials
  (Cloudflare "checking your browser"/"ray id") added to strong markers; the `please enable
  javascript` banner is a wall only when the residue after removing the banner sentence is
  near-empty. Closes findings 3,4,5. -> 209.
- **Round L9l (commit `a46781a`)** -- truncation markers now persist across the human-rung
  re-export resume boundary (`runs.get_counts`/`update_counts` + `counts_json`), so a re-export
  cannot silently claim completeness (D-037). Closes finding 7. -> 210.

**Pass 4 (commit-L9m target, task `wh0r8qlbe`) -- 6 confirmed findings (2 HIGH),** each
adversarially verified on the real venv. The L9j/L9k redesigns still leaked:
- **Round L9m (commit `a0fe080`)** -- (F1 HIGH) a participial post-modifier put a domain word in
  the subject span ("the deposit SECURING your PhD position is due") -> firm deadline; the leading
  noun-phrase run now stops at a participle heading an object phrase (Ving/Ved + determiner). (F4
  HIGH) classification leaned on a CLOSED payment-noun list (D-038 leak) so an unlisted money head
  ("application surcharge/bond/repayment is due") won by absence; removed the list entirely -- a
  clause is an application deadline ONLY when the cue's subject HEAD is a recognised application
  word, else it fails safe (D-061 asymmetry). (F2 MED) a coordinated NOUN subject ("Applications
  and supporting documents are due") was split on `and`, orphaning the subject; `_clauses` keeps a
  short bare-NP left coordinand attached to its shared cue. (F5 MED) the imperative "submit your
  application by <date>" was missed; broadened the submit cue + an object-head test. (F3 HIGH) bare
  `captcha` matched inside reCAPTCHA/g-recaptcha/api.js, dropping real pages to `blocked`; now
  requires a genuine CAPTCHA-challenge phrase. (F6 MED) the greedy `[^.!?]*` banner strip swallowed
  all content on a punctuation-free page -> false LOGIN_WALL; the strip is now a bounded phrase whose
  tail only reaches a terminator or text-end. +7 regression tests. -> **217 passed**.

**State:** suite green at **217 passed** (exit 0), commits `cc587b2`->`a0fe080` on `build/live`.
Clean-room fresh-install verification PASSED earlier at 202 (to be re-run after section 5 closes).
**Pending before DoD:** the pass-5 independent multi-agent audit (task `wh9gmgzqd`) must return
**zero** to formally close section 5; then re-run clean-room and finalize
`docs/LIVE_COMPLETION_REPORT.md`.

**Pass 5 (round L9n, commit `50a1084`) -- the independent re-run, completed this time.** Six
independent finder agents (one per goal-5 dimension: correctness/provenance, genericity, ethics,
honesty, cost/perf, UX) reported 20 candidate findings, each reproduced in code; six adversarial
verifier agents then tried to rebut each one. Survivors: **19 confirmed (7 HIGH, 8 MEDIUM, 4 LOW)**;
1 rebutted (dashboard `env.state` interpolation -- unreachable behind the DB CHECK constraint + two
write-path validators); 1 downgraded to LOW (email-shaped identity fields -- fixed anyway as
defense-in-depth). Fixed in three green waves (217 -> 232 -> 244 -> 253):
- *fetch/export/ethics:* volatile-chrome mask tightened to timestamp-shaped tokens (a deadline
  change after an "updated" stamp now busts the cache, D-061); robots re-checked fail-closed on
  redirect final URLs + provenance recorded under the final URL (D-019/D-010); D-005 `--out` CLI
  guard; email-shaped names redacted/flagged (D-024); comma-less counters masked; backoff cap
  applied after jitter; delta compares confidence (watch->firm flips surface as `newly_deadline`),
  iterates the field-key union, reports schema mismatch, surfaces renames.
- *discover:* ROR client moved to the **v2 API** (v1 retired -- cassettes re-recorded to the live
  shape per goal section 7); `--country` names resolve to ISO alpha-2 at the CLI seam + fail loud on
  unknown (D-002; standards-body table, D-038-safe); diacritic-insensitive university matching +
  0-of-N named-match warning; coverage-preflight wired into `run_live` (D-060); failed OpenAlex
  institution-resolution marks PARTIAL instead of silently dropping a university (D-037); split
  OpenAlex profiles merged on decisive ORCID (D-030/D-057 -- works summed, topics unioned;
  homepage-only match stays two targets).
- *pipeline/roster:* dotted abbreviated-month deadlines quote verbatim (analysis-only dot-strip;
  "1 Dec. 2026" now records, was falsely `never_attempted`); verified removal supersedes stale
  deterministic values (human-assisted values stay protected); advertised walled social links mint
  `awaiting_human` gap tasks (`finalized_with_open_gaps`, D-043); quadratic signal regexes
  sentence-split (linear, verbatim); non-English (de/fr/es) login-wall markers route to the human
  rung (D-052).
All pass-5 probes re-run clean after the fixes (one probe's gitignore-coverage check fails by
adjudicated design -- the fix is the test-locked CLI warning). +36 regression tests over the audit.
-> **253 passed**.

**Clean-room re-run (goal section 4 step 6, after section 5 closed) -- PASSED.** From tip `46811f1`:
wiped `.venv`/egg-info/`__pycache__`/`.pytest_cache`/`output`/`.cache`/`snaps`/`*.sqlite`; `git
status` and `git clean -ndx` both empty (no personal data, no snapshots, no scan output). Fresh
documented install -> **`253 passed` on the first try**; post-install tree clean.

**State: GOAL COMPLETE.** Suite green at **253 passed** on `build/live`; section 5 closed with zero
open findings; clean-room green; every Definition-of-Done box checked in
`docs/LIVE_COMPLETION_REPORT.md`.

## round B0 — Goal 3 docs: D-064…D-067 + GOALS + goal doc (commit `72bcb48`)

- `docs/DECISIONS.md` — appended four locked decisions: **D-064** (browser-primary live fetch is
  agent-driven; page content enters only through the deterministic `ingest-page` snapshot seam;
  raw HTML/DOM never enters agent context; APIs stay httpx; host-portable), **D-065** (social
  pacing policy: jittered intervals, per-session caps, human-like scrolling, abort-on-challenge;
  Scholar minimal; advertised profiles only), **D-066** (subject-map stage: API-derived
  hierarchy, user multi-select before anything expensive), **D-067** (Scan Studio: one
  self-contained Atlas-language plan wizard; conversational multi-select remains the fallback).
- `docs/GOALS.md` — Goal 3 row (branch `build/browser`). `docs/BROWSER_IMPLEMENTATION_GOAL.md`
  — the standing build contract (constraints, phases B1–B6, DoD, guardrails).

## round B1+B2 — browser ingest seam (D-064) + pacing policy (D-065) (commit `ecec3ec`)

- `extract/page_extract.js` — in-page main-text extractor mirroring `normalize.main_text`
  (visible-text TreeWalker, whitespace collapse), UTF-8 byte cap 61440 with word-boundary cut +
  `[truncated]` marker; async scroll mode (4–10 `scrollBy` steps, 1–3 s randomised pauses,
  settle wait) for social pages. ES2019, no imports, `node --check` clean.
- `fetch/browser_rung.py` — `ingest_page()`: text HTML-escaped inside a minimal `<main>` shell
  so snapshots are byte-format-compatible with fetcher snapshots (`main_text`/`quote_in_snapshot`
  round-trip exactly); web source under the FINAL url, tier `agent_browser`,
  `robots_allowed=None` (same honesty convention as `human_assisted`).
- `model/schema.sql` + `model/db.py` — schema v2: `agent_browser` added to the
  `web_source.source_tier` CHECK; `migrate()` rebuilds the table on stale CHECK (data copied,
  index preserved, `legacy_alter_table=ON`).
- CLI `ingest-page` (exit 2 on invalid url/missing file/empty text; one ASCII line).
- `ethics/pacing.py` — POLICY: social (x/twitter/linkedin, subdomains) 45–120 s jitter + cap
  15/session; scholar.google.* 60–180 s + cap 5; non-social no-op. Persistent state JSON;
  `check()` (allowed/wait/reason, injectable rng), `abort()` latch, `reset()`; corrupt state
  fails closed. CLI `pace` (exit 0 ALLOW / 3 DENY; `--abort`, `--reset`, `--state`).
- `.gitignore` — `pacing_state.json` + `**/browser_staging/` (D-005).
- `tests/test_browser_rung.py` (+17), `tests/test_pacing.py` (+15); one expectation update
  (`test_state_machine.py` pins `SCHEMA_VERSION` constant instead of "1" — the bump is the
  intended change).
-> **283 passed** (253 + 30).

## round B3 — subject-map stage (D-066) + --plan/--targets (commit `fac260e`)

- `discover/subjects.py` — `subject_map()`: OpenAlex topics search paginated, grouped
  domain→field→subfield ("ungrouped" buckets for null hierarchy, never a crash), works_count
  sort, `max_results` cap; D-037 truncation honesty (cap, first-page failure, mid-pagination
  failure all marked `topics@<query>`; genuine empties unmarked).
- `discover/openalex.py` — `topics_url` page param, `author_search_url`/`author_url`,
  `author_search(name, affiliation)` (affiliation preference via last-known-institution
  casefold substring; unmatched → top hit flagged `resolution: "unverified"`),
  `author_by_id` (404 = honest skip vs failure = truncation marker).
- CLI `map-field` (preflight email required; `output/subject_map.json` default; PARTIAL noted
  in the summary line).
- `scan --plan` — validated plan file (missing/invalid/keys → exit 2 listing expected keys);
  plan country name resolves via `to_country_code` fail-loud; explicit flags override plan
  values (argparse defaults → None so overrides are detectable); plan `resolved_topic_ids`
  reach the scorer (ladder already prefers them — zero re-resolution, spy-tested).
- `scan --targets` — named professors (dict specs or OpenAlex URLs) resolved in the CLI and
  fed to `run_live(targets_override=...)` in the exact `enumerate_professors` shape, so
  `_process_targets`/opt-out/resume/export work unchanged; unresolved names reported as
  SKIPPED (never silently dropped); targets-only runs skip the country ladder and the
  `--country`/`--field` requirement; `--targets` + `--country` unions both sets.
- `tests/test_subjects.py` (+9), `tests/test_scan_plan.py` (+10).
-> **302 passed** (283 + 19).

## round B4 — Scan Studio UI (D-067) (commit `5809b40`)

- `export/studio.py` — `build_studio(subject_map, *, defaults=None)`: ONE self-contained,
  offline HTML plan wizard in the Atlas "Living" language, same conventions as the dashboard
  (`_inline_json` data embedding — every `<` neutralised, U+2028/U+2029 escaped; `esc()` for
  the one Python-side interpolation; named Space Grotesk/Mono with system fallbacks, never
  imported; `prefers-reduced-motion` kills all animation; `:focus-visible` ring; Escape closes
  transient UI). Sections: Atlas hero (eyebrow `SUPERVISORLY · SCAN STUDIO` + decorative
  cells-and-filaments SVG), intent radio cards (pre_phd default), country, university chips +
  all/prioritise/only mode, the tri-state domain→field→subfield→topics checkbox tree
  (parent cascades to descendants; indeterminate on partial; works-count chips "12.4k works"),
  D-037 PARTIAL MAP banner when `truncated`, named professors, contact email. "Export plan"
  validates inline (no `alert()`), builds the plan JSON
  (`intent_kind, country, field, resolved_topic_ids, university_mode, universities, targets,
  email`) and downloads `supervisorly_plan.json` via Blob (a static file cannot write to disk),
  then shows the next command `supervisorly scan --plan supervisorly_plan.json --out
  output/live.html` with a copy button.
- CLI `studio --map ... [--out ...]` — fails loud (exit 2) on a missing/invalid/wrong-shape map;
  reuses the `_warn_if_committable` D-005 guard on `--out`; ASCII-safe status line.
- `scan --plan` now honours a Studio plan's own `email` (satisfies the polite-pool credential
  check) and `targets` (named professors; invalid entries fail loud) — the exported plan is
  self-sufficient; explicit flags still override the plan.
- `tests/test_studio.py` (+17): self-containment scan, hostile-string injection (exactly one
  `</script>`, no raw U+2028/`<img`), reduced-motion/keyboard/tri-state/plan-shape structure,
  node `--check` on the embedded JS, truncation banner, honest empty map, CLI fail-loud +
  D-005 warning, plan email/targets wiring via cassette.
-> **319 passed** (302 + 17).

## round B5 — Orchestration + docs (this commit)

Documentation + orchestrator contract only — no code changes; every documented command/flag was
verified against the real `--help` output on the project venv first.

- `.claude/skills/supervisorly/SKILL.md` — Stage 0 is now intent → `map-field` (hierarchical,
  API-derived subject map, D-066) → multi-select confirm (numbered list, or the Scan Studio via
  `studio --map`) → plan; the nothing-expensive-before-confirmation rule stays. New section
  **"Browser-primary live fetch (D-064)"**: the exact per-page agent recipe — `pace --host`
  before every page (exit 0 = go, 3 = sleep the printed wait or skip the host), warm-cache pages
  and API JSON (ROR/OpenAlex) never touch the browser, navigate via the `mcp__chrome-devtools__*`
  tools (headful persistent profile; first run = the user logs into the walled sites once,
  themselves), extract in-page with `evaluate_script(page_extract.js)` (scroll mode for social),
  write only the text to a staging file the agent never reads, then `ingest-page --url <finalUrl>
  --file <staging>` and the deterministic engine takes over (snapshot → extractors → D-010
  quote-verified claims). New section **"Social rung (D-065)"**: walled-social `awaiting_human`
  gap tasks are executed by the agent through the logged-in profile — per-target, read-only,
  scroll mode, pacing enforced; any challenge/soft-block/login redirect → `pace --abort`, field
  `blocked`, classic human rung; Scholar profile pages only; advertised profile URLs only, never
  people-search enumeration. The live-orchestration flow now references `--plan` / `--targets` /
  `map-field` / `studio`, carries the full intent list, and documents the host-portable MCP config
  (user-level `mcp.json`; `claude mcp add chrome-devtools --scope user npx
  chrome-devtools-mcp@latest` for Claude Code — same server, slim/no-usage-statistics flags
  recommended).
- `README.md` — new sections "Planning a scan: subject map, Scan Studio, named professors"
  (`map-field`, `studio`, `scan --plan`, `scan --targets` with one-line examples) and "The browser
  tier" (what it is, one-time login, pacing, host-portability; `pace` + `ingest-page` examples);
  the two stale "walled pages go straight to the human rung" sentences now describe the browser
  tier with the human rung as fallback.
- `docs/getting-started.html` — the live section matches reality: the stale "live scanner is the
  next piece being built" status box is replaced with the real flow (intent → subject map → pick
  topics → Scan Studio or conversation → `scan --plan`); step C's commands are real
  (`map-field` → `studio` → `scan --plan`) and the browser tier + one-time login are explained;
  the human-rung section notes the agent's browser reads most walled pages first. Two stale
  "two free keys (ROR & OpenAlex)" lines fixed — a live scan needs only the contact email
  (doc-vs-code mismatch, fixed in the docs).
- `.claude/agents/*.md` — reviewed all five contracts; no changes needed. The only login-wall
  mention (`adapter-author.md`'s `LOGIN_WALL` marker) covers login-walled directory
  *enumeration* (roster, D-052) — the browser tier never enumerates directories, so nothing
  contradicts the new flow.
**Verified:** `-m supervisorly {scan,map-field,studio,ingest-page,pace,init-db,version} --help`
all match the documented flags; full suite re-run after the doc edits.
-> **319 passed** (unchanged — docs only).

## round B6 — eval + adversarial audit + clean-room (commits `4dc65ec`, `22a452c`, `797ed5d`, `96f4e7e`)

Five independent finder agents (ingest seam, pacing, subject-map/plan/targets, Scan Studio,
docs truthfulness), every finding reproduced in code with self-rebuttal: **23 confirmed
(4 HIGH, 11 MEDIUM, 8 LOW)**, fixed in four green waves, each with regression tests:

- **Wave A (`4dc65ec`)** — v1->v2 migration rebuilt per SQLite's documented procedure
  (foreign_keys=OFF, one transaction, leftover-web_source_old recovery; claim-bearing v1 DBs
  were the realistic unpinned case); ingest-page utf-8-sig + BOM + loud decode failures;
  pacing classify() canonicalization (port/trailing-dot/scheme/ccTLD bypasses closed, hostile
  lookalikes still unpaced); jittered interval pinned at fetch-record time
  (next_allowed_epoch — printed waits binding, no re-roll); atomic save + abort merge (a
  concurrent ALLOW can no longer erase the latch); state anchored at ~/.supervisorly/;
  broken state entries fail closed (exit 3). -> **342 passed**.
- **Wave B (`22a452c`)** — author-lookup truncation markers travel into the run and persist
  across reexport (PARTIAL honesty for named targets); identity resolution
  verified/unverified/unchecked reaches export + dashboard badge; plan/targets values
  type-checked at load (fail loud by key+type); university_mode/intent_kind enums validated
  (a typo can no longer widen "only" to a whole-country scan); select_institutions raises on
  unknown mode; opt-out coverage line honest. -> **353 passed**.
- **Wave C (`797ed5d`)** — Studio: reduced-motion gates the export scroll; focus ring on the
  intent card; malformed map entries can't brick the wizard (Python sanitize + JS guards +
  wiring order); hostile intent_kind falls back; parseProfs last-comma split; id-less topics
  never enter resolved_topic_ids. -> **363 passed**.
- **Wave D (`96f4e7e`)** — **the consumer half of the D-064 seam**: fetch/browser_fill.py runs
  the pipeline's own extractors over an agent_browser snapshot, records through the D-010
  evidence path, closes awaiting_human gap_fill tasks, recomputes run status — the
  walled-social gap now closes via the browser tier (the docs-truthfulness audit's headline
  finding). CLI ingest-page --entity/--run + reexport command; default db reconciled to
  output/supervisorly.sqlite; plan-download move step documented; stale test count fixed.
  -> **377 passed**.

**Clean-room (goal §B6) — PASSED.** Wiped .venv/egg-info/__pycache__/.pytest_cache/output/
.cache/snaps/browser_staging/*.sqlite/scratchpad; git status + git clean -ndx empty (no
personal data, no profile data, no scan output). Fresh install -> **377 passed, first try**;
post-install tree clean. Live Chrome smoke test recorded **skipped** (MCP tools load at
session start; this build session has none) — procedure documented in
docs/BROWSER_COMPLETION_REPORT.md §5.

**State: GOAL 3 COMPLETE.** Suite green at **377 passed** on `build/browser`; audit closed
with zero open findings; clean-room green; DoD checked in docs/BROWSER_COMPLETION_REPORT.md.

## round B7 — design-atlas artifacts brought up to date with the shipped reality (this commit)

- `docs/design-atlas.md` + `docs/atlas.html` — audited against the codebase, stale claims fixed
  ("56 decisions" -> 67 everywhere; "Dashboard HTML + JSX" / the D-048 drawer summary replaced
  with what actually ships: ONE self-contained offline HTML, hand-written JS in the Atlas
  'Living' language — the vendored-React/JSX mechanism was never built; the human-rung-only
  fetch/source maps redrawn). Three new maps in both files: **MODES** (offline demo vs live),
  **SCAN SETUP** (free text -> map-field subject map -> multi-select in the Scan Studio or
  conversation -> plan -> scan --plan/--targets -> dashboard), and **BROWSER TIER** (the
  D-064/D-065 recipe: pace gate -> Chrome via MCP -> in-page extract -> staging file never
  read into context -> ingest-page -> snapshot -> extractors -> D-010 claims -> gap tasks
  close -> reexport). New violet "agent-browser" class in the colour key. COMPONENTS map gains
  subject-map/studio/pacing/browser-rung+fill; FETCH map shows Phase 3 = browser tier with the
  classic MD rung as fallback; RULES gains the pace gate; DECISIONS cluster -> 67 with the new
  browser-tier/front-door theme; atlas.html drawer data gains the D-064..D-067 summaries and
  the new node details.
- `src/supervisorly/export/dashboard.py` — the dashboard's own how-it-works diagram updated:
  the walled path now shows the browser tier (your session) via ingest-page, with the MD human
  rung as the on-challenge fallback (data + caption only, no engine changes).
- Verified: every command/flag/module/decision-id/count grepped against the code; all 24
  Mermaid diagrams render (mermaid-cli + system Chrome); inline JS passes node --check; the
  demo-fixture "3 shapes / 3 countries" claim confirmed in demo.py; suite green at **377**.

---

# GOAL 4 — the hosted web product (`build/web`)

> **Backfill notice.** Rounds W0–W6 below were written **after the fact**, during the W8
> verification round, by reading `git log` — the build log was not kept current while that
> work happened, which is a contract violation (`IMPLEMENTATION_GOAL.md` §8) worth naming
> rather than papering over. The commit hashes, file lists and behaviour are read from the
> commits themselves and are accurate. **Per-round test counts were never recorded and are
> not reconstructable, so they are omitted rather than guessed**; the first trustworthy
> figure is 534 at `744c016`, corroborated in W8 (566 today minus the 32 tests W8 added).

## round W0 — groundwork before the web build (commits `fb9781b`…`224207b`)

Pre-web fixes and the plan itself: `docs/atlas.html` bundled Mermaid inline (truly
standalone) and its lightbox fixed; `map-field` learned to relax zero-hit subject queries
per-word with idf-weighted ranking so distinctive words outrank generic ones; `run_live`
gained topic-filtered enumeration, the D-056 shortlist gate and an ORCID deep-dive fallback;
the first `subject_map` HTTP endpoint (`webapi.py`) + its Functions wrapper landed. Then
`docs/FIREBASE_WEB_PLAN.md` in three passes — v1, a hardening edge-case review (v2), and v3
adding the progress UX, scale controls, safe-exit/resume and the safety matrix.

## round W1 — D-068/D-069 + query expansion (commits `9688d72`, `e8d1b91`)

- `docs/DECISIONS.md` — **D-068** (the LLM may generate queries, never claims) and **D-069**
  (the hosted web product: honesty, privacy, user control) locked before any code.
- `src/supervisorly/discover/expand.py` — the expansion call, fail-closed: no key → no
  expansion → the student's own words, never an error and never a leaked key.
- `discover/subjects.py` — `subject_map_multi` (merge by `topic_id`, best rank, `found_by`
  tags, ≤8 queries). **Never wired in** — see round W8 and D-070.
- `discover/ladder.py` + `pipeline.py` + `cli.py` — `max_institutions`, the §4.3 scale
  control, with an honest "capped at N of M" warning rather than a silent truncation.

## round W2 — progress events + graceful cancel (commit `4b4068b`)

`pipeline.py run_live` emits rich progress events and honours a `should_stop` hook, so a
scan can be stopped between units of work and still export what it gathered; `model/db.py`
+ `schema.sql` persist the events; CLI gains `--progress`. Default CLI behaviour unchanged.

## round W3 — the job layer (commit `125d6cc`)

`src/supervisorly/jobs.py` (lifecycle `queued → running → done|failed|cancelled`, the §3.3
idempotency key, the §3.2 stall watchdog, `JsonJobStore` guarded by a lock) and the scan
endpoints in `webapi.py` (start/status/cancel/resume/result) with a local threaded worker,
so the whole flow runs offline on cassettes before any cloud existed.

## round W4 — the one dynamic page (commit `7ef3b21`)

`src/supervisorly/export/webapp.py` — the 5-step Atlas wizard as a single self-contained
page (1140 lines): you → field (*Understand*) → topics → scope → progress. Escapes every
API string, degrades honestly, and merges the D-068 phrasings **client-side** (the choice
that round W8 later had to put on the record as D-070).

## round W5+W6 — Firebase wrappers + deploy files (commit `744c016`)

`firebase/_core.py` (Firestore job store mirroring `jobs.py` one-for-one, per-IP throttles,
the expansion cache, the Cloud Run Job bridge, signed result URLs), `firebase/main.py`
(thin Functions wrappers), `firebase/worker.py` (the Cloud Run Job entrypoint), and the
step-7 deploy artifacts: `firebase.json`, `.firebaserc`, `firestore.rules`, `storage.rules`,
`lifecycle.json` (7-day TTL), `Dockerfile.worker` and an 8-step `README.md` runbook incl.
the `roles/run.invoker` IAM binding. Every `google.cloud.*` import is lazy so the module
loads with no SDKs and the suite stubs `sys.modules` instead of installing them.
→ **534 passed.** Deploy placeholders left unfilled by design (plan §8).

## round W8 — verification round (commits `bcc370d`, `3308b90`, `ab8bac2`)

Plan §7 step 8. Three green waves:

- **Wave 1 (`bcc370d`) — adversarial audit of the new surface, 8 findings, all fixed with a
  regression test each.** **HIGH:** `_ip` keyed the throttles on the *leftmost*
  X-Forwarded-For entry, which GCP appends to rather than replaces — a fresh header per
  request bought an unlimited source budget; the job endpoints were unthrottled entirely, so
  cancel→resume in a loop re-invoked the Cloud Run Job without limit; `firestore.rules`
  `allow get: if true` returned the whole job doc (email, plan) to anyone with an id while
  the HTTP handler filters; `set_status` was a non-transactional full-document overwrite that
  silently reverted a concurrent cancel and dropped progress events. **MED/LOW:** the named
  wrappers ran on any method (`GET /scan_cancel?id=…` was CSRF-able), the legacy
  `subject_map` alias skipped the throttle, `/api/map` matched on path alone, `esc()` left
  `'` unescaped. Also made `firebase/main.py`'s wrappers testable offline for the first time
  — they sat behind `if https_fn is not None` and were wholly untested, which is how two of
  these survived review. → **556 passed**.
- **Wave 2 (`3308b90`) — the click-through.** No real-Chrome harness exists in this repo (B7's
  Chrome check was manual and uncommitted), so this extends the Node `vm` + mini-DOM pattern
  from `test_studio.py` that plan step 8 actually names, driving the page's own unmodified JS
  through all five steps and a **cancel + resume** pass, asserting the exact request sequence,
  the honest-state text and the button visibility at each stage. → **565 passed**.
- **Wave 3 (`ab8bac2`) — D-070 + `docs/BLOCKERS.md` created.** `subject_map_multi` was correct,
  tested and unreachable. Recorded as a decision with both sides of the trade-off (client-side
  keeps per-phrasing failure honest; server-side would cost 1 throttle unit instead of 8)
  rather than silently deleted or silently refactored. → **566 passed**.
- **Wave 4 (`ace785d`) — this build log backfilled** for W0–W6, with a notice saying plainly
  that it was written after the fact and that per-round test counts are omitted, not guessed.
- **Wave 5 (this commit) — clean-room + README + the completion report.** The root `README.md`
  had **no mention of the web app at all** (a §6 DoD item); it now documents the local two-step
  run and points at the deploy runbook. Writing it caught a false claim before it shipped: the
  dev server serves the **API only**, not the page.

**Clean-room (contract §4 step 6) — PASSED.** Wiped `.pytest_cache`, egg-info, every
`__pycache__`, all `*.sqlite`, `.cache/`, `snaps/`, `browser_staging/`, `scratchpad/` and
`output/` (a smoke run: dashboard HTML/JSON, subject map, one page snapshot, the SQLite store —
moved aside, not destroyed). `git status` + `git clean -ndx` empty before the run; a brand-new
virtualenv (3.12.2) + `pip install -e ".[dev]"` → **566 passed, first try**; after the run the
tree still carried no database, snapshot or scan output (D-005). One deviation recorded in
`docs/WEB_COMPLETION_REPORT.md` §4: the existing `.venv` was kept and a *separate* fresh venv
used, rather than deleting the machine's only working environment.

## round W9 — first production deploy (commits `def587b`…`b9804e9`)

Deployed to Firebase project `supervisorly` (`us-central1`, Blaze), live at
**https://supervisorly.web.app**. The round W8 report called the untested cloud surface
"the single biggest untested surface, and no test in this repo can close it". It yielded
**seven defects**, and — the part worth remembering — **four of them deployed green**:

1. `firestore.Client()` implicitly targeted `(default)`; this project got a *named*
   database, so every call 404'd. The id is now deploy-time config.
2. The runbook's `--no-public-access-prevention` was commented "keep it PRIVATE" and does
   the opposite. A bucket of personal data would have been left exposable (D-005).
3. `gcloud run jobs create --source` does not exist — it is `jobs deploy`.
4. `git+https://` requirement on `python:3.11-slim`, which ships no `git`. Now a tag
   tarball, which also pre-empts the same failure in the Functions buildpack.
5. The IAM step named `<project>@appspot.gserviceaccount.com` — **404 Unknown service
   account** here — and omitted three roles. Step 6 now *reads* the runtime SA.
6. `public/index.html` shadowed the `webapp` function: Hosting serves static files
   **before** rewrites, the reverse of what that placeholder's own text claimed. The site
   served a 664-byte stub while every function was healthy.
7. v4 signing needs `service_account_email` + `access_token` to use IAM signBlob; the
   `serviceAccountTokenCreator` grant alone is not enough. `/api/result/<id>` 500'd with
   "you need a private key to sign credentials" — the last step of the product.

Verified live: the real 54 KB page with zero external URLs; `/api/map` against live
OpenAlex; a full `queued → running → done` scan; **cancel → cancelled** and
**resume → done** (§3.4 proven); `/api/result` 302 → signed URL → 21,890-byte dashboard;
and the same object unsigned → **403**.

One false alarm, recorded on purpose: a cancelled queued job looked stuck in `cancelling`
and was called a dead-end bug. The document actually said `cancelled` ~130 s in — a Cloud
Run cold start, and a 100 s poll window. Not a defect, an impatient test.

## round W10 — least privilege, and the defect it exposed (commit `145690a`)

Two cleanups from the W9 report, both done — and the second one earned its keep.

- **Orphaned Firestore database deleted.** `firebase deploy` had created `(default)`
  alongside the named `default` the project shipped with, leaving rules on one and data on
  the other. Standardised on `(default)`; the named one held only stale throttle counters
  (no job docs, no scan data) and is gone.
- **`roles/editor` removed from the runtime service account** — and it immediately broke
  `POST /api/scan`:

  > `PERMISSION_DENIED: Permission 'run.jobs.runWithOverrides' denied`

  **`roles/run.invoker` was never sufficient.** The Functions launch the worker WITH
  OVERRIDES (that is how `JOB_ID` is injected per execution), and overriding needs
  `run.jobs.runWithOverrides`, which lives in `roles/run.developer`. Every scan that had
  succeeded until then worked only because the default compute SA ships with
  `roles/editor`, which silently covered it. `roles/editor` does not merely over-permit —
  **it masks missing grants**, so "it works" was never evidence the documented permissions
  were right. The runbook would have failed on any hardened project, at the moment a
  student pressed *Start scan*.

  Replaced with explicit grants (`cloudbuild.builds.builder` — Cloud Build uses this same
  account, so without it the next deploy breaks; `logging.logWriter` — without it the
  worker's output vanishes exactly when it is needed; `monitoring.metricWriter`,
  `artifactregistry.writer`) plus the resource-scoped roles, then **verified by running a
  real scan**, not by redeploying: a deploy with no source change is skipped outright.

**A gift from the failure:** the job stranded by the permission error let the **§3.2
watchdog** prove itself in production — it flipped the stuck job to `failed` with "worker
stalled; safe to resume" after the 600 s window, and the job then resumed to `done` and
issued a signed URL. §3.3 idempotent start (`"existing": true`) and the §3.5 one-active-
job-per-email 429 were both observed incidentally too.

Also this round: the expansion endpoint and model became **server config**
(`SUPERVISORLY_EXPAND_BASE_URL` / `_MODEL`), so the same OpenAI-compatible call can point
at Gemini/DeepSeek/Groq with no code change. D-068 §3 is preserved — env only, never a
request param, with a test pinning that a caller cannot smuggle either one in.

## round W11 — the atlas points at real code, and one thing it exposed got built

Bringing the design artifacts up to the shipped reality (the whole web tier was missing
from every diagram) turned into a defect hunt, because mapping each diagram node to the
code that implements it makes an unimplemented node impossible to hide.

- **The atlas is now an index into the tree.** Click a node in `docs/atlas.html` and the
  drawer names the files and symbols that implement it; `design-atlas.md` carries the same
  mapping as a table. 59 nodes, 115 references, **machine-verified** by
  `tests/test_atlas_code_map.py` — the file must exist and the symbol must really be
  defined in it, so a rename fails the suite instead of leaving the atlas lying. Building it
  caught two references I had invented (`extract/md_ingest.py` does not exist; MD ingestion
  is `ingest.py:ingest_md`).
- **D-010 conflicts were prose, not code.** The `conflict` table shipped with the first
  schema and *nothing ever wrote a row*: the second source silently overwrote the first,
  while the atlas, the domain model and D-010 all promised disagreements were recorded.
  `model/conflicts.py` closes it — a disagreement is recorded, the loser superseded rather
  than deleted, and the head chosen by a policy a reader can check (higher trust wins on
  provenance; within a tier the fresher observation wins; a standoff stays **`open`** for a
  human instead of being quietly decided). Wired into `record_claim`, the one choke point
  every claim already passes through, for the same reason the quote gate is there: a
  guarantee a caller must remember is not a guarantee.
  Writing the tests caught a real bug in my own first cut — the schema's `source_tier` CHECK
  allows **eight** tiers and I had ranked four, so `official_api`, `cris`, `registry` and
  `open_social` would have scored zero and lost to an aggregator. A test now asserts the
  ranking and the schema vocabulary match exactly.
- **`people search` (Stage 4) stays labelled "not built"** — it is SKILL.md prose with no
  module behind it. Implementing it is a feature, not a docs fix, so the atlas says so
  rather than quietly omitting the node.

Suite **571 → 702**.

**State: GOAL 4 COMPLETE, DEPLOYED, AND HARDENED.** Suite green at **702** on `build/web`.
Still unproven by anything: the 6 h task timeout, the 7-day TTLs (they need seven days),
throttles under real concurrency, and any scan large enough to meet the OpenAlex daily
budget.

## round W — CC-1 phase ledger, FLAG phase flags, and SPIKE-0 (web-v19)

**Built:**
- **CC-1 phase ledger.** Schema v4 adds `phase_ledger` (a new table — that *is* what additive
  means, so `migrate` needed no rebuild path). `runs.record_phase` / `runs.phase_ledger`;
  the rows travel in the export as `run.ledger` and render in the dashboard's "How it works"
  view. A skip with no reason **raises**: a blank "Why" cell reads as "no reason" rather than
  "nobody recorded one". Rows order by `rowid`, not `created_at` — `utcnow()` is
  second-resolution and a ledger that reshuffles between reads is one nobody trusts.
- **FLAG.** `src/supervisorly/phases.py`. `PHASES` env var, read once, server-side only
  (D-068). Off by default. Every off phase writes a ledger row naming the variable, so
  "off" is visible rather than silent — the render rung once did nothing for two deploys
  and nothing said so. Typos and not-yet-built names are reported, not dropped.
- `tools/spikes/spike_orcid_employments.py`, `tools/e2e/check_ledger.js`.

**Ran:** `python -m pytest` → **926 passed** (`TMPDIR` outside the repo). Both tiers deployed
at tag `web-v19`; worker image digest `8c360618…` → `4499515b…`. One real scan
(`176837fed485…`, Egypt · cardiovascular disease, 428 professors) verified with headful
Chrome: `record_flow.js` **33/33**, `check_ledger.js` **7/7**.

**SPIKE-0 = 22%, gate is 30% → P0 NOT built.** Three cohorts: EG/cardiovascular 28%,
CA/machine-learning 28%, DE/water-treatment 7%. The binding constraint is not employments:
55% of shortlisted professors carry **no ORCID at all**. Full write-up and three re-plan
directions in `docs/plan/20-p0-orcid.md`.

**Caught during the round:**
- The sampling error `01-spikes.md` warns about reproduced itself on the first run:
  `--field cardiology` resolves to **zero** OpenAlex topics, the enumeration fell back to
  unfiltered, and the flattered cohort scored 68% against the filtered 28%. The spike now
  prints `topics N` and the doc says to check it before believing any number.
- Deploying with `--set-secrets SUPERVISORLY_OPENALEX_KEY` broke the worker
  (`Ready = False`): that secret **has never existed** in this project. It is documented as
  optional; the job now binds only `SUPERVISORLY_CONTACT_EMAIL`.
- `.gitignore` did not cover e2e screenshots. Every run leaves a directory of named
  academics one `git add -A` from a commit (D-005/D-032). Now ignored, unanchored, because
  the runbook invents a new output directory per pass.
- Two false alarms from the new checker, both worth writing down: the dashboard's `DATA` is
  a top-level `const` and never lands on `window`; and `innerText` falls back to
  `textContent` for unrendered elements, so it can never prove visibility — ask the layout.

## round X — multiple intents and the supervision-level filter (web-v20)

**Built:** MI-1 (step-1 intent cards become checkboxes; at least one required, never a silent
default), MI-2 (`intent_kinds` is the truth, `intent_kind` derived — `cli.normalize_plan_intents`
re-derives it on both entry paths, and in `webapi.scan_start` *before* the job key so a stale
scalar cannot split idempotency), MI-4 (level chips with counts, composing with the text
filter) and MI-5 (the honesty rules). MI-3 is `[!]` blocked on P5.

**Ran:** `python -m pytest` → **962 passed** (`TMPDIR` outside the repo). Both tiers deployed at
`web-v20`; worker digest `4499515b…` → `6dd13cdd…`. Real scan `88ff75e9a5eb…` (428 professors)
verified headful: `record_flow.js` **44/44**, extended to tick two intents and drive the filter.

**The thing worth remembering:** `supervises` is not a declared export field yet — it arrives
with P5 — so today **every** professor is `unknown`. Unticking `unknown` on the live dashboard
takes 428 rows to 0. A filter that hid unknowns by default would therefore have shipped an
empty dashboard for a scan that found 428 people, and it would have looked like a data bug
rather than a design one. The chips say "No professor has stated a level yet" and the empty
state names the count and the way back.

**Caught during the round:** two `const` collisions in `record_flow.js` (`chips`, `before`)
that only `node --check` surfaced — worth running before a 10-minute live pass. The
click-through harness modelled intents as radios with exactly one winner; it now models a
checkbox group and records request *bodies*, so "two ticked reach the plan" is asserted on
what the page actually sent rather than on what its source contains.

## round Y — CC-3, CC-5, and a SPIKE-1 that found something bigger than P1

**Built:** CC-5 (PDF text extraction) and CC-3 (host pool + batch renderer). Both needed more
than their task descriptions implied:

- **CC-5 needed a transport change.** `Response` carried only `text`, so a PDF body could not
  be recovered at all and the magic-byte sniff had nothing to look at. It now carries
  `content: bytes`. The 200 MB cap needed *streaming* — `client.get()` downloads the whole
  body before returning, so a cap checked afterwards has already paid the cost. Two guards:
  `Content-Length` up front, and a running byte count for chunked responses that never declare
  a size. Extracted text is escaped into a `<pre>` envelope so the D-010 quote gate is
  untouched — without it, PDF prose containing `<` or `&` is eaten by `main_text`'s HTML
  parser and a quote fails against its own snapshot, discarding a *true* claim.
- **CC-3's lock order is the design.** Host lock first, global semaphore second. The obvious
  order starves the pool exactly when a scan walks one university: twenty URLs take twenty
  global slots and then all queue on one host lock. Inverting the two lines makes the test's
  lone other-host request finish 9th instead of within 4.

**Ran:** `python -m pytest` → **1011 passed** (`TMPDIR` outside the repo). CC-5 also verified
against the live network (a real PDF extracted; a 500-byte cap refused a real response at 0
bytes downloaded) because cassettes cannot exercise the streaming path at all.

**SPIKE-1 = 0% on the real cohort → P1 NOT built.** But the number is not about P1. Where a
university exists and permits crawling, its postgraduate page was **one hop from the
homepage** — `asu.edu.eg/postgraduate`, `must.edu.eg/.../graduate-studies`. The 0% is because
the institutions a scan surfaces are not universities: for CA + machine learning the
shortlist's institutions were Nexen, Purdue Pharma, Nutrition International and a military
institute.

**Root cause, measured and recorded as B-006:** `institutions_in_country` takes ROR's first
100 per country in an order that is not relevance, and `select_institutions` filters nothing
— despite the former's docstring claiming the caller filters to education types. Education-
typed institutions in that slice: **41/97 Egypt, 5/100 Canada, 1/98 Germany.** A German
student's scan enumerates professors at a clinical-drug-research company. This plausibly also
limits P2 and P4/P5, and it needs a product decision (filter by type? raise the cap? order by
OpenAlex output in the student's field?) before any institution-dependent spike is re-run.

**Method note now in `01-spikes.md`:** the sampling rule got a third worked example, and a
refinement — "the cohort a real scan produces" is only the right sample if the scan is itself
sampling the right things. When a spike scores zero, say whether the *phase* is unviable or
the *input* is wrong. A bare number would have killed a phase that was never actually tested.

**Deployed web-v21** (CC-3 + CC-5). Worker digest `6dd13cdd…` → `764f672d…`, page verified
identical. Real scan `7a3df6065a07…` (394 professors): `record_flow.js` **44/44**,
`check_ledger.js` **7/7**, `logs.py errors` clean. The check that mattered: CC-5 rewrote the
live transport to stream every response, so *every* production fetch changed — the deep-dive
ledger row is unchanged at 40 attempted / 10 reached / 30 skipped, so nothing regressed.

## round Z — SPIKE-4 could not be measured, and finding out why fixed a real defect

**SPIKE-4 = INCONCLUSIVE, not a MISS. P4 and P5 are NOT built.** The independent judge (the
model triage exists to feed, so the labels are not the regexes under test) found recruiting
language on **0** pages across two cohorts. Recall has no denominator, and reporting "0% —
MISS" would have killed a phase that was never tested; the spike now exits distinctly on that.

**Why zero, measured rather than guessed** (`tools/spikes/spike_page_supply.py`): of 49
shortlisted GB machine-learning professors, **0% resolve to a page they control** — 88% to no
page at all, 12% to an ORCID/Publons profile. "I am recruiting PhD students" is a sentence a
person writes on their own page; a registry has no field for one. Recorded as **B-007**, with
the sequencing consequence: **P2 (the directory rung) is what creates this supply, and the
plan orders P4/P5 before it.**

**A real defect, found by the spike and fixed:** `OpenAlexClient.topic_ids` returned `[]` for
both "no such topic" and "the lookup failed". An empty topic list makes `build_targets`
enumerate **unfiltered**, so a rate-limited lookup silently turned "professors in my field"
into "the most prominent professors at these institutions" — with the coverage line still
claiming nothing was dropped. Found because OpenAlex's free daily budget ran out mid-session
(`429 "Insufficient budget… Resets at midnight UTC"`), which is a state this tool will hit
routinely. A failed lookup now records a `topics@<field>` truncation marker, and a field that
resolves to nothing produces an explicit warning that the scan was NOT filtered by field.
This is also the mechanism behind the "cardiology" trap already recorded in `01-spikes.md`.

Two `test_cli_live.py` expectations changed with it: both had pinned the old silence. One
also caught an em-dash in the new warning — CLI output asserts `printed.isascii()`.

**Ran:** `python -m pytest` → **1019 passed** (`TMPDIR` outside the repo).

**Method note:** the first version of `spike_triage.py` skipped the render rung and reported
15 of 17 pages as unreadable JS apps — a blocker that was really its own measurement gap,
since the deployed worker reaches 10 of 40 targets on the same cohort. A spike that skips a
rung the product has measures a product nobody ships.

## round AA — the front end (web-v22)

**Built:** CC-4/FE-1 past searches, T-1 translation display, FE-2 cost preview, FE-5 model-key
panel, FE-6 sweep. FE-3 and FE-4 are `[~]`: seven of their subtasks need data from P0/P1/P2/P5,
none of which is built, and rendering empty blocks for them is not "done".

**Ran:** `python -m pytest` → **1035 passed**. Deployed `web-v22`; worker digest `764f672d…` →
`2edd2068…`; real scan `34948a813698…` verified headful — **54/54**, up from 33 when this
session started.

**Two decisions worth carrying forward:**
- **CC-4.1 vs D-069.** The plan asks to store "job ids + field / country / date" in
  `localStorage`; D-069 forbids `localStorage` for *plan* or email, and the field and country
  are plan. A locked decision outranks a plan task, so the list stores id + date only and the
  conflict is **B-008** for Ahmed. A blanket "no localStorage" guard test became a precise one
  that fails if the email, plan, fields, country or a professor ever reaches a `setItem`.
- **FE-5's promise is enforced, not asserted.** The key never enters `state`; tests check that
  no line touching it mentions `api(`, that the POSTed plan has no key-shaped field, and that
  the D-071 error beacon cannot reach it — that beacon posts error text to us and is the real
  leak path. `Test key` calls Google directly and fails soft.

## round AB — SPIKE-2, and a wrong conclusion caught by a second cohort

**SPIKE-2 = 29% pooled against a 30% gate. Undecided — P2 not built.**
`tools/spikes/spike_directory.py` (ROR only, so the OpenAlex budget does not block it),
education-typed institutions:

| cohort | found | robots-refused | share |
|---|---|---|---|
| Egypt | 2/10 | **5/10** | 20% |
| United Kingdom | 2/4 | **0/4** | 50% |
| **pooled** | **4/14** | 5/14 | **29%** |

**The methodological point of this round.** After the Egyptian cohort I had written, in
`24-p2-directory.md` and in B-007, that "half the institutions forbid us outright" and drawn a
product-shape conclusion from it: that the deterministic path cannot supply professor pages
and the human rung is therefore the product's real centre. The UK cohort refuted the premise
within the hour — **zero** robots refusals. Both documents were corrected and the claim
withdrawn before either was committed.

That is the same error the sampling rule already warns about, in a third costume: not a
flattering sample this time, but a *discouraging* one generalised from a single country. The
rule that would have caught it earlier is the one now written down — never conclude from one
cohort, in either direction.

**What survives:** robots refusal is real, legitimate and obeyed, but **country-specific**.
Every directory found was at **depth 1**, so the 3-hop budget is not the constraint. And both
cohorts are small *because of B-006* — the UK sample is 4 institutions, all the education-typed
ones ROR's first 100 GB rows contain. Fixing B-006 widens every future cohort.

**Next step, cheap and unblocked:** re-run on 2–3 more countries. It needs no OpenAlex.

## round AC — SPIKE-6 passes, and the P7 UI ships

**SPIKE-6 = 50% (2/4), gate 25% → PASS.** `asu.edu.eg/postgraduate` has six archived cycles
and `aisegypt.com/admissions/…` five. Cycles are counted **per year** and only 2xx captures
count — fifty captures in one busy year is one cycle, and a 404 capture records that a URL
existed, not a deadline anyone could read.

**But P6 is still blocked**, on P1 rather than on its own gate: it projects from admissions
pages P1 would discover, and P1 is `[!]`. Four hand-carried URLs from SPIKE-1's crawl are not
a pipeline. This is a good state — when P1 lands, its URLs feed a projection whose feasibility
is already measured.

**P7 is `◐`:** FE-5 shipped the UI half and the security rules are enforced by tests rather
than promised. The remaining work is switching the expansion step from the server key to the
student's, failing closed to their own words.

**Session totals:** 1035 tests passing (from 907); deployed web-v19 → v22 with the worker
digest confirmed changing at every step; the e2e went 33 → 54 checks against production.

## round AD — P6-1, the archive client

SPIKE-6 passed its gate, so P6-1 was built — for the same reason CC-3 was: it is the
self-contained client that phase needs, exercised as a primitive rather than wired in, because
P1 has no admissions URLs to give it yet.

`discover/archive.py` reads Wayback CDX and refuses to project far more often than it
projects, which is the point — the dangerous output here is a *date*, and a student who plans
around a fabricated one has been badly served. Three refusals worth remembering:

- **Only 2xx captures count as cycles.** A 404 capture proves the URL existed, not that a page
  was archived whose deadline could be read.
- **Enough captures but too few readable dates still refuses.** Otherwise "four cycles" would
  license projecting from two dates, sidestepping the 3-cycle rule through the back door.
- **A 429 is a failure, not an empty history.** The archive is a charity and throttles;
  reporting that as "no history" turns their rate limit into our claim about an institution.

`p6` deliberately stays in `PLANNED_PHASES` rather than `OPTIONAL_PHASES`: a phase joins the
latter only when it has a call site that can be skipped. Listing it early would let
`PHASES=p6` read as accepted while changing nothing — the failure FLAG exists to prevent.

**Ran:** `python -m pytest` → **1051 passed**.
