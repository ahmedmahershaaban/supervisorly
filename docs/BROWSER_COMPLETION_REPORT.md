# Supervisorly — Goal 3 Completion Report (browser-primary tier + subject map + Scan Studio)

> Status: **COMPLETE** — all phases B0–B6 green, adversarial audit closed with zero open
> findings, clean-room verified. Branch: `build/browser` (off `build/live`, which closed Goal 2).
> Commit range: **`72bcb48` (B0) … this report's commit**.

Goal 3 makes the browser (chrome-devtools-mcp, agent-driven) the **primary page fetch** for live
scans — the user does nothing after a one-time login — while the deterministic engine stays
LLM-free and every fact remains a quote-verified Claim. Around it: the anti-ban social pacing
policy (D-065), the API-derived subject-map stage with user multi-select (D-066), direct
named-professor targets, and the Scan Studio plan wizard in the Atlas design language (D-067).

---

## 1 — What was built (phase by phase)

- **B0 — decisions & contract.** D-064 (browser-primary, agent-driven, seam-guarded; raw
  HTML/DOM never enters agent context), D-065 (social pacing is code), D-066 (subject-map
  stage), D-067 (Scan Studio) appended to `DECISIONS.md`; `BROWSER_IMPLEMENTATION_GOAL.md`;
  GOALS.md row.
- **B1 — browser ingest seam.** `extract/page_extract.js` (in-page main-text extractor mirroring
  `normalize.main_text`, 60 KiB byte cap, async human-like scroll mode);
  `fetch/browser_rung.py` (`ingest_page` → content-addressed snapshot byte-compatible with
  fetcher snapshots, web source tier `agent_browser` under the final URL); CLI `ingest-page`;
  schema v2 migration adds the tier.
- **B2 — pacing policy.** `ethics/pacing.py`: social (x/twitter/linkedin incl. subdomains)
  45–120 s jitter + 15 pages/session; scholar.google.* 60–180 s + 5/session; abort latch;
  corrupt state fails closed. CLI `pace` (exit 0 ALLOW / 3 DENY). `.gitignore` covers pacing
  state + browser staging (D-005).
- **B3 — subject map + scan inputs.** `discover/subjects.py` (OpenAlex topics →
  domain/field/subfield hierarchy, works-count sorted, D-037 truncation honesty); CLI
  `map-field`; `scan --plan` (validated plan, country names resolve, flags override plan);
  `scan --targets` (named professors via `author_search` with affiliation preference, or
  OpenAlex URLs; unresolved reported, never silently dropped; targets-only runs skip the
  ladder; union with `--country` dedupes by OpenAlex id).
- **B4 — Scan Studio.** `export/studio.py`: one self-contained offline HTML wizard (Atlas
  tokens/type, no external requests, `_inline_json`/`esc()` discipline, reduced-motion,
  keyboard) — intent picker, country, universities+mode, tri-state checkbox subject tree,
  named professors, email; validated plan export via Blob download + next command. CLI
  `studio`; `scan --plan` honors plan-carried email/targets.
- **B5 — orchestration.** SKILL.md: Stage 0 = intent → `map-field` → multi-select confirm;
  the browser-primary recipe (pace → navigate via MCP → in-page extract → staging file never
  read into context → `ingest-page`); the social rung via the logged-in profile under pacing;
  host-portable MCP config (Kimi/Claude). README + getting-started updated.
- **B6 — eval + adversarial audit + clean-room.** Below (§2–§4).

## 2 — Adversarial audit (goal §B6)

Five independent finder agents (ingest seam, pacing, subject-map/plan/targets, Scan Studio,
docs truthfulness), every finding reproduced in code with self-rebuttal: **23 confirmed
(4 HIGH, 11 MEDIUM, 8 LOW)**, all fixed with regression tests across four green waves
(319 → 342 → 353 → 363 → **377**).

- **HIGH — v1→v2 migration crashed on claim-bearing DBs** (`legacy_alter_table` does not stop
  FK rewrites; no `foreign_keys=OFF`; non-atomic) then silently orphaned all web_source
  provenance on retry. Fixed per SQLite's documented rebuild procedure + leftover-`web_source_old`
  recovery; a claim-bearing v1 DB is now the pinned regression.
- **HIGH — pacing bypass via un-normalized hosts** (`x.com:443`, `x.com.`, URL forms,
  `linkedin.com.cn` skipped pacing entirely; abort latches invisible to them). `classify()`
  now canonicalizes scheme/userinfo/path/port/trailing-dot; hostile lookalikes stay unpaced.
- **HIGH — `--targets` truncation markers died on a throwaway client** (a failed author lookup
  vanished a named professor while coverage claimed "none were dropped"). Markers now flow
  into the run and persist across reexport; failure vs absence distinguished.
- **HIGH — the consumer half of the D-064 seam did not exist** (docs-truthfulness audit):
  ingested browser snapshots were stored and never read; the documented "engine takes it from
  there" was inert. Built `fetch/browser_fill.py`: the pipeline's own extractors run over the
  browser snapshot, claims record through the same D-010 evidence path, `awaiting_human`
  gap_fill tasks close, run status recomputes — the walled-social gap now closes via the
  browser tier exactly as documented. CLI `ingest-page --entity --run` + a new `reexport`
  command.
