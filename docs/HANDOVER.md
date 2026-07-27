# Handover — read this first

**Written:** 2026-07-22, while Ahmed was away, as a design handover before any code existed.

> **Status, 2026-07-27 — this document's framing is historical.** Everything below described a
> design about to be built. It has since been built, tested and **deployed**: the engine (Goals
> 1–3) and the hosted web product (Goal 4, live at `supervisorly.web.app`). The reading order
> and findings below are still the right way in; the "what has not been done" section at the end
> is preserved only as a record of where this started. For current state read
> [BUILD_LOG.md](BUILD_LOG.md) (newest entry last) and the completion reports
> ([COMPLETION_REPORT.md](COMPLETION_REPORT.md),
> [BROWSER_COMPLETION_REPORT.md](BROWSER_COMPLETION_REPORT.md),
> [LIVE_COMPLETION_REPORT.md](LIVE_COMPLETION_REPORT.md),
> [WEB_COMPLETION_REPORT.md](WEB_COMPLETION_REPORT.md)).

## What happened

Three research passes ran against the existing corpus in
`C:\Users\ahmed\Documents\Downloads\` and the open web:

1. **Corpus discovery** — 14 parallel agents over ~90 of Ahmed's research files, then a
   synthesis pass, then three adversarial critics. 18 agents, zero failures.
2. **Data-source research** — empirical testing of OpenAlex, ROR, ORCID, Crossref, DBLP,
   Semantic Scholar and six real faculty pages across five countries.
3. **Prior-art review** — GitHub API sweeps and web search for existing tools.

Nothing in these documents is invented. Where a number came from Ahmed's own files it is
cited; where it came from a live API call it is marked verified; where it is arithmetic
over an assumption it is marked modelled.

## Read in this order

| Document | What it holds |
|---|---|
| [atlas.html](atlas.html) / [design-atlas.md](design-atlas.md) | **Start here** — 13 diagrams connecting the whole design. `atlas.html` is the interactive version (published artifact); the `.md` renders on GitHub |
| [product-flow.md](product-flow.md) | The student's journey, in their terms — the authoritative flow, both surfaces |
| [requirements.md](requirements.md) | What Ahmed already built, what broke, and why — 13 ranked pain points |
| [DECISIONS.md](DECISIONS.md) | **70 decisions** with rationale and reversal conditions. **None open** |
| [architecture.md](architecture.md) | The system design; §11 is the hosted web tier |
| [domain-model.md](domain-model.md) | **32 entities** (24 world-model + 8 pipeline/user), each field with an obtainability estimate |
| [FIREBASE_WEB_PLAN.md](FIREBASE_WEB_PLAN.md) / [../firebase/README.md](../firebase/README.md) | The hosted product's plan, and the deploy runbook |
| [BLOCKERS.md](BLOCKERS.md) | Recorded deviations from plan, with the reasoning |
| [parameter-catalog.md](parameter-catalog.md) | 93 dashboard filters/sorts/facets merged from every corpus table |
| [cost-and-performance.md](cost-and-performance.md) | Budget and speed targets, with the numbers |
| [ethics-and-compliance.md](ethics-and-compliance.md) | GDPR posture, opt-out, scope limits |
| [critiques.md](critiques.md) | The three design critics, verbatim — 52 gaps, 44 overconfident claims |
| [research/data-sources.md](research/data-sources.md) | Every source, tested |
| [research/social-sources.md](research/social-sources.md) | Social recruiting sources, tested 2026 (Bluesky/Mastodon in, X out) |
| [research/prior-art.md](research/prior-art.md) | Competitors, and the honest gap |

## The five findings that matter most

1. **The name "ProfScout" is taken.** `satyam-thakur/profscout` on GitHub, pushed
   2026-07-19, same concept. Three other close competitors exist — all hobby-scale, none
   maintained, and *all* CS-only because they wrap CSRankings, which is CC BY-NC-ND.
   Non-CS and non-US coverage is the real gap.

2. **The flagship field is ~20% populated, not 80%.** Ahmed's own corpus: only 20 of 104
   professors had a verbatim recruiting quote. "No signal found" is the majority state and
   has to be the designed-for default, not an edge case.

3. **Scraping-first would have failed.** Of six real faculty pages tested across five
   countries: zero had schema.org markup, two 404'd, one was an SPA, one returned "Account
   Suspended". APIs and CRIS portals are the spine; page fetching is enrichment.

4. **Current students are not obtainable anywhere — but past students are.** No source
   records live supervision. National thesis registries (theses.fr, DART-Europe, NDLTD)
   *do* publish completed dissertations with supervisors named. Retrospective, structured,
   legal.

5. **The obvious two-stage design is circular.** "Cheap enumeration → user shortlists →
   expensive deep dive" asks the user to filter on recruiting/funding/eligibility — the
   fields that only exist *after* the deep dive. Fixed with three tiers, shortlisting on
   research fit instead.

## Four questions — all answered (2026-07-23)

| # | Decision | Resolution |
|---|---|---|
| [D-012](DECISIONS.md#d-012--project-name) | Project name | **Supervisorly** |
| [D-033](DECISIONS.md#d-033--dashboard-technology) | Dashboard tech | **Single self-contained HTML with embedded JSX** (component model + virtualisation, no build project); mechanism in [D-048](DECISIONS.md#d-048--dashboard-delivery-pre-transpiled-jsx-vendored-inline-no-runtime-toolchain) |
| [D-034](DECISIONS.md#d-034--v1-breadth-fully-generic-risk-accepted) | v1 breadth | **Fully generic** — Ahmed held his choice; risk accepted, mitigations in the decision |
| [D-011](DECISIONS.md#d-011--validation-strategy) | Validation | **No golden fixture from the corpus.** Cassettes + synthetic data instead |

**The decisive constraint — [D-035](DECISIONS.md#d-035--the-corpus-is-a-methodology-reference-not-a-data-source):**
Ahmed's corpus is a **methodology reference only**. It teaches the project *how* to filter,
search and extract — parameters, keywords, taxonomy, layout. It supplies **no content**
about real people: no harvested facts, no seed data, no test fixtures. Every real fact the
tool shows must be one it fetched itself, live, from a citable public source. This is a
clean-room posture and it governs everything downstream.

## Round 4 — the pre-build audit (2026-07-23)

An independent 6-dimension audit of the whole doc set ran before the schema phase. It found
9 blocking gaps and several contradictions; all are resolved:

- **Design questions resolved as decisions D-045–D-056** — intent/query ownership (orchestrator-
  inline, producing a `SearchPlan`), the JSON export contract (four-state value envelope), one
  canonical confidence model, the dashboard's pre-transpiled-JSX mechanism, terminal run states
  (dashboard never blocked on the human), the recruiting-classification contract, the shared MD
  grammar, roster-enumeration via the human rung, opt-out match keys, the overlay clean-room
  rule, one orchestration vocabulary, and the explicit shortlist gate.
- **Contradictions fixed in the source docs** — the shortlist gate added to `product-flow`;
  students reframed as collaborators/former-students (display-only, non-exported); the
  corpus-fixture references removed from `architecture` §8; the install story split by mode;
  the `first_author_junior_ratio` field dropped per D-024.
- **Model completed** — field tables added for the 7 pipeline/user entities (SearchPlan, Run,
  Task, Checkpoint, ExtractionCache, Outreach, Application); entity count reconciled to 31.

Deferred to the schema phase (design decided, spec is the next deliverable): the full JSON
worked example, the shared MD worked example, the scorer formula, and Stage-1 enumeration
robustness cases.

## Suggested next steps *(as of 2026-07-22 — all now done; kept as the original plan of record)*

1. Write `SKILL.md` + the agent/tool contracts (the install-and-run product surface).
2. The SQLite DDL from the 31-entity model, starting with `Claim`, `Run`/`Task`, and the state machine.
3. The shared **Phase-3 MD grammar** ([D-051](DECISIONS.md#d-051--one-shared-markdown-grammar-for-the-human-rung)) — the seam between the human and the pipeline; do this early.
4. The **JSON export contract** worked example ([D-046](DECISIONS.md#d-046--the-json-export-contract-is-the-systems-interchange-format-with-a-four-state-value-envelope)).
5. Build the discovery ladder, tested against recorded cassettes + synthetic data.
6. Only then: dashboard.

## What was actually built (2026-07-22 → 2026-07-27)

Four goals, each closed with a clean-room verification and a completion report. `BUILD_LOG.md`
is the round-by-round record; the short version:

- **Goal 1 — the engine.** Discovery ladder, three-phase fetch, extraction behind the D-010
  quote gate, scoring, four-state JSON and the self-contained dashboard.
  → [COMPLETION_REPORT.md](COMPLETION_REPORT.md)
- **Goal 2 — live running.** Real scans against real sources, pacing, credentials, resume.
  → [LIVE_COMPLETION_REPORT.md](LIVE_COMPLETION_REPORT.md)
- **Goal 3 — the browser tier.** The D-064/D-065 agent-browser seam that closes walled-source
  gaps through the student's own session, with the Markdown human rung as fallback.
  → [BROWSER_COMPLETION_REPORT.md](BROWSER_COMPLETION_REPORT.md)
- **Goal 4 — the hosted web product.** D-068 query expansion, the async scan job, the HTTP
  surface, the 5-step wizard page, and the Firebase deployment. **Live at
  `supervisorly.web.app`.** → [WEB_COMPLETION_REPORT.md](WEB_COMPLETION_REPORT.md)

The most transferable lesson is in that last report's §4b: a green test suite, an adversarial
audit and a clean-room pass all passed while **eight** defects sat in the deploy path — four of
which *deployed successfully*. Passing tests were never evidence that the deployment worked.

## What has *not* been done — *original entry, 2026-07-22*

> - No code written. Ahmed asked for definition first, then schemas, then implementation.
> - No git commits. Files are in the working tree, unstaged.
> - The stray `CLAUDE.md` at the repo root is still the context-mode routing rules copied
>   from the parent directory; it should be replaced with real project guidance.

All three are resolved: the code exists and is committed round by round, and the root
`CLAUDE.md` now carries real project guidance. **Still genuinely unproven** — and the honest
current answer to "what hasn't been done" — is in
[WEB_COMPLETION_REPORT.md](WEB_COMPLETION_REPORT.md) §6: the 6-hour worker timeout, the 7-day
TTL deletes (they need seven days to observe), throttle behaviour under real concurrent load,
and any scan large enough to meet the OpenAlex daily budget.
