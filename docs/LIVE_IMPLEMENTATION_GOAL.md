# GOAL — Implement, self-test, and ship Supervisorly's LIVE scan (end-to-end, real sources)

> **How to use this:** paste everything below the line into Claude Code's `/goal` (or a fresh
> session in this repo). It is a standing directive to the implementing agent. It is autonomous:
> it builds, runs itself on recorded cassettes, judges its own output, fixes what's wrong, and
> only reports complete when a hard Definition of Done is met. Nothing here overrides the design —
> *(Counts as-written for Goal 2, 2026-07-24, left unedited. The binding set is now
> D-001…D-070 and the model 32 entities; `DECISIONS.md` and `domain-model.md` win.)*
>
> `docs/DECISIONS.md` (D-001…D-063) is binding, and the **already-built, tested offline engine is
> reused, not rewritten**.

---

You are completing **Supervisorly's live scan** — the real path that turns *a country + a field +
an intent* into an evidence-backed, filterable dashboard of **real** professors, plus the extra
signals the author asked for (the students who joined each lab, the companies each professor has
worked with, and each professor's recruiting status incl. social pages via the human rung), with
university- and professor-level ranking and optional scheduled re-runs.

**What already exists and MUST be reused (do not rewrite it):** the deterministic engine is built
and green (run `python -m pytest` — it passes). That includes `fetch/` (robots-fail-closed fetcher,
cassette + httpx transport behind one seam, content-addressed snapshots, per-host rate-limit +
backoff, normalised-content cache hash), `extract/` (the Phase-3 human-rung grammar + chrome-prompt
generator), `model/` (SQLite source of truth, Claim/WebSource provenance spine with the
quote-in-snapshot anti-hallucination control, Run/Task/Checkpoint state machine + resume, per-entity
ExtractionCache, opt-out), `score/` (intent gates, topic-ID overlap, works reconciliation, program
roll-up), `export/` (four-state JSON + self-contained dashboard with the deadline watch-date view),
`ethics/` (opt-out at build), `preflight.py` (credential fail-loud + coverage warning), `ingest.py`
(md-ingester), and `pipeline.run_offline` / `pipeline.reexport`. **Your job is the front door and
the extra collectors, wired into that engine — everything remains cassette-testable offline.**

## ⚑ Persistence — this goal DOES NOT STOP until it is DONE

This is a long-running, autonomous build. **Do not stop, pause, or hand back until every box in the
Definition of Done (§6) is checked and the live self-run + adversarial audit + clean-room are all
green.** Concretely:

- After each round, **commit (§8) and immediately continue to the next unmet DoD item** — never end
  a turn with the goal incomplete and no work in flight.
- If your context is reset or summarized mid-build, **resume from `docs/BUILD_LOG.md` + `git log` +
  re-running the suite** — re-enter this goal and keep going; do not restart from scratch and do not
  re-declare earlier phases "to do."
- Treat a red suite, an open audit finding, or an unchecked DoD box as **not done** — keep fixing and
  re-running until green. "It compiles" / "most of it works" is NOT done (§7).
- The ONLY legitimate stops are: (a) **every** DoD box checked → write `docs/LIVE_COMPLETION_REPORT.md`
  and declare complete; or (b) a genuine blocker only Ahmed can resolve → record it in
  `docs/BLOCKERS.md` with the specific ask and stop **there**, not elsewhere.

Report progress as you go, but keep working straight through to completion.

## 0 — Before you write any code

1. **Read, in this order, and treat as the source of truth:** `docs/HANDOVER.md` →
   `docs/architecture.md` (esp. §7 layout and the discovery ladder) → `docs/product-flow.md` →
   `docs/domain-model.md` (31 entities — Person/Institution/Unit/Student/Organisation/Collaboration/
   SocialProfile/etc.) → `docs/DECISIONS.md` (D-001…D-063 — **binding**) →
   `docs/research/{data-sources,social-sources,prior-art}.md` → `docs/cost-and-performance.md` →
   `docs/ethics-and-compliance.md` → `docs/COMPLETION_REPORT.md` (what's built) → the source under
   `src/supervisorly/` and the tests under `tests/`.
   **Also read, as the BINDING front-end + diagram spec:** `design_handoff_supervisorly_atlas/README.md`
   (the hifi "Supervisorly Atlas — Living" design language — tokens, layout shell, and the
   cells-and-filaments diagram engine) and `design_handoff_supervisorly_atlas/Supervisorly Atlas -
   Living.dc.html` (the reference prototype + the diagram/decision data + final copy). **Reimplement**
   that design in this codebase's conventions; **never ship** the `.dc.html`/`support.js` runtime.
2. **Never contradict a locked decision.** If you become convinced one is wrong or impossible,
   **stop and record it in `docs/BLOCKERS.md`** with evidence — do not silently deviate.
3. **Keep `docs/BUILD_LOG.md`** — one short entry per round: what you built, what you ran, what
   passed, what you changed. **One tracked commit per round** with a real message (§8).
4. **Reuse the engine.** Every new module goes behind the existing seams (the `Transport`
   protocol, `Claim` recorder, `Run/Task` state machine, `SearchPlan`, the four-state export). If
   you feel the urge to rewrite `pipeline`/`fetch`/`export`, stop — extend instead.

## 1 — Non-negotiable governing constraints (violating any = a defect, not a choice)

- **Generate, don't look up (D-038).** No embedded university list, no per-field keyword
  dictionary. Institutions, venues, topic-IDs, and directory URLs are **derived per query** from
  the `SearchPlan` via ROR/OpenAlex + the discovery ladder — never hardcoded. An enum of source
  *types* is allowed structure; a dictionary of a field's search *terms* is forbidden.
- **The corpus is methodology-only (D-035).** Never read, import, or ship any file from
  `C:\Users\ahmed\Documents\Downloads` as data, seed, or fixture — not even for a test.
- **Deterministic collection, LLM interpretation (D-009/D-021).** The `discover/`, `fetch/`,
  `model/`, `score/`, `export/` layers contain **zero LLM calls**; they gather + verify. Nuanced
  judgement (is this the same person? is this "recruiting"? is this student really an alum?) is the
  LLM analysts' Stage-2 job, expressed as `.claude/agents/*.md` contracts, orchestrated by the
  SKILL — not the Python CLI.
- **Every field is a verified Claim (D-010/D-047).** value + verbatim quote + source URL +
  content-hashed snapshot + timestamp + confidence + extractor. **A value claim whose quote is not
  in its snapshot is rejected in code** — this already exists; every new collector routes through it.
- **Honest emptiness (D-022/037/046).** The four states `value / searched_absent / never_attempted
  / blocked` stay distinct and are rendered distinctly. **A professor — or a student, or a company
  link — is never dropped for missing data;** you record an honest empty, never a guess.
- **API-first, public sources, human rung for the walled (D-039/043/044/052).** Fetch open APIs
  (ROR, OpenAlex, Crossref, etc.) and public pages; obey `robots.txt` (fail closed); **never defeat
  a login or a bot-wall.** Walled sources — X/Twitter, LinkedIn, Scholar, login-only directories —
  go to the existing Phase-3 human rung (generate the prompt; ingest the pasted Markdown).
- **Be a good API citizen; fail loud without a contact email (D-014/019/023).** The open services
  are **free and keyless** — ROR's API is open, OpenAlex is free. The one hard requirement is a
  **contact email** (`SUPERVISORLY_CONTACT_EMAIL`): OpenAlex's polite-pool `mailto` marker and the
  `User-Agent` we identify with. A live scan calls `preflight.require_credentials` first and refuses
  to run without a valid email rather than hammering public APIs anonymously; an OpenAlex **premium**
  key (`SUPERVISORLY_OPENALEX_KEY`) is supported but optional. `preflight.coverage_preflight` warns
  up front for thin countries/fields but never blocks (D-060). **Do not invent a ROR "key" — there
  isn't one.**
- **Recruiting normalised to the target cycle (D-050); topic-ID overlap for fit (D-058); reconcile
  fragmented (non-Western) author profiles before scoring (D-057); intent-aware gates (D-059);
  program roll-up (D-031); deadlines as watch-dates unless published (D-061).** These already exist
  in `score/` and `export/` — feed them real data, don't reimplement them.
- **Ethics in code (D-005/019/023/024/032/053).** Opt-out enforced at build *and* on re-export;
  `robots` fail-closed; no bare-email / email-list / mailto in exports; no bulk-outreach path; no
  LLM-judgements exported; **never commit scan output, snapshots, DB, or any personal data.**
- **Front-end & diagrams follow the Atlas design language (binding).** Every UI and every diagram
  the tool ships uses the hifi **"Supervisorly Atlas — Living"** language in
  `design_handoff_supervisorly_atlas/` (Phase L7): the bioluminescent token system, Space Grotesk +
  Space Mono type, the sidebar/drawer/lightbox shell, and the **glowing cells + curved animated
  filament** diagram engine. **BUT the shipped dashboard stays a single self-contained, offline file
  (D-033/D-048):** self-host/inline the fonts (no Google-Fonts URL, no CDN, no external request),
  everything CSS/SVG/inline-JS, `prefers-reduced-motion` honoured, injection/scheme-safe. Recreate
  the look faithfully; never ship the `.dc.html`/`support.js` runtime.

## 2 — Build plan (phased; each phase has a Definition of Done you must meet before moving on)

> Everything below is built **behind the existing `Transport` seam** and tested on **recorded
> cassettes** — no live network in the test suite. Real keys are needed only for the optional
> credentialed smoke test (§4 step 4).

**Phase L0 — Credentialed open-API clients (ROR + OpenAlex), cassette-tested.**
Add `discover/ror.py` and `discover/openalex.py` — thin clients that take the injected `Transport`
(so tests use cassettes), send the **contact email** as OpenAlex's `mailto` + in the `User-Agent`
(ROR needs no auth), page results, and map raw JSON into the domain entities (Institution,
Person/author, Topic, Work). Wire `preflight.require_credentials` + `coverage_preflight` into the
live entry path. *DoD:* both clients round-trip recorded cassettes into typed results; a **missing
contact email fails loud** with the exact fix (and the run works with just that email — no ROR key,
optional OpenAlex premium key); a sparse-country preflight warns and continues; **no live network
in tests.**

**Phase L1 — Discovery ladder (D-028): country/field → professor targets, two rounds.**
Build `discover/ladder.py` that, from a confirmed `SearchPlan`, generates targets **without any
hardcoded list (D-038)**:
- **Round 1 — enumerate (Stage-1):** country → institutions (ROR, honouring `university_mode` =
  all/prioritise/only, D-045); institution → candidate faculty/directory URLs via the ladder
  rungs (CRIS → sitemap.xml → JSON-LD → OpenAlex authors-by-institution → the existing `roster`
  triage for login-walls). Produce a **de-duplicated list of professor targets, each with links**,
  reconciling fragmented author identities before they become targets (D-057). Login-walled
  directories become a `roster_enumerate` human-rung task (D-052), never scraped.
- **Round 2 — deep-dive (Stage-2):** each target's own pages (homepage, group page, publications)
  are fetched through the **existing** `Fetcher`, ready for extraction.
Persist everything as `Task`s so the run is resumable (D-029) and cheap on re-scan (warm cache).
*DoD:* on a recorded multi-institution cassette set, Round 1 yields the expected professor targets
(nobody duplicated, nobody dropped); a login-walled directory routes to the human rung; a thin
country still produces an honest, smaller target set with a coverage note.

**Phase L2 — The live driver `pipeline.run_live`, wiring the existing pipeline.**
Add `run_live(plan, transport, snap_root, *, db_path, optout_path, resume)` that: preflights
credentials/coverage → runs the discovery ladder → feeds the resulting targets into the **same**
fetch → deterministic-signal-extract → quote-verified-claim → score → four-state-export →
dashboard path already proven by `run_offline`. Reuse opt-out, warm-cache, resume, blocked→human-
rung, and the gap-derived run status verbatim. Replace the `cli.py` `scan` stub with this driver
(and keep `--demo` working). *DoD:* `scan` (no `--demo`) runs end-to-end on cassettes and produces
the same honest, hallucination-free four-state dashboard `run_offline` does — now from discovered
(not hand-fed) targets; a warm re-scan re-extracts ~nothing.

**Phase L3 — The extra collectors the author asked for (each an honest, sourced Claim).**
For every deep-dived professor, collect — through the deterministic tier for public pages, and the
**human rung** for walled ones — and record as four-state Claims (D-010/046):
- **Students who joined the lab** (current + alumni): from the professor's group/people page,
  OpenAlex co-author/advisee signals, and thesis/registry sources where public. Each student is a
  Claim-backed entity linked to the professor with its source; unknown → `searched_absent`, never
  invented (D-035 forbids using the corpus; only live-fetched facts).
- **Companies / organisations the professor has worked with:** industry co-authors, acknowledged
  funders/partners, "industry experience" lines — as `Collaboration` claims with sources.
- **Recruiting status incl. social (D-050, the author's explicit ask):** the professor's own pages
  and any linked social/personal site they advertise. X/Twitter and other login-walled social go
  to the **human rung** (generate the chrome prompt; ingest the pasted Markdown) — never scraped.
Every one of these is exportable only with a verified quote + source; LLM value-judgements about
people are **not** exported (D-024). *DoD:* a recorded professor cassette yields sourced student /
company / recruiting claims where present and honest `searched_absent` where not; a walled social
page produces a human-rung task, not a scrape; the dashboard shows the new fields as generic,
filterable columns (D-038) without hardcoding them.

**Phase L4 — Ranking: universities and professors.**
Extend `score/` (do not fork it): keep the existing intent-aware professor score, and add a
**university/program roll-up ranking** (D-031) that aggregates its professors' fit + recruiting +
activity into a transparent, re-weightable institution score, with confidence lowered by sparse
evidence (never faked). *DoD:* on a fixture, universities and professors both rank deterministically
and re-weightably; a fragmented profile is reconciled, not dropped; a `pre_phd` search is not gated
on PhD-admission rules.

**Phase L5 — University-scope input (default all; prioritise / only).**
Surface the existing `SearchPlan.university_mode` (all / prioritise / only) + `universities_json`
through the CLI/skill so the student can (optionally) name universities to **prioritise** or
**restrict to**, defaulting to **all** (the author's ask). *DoD:* `only` scans just the named set;
`prioritise` ranks them first but still covers the rest; `all` (default) covers everything the
ladder finds; each mode is tested.

**Phase L6 — Scheduled / automatic re-scans.**
Make a repeat run first-class: a `resume`/re-scan that reuses the warm cache (already ~zero
re-extraction on unchanged pages) and emits a **"what changed since last run"** delta (new
professors, newly-open recruiting, newly-published deadlines). Document a safe scheduling recipe
(Windows Task Scheduler / cron) — **without** committing any output. *DoD:* a second scheduled run
over unchanged cassettes issues ~0 new extraction and reports an empty, honest delta; a changed
page shows up in the delta.

**Phase L7 — Front-end & diagrams in the Atlas design language (binding spec:
`design_handoff_supervisorly_atlas/`).**
Recreate the results UI and every diagram in the hifi **"Supervisorly Atlas — Living"** language.
The `README.md` in that folder is the binding spec; the `.dc.html` holds the reference prototype,
the diagram/decision **data**, and the final **copy** — port the data as-is, reimplement the runtime.
- **Tokens verbatim:** base void `#05070c`; tissue-type kind colors (teal `#43c9d6` tool, chartreuse
  `#79d06a` verified, coral `#f0839a` human, amber `#e8b24a` core, violet `#b58cf0` rule, slate
  `#7d828e` skip); amber `#e8b24a` global accent; teal `#7fd6e0` focus ring; the radii/shadows and
  the keyframes `omBreathe`/`omHalo`/`omFlow`/`omDrift`/`omScan`.
- **Type:** Space Grotesk (display/UI) + Space Mono (labels/codes), with the documented scale/tracking.
- **Layout shell:** the fixed decorative background (nebula blooms + vignette + drifting orbs + scan
  line), the left "CATALOGUE" sidebar (→ top drop-down < 900px), the main column, the scroll-progress
  bar, the **cell drawer** + **law/detail drawer** (right sheet), and the **isolate lightbox**.
- **The diagram engine — this is "how diagrams appear":** each diagram is a stage of glowing **cell**
  nodes (nested halo / membrane body / nucleus, sized by kind) and **filament** edges computed in a
  layout effect as **cubic-bezier curves** bowed perpendicular (deterministic sign per `hash(from+to)`),
  each drawn as **4 stacked SVG elements** (soft glow + base line + animated light-packet dashes
  `omFlow` + arrowhead) with optional midpoint label pills; **highlight-connected** on hover/focus
  (dim non-neighbors + non-touching edges); **scroll-spy** active nav. Recompute all geometry on
  mount / resize / font-load / lightbox-open; node coordinates are data, derive the rest.
- **Apply it to the product, not just the architecture atlas:** render (a) the architecture "specimens"
  (context/components/pipeline/data/rules/roles/lifecycle/observability), (b) a **how-it-works** flow,
  and (c) the **results dashboard** — where the four-state honesty, the deadline watch-date view, and
  clickable professor detail all survive: professor detail becomes a **cell drawer**, and a professor's
  students/collaborations render as a **filament graph**.
- **Hard constraint — self-contained & offline (D-033/D-048):** the shipped dashboard is ONE file with
  **no external resources** — self-host/inline the two fonts (or a faithful fallback), no Google-Fonts
  URL, no CDN, no fetch; all CSS/SVG/inline-JS. Honour `prefers-reduced-motion` (kill all animation),
  keep it keyboard-operable (focus triggers highlight; Escape closes lightbox→drawer) with a visible
  focus ring, and injection/scheme-safe.
*DoD:* the results dashboard **and** at least one architecture/how-it-works diagram render in the
Atlas language from real (cassette-discovered) data — fully self-contained, offline, **no console
errors, no external requests**; `prefers-reduced-motion` disables animation; the four states +
deadline view + clickable cell-drawer detail all work; a diagram's filaments recompute correctly on
resize and when the lightbox opens.

**Phase L8 — CLI + SKILL orchestration.**
Finish the CLI (`scan` live flags: field/country/intent/universities/optout/out/schedule) and
update `.claude/skills/supervisorly/SKILL.md` so a student's request flows: **intent recognition →
generated `SearchPlan` → confirm with the user → live scan (Stage-1 enumerate → Stage-2 deep-dive →
students/companies/social → score/rank) → dashboard**, with the LLM agents doing Stage-2 judgement
and the deterministic tools doing collection. *DoD:* the skill contract validates; the documented
flow matches `product-flow.md`; the CLI help lists every live flag.

**Phase L9 — Eval + self-test (§4) + refine (§5) + clean-room + `docs/LIVE_COMPLETION_REPORT.md`.**

## 3 — Edge-case matrix (each row needs a passing test before Done)

| Edge case | Required behaviour |
|---|---|
| Missing contact email | fail loud with the exact fix; never hit public APIs anonymously (D-019/023). ROR is keyless; OpenAlex premium key optional |
| Sparse country/field | preflight warns up front; run continues; coverage honest (D-060) |
| Institution has no machine-readable directory | ladder falls through the rungs; if still none → login-wall/human-rung or an honest `CoverageRecord`, never a fabricated roster |
| Login-walled faculty directory | `roster_enumerate` human-rung task; unit `LOGIN_WALL`; nothing scraped (D-052) |
| Fragmented / non-Western author identity | reconciled before it becomes a target and before scoring (D-057); risk lowers score-confidence, not activity |
| Professor found via API but page unreachable | professor kept; fields `blocked`; open gap resumable (D-049) |
| Student/company/recruiting fact absent | `searched_absent`, never invented; the professor is not dropped |
| Recruiting only on X/Twitter or a walled social page | human-rung prompt generated; ingested Markdown fills it; never scraped (D-043/044) |
| Two professors, same program | roll up to one application/fee (D-031); ranked as a program |
| `university_mode = only` / `prioritise` | restrict / rank-first correctly; `all` is the default |
| Monthly scheduled re-scan, nothing changed | ~0 re-extraction (warm cache); empty honest delta |
| Re-scan after a page changed | delta shows the change; stale claim superseded, not duplicated |
| A country/field the author never imagined | still generates a `SearchPlan` and runs (D-038) |
| Opt-out person discovered mid-scan | dropped before fetch **and** absent from every export/delta (D-023/053) |
| Rate-limit / 5xx from ROR/OpenAlex or a page | polite exponential backoff + jitter; never retries harder (D-039) |
| Non-English professor page | recruiting/eligibility extracted in the original language; translate only for display (D-044) |

## 4 — Self-test protocol (you must actually RUN it, not just compile it)

1. **Deterministic end-to-end LIVE-path run on cassettes** (offline, no network, no real keys):
   record a small, realistic cassette set — a country's ROR institutions, their directory pages,
   an OpenAlex authors-by-institution response, and a handful of professor pages (incl. one
   login-walled directory and one walled social page). Drive `scan` (no `--demo`) through
   discovery → deep-dive → students/companies/social → score/rank → dashboard. Produce the real
   JSON + dashboard.
2. **Inspect the output like a user would.** Assert programmatically: every displayed fact traces
   to a Claim whose quote is present in a snapshot (**zero hallucinations**); the four states render
   distinctly; **no professor/student/company dropped**; ranking, filters, the deadline view, and
   clickable detail all work; walled sources became human-rung tasks, not scrapes; opt-out held.
3. **Run the skill the way a student would** (via `SKILL.md`) on the cassette fixture and confirm
   the orchestration (intent → confirm plan → Stage-1 → Stage-2 → extra signals → rank → dashboard)
   matches `product-flow.md`.
4. **Optional live smoke test** (only if a real `SUPERVISORLY_CONTACT_EMAIL` is set — that's all
   it takes; no keys): one small, polite real department; confirm real-world behaviour; then
   **discard the output — never commit it** (D-005). If no email is configured, mark this step
   **skipped**, never passed (D-007/§7).
5. **Budget checks:** a representative scan stays within `cost-and-performance.md`; a warm re-scan
   issues ~0 re-extraction.
6. **Clean-room fresh-install verification (last, once everything else is green).** Wipe every
   generated/transient artifact (`.venv`, caches, snapshots, `output/`, `*.sqlite`, `__pycache__`,
   `*.egg-info`, the editable install); confirm `git status` shows **only** committed code, docs,
   and synthetic/public fixtures — **no personal data, no real-page snapshots, no scan output**.
   From that clean state, run the documented install fresh and re-run the offline cassette
   self-test (steps 1–3) end to end; it must pass on the first try. If it fails where the dirty run
   passed, fix the hidden dependency and repeat.

## 5 — Refine & fix loop (do not skip)

After Phase L8's first green, run an **adversarial self-audit** across these dimensions, fix every
finding with a regression test, and re-run the whole suite until zero open findings:
- **Correctness & provenance** — any displayed fact without a verified quote? any invented student/
  company/date? any identity mis-reconciled (wrong person merged)?
- **Genericity (D-038)** — does discovery break on a second/third country's ROR/directory shape?
  any hardcoded institution/field/URL?
- **Ethics** — opt-out (mid-scan discovery), robots fail-closed, no bare-emails, no bulk path, no
  login defeated, corpus never read, output never committed.
- **Honesty** — is every empty one of the four states, never a guess? is a walled source a task,
  not a scrape?
- **Cost/perf** — warm re-scan skips unchanged work? deterministic layer LLM-free? backoff polite?
- **UX** — is the ranked, filterable dashboard genuinely usable and trustworthy (students, company
  links, recruiting, deadlines, sources on everything)?
Log each pass. Prefer adversarial verification of your own findings before acting on them.

## 6 — Definition of Done (mark complete ONLY when EVERY item is true)

- [ ] Every phase (L0–L9) meets its DoD.
- [ ] `scan` (no `--demo`) runs the **full live path end-to-end on cassettes** and produces a
      correct, honest, hallucination-free four-state dashboard from **discovered** targets — with
      students, company/collaboration links, and recruiting/social status where present.
- [ ] **The UI + diagrams are recreated in the Atlas design language** (`design_handoff_supervisorly_
      atlas/`): the results dashboard and ≥1 architecture/how-it-works diagram render faithfully
      (tokens, type, cell-and-filament engine, drawers, lightbox), **fully self-contained and offline**
      — no external requests, no console errors — with `prefers-reduced-motion` and keyboard support.
- [ ] **Every edge case in §3 has a passing test.**
- [ ] Ranking (universities + professors) is deterministic, re-weightable, and intent-aware.
- [ ] University scope (all / prioritise / only) works and is tested; default is all.
- [ ] Scheduled re-scan issues ~0 re-extraction and emits an honest "what changed" delta.
- [ ] The adversarial self-audit (§5) returns **no open findings**.
- [ ] Ethics gates verified by tests: opt-out (build + re-export + mid-scan), robots, no-bare-emails,
      no-bulk-path, corpus-never-read, no-login-defeated, LLM-free deterministic layer.
- [ ] All unit + integration + eval + existing offline tests pass; **the previously-green suite
      stays green** (no regressions to the offline engine).
- [ ] Docs updated: `README.md` (live install, credentials, the live command + flags, scheduling),
      `BUILD_LOG.md`, `docs/getting-started.html` (the beginner guide's live section now describes a
      working scan), and any implementation decisions appended to `DECISIONS.md`.
- [ ] **Clean-room verification passes** (§4 step 6) on the first try from a clean checkout.
- [ ] `git status` shows **no scan output / no personal data**; `.gitignore` honoured; only code,
      docs, and synthetic/clearly-public fixtures survive the teardown.
- [ ] The live smoke test (§4 step 4) is either **passed with a real contact email** or explicitly
      **skipped** with the reason — never fabricated.
- [ ] A final **`docs/LIVE_COMPLETION_REPORT.md`**: what was built, full test/eval numbers,
      edge-case coverage, honest known limitations, the exact commit range, and exact run steps.

**Only when all boxes are checked, declare the goal complete** with a one-screen summary and a link
to `LIVE_COMPLETION_REPORT.md`.

## 7 — Guardrails against false completion (read twice)

- **"It compiles" ≠ done.** Done requires the live cassette self-run + eval + audit + clean-room all
  green, and the pre-existing offline suite still green.
- **Never fabricate or predict a test/scan result.** If a step can't run (no keys, no network), mark
  it **skipped** with the reason — never as passed. Never invent a student, a company, or a date.
- **Never weaken or delete a test to go green.** Fix the code. (Correcting an over-eager *expectation*
  to a more honest behaviour is allowed — say so explicitly and why.)
- **Never defeat a login or scrape a walled page to "complete" a field** — route it to the human rung.
- **If genuinely blocked** — an irreversible action, a real credential you can't obtain, or an
  ambiguity only Ahmed can resolve — **stop and write `docs/BLOCKERS.md`** with the specific ask.
- **Work in small, reversible, per-round commits (§8); every commit leaves the suite green.**

## 8 — Version control discipline (every round is a tracked commit)

- Work on a dedicated branch (e.g. `build/live` off the current tip), never the default branch.
- **One commit per round** (per phase as it meets DoD, per refine pass, and one clearly-marked
  `clean-verified` commit), each leaving the whole suite green. Real messages: a summary line
  (what changed) + a body saying *why* and *what you ran and the result* (e.g. `live: 3/3 ROR
  cassettes discover the expected faculty; 0 hallucinations; edge-cases N/N`).
- **No broken commits.** Split work so each commit is green; never commit to "save progress" red.
- **Never commit generated state or personal data** — DB, caches, snapshots, scan output (D-005).
- The final `LIVE_COMPLETION_REPORT.md` cites the commit range so every change is auditable.

*(The harness adds its own author/session trailer to each commit — you supply the summary + body.)*

---

Your goal is not "code that reaches the network." It is **a live scan that turns a country and a
field into an honest, evidence-backed, ranked dashboard of real professors — their recruiting
status, the students who joined them, and the companies they've worked with — every fact backed by
a citable source, every gap stated honestly, no login ever defeated — and proves it does, to
itself, on recorded sources before ever touching a real key.** Build it on the engine that already
exists, run it, judge it, fix it, finish it — and leave a clean, per-round commit history.
