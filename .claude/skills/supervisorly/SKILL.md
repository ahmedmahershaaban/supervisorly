---
name: supervisorly
description: >-
  Find a research supervisor (PhD, master's, postdoc) in any country. Use when the
  user wants to find professors to work with, build a supervisor shortlist, check who
  is recruiting students, or research faculty by field and country. The user gives a
  country, a field/subfield, and what they need (pre-PhD/RA, master's, PhD, postdoc,
  mentor); this produces a filterable, evidence-backed dashboard of professors.
---

# Supervisorly — orchestrator

You are the orchestrator. You interpret intent and generate the search strategy **inline**
(this is the "generate, don't look up" judgement — D-038/D-045); the deterministic tools under
`src/supervisorly/` do the fetching, parsing, caching, scoring and export (no LLM inside them);
and the agents under `.claude/agents/` do the bounded extraction judgement. **Never contradict a
locked decision in `docs/DECISIONS.md`.**

## Vocabulary (one set — D-055)
- **Stages 0–4** = the student's journey: intent → roster → deep-dive → gap-fill → people.
- **Phases 1–3** = the fetch escalation: structured → automated browse → human rung.
- **Tiers** = enumerate → signal → deep-dive (who gets how much work).
- **Tools** are named (`discovery-ladder`, `fetcher`, `deep-dive`, `gap-queue`,
  `chrome-prompt-generator`, `md-ingester`, `scorer`, `exporter`) — see `architecture.md §4`.

## Flow

**Stage 0 — interpret intent (you, inline).** From the student's country + field + need, interpret
the intent inline (this is the "generate, don't look up" judgement — D-038/D-045). Then run
`supervisorly map-field --field "<the student's free-text field>"` (D-066): it maps the field to a
hierarchical, API-derived OpenAlex subject map (domains → fields → subfields → topics). Present
that map as a **multi-select** — a numbered list in conversation, or generate the Scan Studio
(`supervisorly studio --map <subject-map>`) and point the student at it. The student keeps the
topics they want and skips the rest; the kept topic IDs become the plan's `resolved_topic_ids`.
Finish the `SearchPlan` around them: the `intent_kind`, venues, target/excluded sources, languages,
university mode. Run a **country-source preflight** (D-060) and tell the student what will be thin.
**Show the plan and wait for confirmation** — nothing expensive runs until `confirmed_by_user`.

**Stage 1 — roster (enumerate + signal tiers).** For each targeted university, run
`discovery-ladder` (CRIS → sitemap → JSON-LD → CT logs → OpenAlex/ROR → adapter). Capture every
professor with links. Then the cheap signal tier over all of them (one cached homepage fetch).
If a directory is login-walled, queue a **roster-enumeration** human-rung task (D-052).

**Shortlist gate.** Promote ~40 on research-fit (topic-ID overlap), reconciling fragmented
works first so non-Western names aren't wrongly dropped (D-057). "Never dropped" = display;
"deep-dive" = the shortlist (D-056).

**Stage 2 — deep-dive the shortlist.** Fetch each professor's sources through `fetcher`
(robots-gated, snapshots). Call the agents: `recruiting-analyst`, `eligibility-analyst`,
`profile-synthesist`. Every value claim is quote-verified against its snapshot before storage
(D-010) — the recorder rejects anything unverifiable.

**Stage 3 — gap-fill (3-phase).** For still-empty fields: Phase 1 structured, Phase 2 browse,
Phase 3 human rung — `chrome-prompt-generator` emits a prompt (shared MD grammar, D-051) the
student runs in Claude for Chrome; `md-ingester` parses the returned Markdown into claims and
resumes. The dashboard is generated **after Phase 2** and never waits on the human (D-049).

**Stage 4 — people.** Collaborators, and former doctoral students only where the registry
exposes advisors (D-062). Display-only, never exported (D-024).

**Score + export.** `scorer` applies **intent-aware** hard gates (D-059) on gate-eligible claims
(D-047), then a transparent weighted score. `exporter` writes the four-state JSON (D-046) and the
self-contained dashboard.

## Rules you enforce
- Generate queries/keywords; never use a hardcoded list. Enum of categories ok; dictionary of a
  field's search terms forbidden (D-038).
- Public sources + open APIs only; never defeat a login or bot-wall — that's the human rung.
- Honest emptiness: four states, distinct; never drop a professor for missing data.
- Never read the professor corpus as data (D-035); never commit scan output / personal data.

## Live scan orchestration (Stage-1 → Stage-2)

For a **live** run against real sources, the flow is:

1. **Intent recognition → subject map → plan.** From the student's request (a country, a field,
   and what they need — training / pre_master / pre_phd / master / phd / postdoc / mentor),
   interpret the intent inline (D-038), then run `supervisorly map-field --field "<field>"` and
   present the hierarchical subject map as a multi-select (a numbered list in conversation, or
   `supervisorly studio --map output/subject_map.json` for the Scan Studio wizard, D-066/D-067).
   The kept topic IDs become the plan's `resolved_topic_ids`. A plan the student exports from the
   Studio (or confirms in conversation) drives the scan via `supervisorly scan --plan plan.json`
   (explicit flags override its values); named professors go in via `--targets profs.json`.
   Nothing is looked up from a fixed list.
