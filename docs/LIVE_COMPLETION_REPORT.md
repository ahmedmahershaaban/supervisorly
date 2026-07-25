# Supervisorly — LIVE scan Completion Report

> Status: **COMPLETE** — build phases L0–L8, the adversarial refine loop (§5/L9, five passes, the
> last one independent and zero-open-findings), and the clean-room verification are all green.
> Branch: `build/live`. Live commit range: **`bbd6174` (round L0) … this report's commit**.

The live scan turns *a country + a field + an intent* into an honest, evidence-backed, **ranked**
dashboard of **real** professors — their recruiting status, application deadlines, the students who
joined them, the companies they've worked with, and their advertised social — every fact backed by a
citable source, every gap stated honestly, no login ever defeated. It **reuses the proven offline
engine** (fetch/extract/verify/score/export/ethics/cache/resume/human-rung) and adds the front door,
the extra collectors, ranking, scheduled re-scans, and the Atlas front-end.

---

## 1 — What was built (phase by phase)

- **L0 — Open-API clients** (`discover/ror.py`, `discover/openalex.py`): keyless ROR (country →
  institutions) and free OpenAlex (topics, authors-by-institution, works) behind the transport seam;
  contact-email polite pool + optional premium key. Cassette-testable, LLM-free.
- **L1 — Discovery ladder** (`discover/ladder.py`): generate-don't-look-up (D-038) Round 1 — country
  → institutions (ROR, honouring `university_mode`) → professors (OpenAlex), **reconciled/de-duped by
  identity** (D-057). Login-walled directories → the human rung (D-052), never scraped.
- **L2 — Live driver** (`pipeline.run_live`): preflight (fail loud without a contact email) →
  discovery → the *same* fetch → extract → claim → score → export → dashboard path as `run_offline`
  (refactored into the shared `_process_targets`). A professor with no discoverable page is an honest
  blocked open gap for the human rung, never a fabricated value.
- **L3 — Extra collectors**: `extract_students_signal` (lab members / alumni), `extract_industry_
  signal` (collaborations / funders), `extract_social` (an *advertised* link only — the walled page
  goes to the human rung, D-039/043). Each a quote-verified four-state Claim.
- **L4 — Ranking** (`score/ranking.py`): reuses `score_professor`; `rank_professors` +
  `rank_universities` (D-031 roll-up, transparent, re-weightable, confidence lowered for sparse
  institutions).
- **L5 — University scope**: `all` / `prioritise` / `only` via the ladder + CLI.
- **L6 — Scheduled re-scans** (`export/delta.py`): a warm re-scan does ≈0 re-extraction and emits a
  *"what changed"* delta — new/removed professors, **recruiting-signal changes flagged for review**
  (never asserted as "now recruiting" — that's the Stage-2 LLM's call), and newly-published deadlines.
- **L7 — Atlas front-end** (`export/dashboard.py`): the results dashboard + a how-it-works diagram in
  the "Supervisorly Atlas — Living" language (bioluminescent tokens, Space Grotesk/Mono, the glowing
  **cells + curved animated filaments** engine, cell-drawer detail) — ONE self-contained offline
  file, reduced-motion-aware, injection/scheme-safe (D-033/D-048).
- **L8 — CLI + SKILL**: `scan --country --field --intent --universities --university-mode --email
  --openalex-key --optout --resume`; SKILL.md documents the intent → plan → Stage-1 → Stage-2 → rank
  → dashboard flow; README has the live command + a Task-Scheduler/cron recipe.

## 2 — Test inventory

`python -m pytest` → **253 passed** (exit 0), and **253 passed on the first try from the clean-room
fresh install** (§6). Live-path test files (74):

| File | Tests | Covers |
|---|---|---|
| test_discover_clients | 14 | ROR **v2** + OpenAlex mapping, error→[], premium key, honest empties, pagination + **truncation on cap AND on mid-pagination failure**, institution-resolution failure ≠ absence |
| test_discover_ladder | 11 | enumerate + dedupe/reconcile, **ORCID split-profile merge**, topic resolution, all/prioritise/only, word-boundary scope, **diacritic folding + 0-of-N named-match warning**, truncation surfaced |
| test_run_live | 8 | discover → export, honest states, zero hallucinations, fail-loud, opt-out, **sparse-coverage warning**, **PARTIAL on institution-resolution failure** |
| test_collectors | 11 | students/industry/social extractors, honest searched_absent, login-wall blocked, **noscript-banner page still extracted**, **walled social → human-rung task + open gap**, **period-free-blob linearity** |
| test_ranking | 7 | professor + university ranking, re-weightable, **axis independence**, reconcile, pre_phd not gated |
| test_delta | 12 | re-scan delta + warm-cache ≈0 re-extraction + changed-page + recruiting-change-is-review, **verified removal supersedes stale value** (+ human-assisted survives), **watch→firm confidence flip → newly_deadline**, vanished field, schema mismatch, rename |
| test_dashboard_atlas | 5 | Atlas tokens/type, self-contained fonts, diagram engine, reduced-motion, cell drawer |
| test_cli_live | 6 | fail-loud, needs country+field, full live run via patched transport, **country-name → ISO resolution + loud reject of unknown countries** |

