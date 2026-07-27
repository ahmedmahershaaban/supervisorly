# GOAL 3 — Browser-primary live scan + subject-map stage + Scan Studio UI

> **How to use this:** paste everything below the line into an agent's `/goal` (or a fresh
> session in this repo). It is a standing directive to the implementing agent. It builds on
> the **completed, green** engine (Goal 1) and live scan (Goal 2) — reused, never rewritten.
> *(Counts as-written for Goal 3, 2026-07-25, left unedited. The binding set is now
> D-001…D-070 — the web round added D-068…D-070.)*
>
> `docs/DECISIONS.md` (D-001…D-067) is binding; the newest four (D-064…D-067) are the ones
> this goal implements.

---

You are building **Supervisorly's browser-primary tier and its front door**: the agent drives
Chrome (chrome-devtools-mcp) as the primary page fetch for live scans — the user does nothing
after a one-time login — while the deterministic engine stays LLM-free and every fact remains a
quote-verified Claim. Around it: an anti-ban social pacing policy for X/LinkedIn/Scholar, an
API-derived **subject-map stage** with user multi-select before any scan, direct
named-professor targets, and a **Scan Studio** plan wizard in the binding Atlas design language.

**What already exists and MUST be reused:** the whole deterministic engine (`fetch/` robots +
snapshots + cache, `model/` claims + quote-gate, `score/`, `export/`, `ethics/`), the live
driver (`pipeline.run_live`), the CLI, the country-name resolution (`discover/countries.py`),
the OpenAlex client (`discover/openalex.py` — `topics_url` exists), the human-rung ingest
(`ingest.py` + `extract/md_grammar.py`), and the Atlas dashboard (`export/dashboard.py`).
253 tests are green — they stay green.

## ⚑ Persistence — this goal DOES NOT STOP until it is DONE

Same contract as Goals 1–2: never end a turn with an unmet DoD item and no work in flight;
resume from `docs/BUILD_LOG.md` + `git log` + the suite if interrupted; a red suite, an open
audit finding, or an unchecked box is **not done**; the only legitimate stops are (a) every DoD
box checked → write `docs/BROWSER_COMPLETION_REPORT.md` and declare complete, or (b) a genuine
blocker only Ahmed can resolve → record it in `docs/BLOCKERS.md` and stop there.

## 1 — Non-negotiable governing constraints (violating any = a defect)

- **D-064 — browser-primary, agent-driven, seam-guarded.** Chrome is launched and driven by
  the agent via chrome-devtools-mcp. The Python layer stays **LLM-free** (D-009): browser
  content enters ONLY through `supervisorly ingest-page` — cleaned, capped main text stored as
  a normal content-addressed snapshot; the existing extractors and the D-010 quote gate run
  unchanged. **Raw HTML/DOM never enters the agent's context** — the agent handles file paths,
  byte counts, one-line results only. APIs (ROR/OpenAlex) stay on httpx; the warm cache may
  skip the browser. Host-portable: the same recipe works under Kimi Code, Claude Code, any
  MCP host.
- **D-065 — social pacing is code.** X/LinkedIn/Scholar via the user's own session:
  per-target, read-only, jittered intervals, per-session page caps, human-like in-page
  scrolling, **abort-on-challenge** (captcha/soft-block → host latched aborted, field
  `blocked`, human rung). Scholar: profile pages only. Only the professor's **advertised**
  profile URL is ever visited — never people-search enumeration.
- **D-066 — subject-map stage.** Free-text field → OpenAlex topics API → hierarchical map →
  user multi-select → selected IDs become `resolved_topic_ids`. API-derived only (D-038);
  nothing expensive runs before confirmation.
- **D-067 — Scan Studio.** One self-contained offline HTML wizard (D-033/D-048 rules) in the
  Atlas "Living" language; consumes a subject-map JSON, exports a plan JSON (download).
  Conversational numbered multi-select remains the fallback.
