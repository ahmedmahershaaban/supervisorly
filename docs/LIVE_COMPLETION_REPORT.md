# Supervisorly — LIVE scan Completion Report

> Status: build phases L0–L8 complete and green; the adversarial refine loop (§9/L9) and clean-room
> verification are the last steps (their sections are filled in last). Branch: `build/live`. Live
> commit range: **`bbd6174` (round L0) … this report's commit**.

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

`python -m pytest` → **202 passed** (exit 0), and **202 passed on the first try from the clean-room
fresh install** (§6). Live-path test files (52):

| File | Tests | Covers |
|---|---|---|
| test_discover_clients | 11 | ROR/OpenAlex mapping, error→[], premium key, honest empties, pagination + **truncation on cap AND on mid-pagination failure** |
| test_discover_ladder | 7 | enumerate + dedupe/reconcile, topic resolution, all/prioritise/only, word-boundary scope, truncation surfaced |
| test_run_live | 5 | discover → export, honest states, zero hallucinations, fail-loud, opt-out |
| test_collectors | 8 | students/industry/social extractors, honest searched_absent, login-wall blocked, **noscript-banner page still extracted** |
| test_ranking | 7 | professor + university ranking, re-weightable, **axis independence**, reconcile, pre_phd not gated |
| test_delta | 6 | re-scan delta + warm-cache ≈0 re-extraction + changed-page + recruiting-change-is-review |
| test_dashboard_atlas | 5 | Atlas tokens/type, self-contained fonts, diagram engine, reduced-motion, cell drawer |
| test_cli_live | 3 | fail-loud, needs country+field, full live run via patched transport |

The refine loop (§5) also hardened offline-engine test files: **test_deadline_parse** (28 — payment/
event/domain-modifier/subject-tie cases), **test_ethics** (12 — bare-email/list/mailto, gitignore
under any `--out`, corpus-never-read, LLM-free), **test_discovery** (7 — the JS/noscript wall cases),
**test_dashboard** (10 — script-injection escape). The **previously-green offline suite stays green** —
no regressions.

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

**§5-final (independent re-confirmation):** _pending — the re-run multi-agent audit is completing; its
verdict (must be zero open findings to close this box) is recorded here._

## 6 — Clean-room verification (goal §4 step 6) — PASSED

From tip `ad96e52`: wiped every generated/transient artifact (`.venv`, `src/supervisorly.egg-info`,
`__pycache__`, `.pytest_cache`, and any `output/`/`.cache`/`snaps`/`*.sqlite`). **`git status` and
`git clean -ndx` were both empty** — only committed code, docs, and synthetic/public fixtures survived;
**no personal data, no real-page snapshots, no scan output.** From that clean state ran the documented
install (`python -m venv .venv` → `pip install -e ".[dev]"`) and re-ran the offline cassette self-test:
**`202 passed in ~22s` on the first try.** Post-install `git status` clean (`.venv` + egg-info
gitignored). The dirty-run and clean-run counts match (202 = 202) — no hidden dependency.

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
| The §5 adversarial self-audit returns **no open findings** | ⏳ **pending** the re-run audit's verdict (in-loop probe clean; passes 1–2 + L9i fixed and regression-tested) |
| Ethics gates test-verified (opt-out build/re-export/mid-scan, robots, no-bare-email, no-bulk, corpus-never-read, no-login-defeated, LLM-free) | ✅ test_ethics + test_optout |
| All tests pass; previously-green offline suite stays green | ✅ 202 passed |
| Docs updated (README live/creds/command/scheduling, BUILD_LOG, getting-started live section, DECISIONS) | ✅ |
| **Clean-room verification passes on the first try** | ✅ §6 (202 passed) |
| `git status` shows no scan output / no personal data; `.gitignore` honoured | ✅ §6 |
| Live smoke test **passed-or-skipped** (never fabricated) | ✅ **skipped** — no real contact email in this environment (§8) |
| Final `LIVE_COMPLETION_REPORT.md` | ✅ this file |

**One box (§5 re-confirmation) is intentionally left open until the independent audit re-run returns
zero — per goal §7, a session-limit-aborted audit is not a pass. Completion is declared only when it
is checked.**

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
- **Fonts are named with a faithful system fallback**, not embedded, to keep the dashboard a single
  self-contained offline file with no external request (D-033).

## 9 — How to run

```bash
supervisorly scan --demo --out output/dashboard.html                 # offline, no keys
supervisorly scan --country Canada --field "causal ML" \             # live
  --intent pre_phd --email you@example.com --out output/live.html
```