The refine loop (§5) also hardened offline-engine test files: **test_deadline_parse** (38 — payment/
event/domain-modifier/subject-tie cases + verbatim dotted-abbreviation quotes), **test_ethics** (13 —
bare-email/list/mailto, gitignore under any `--out`, corpus-never-read, LLM-free, email-shaped
identity fields), **test_discovery** (15 — the JS/noscript wall cases + non-English wall markers),
**test_dashboard** (10 — script-injection escape), plus pass-5 regressions in **test_fetch_normalize**
(11 — timestamp-shaped volatile masks, comma-less counters), **test_fetcher** (8 — redirect robots
re-check), **test_backoff** (6 — post-jitter cap), and **test_cli** (5 — the D-005 `--out` guard).
The **previously-green offline suite stays green** — no regressions.

## 3 — Feature-request coverage (everything asked for)

| Requested | Delivered |
|---|---|
| Enter a country / optional universities | `--country` + `--universities`/`--university-mode` (all/prioritise/only) |
| Rank universities | `score/ranking.py` `rank_universities` (D-031) |
| Professors, students who joined, companies worked with | L3 collectors — each a sourced four-state Claim |
| Recruiting status incl. social | recruiting extractor + advertised-social link; walled social → human rung |
| Generic, intent-first | SearchPlan + generated ROR/OpenAlex queries (D-038); no hardcoded lists |
| First round list+links, second deep-dive | ladder Stage-1 enumerate → Stage-2 deep-dive |
| No data → don't drop, honest emptiness | four states everywhere; nobody dropped |
| Deadline/urgency view | dashboard Deadlines view (watch vs firm, D-061) |
| Automatic/scheduled re-scans | `--resume` + warm cache + `export/delta.py` |
| Front-end + diagrams per the Atlas | L7 Atlas dashboard + cells-and-filaments diagram engine |

## 4 — Governing-constraint compliance

Generate-don't-look-up (D-038), corpus-never-read (D-035), deterministic-collection/LLM-interpretation
(D-009/021), verified claims (D-010), honest four states (D-046), public + human rung (D-039/043/044/
052), credentials-reality (contact email; ROR keyless, OpenAlex free), ethics-in-code (opt-out at
build + discovery + re-export; robots fail-closed; no bare-email/list/mailto; no bulk path; no login
defeated; scan output never committed). All test-guarded (the offline suite's ethics tests scan the
new `discover/` + `pipeline` code too).

## 5 — Adversarial refine loop (goal §5)

Multi-agent adversarial audits (independent finders → adversarial verifiers; only reproduced-in-code
findings kept), each finding fixed with a regression test, suite re-run green after every round.

**Pass 1 (rounds L9b–L9g) — 9 confirmed, all fixed → 195 passed:** deadline payment-exclusion;
login-wall detection wired into the deep-dive; discovery pagination + truncation marker + word-boundary
scope; dashboard `_inline_json` script-injection escape (`<` → `<`); unanchored `.cache/`/`snaps/`
gitignore (content-based, D-005); ranking axis independence (no recruiting/activity double-count);
delta highlight relabeled `recruiting_changed` (a *review* signal, never "now recruiting").

**Pass 2 (round L9h, commit `cc587b2`) — 6 confirmed, all fixed → 202 passed (+7 tests):**
1. **JS/noscript wall false-positive** (3 auditors): `please enable javascript` matched raw HTML, so a
   content-rich page shipping a routine `<noscript>` fallback was misread as a wall and its real
   recruiting/students/social signals discarded. Split into strong `_WALL_MARKERS` (fire anywhere) +
   `_JS_WALL` that is a wall **only** when `main_text` (which strips `<noscript>`) is near-empty — a
   genuine JS shell. Fixes a coverage regression on a very common page shape (D-022/037/046).
2. **Deadline payment-guard bypass + over-drop:** the exclusion was co-occurrence-based, so "the
   deposit for PhD studentships is due 1 Dec" fabricated a firm deadline (D-010/D-061), while
   "Applications close 1 Dec and the fee is due then" over-dropped a real one. Made it **subject-tied**
   (`_PAYMENT_HEAD` — the money heads the phrase via a `for/of` modifier).
