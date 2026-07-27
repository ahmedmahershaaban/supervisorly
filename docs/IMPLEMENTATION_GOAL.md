# GOAL — Implement, self-test, and ship Supervisorly v1

> **How to use this:** paste everything below the line into Claude Code's `/goal` (or a fresh
> session in this repo). It is written as a standing directive to the implementing agent. It is
> autonomous: it builds, runs itself, judges its own output, fixes what's wrong, and only
> reports the goal complete when a hard Definition of Done is met. Nothing here overrides the
> design — `docs/DECISIONS.md` (D-001…D-063) is binding.
>
> **Counts here are as-written (Goal 1, 2026-07-22) and are left unedited so this contract
> still records what it actually required.** The binding set has since grown to
> **D-001…D-070** and the model to **32 entities** — later goals are covered by
> `LIVE_IMPLEMENTATION_GOAL.md`, `BROWSER_IMPLEMENTATION_GOAL.md` and
> `FIREBASE_WEB_PLAN.md`. Where a count below disagrees with `DECISIONS.md` or
> `domain-model.md`, those files win.

---

You are building **Supervisorly v1** — a Claude-Code skill + agents + tools that helps a student
find a PhD / master's / postdoc supervisor in **any country**. The complete design already
exists in `docs/`. Your job is to implement it, prove it works by running it yourself, judge the
quality of what it produces, fix and enhance until it is genuinely excellent, and only then mark
this goal complete.

## 0 — Before you write any code

1. **Read the design, in this order, and treat it as the source of truth:**
   `docs/HANDOVER.md` → `docs/design-atlas.md` → `docs/product-flow.md` → `docs/architecture.md`
   → `docs/domain-model.md` (31 entities) → `docs/DECISIONS.md` (63 decisions — **binding**) →
   `docs/cost-and-performance.md` → `docs/ethics-and-compliance.md` →
   `docs/research/{data-sources,social-sources,prior-art}.md`.
2. **Never contradict a locked decision.** If you become convinced one is wrong or impossible,
   **stop and record it in `docs/BLOCKERS.md`** with evidence — do not silently deviate.
3. **Keep `docs/BUILD_LOG.md`** — one short entry per milestone: what you built, what you ran,
   what passed, what you changed. This is how progress is auditable.
4. Detect the stack from the docs (Python for the deterministic layer + tooling; the dashboard
   is a single self-contained HTML file with embedded JSX). Match the repo layout in
   `architecture.md §7`. Name the package `supervisorly` (D-012).

## 1 — Non-negotiable governing constraints (violating any = a defect, not a choice)

- **Generate, don't look up** (D-038): no embedded university list, no keyword dictionary. The
  agent derives search terms/venues/topic-IDs per search. An *enum of categories* is allowed
  structure; a *dictionary of a field's search terms* is forbidden.
- **The corpus is methodology-only** (D-035): never read, import, or ship any file from
  `C:\Users\ahmed\Documents\Downloads` as data, seed, or fixture — not even locally, not even for
  tests. Every real fact must be one the tool fetched itself, live, from a citable public source.
- **Deterministic collection, LLM interpretation** (D-009, D-021): the deterministic layer
  (`discover/ fetch/ model/ score/ export/`) contains **zero LLM calls**. Never send raw HTML to
  a model — boilerplate-stripped text with a hard byte cap only.
- **Every field is a Claim with provenance** (D-010, D-047): value + verbatim quote + source URL
  + content-hashed snapshot + timestamp + confidence + extractor. **A claim whose quote is not
  found in its snapshot is rejected** — this is enforced in code, not prose.
- **Honest emptiness** (D-022, D-037, D-046): the four states `value / searched_absent /
  never_attempted / blocked` are distinct and rendered distinctly. **A professor is never dropped
  for missing data.**
- **API-first, human rung for the walled** (D-039, D-043, D-044): the tool fetches public
  sources + open APIs and **never defeats a login or a bot-wall**. Walled sources (X/Twitter,
  LinkedIn, Scholar, login-walled directories) go to the Phase-3 human rung.
- **Ethics enforced in code** (D-005/019/023/024/032/053): `robots.txt` obeyed (fail closed);
  `optout.txt` filtered at build with a failing test; no nationality gate; no LLM-judgements or
  bare-email lists in any export; no bulk-outreach path.
- **Fail loud on missing credentials** (D-014/020, cost §2): ROR client ID and a free OpenAlex
  key are required; refuse to run silently on the throttled tiers.

