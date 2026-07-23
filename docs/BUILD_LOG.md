# Build log

One short entry per milestone: what was built, what was run, what passed, what changed.
Newest at the bottom. Branch: `build/v1`.

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

## COMPLETION — goal met

All phases (A–J) met their DoD; 18/18 edge-case rows have passing tests; the offline self-run is
hallucination-free; the four-pass adversarial audit (10 → 6 → 2 → 1) is closed with all 19 findings
fixed + regression-tested; ethics gates are all test-guarded; clean-room verification is green from a
fresh checkout. **135 tests pass (exit 0).** See `docs/COMPLETION_REPORT.md` for the full sign-off.
The only step recorded **skipped** (never passed) is the credentialed live smoke test — no
ROR/OpenAlex keys in this environment; it is the natural next build increment.