3. **Silent truncation on a mid-pagination fetch failure:** a transient non-200 returned partial
   results with **no** truncation marker → false completeness (D-037). Both clients now mark PARTIAL on
   the not-data early return.

**Pass 3 (round L9i, commit `272ed0c`):** the third independent multi-agent audit first **could not run
— all three finder agents errored on a session usage limit (0 ran).** Per goal §7 that is **not** a
"zero findings" result and was **not** treated as convergence. An **in-loop adversarial probe** of the
pass-2 fix areas (`scratchpad/probe_l9h.py`, real code, 16 checks) then reproduced one residual defect:
`_PAYMENT_NOUNS` listed a bare `deposit`, so `\bdeposit\b` missed the plural "Deposits" and "Deposits
for PhD applicants are due 1 Dec" fabricated a firm deadline. Fixed (every payment noun plural-tolerant)
with regression cases → probe 0/16 failures; **202 passed**. The audit was then **re-run once the limit
reset**; result recorded in §5-final below.

**Pass 4 (rounds L9j–L9m, commits `2ebc21d`…`a0fe080`) — 6 confirmed (2 HIGH), all fixed → 217
passed (+7 tests):** deadline subject-detection redesigned (participial post-modifiers, coordinated
noun subjects, imperative submit cues); the CLOSED payment-noun list removed entirely (a D-038 leak —
a clause is an application deadline only when the cue's subject head is a recognised application
word, else fail-safe); robust wall detection (Cloudflare/bot-challenge interstitials, genuine-CAPTCHA
phrasing, bounded banner strip); truncation markers persisted across the re-export resume boundary.
(Full detail in `BUILD_LOG.md` rounds L9j–L9m.)

**Pass 5 (round L9n, commit `50a1084`) — the independent re-run: 20 candidates → 19 confirmed
(7 HIGH), all fixed → 253 passed (+36 tests over the audit).** Structure per §5: **6 independent
finder agents** (one per audit dimension) → **6 adversarial verifier agents** instructed to rebut;
only findings reproduced in code survived (1 **rebutted** — dashboard `env.state` HTML interpolation
is unreachable: DB CHECK constraint + two write-path validators; 1 **downgraded** — email-shaped
identity fields, near-nil reachability, still fixed as defense-in-depth). Every fix landed with a
regression test and the suite re-ran green after each of the three fix waves (217 → 232 → 244 →
253). The confirmed seven HIGH findings: dotted abbreviated-month deadlines ("1 Dec. 2026") were
extracted correctly then quote-rejected at record time (analysis-only dot-strip now returns the
**verbatim** raw quote); split OpenAlex profiles were never reconciled (decisive-ORCID merge in the
ladder — D-030/D-057 — works summed, topics unioned, homepage-only match stays two targets); the ROR
client targeted the **retired v1 schema** (moved to the v2 API, cassettes re-recorded to the live
shape per goal §7); `--country Canada` flowed verbatim into ROR's alpha-2 filter (names now resolve
via a standards-body ISO table at the CLI seam — D-038-safe — and unknown input fails loud, D-002);
**robots.txt was bypassed on redirects** (final URLs now re-checked fail-closed, no snapshot on
deny, provenance recorded under the final URL — D-019/D-010); the volatile-chrome mask swallowed
real content after "updated" stamps, freezing changed deadlines in the warm cache (mask now covers
timestamp-shaped tokens only — D-061); and a failed OpenAlex institution-resolution silently dropped
a whole university while claiming full coverage (now a PARTIAL truncation marker — D-037). The 8
MEDIUM + 4 LOW: verified-removal supersedes stale deterministic values (human-assisted values stay
protected), coverage-preflight wired into the live path (D-060), diacritic-insensitive university
matching + 0-of-N warning, non-English (de/fr/es) login-wall markers → human rung (D-052), walled
advertised-social links mint `awaiting_human` gap tasks (D-043), quadratic signal regexes made
linear, the D-005 `--out` CLI guard, delta confidence/rename/field-union/schema-version honesty,
comma-less counters, post-jitter backoff cap, email-shaped-name redaction. All pass-5 probes re-run
clean after the fixes (one probe's gitignore-coverage check fails by adjudicated design — the fix is
the test-locked CLI warning instead).

**§5-final (independent re-confirmation):** ✅ **CLOSED — zero open findings.** The pass-5
independent multi-agent audit ran to completion (no aborted agents): 6 finders → 6 adversarial
verifiers → 19 confirmed findings, all fixed with regression tests, full suite green after every
wave, all finder probes re-run clean. Nothing remains open from any pass.

