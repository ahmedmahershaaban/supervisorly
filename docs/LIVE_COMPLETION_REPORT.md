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
  *"what changed"* delta (new professors, newly-open recruiting, newly-published deadlines).
- **L7 — Atlas front-end** (`export/dashboard.py`): the results dashboard + a how-it-works diagram in
  the "Supervisorly Atlas — Living" language (bioluminescent tokens, Space Grotesk/Mono, the glowing
  **cells + curved animated filaments** engine, cell-drawer detail) — ONE self-contained offline
  file, reduced-motion-aware, injection/scheme-safe (D-033/D-048).
- **L8 — CLI + SKILL**: `scan --country --field --intent --universities --university-mode --email
  --openalex-key --optout --resume`; SKILL.md documents the intent → plan → Stage-1 → Stage-2 → rank
  → dashboard flow; README has the live command + a Task-Scheduler/cron recipe.

## 2 — Test inventory (live additions)

`python -m pytest` → **183 passed** (exit 0). New live tests (41):

| File | Tests | Covers |
|---|---|---|
| test_discover_clients | 6 | ROR/OpenAlex mapping, error→[], premium key, honest empties |
| test_discover_ladder | 5 | enumerate + dedupe/reconcile, topic resolution, all/prioritise/only |
| test_run_live | 5 | discover → export, honest states, zero hallucinations, fail-loud, opt-out |
| test_collectors | 6 | students/industry/social extractors + honest searched_absent |
| test_ranking | 6 | professor + university ranking, re-weightable, reconcile, pre_phd not gated |
| test_delta | 5 | re-scan delta + warm-cache ≈0 re-extraction + changed-page |
| test_dashboard_atlas | 5 | Atlas tokens/type, self-contained fonts, diagram engine, reduced-motion, cell drawer |
| test_cli_live | 3 | fail-loud, needs country+field, full live run via patched transport |

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

_(pending — the live-additions audit is running; findings + fixes recorded here)_

## 6 — Clean-room verification (goal §4 step 6)

_(pending — wipe all generated state, fresh install, re-run the offline cassette self-test green)_

## 7 — Definition of Done

_(pending — checked off last)_

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