- All earlier constraints still bind: D-005 (never commit output/session data — staging dir,
  pacing state, and any browser profile path must be gitignored), D-010, D-035 (corpus never
  read), D-038, D-043/044/052 (logins never defeated; the user logs in once, themselves),
  D-046 (four-state honesty).

## 2 — Build plan

**B1 — Browser ingest seam.** `extract/page_extract.js` (in-page main-text extractor +
human-like scroll mode, capped output `{title, finalUrl, text}`);
`fetch/browser_rung.py` (`ingest_page` → snapshot + web source tier `agent_browser` under the
FINAL url); CLI `ingest-page`. *DoD:* synthetic extracted text becomes a snapshot whose claims
pass the D-010 quote gate; wrong-text quotes reject; final-url provenance; oversized text
capped; suite green.

**B2 — Pacing policy.** `ethics/pacing.py` (policy table + persistent state JSON + `check(host)
→ {allowed, wait_seconds, reason}`) + CLI `pace`. *DoD:* interval/jitter/cap/abort-latch/reset
all test-covered; corrupt state fails closed.

**B3 — Subject map + new scan inputs.** `discover/subjects.py` (`subject_map` grouped by
OpenAlex domain/field/subfield, capped, truncation-marked); CLI `map-field`; `scan --plan
plan.json` (selected topic IDs + scope) and `scan --targets profs.json` (named professors via
OpenAlex author search). *DoD:* cassette tests for grouping, honest empties, truncation,
plan-driven scan, named-professor resolution + unresolved-skip.

**B4 — Scan Studio.** `export/studio.py` + CLI `studio`: self-contained Atlas-language wizard —
intent picker, country, universities+mode, **checkbox subject tree** (tri-state groups), named
professors, email; "Export plan" downloads `plan.json`. *DoD:* self-containment (no external
requests), injection-safe (hostile topic names), checkbox→plan-JSON correctness,
reduced-motion, keyboard.

**B5 — Orchestration + docs.** SKILL.md: Stage 0 = intent → `map-field` → multi-select confirm;
live flow = browser-primary recipe (navigate → `evaluate_script(page_extract.js)` → staging
file → `ingest-page` — never read the file); `pace` before every page; walled-social gap tasks
execute via the logged-in profile under D-065; abort-on-challenge → human rung. Document the
identical MCP config for Claude Code. Update README + `docs/getting-started.html`.

**B6 — Eval + adversarial audit + clean-room.** §5-style multi-agent audit of the new surface
(injection, pacing bypass, provenance, context-leak paths, D-005 coverage), fixes with
regression tests, clean-room fresh-install re-run, `docs/BROWSER_COMPLETION_REPORT.md`.

## 3 — Definition of Done

- [ ] Every phase B1–B6 meets its DoD; suite green (253 + new tests).
- [ ] `ingest-page` stores browser text as a snapshot; claims pass D-010; final-url provenance.
- [ ] `pace` enforces D-065 (intervals, caps, abort-latch) with tests.
- [ ] `map-field` produces a hierarchical API-derived subject map; `--plan` drives a scan.
- [ ] `--targets` resolves named professors; unresolved are honest skips.
- [ ] Scan Studio is self-contained/offline, injection-safe, Atlas-faithful, exports a valid plan.
- [ ] SKILL.md documents the browser-primary, paced, host-portable flow.
- [ ] `.gitignore` covers staging/pacing/profile paths; `git status` shows no personal data.
- [ ] Adversarial audit: zero open findings. Clean-room fresh install: suite passes first try.
- [ ] Live Chrome smoke test (in an MCP-enabled session): passed with evidence or explicitly
      skipped with the reason — never fabricated.
- [ ] `docs/BROWSER_COMPLETION_REPORT.md` written; per-phase commits on `build/browser`.

## 4 — Guardrails

- Never fabricate a test/scan/browser result; mark what can't run **skipped** with the reason.
- Never weaken a test to go green; never defeat a login; never bulk-scrape social.
- No live network in the test suite — cassettes and synthetic text only.
- Small, reversible, per-phase commits; each leaves the suite green.
