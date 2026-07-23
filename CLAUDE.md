# CLAUDE.md — working in the Supervisorly repo

Supervisorly is a **Claude-Code skill + agents + tools** that helps a student find a research
supervisor (PhD / master's / postdoc) in **any country**, with every fact backed by a citable
source. This file orients any Claude instance working here.

## Read first
- `docs/HANDOVER.md` — the map of everything.
- `docs/DECISIONS.md` — **binding.** 63 numbered decisions (D-001…D-063). Never contradict a
  locked decision; if you think one is wrong, record it in `docs/BLOCKERS.md`, don't silently
  deviate.
- `docs/IMPLEMENTATION_GOAL.md` — the build/self-test/refine/completion contract.
- `docs/architecture.md`, `docs/product-flow.md`, `docs/domain-model.md` — how it works.

## Governing constraints (violating any is a defect, not a choice)
- **Generate, don't look up** (D-038): no embedded university list, no keyword dictionary; the
  search strategy is generated per query. Enum of categories = allowed; dictionary of a field's
  search terms = forbidden.
- **The corpus is methodology-only** (D-035): never read/import/ship anything from
  `C:\Users\ahmed\Documents\Downloads` as data, seed, or fixture. Every real fact must be one the
  tool fetched itself, live, from a citable public source.
- **Deterministic layer has no LLM** (D-009): `src/supervisorly/{discover,fetch,model,score,export}`
  contain zero model calls. The LLM judgement lives in `.claude/agents/`.
- **Every field is a Claim with a verified quote** (D-010, D-047): a claim whose quote is not
  found in its snapshot is rejected in code. `NOT_FOUND` is a real value; never guess.
- **Honest emptiness** (D-022/037/046): the four states `value / searched_absent /
  never_attempted / blocked` are distinct; a professor is never dropped for missing data.
- **Public sources + human rung** (D-039/043/044): fetch public pages and open APIs; never defeat
  a login or bot-wall. Walled sources go to the Phase-3 human rung (Claude for Chrome).
- **Ethics in code** (D-005/019/023/024/032/053): obey robots.txt; enforce `optout.txt` at build;
  no nationality gate; no LLM-judgements or bare emails in exports; no bulk outreach; **never
  commit scan output, snapshots, or any personal data.**

## How to work here
- Use the project **`.venv`**; run the CLI as `python -m supervisorly …`; run tests with
  `python -m pytest`.
- Work on `build/v1` (or a feature branch), never `master` directly.
- **One tracked commit per round** with a real message (what changed, what you ran, the result) —
  see `docs/IMPLEMENTATION_GOAL.md §8`. Each commit leaves the suite green.
- Keep `docs/BUILD_LOG.md` current.
- Never mark work done on "it compiles" — done means the self-run + tests + audit all pass
  (`IMPLEMENTATION_GOAL.md §6/§7`).