## 6 — Clean-room verification (goal §4 step 6) — PASSED (re-run after §5 closure)

First passed from tip `ad96e52` (202 passed, first try). **Re-run after the §5 audit closed**, from
tip `46811f1`: wiped every generated/transient artifact (`.venv`, `src/supervisorly.egg-info`,
`__pycache__`, `.pytest_cache`, and any `output/`/`.cache`/`snaps`/`*.sqlite`). **`git status` and
`git clean -ndx` were both empty** — only committed code, docs, and synthetic/public fixtures survived;
**no personal data, no real-page snapshots, no scan output.** From that clean state ran the documented
install (`python -m venv .venv` → `pip install -e ".[dev]"`) and re-ran the offline cassette self-test:
**`253 passed in ~28s` on the first try.** Post-install `git status` clean (`.venv` + egg-info
gitignored). The dirty-run and clean-run counts match (253 = 253) — no hidden dependency.

## 7 — Definition of Done

| DoD item | Status |
|---|---|
| Every phase L0–L9 meets its DoD | ✅ |
| `scan` (no `--demo`) runs the full live path on cassettes → honest four-state dashboard from **discovered** targets (students, companies, recruiting/social) | ✅ test_run_live + test_cli_live + test_collectors |
| UI + ≥1 diagram in the Atlas language, self-contained/offline, reduced-motion + keyboard | ✅ test_dashboard_atlas |
| Every §3 edge case has a passing test | ✅ |
| Ranking (uni + prof) deterministic, re-weightable, intent-aware | ✅ test_ranking |
| University scope all/prioritise/only; default all | ✅ test_discover_ladder |
| Scheduled re-scan ≈0 re-extraction + honest "what changed" delta | ✅ test_delta |
| The §5 adversarial self-audit returns **no open findings** | ✅ pass 5 ran to completion — 19 confirmed, all fixed + regression-tested, zero open (§5-final) |
| Ethics gates test-verified (opt-out build/re-export/mid-scan, robots, no-bare-email, no-bulk, corpus-never-read, no-login-defeated, LLM-free) | ✅ test_ethics + test_optout + test_fetcher (redirect robots) |
| All tests pass; previously-green offline suite stays green | ✅ 253 passed |
| Docs updated (README live/creds/command/scheduling, BUILD_LOG, getting-started live section, DECISIONS) | ✅ |
| **Clean-room verification passes on the first try** | ✅ §6 (253 passed, re-run after §5 closure) |
| `git status` shows no scan output / no personal data; `.gitignore` honoured | ✅ §6 |
| Live smoke test **passed-or-skipped** (never fabricated) | ✅ **skipped** — no real contact email in this environment (§8) |
| Final `LIVE_COMPLETION_REPORT.md` | ✅ this file |

**Every box is checked.** The §5 re-confirmation ran to completion (no aborted agents) and returned
zero open findings after its 19 confirmed findings were fixed and regression-tested; the clean-room
was then re-run and passed on the first try at 253. The goal is **COMPLETE**.

## 8 — Known limitations (honest)

- **Live network is exercised via cassettes**, not a real credentialed smoke test (no keys in this
  environment). The transport seam means a live run is the cassette-tested path with httpx swapped
  in; the credentialed smoke test (goal §4 step 4) is recorded **skipped**, never passed.
- **Discovery uses the OpenAlex authors-by-institution rung** (open API) rather than scraping faculty
  directory HTML — robust and polite, but coverage depends on OpenAlex's institution affiliations.
  The sitemap/JSON-LD/CT-log rungs (D-028) remain a future enrichment; the roster/human-rung path
  handles login-walled directories.
- **The extra collectors (students/industry/social) are deterministic signal tiers** — quote-verified
  candidates the LLM synthesist structures in Stage 2 (D-009/021), not fully-structured records.
- **A quote-only evidence swap is not surfaced in the re-scan delta** — when a re-scan supports the
  same value at the same confidence with a different verbatim quote, `compute_delta` reports no
  change (state, value, confidence, and name changes ARE surfaced). Adjudicated during pass 5 as
  acceptable churn; recorded here honestly.
- **Fonts are named with a faithful system fallback**, not embedded, to keep the dashboard a single
  self-contained offline file with no external request (D-033).

## 9 — How to run

```bash
supervisorly scan --demo --out output/dashboard.html                 # offline, no keys
supervisorly scan --country Canada --field "causal ML" \             # live
  --intent pre_phd --email you@example.com --out output/live.html
```
