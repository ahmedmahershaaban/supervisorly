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

**Stage 0 — interpret intent (you, inline).** From the student's country + field + subfield +
need, build a `SearchPlan`: the `intent_kind`, generated `resolved_topic_terms` and OpenAlex
`resolved_topic_ids` (D-058), venues, target/excluded sources, languages, university mode. Run a
**country-source preflight** (D-060) and tell the student what will be thin. **Show the plan and
wait for confirmation** — nothing expensive runs until `confirmed_by_user`.

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

1. **Intent recognition → SearchPlan.** From the student's request (a country, a field, and what
   they need — pre_phd / master / phd / postdoc / mentor), *generate* a SearchPlan (D-038): resolve
   the field to OpenAlex topic IDs, pick the country, and note any universities to prioritise or
   restrict to (`university_mode` = all / prioritise / only). Nothing is looked up from a fixed list.
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