- **MEDIUM (11):** jittered wait re-rolled per check (now pinned `next_allowed_epoch` — printed
  waits are binding); lost-update race erasing the abort latch (atomic save + merge-on-abort);
  CWD-relative pacing state (anchored at `~/.supervisorly/`); `identity resolution` never
  reaching export/dashboard (now `verified/unverified/unchecked` everywhere, badge in the
  dashboard); plan values validated for presence only (mangled types → char-lists/tracebacks;
  now fail loud by key+type); plan `university_mode` typo silently widening "only" to the
  whole country (now exit 2; `select_institutions` raises on unknown mode); Studio smooth
  scroll ignoring reduced-motion; invisible focus ring on intent cards; ingest-page defaults
  writing to a different DB than `scan`; the Studio→`scan --plan` docs skipping the
  move-from-Downloads step.
- **LOW (8):** BOM-only staging files; non-UTF-8 staging tracebacks; semantically-broken pacing
  state entries; non-string targets entries; opt-out misreported as "coverage gap"; malformed
  map entries bricking the Studio; hostile `defaults.intent_kind`; `parseProfs` first-comma
  split; id-less topics entering `resolved_topic_ids`; stale "140 passed" in the guide.
  All fixed; all finder probes re-run clean after the fixes.

## 3 — Test inventory

`python -m pytest` → **377 passed** (Goal 2's 253 + 124). New files: `test_browser_rung.py`
(17), `test_pacing.py` (16), `test_subjects.py` (9), `test_scan_plan.py` (10+), `test_studio.py`
(27), `test_browser_fill.py` (14 — incl. the end-to-end walled-gap-close regression), plus
audit regressions across `test_run_live.py`, `test_state_machine.py`, `test_discovery.py`
et al. The previously-green suite (Goals 1–2) stayed green throughout — no regressions.

## 4 — Clean-room verification — PASSED

From tip `96f4e7e`: wiped `.venv`, egg-info, `__pycache__`, `.pytest_cache`, `output/`,
`.cache/`, `snaps/`, `browser_staging/`, `*.sqlite`, and the audit `scratchpad/`. `git status`
and `git clean -ndx` both empty — only committed code, docs, and synthetic fixtures; **no
personal data, no browser profile data, no scan output**. Fresh documented install
(`python -m venv .venv` → `pip install -e ".[dev]"`) → **377 passed on the first try**.
Post-install tree clean. Dirty-run and clean-run counts match (377 = 377).

## 5 — Definition of Done

| DoD item | Status |
|---|---|
| Every phase B1–B6 meets its DoD; suite green | ✅ 377 passed |
| `ingest-page` stores browser text as a snapshot; claims pass D-010; final-url provenance | ✅ test_browser_rung |
| `pace` enforces D-065 (intervals, caps, abort-latch) with tests | ✅ test_pacing |
| `map-field` hierarchical API-derived map; `--plan` drives a scan | ✅ test_subjects + test_scan_plan |
| `--targets` resolves named professors; unresolved are honest skips | ✅ test_scan_plan |
| Scan Studio self-contained/offline, injection-safe, Atlas-faithful, valid plan export | ✅ test_studio |
| SKILL.md documents the browser-primary, paced, host-portable flow | ✅ + docs-truthfulness audit pass |
| `.gitignore` covers staging/pacing; `git status` shows no personal data | ✅ §4 |
| Adversarial audit: zero open findings | ✅ §2 (23 confirmed, all fixed) |
| Clean-room: suite passes first try | ✅ §4 |
| Live Chrome smoke test (MCP-enabled session) | ⏸ **skipped** — MCP servers load at session start; this build session has no `mcp__chrome-devtools__*` tools. To run in a fresh session: `supervisorly pace --host example.com`, navigate, `evaluate_script(page_extract.js)`, `ingest-page` — see SKILL.md "Browser-primary live fetch". |
| `docs/BROWSER_COMPLETION_REPORT.md`; per-phase commits | ✅ this file; `72bcb48`… |

## 6 — Known limitations (honest)

- **The live browser path is cassette/code-tested, not yet smoke-tested against real Chrome**
  (previous row). The deterministic seam is fully covered; the MCP mechanics are exercised
  only via the server's own smoke test (initialize handshake passed during install).
- **`reexport` rebuilds targets from persisted claims, so its dashboard names professors by
  id** — the full named view comes from `scan --resume` (documented in the command's docstring).
- **Pacing merge is field-level, not locked**: two simultaneous same-host `check` calls can
  under-count by one page (documented in `pacing.py`; single-user CLI, conservative direction
  anyway — waits are never shortened).
- **One-time login is unavoidable**: the agent-launched profile starts logged out; the user
  logs into walled sites once (or attaches their everyday Chrome per the SKILL's fallback).
- **Social rung stays per-target and read-only** (D-065): no bulk, no people-search
  enumeration, Scholar profile pages only — by design, not by gap.

## 7 — How to run

```bash
supervisorly map-field --field "causal ML" --email you@example.com   # subject map (D-066)
supervisorly studio --map output/subject_map.json                    # Scan Studio (D-067)
supervisorly scan --plan supervisorly_plan.json --out output/live.html
supervisorly scan --targets profs.json --out output/profs.html       # named professors
supervisorly pace --host x.com                                       # pacing gate (D-065)
supervisorly ingest-page --url <final> --file page.txt \
  --entity professor:openalex_A123 --run <run_id>                    # browser fill (D-064)
supervisorly reexport --db output/supervisorly.sqlite --out output/live.html
```