## 2 — Build plan (phased; each phase has a Definition of Done you must meet before moving on)

**Phase A — Scaffold + schema.** Repo layout (arch §7), `pyproject`, CLI entry, SQLite DDL for
all 31 entities — start with `Claim`, `WebSource`, `Conflict`, `Run`, `Task`, `Checkpoint`,
`ExtractionCache`, `SearchPlan`. *DoD:* DB migrates; `Run`/`Task` state machine round-trips incl.
`awaiting_human_input` and `finalized_with_open_gaps` (D-049).

**Phase B — Contracts.** `SKILL.md` (orchestrator: intent → SearchPlan → tier/phase gating, with
the vocabulary crosswalk of D-055); the five agent definition files; the **one shared Phase-3
Markdown grammar** with a worked example (D-051 — do this early, it's the human↔pipeline seam);
the **four-state JSON export contract** with a worked example (D-046). *DoD:* a fixture MD parses
losslessly into Claims; the JSON schema validates against a hand-written example.

**Phase C — Deterministic collection.** The discovery ladder (CRIS → sitemap → JSON-LD → CT logs
→ OpenAlex/ROR → adapter, D-028); the fetcher with the **three-phase escalation** (D-039), robots
check, per-host rate-limit/backoff, disk cache, **content-hashed snapshots over normalised
content** (cost §3b-i — strip volatile chrome). *DoD:* runs offline against recorded cassettes;
the normalised hash is identical across two captures of a page with injected volatile chrome.

**Phase D — Extraction + provenance.** Deterministic parsers + the LLM agents
(`recruiting-analyst` with target-cycle normalisation D-050, `eligibility-analyst`,
`profile-synthesist`, `evidence-auditor`), each emitting Claims through **quote-verification**;
`NOT_FOUND` is a required output value. *DoD:* a planted hallucination (quote not in snapshot) is
rejected; `searched_absent` vs `never_attempted` are produced correctly.

**Phase E — Scoring.** Intent-aware hard gates (D-059), research-fit via **OpenAlex topic-ID
overlap** from `SearchPlan.resolved_topic_ids` (D-058), **works reconciliation before scoring**
for fragmented/non-Western profiles (D-057), confidence-of-score penalties. *DoD:* the
non-Western fragmentation fixture is reconciled and **not** wrongly dropped from the shortlist; a
`pre_phd` search is **not** gated on PhD-admission rules.

**Phase F — Export + dashboard.** Four-state JSON; the **single self-contained HTML + embedded
JSX** dashboard (D-033/D-048): pre-transpiled JSX, vendored React + virtualiser inline, no CDN,
offline, virtualised, retained editable JSX block, sibling JSON; the **deadline view** (D-061)
that shows projected/unpublished deadlines as *watch dates, never firm*. *DoD:* the file opens
offline with no console errors; the four states render distinctly; filters + deadline sort work.

**Phase G — Human rung.** `chrome-prompt-generator` (emits the D-051 grammar), `md-ingester`
(parses it back, resumes the run), plus **roster-enumeration** for login-walled directories
(D-052). *DoD:* an abandoned Phase 3 still yields a finalized dashboard; a later MD return fills
the gaps and re-exports without re-fetching.

**Phase H — Tests + eval set.** Unit tests per module; **synthetic fixtures**; the
**hand-labelled cassette eval set** — ≥3 directory shapes across ≥3 countries, per-field expected
extractions, per-model pass thresholds (D-063); a golden-path integration test. *DoD:* all green;
eval thresholds met; coverage recorded in the log.

**Phase I — Self-run + quality audit** (see §4). **Phase J — Refine loop** (see §5).

## 3 — Edge-case matrix (each row must have a passing test before Done)

| Edge case | Required behaviour |
|---|---|
| Country with sparse OpenAlex/ROR | preflight (D-060) warns up front; run continues; coverage report is honest |
| Faculty directory is login-walled | roster-enumeration task to the human rung; unit marked `LOGIN_WALL` (D-052) |
| Department page not found | search for it (Stage 1); if still absent, `CoverageRecord` records it distinctly |
| Non-Western name split/merged in OpenAlex | works reconciled before scoring; risk lowers score-confidence, not activity (D-057) |
| Interdisciplinary field ("causal NLP") | topic-ID overlap matches "NLP"+"causal inference" separately (D-058) |
| Zero professors match | short-circuit Stages 2–4; empty-state dashboard distinguishes "none matched" vs "sources returned nothing" (D-049) |
| Student never returns Phase-3 MD | dashboard generated after Phase 2; run = `finalized_with_open_gaps`, resumable (D-049) |
| Run interrupted mid-Stage-2, resumed later | resumes from `Task`/`Checkpoint` state; nothing re-fetched (D-029) |
| Monthly re-scan, nothing changed | ~zero LLM calls; normalised-hash cache hits (cost §3b-i) |
| Missing ROR client ID / OpenAlex key | fail loud with the exact fix; do not run on throttled tiers |
| Volatile page chrome (news feed, counter) | normalised hash stable across captures (tested property) |
| Blocked source (Scholar `Disallow`, X login) | skipped / routed to human rung; never scraped |
| Rate-limit 429 / 5xx | exponential backoff + jitter; polite; never retries harder |
| Non-English page | recruiting/eligibility extracted in the original language; translate only for display (D-044/050) |
| Projected/not-yet-published deadline | shown as a watch date, never a firm one (D-061) |
| Intent = postdoc vs pre_phd vs phd | intent-aware gate set applied (D-059) |
| Two great professors, same department | roll-up to programs: one application/fee (D-031) |
| A field/country the author never imagined | still produces a SearchPlan and runs (D-038 genericity) |

## 4 — Self-test protocol (you must actually RUN the app, not just compile it)

1. **Deterministic end-to-end run on cassettes** (offline, no network, no credentials): drive the
   CLI/skill for `country=Canada-fixture, field=..., intent=pre_phd` against the recorded cassette
   set. Produce the real JSON + dashboard.
2. **Inspect the output like a user would.** Open/parse the dashboard and assert, programmatically
   where possible: it renders with no console errors; **every displayed fact traces to a Claim
   whose quote is present in a snapshot** (zero hallucinations); the four empty-states render
   distinctly; no professor is missing; filters, sort, the deadline view, and clickable
   professor detail all work; projected deadlines show as watch-dates.
3. **Run the skill the way a student would** — via `SKILL.md` in Claude Code on the fixture —
   and confirm the orchestration (intent → confirm plan → tiers → phases → dashboard) behaves as
   `product-flow.md` describes.
4. **Optional credentialed live smoke test** (only if ROR/OpenAlex keys are available): one small,
   polite real department to confirm real-world behaviour, then **discard the output — never
   commit it** (D-005). If keys are absent, mark this step explicitly **skipped**, never passed.
5. **Budget checks:** assert the representative-scan cost/latency stay within
   `cost-and-performance.md` (five-cents-of-credit order of magnitude; warm re-scan ~0 LLM).
6. **Clean-room fresh-install verification (do this last, once everything else is green).**
   Development accumulates state — a database, disk caches, page snapshots, scan output,
   editable-install artifacts — and that state can silently make the tool "work on my machine."
   So, at the end: **tear all of it down and prove the tool works from a clean checkout.**
   - Delete every generated/transient artifact: `*.sqlite`, `.cache/`, snapshot store, `output/`,
     any `runs/`, `__pycache__`, `.egg-info`, the editable install. Confirm `git status` shows
     **only** committed code, docs, and *synthetic/clearly-public* fixtures — **no personal data,
     no real-page snapshots, no scan output** (D-005).
   - From that clean state, run the documented install steps fresh, then re-run the **offline
     cassette self-test (steps 1–3) end to end** and confirm it passes with nothing pre-warmed.
   - This is a *rebuild-and-verify from scratch*, **not** a rewrite: the code and tests are kept;
     only accumulated state is wiped. If the clean run fails where the dirty run passed, you had a
     hidden dependency on dev state — fix it, then repeat until the clean run passes on the first try.

## 5 — Refine & fix loop (do not skip; this is where "good" becomes "excellent")

After Phase I, run an **adversarial self-audit** across these dimensions and fix everything it
finds, adding a regression test for each fix, then re-run the whole suite:
- **Correctness & provenance** — any displayed fact without a verified quote? any `NOT_FOUND`
  rendered as a value? any hallucination the auditor can plant and get through?
- **Edge cases** — is every row of §3 actually exercised and passing?
- **Ethics** — optout test, robots test, no bare-email export, no bulk path, corpus never read.
- **Genericity** — does it break on a second/third country's directory shape?
- **Performance/cost** — cache actually skips unchanged pages? deterministic layer LLM-free?
- **UX quality** — is the dashboard genuinely usable, honest, and readable (dark theme, four
  states, deadline urgency, clickable detail)? Would a real applicant trust it?
Loop until the audit returns **zero open findings** and every gate in §6 is green. Log each pass.

## 6 — Definition of Done (mark the goal complete ONLY when EVERY item is true)

- [ ] Every phase (A–J) meets its DoD.
- [ ] All unit + integration + eval tests pass; eval thresholds met (≥3 shapes / ≥3 countries).
- [ ] **Every edge case in §3 has a passing test.**
- [ ] The self-run (§4) produces a correct, honest dashboard from cassettes with **zero
      hallucinated facts** and all four states rendering.
- [ ] The adversarial self-audit (§5) returns **no open findings**.
- [ ] Ethics gates verified by tests: optout, robots, no-bare-emails, no-bulk-path,
      corpus-never-read.
- [ ] Cost/latency within budget; warm re-scan issues ~0 LLM calls.
- [ ] Docs updated: `README.md` (honest install incl. required credentials, the two run modes,
      `--offline --demo`); `BUILD_LOG.md`; any implementation decisions appended to `DECISIONS.md`.
- [ ] **Clean-room verification passes:** all generated/transient state wiped, and a fresh
      install + offline self-test runs green from a clean checkout on the first try (§4 step 6).
- [ ] `git status` shows **no scan output / no personal data** staged; `.gitignore` honoured;
      only code, docs, and synthetic/clearly-public fixtures survive the teardown.
- [ ] A final **`docs/COMPLETION_REPORT.md`**: what was built, the full test/eval results with
      numbers, edge-case coverage, known limitations stated honestly, and exact steps to run it.

**Only when all boxes are checked, declare the goal complete** with a one-screen summary and a
link to `COMPLETION_REPORT.md`.

## 7 — Guardrails against false completion (read these twice)

- **"It compiles" ≠ done.** Done requires the self-run + eval + audit all green.
- **Never fabricate or predict a test result.** If a test cannot run (missing credential, network
  off), mark it **skipped** in the report with the reason — never as passed.
- **Never weaken or delete a test to make the suite green.** Fix the code.
- **Never invent data to fill a gap.** An honest "we looked, found nothing" is the correct output;
  a plausible guess is a defect.
- **If genuinely blocked** — an irreversible action, a real credential you can't obtain, or an
  ambiguity only Ahmed can resolve — **stop and write `docs/BLOCKERS.md`** with the specific ask,
  rather than guessing. For everything else, proceed with the best-recommended option and log it.
- **Work in small, reversible increments**, committed per §8. Every commit leaves the suite green.

## 8 — Version control discipline (every round is a tracked commit)

Every meaningful change lands as **its own commit with a real message**, so the whole build is a
readable, revertable history — never one giant unlabelled dump.

- **Work on a dedicated branch** (e.g. `build/v1`), never the default branch. Create it before
  Phase A.
- **Commit at every green checkpoint**, each leaving the test suite passing:
  - one per build phase (A–J) as it meets its DoD,
  - one per refine-loop round (§5),
  - one for the clean-room verification (§4 step 6) — **tag or clearly mark this
    `clean-verified` state**,
  - and **after the clean, every subsequent round of changes is its own commit** — never pile
    unrelated fixes into one.
- **Write real messages, not `wip`/`fix`:** a concise summary line (what changed), then a body
  saying *why* and *what you ran and the result* (e.g. `eval: 3/3 directory shapes green, 0
  hallucinations; edge-cases 18/18`). The log should read as the story of the build, so any round
  can be found and reverted by its message.
- **No broken commits.** If a change would leave tests red, finish it or split it so each commit
  is green. Never commit to "save progress" in a failing state — the branch + small steps are how
  you checkpoint.
- **Never commit generated state or personal data** — DB, caches, snapshots, scan output (D-005).
  The `.gitignore` plus the clean-room teardown enforce this; a commit that stages any of it is a
  defect to fix, not to push.
- The final `COMPLETION_REPORT.md` cites the **commit range** of the build so every change is
  auditable end to end.

*(The harness adds its own author/session trailer to each commit — you supply the summary +
body.)*

---

Your goal is not "code that runs." It is **a tool that produces honest, evidence-backed,
genuinely useful supervisor shortlists across arbitrary countries — and proves it does, to
itself, before claiming to be done.** Build it, run it, judge it, fix it, finish it — and leave a
clean, per-round commit history that tells the whole story.
