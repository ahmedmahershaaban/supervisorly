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
