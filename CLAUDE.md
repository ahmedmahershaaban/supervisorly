# CLAUDE.md — working in the Supervisorly repo

Supervisorly helps a student find a research supervisor (PhD / master's / postdoc) in **any
country**, with every fact backed by a citable source. It has **two surfaces over one engine**:
the **Claude-Code skill + agents + tools**, and a **hosted web app** (D-069) — deployed at
`supervisorly.web.app`, a 5-step wizard that runs the same scan as a background job. This file
orients any Claude instance working here.

## Read first
- `docs/HANDOVER.md` — the map of everything.
- `docs/DECISIONS.md` — **binding.** 70 numbered decisions (D-001…D-070). Never contradict a
  locked decision; if you think one is wrong, record it in `docs/BLOCKERS.md`, don't silently
  deviate.
- `docs/IMPLEMENTATION_GOAL.md` — the build/self-test/refine/completion contract.
- `docs/architecture.md`, `docs/product-flow.md`, `docs/domain-model.md` — how it works.
- `docs/FIREBASE_WEB_PLAN.md` + `firebase/README.md` — the web product and its deploy runbook;
  `docs/WEB_COMPLETION_REPORT.md` §4b lists the defects that only a real deploy could find.

## Governing constraints (violating any is a defect, not a choice)
- **Generate, don't look up** (D-038): no embedded university list, no keyword dictionary; the
  search strategy is generated per query. Enum of categories = allowed; dictionary of a field's
  search terms = forbidden.
- **The corpus is methodology-only** (D-035): never read/import/ship anything from
  `C:\Users\ahmed\Documents\Downloads` as data, seed, or fixture. Every real fact must be one the
  tool fetched itself, live, from a citable public source.
- **Deterministic layer has no LLM** (D-009): `src/supervisorly/{discover,fetch,model,score,export}`
  contain zero model calls. The LLM judgement lives in `.claude/agents/`. **One sanctioned
  exception** (D-068): `discover/expand.py` may ask an LLM for *search queries, never claims* —
  it is fail-closed (no key → the student's own words), and every fact still passes the D-010
  quote gate, so a bad expansion can only cost topics, never mint a professor or a deadline.
- **The web tier is honest, private, and stoppable** (D-069/D-070): endpoints are rate-limited;
  a job id is an unguessable access token and jobs are never listable; results are personal data
  (private bucket, short-lived signed URLs, 7-day delete); cancel is graceful and every terminal
  state is resumable — never a dead end. The multi-phrasing subject-map merge lives client-side
  (D-070) so one failing phrasing cannot fail the click.
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
  `python -m pytest`. Set `TMPDIR` **outside the repo** first, or the D-005 guard correctly
  fires on pytest's `tmp_path` and one CLI test fails for the wrong reason.
- The web app locally is two commands: `python -m supervisorly.webapi --port 8765` serves the
  **API only**, and the page is generated separately with
  `build_webapp(api_base='http://localhost:8765')`. Deploying is `firebase/README.md`, run from
  the `firebase/` folder.
- Work on `build/v1` (or a feature branch), never `master` directly.
- **One tracked commit per round** with a real message (what changed, what you ran, the result) —
  see `docs/IMPLEMENTATION_GOAL.md §8`. Each commit leaves the suite green.
- Keep `docs/BUILD_LOG.md` current.
- Never mark work done on "it compiles" — done means the self-run + tests + audit all pass
  (`IMPLEMENTATION_GOAL.md §6/§7`).

# context-mode — MANDATORY routing rules

You have context-mode MCP tools available. These rules are NOT optional — they protect your context window from flooding. A single unrouted command can dump 56 KB into context and waste the entire session.

## BLOCKED commands — do NOT attempt these

### curl / wget — BLOCKED
Any Bash command containing `curl` or `wget` is intercepted and replaced with an error message. Do NOT retry.
Instead use:
- `ctx_fetch_and_index(url, source)` to fetch and index web pages
- `ctx_execute(language: "javascript", code: "const r = await fetch(...)")` to run HTTP calls in sandbox

### Inline HTTP — BLOCKED
Any Bash command containing `fetch('http`, `requests.get(`, `requests.post(`, `http.get(`, or `http.request(` is intercepted and replaced with an error message. Do NOT retry with Bash.
Instead use:
- `ctx_execute(language, code)` to run HTTP calls in sandbox — only stdout enters context

### WebFetch — BLOCKED
WebFetch calls are denied entirely. The URL is extracted and you are told to use `ctx_fetch_and_index` instead.
Instead use:
- `ctx_fetch_and_index(url, source)` then `ctx_search(queries)` to query the indexed content

## REDIRECTED tools — use sandbox equivalents

### Bash (>20 lines output)
Bash is ONLY for: `git`, `mkdir`, `rm`, `mv`, `cd`, `ls`, `npm install`, `pip install`, and other short-output commands.
For everything else, use:
- `ctx_batch_execute(commands, queries)` — run multiple commands + search in ONE call
- `ctx_execute(language: "shell", code: "...")` — run in sandbox, only stdout enters context

### Read (for analysis)
If you are reading a file to **Edit** it → Read is correct (Edit needs content in context).
If you are reading to **analyze, explore, or summarize** → use `ctx_execute_file(path, language, code)` instead. Only your printed summary enters context. The raw file content stays in the sandbox.

### Grep (large results)
Grep results can flood context. Use `ctx_execute(language: "shell", code: "grep ...")` to run searches in sandbox. Only your printed summary enters context.

## Tool selection hierarchy

1. **GATHER**: `ctx_batch_execute(commands, queries)` — Primary tool. Runs all commands, auto-indexes output, returns search results. ONE call replaces 30+ individual calls.
2. **FOLLOW-UP**: `ctx_search(queries: ["q1", "q2", ...])` — Query indexed content. Pass ALL questions as array in ONE call.
3. **PROCESSING**: `ctx_execute(language, code)` | `ctx_execute_file(path, language, code)` — Sandbox execution. Only stdout enters context.
4. **WEB**: `ctx_fetch_and_index(url, source)` then `ctx_search(queries)` — Fetch, chunk, index, query. Raw HTML never enters context.
5. **INDEX**: `ctx_index(content, source)` — Store content in FTS5 knowledge base for later search.

## Subagent routing

When spawning subagents (Agent/Task tool), the routing block is automatically injected into their prompt. Bash-type subagents are upgraded to general-purpose so they have access to MCP tools. You do NOT need to manually instruct subagents about context-mode.

## Output constraints

- Keep responses under 500 words.
- Write artifacts (code, configs, PRDs) to FILES — never return them as inline text. Return only: file path + 1-line description.
- When indexing content, use descriptive source labels so others can `ctx_search(source: "label")` later.

## ctx commands

| Command | Action |
|---------|--------|
| `ctx stats` | Call the `ctx_stats` MCP tool and display the full output verbatim |
| `ctx doctor` | Call the `ctx_doctor` MCP tool, run the returned shell command, display as checklist |
| `ctx upgrade` | Call the `ctx_upgrade` MCP tool, run the returned shell command, display as checklist |