2. **Confirm the plan with the user** before anything expensive runs.
3. **Stage-1 — enumerate.** The discovery ladder (ROR by country → OpenAlex authors-by-institution)
   produces a de-duplicated list of professor targets with links; login-walled directories go to the
   **human rung** (never scraped).
4. **Stage-2 — deep-dive.** Each professor's own public pages are fetched (robots-obeying) and every
   field becomes a quote-verified **Claim** (D-010): recruiting signal, application deadline, the
   **students / lab members**, the **companies / collaborations**, and any **advertised social**
   link. Walled social content (a recruiting post on X/LinkedIn) is routed to the human rung.
5. **Score & rank.** Professors are scored (intent-aware gates, topic-ID overlap) and rolled up into
   ranked universities; nobody is dropped for missing data — the **four states** stay honest.
6. **Dashboard.** A single self-contained page (the Atlas design language) with the results, the
   deadline watch-dates, and the how-it-works diagram.

The deterministic tools do collection + verification; the LLM analysts (this skill's agents) do the
Stage-2 judgement. Run it from the CLI:

```
supervisorly scan --country Canada --field "causal ML" --intent pre_phd \
  --email you@example.com --out output/live.html
```

Only a **contact email** is required (ROR is keyless, OpenAlex is free); the corpus is never read
(D-035). Re-run with `--resume` for a cheap scheduled refresh (warm cache + a "what changed" delta).

The MCP browser config is **host-portable** (D-064): the chrome-devtools server is registered once
at user level (`mcp.json`); for Claude Code it's
`claude mcp add chrome-devtools --scope user npx chrome-devtools-mcp@latest` — the same server
(the slim / no-usage-statistics flags are recommended). The recipe below is identical under any
MCP host.

## Browser-primary live fetch (D-064)

Chrome — launched and driven by you via the chrome-devtools MCP tools (`mcp__chrome-devtools__*`;
the server auto-launches Chrome, headful, on a persistent profile) — is the **primary** page fetch
for live scans. The exact recipe for every page:

1. **Pace first.** Run `supervisorly pace --host <host>` BEFORE each page and branch on the exit
   code: `0` = go; `3` = respect the printed verdict — sleep the printed `wait=` seconds and
   re-check, or skip the host entirely on a cap/abort deny.
2. **Skip the browser when you can.** A page already fresh in the warm cache needs no fetch at
   all, and API endpoints never get one — ROR/OpenAlex JSON stays on the Python/httpx side.
3. **Navigate** with the `mcp__chrome-devtools__*` tools. Walled pages use the logged-in
   persistent profile — on the **first** browser run, pause and ask the user to log into the
   walled sites once, themselves, in the opened Chrome window; after that the session persists.
4. **Extract in-page.** Call `evaluate_script` with `src/supervisorly/extract/page_extract.js`
   as the function body (default for static pages; args `[{"scroll": true}]` for scroll mode on
   social pages). Write ONLY the returned `text` to a staging file (e.g. `browser_staging/`)
   WITHOUT reading it into context — you handle paths and byte counts, never raw page content.
5. **Ingest.** `supervisorly ingest-page --url <finalUrl> --file <staging>` stores the text
   as a snapshot and prints a one-line result. To also close a target's gap, add
   `--entity professor:<id> --run <run_id>`: the deterministic engine takes it from there —
   the pipeline's own extractors run over the snapshot, D-010 quote-verified claims are
   recorded (a human-assisted value is never clobbered), the target's `awaiting_human`
   gap-fill tasks close, and the run flips to `finalized` when no open gaps remain. A
   browser page is just another snapshot. Both this and `reexport` default to
   `output/supervisorly.sqlite` — the store the documented scan (`--out output/...`) writes;
   **if the scan used a custom `--out`, pass `--db <out-dir>/supervisorly.sqlite`**.
6. **Re-export after a fill.** `supervisorly reexport --db <db> --out output/dashboard.html`
   rebuilds the dashboard from the persisted store (no fetching) so the filled values show.

## Social rung (D-065)

Walled-social gap tasks — the `awaiting_human` gap_fill tasks minted for a professor's
**advertised** x.com / linkedin.com profiles — are executed by you through the logged-in profile,
not parked for the student: per-target, read-only, scroll mode, `pace` enforced before every page.
Read the advertised profile, then return the page through the browser seam **with the target and
run attached** — `supervisorly ingest-page --url <finalUrl> --file <staging> --entity
professor:<id> --run <run_id>` — which fills the signal fields from the snapshot, closes the gap
task, and recomputes the run status; finish with `supervisorly reexport` so the dashboard shows
the filled values. On ANY challenge, soft-block, or unexpected login redirect: `supervisorly pace
--host <h> --abort "<reason>"` (the host latches aborted for the session), mark the field
`blocked`, and route it to the classic human rung — never retry harder. Scholar is minimal-use:
profile pages only, no search pagination. Only advertised profile URLs are ever visited — never
people-search enumeration.
