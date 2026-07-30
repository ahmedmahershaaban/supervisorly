# Wiring audit — what was built, tested, and called by nothing

**Round AK, 2026-07-30.** Third time this shape of defect has surfaced (`extract/llm_claims.py`,
`fetch/render.BatchRenderer`, `score/scorer.py`), so this time it was looked for systematically
instead of stumbled on.

## Method

`ast`-walk every `.py` under `src/supervisorly` (62 modules, 361 public symbols). For each
public symbol, ask whether any **other** src module ever names it — as a `Name`, an
`Attribute`, an `ImportFrom` target, or a string literal (dispatch tables). Cross-reference
against the 72 test files and against `tools/`.

The signal is the **[tested but not called] quadrant**. A green suite says the code is
correct; it never says anything calls it. Every defect below had passing tests.

Two classes of false positive were filtered by hand:

* a symbol used only inside its own module (`openalex.author_url`, `webapi.handle_*` behind
  `route_request`, `cli.cmd_*` behind `set_defaults`) — wired, just locally;
* a symbol reached through a subclass (`ChromiumRenderer` is instantiated as `BatchRenderer`).

Script kept out of the repo: it is a one-off, and a lint rule that fires on legitimate
single-module helpers would be turned off within a week. Re-run it before a release round.

## Findings

| Module / symbol | What it does | Was | Now |
|---|---|---|---|
| `score/ranking.rank_universities` | rolls professors up to their institution, ranked | imported by nothing | **wired** → `run.universities` |
| `export/delta.compute_delta` | what changed since the previous scan | imported by nothing | **wired** → `scan --compare-to` |
| `model/conflicts.open_conflicts` | the contested set | write half wired, read half not | **wired** → `profile.contested_fields` |
| `ingest.ingest_md` | parses the human rung's Markdown reply | imported by nothing | **wired** → `supervisorly ingest-md` |
| `discover/archive.cycles_for` | past admissions cycles → next-cycle projection | imported by nothing | **deferred**, see below |
| `score/programs.group_by_program` | one application per program, not per professor | imported by nothing | **blocked**, see below |
| `model/runs.save_checkpoint` (+`latest_checkpoint`, `incomplete_tasks`) | durable checkpoints | imported by nothing | **redundant**, see below |
| `model/units.set_unit_coverage`, `get_unit` | per-department coverage note | imported by nothing | open, low value |
| `preflight.contact_email`, `openalex_key` | env accessors | callers read the env directly | cosmetic duplication |
| `phases.PhaseFlags.is_on/of/all_off/summary` | phase gating helpers | gating goes through `off()`/`off_reason()` | not a defect |

### The one that mattered most: the human rung had no return path

`extract/chrome_prompt.py` generates the prompt the dashboard hands the student for a blocked
field, and embeds its required output shape by calling `md_grammar.emit()` on a worked example.
So the student is asked, by name, for `## field:` Markdown blocks.

**No command parsed that grammar back.** `ingest-page` takes raw page *text* and runs the
deterministic extractors over it — a different rung entirely. `ingest.ingest_md`, written for
exactly this and tested in `test_resume.py`, was called by nothing.

The emitting half shipped, the receiving half did not, and the seam between them is a
generated prompt — so nothing failed, no test went red, and the student simply had nowhere to
put the answer. A blocked field that offers a prompt and accepts no reply is the dead end
D-070 forbids.

Fixed by `supervisorly ingest-md --file reply.md --db output/supervisorly.sqlite`.
`test_wiring_round.py` pins emitter and parser to the same worked example so they cannot drift
apart again silently.

### Deferred: `discover/archive.py` (Wayback cycle projection)

The highest-value item still unwired, because `deadline` is the field that comes back
`NOT_FOUND` most often. An admissions page publishes one deadline; its archive shows the same
page across several years, and the pattern says roughly when the next cycle opens.

Not wired in this round because it needs three decisions recorded first, not because it is
hard:

1. **A new external endpoint** (`web.archive.org` CDX) — `test_no_seed_urls` must gain an
   allowlist entry with reasoning, on the same terms as the four search providers.
2. **A projection is not a claim.** It must never enter the quote-gated `fields` block: no
   snapshot of a *future* deadline exists to verify a quote against. It belongs beside `match`
   as run-level arithmetic — `profile.deadline_projection`, carrying the cycles it came from.
3. **Robots and pacing** apply to `web.archive.org` like any host.

The module already refuses to project from fewer than 3 cycles, which is the hard part.

### Blocked: `score/programs.py`

`group_by_program` groups professors by a `program` dict — and **nothing ever sets one.**
There is no `program` field descriptor and no extractor that produces one. Wiring it today
would emit N singleton groups, each announcing "One application", which is noise dressed as
insight.

The real fix is upstream: extract the graduate program a professor's department belongs to,
then group. Tracked in `BLOCKERS.md` as the prerequisite; the roll-up code is ready and
correct once it has an input.

### Redundant: the `runs` checkpoint API

`save_checkpoint` / `latest_checkpoint` / `incomplete_tasks` are a durable-checkpoint design
that resume never adopted — `--resume` works through `runs.target_stage_done`, which is
simpler and already covers the case. Two mechanisms for one job is worse than one. Either
delete them or adopt them for the web tier's resumable jobs (D-069); leaving both is the
state that produced this audit.

### Also noted

`score/ranking.rank_professors` is now genuinely redundant with `pipeline._match_rating` plus
the export sort — same score, one ordering. Kept for the moment because `rank_universities`
lives in the same module and reuses its imports; delete it when that module is next touched.

## What shipped in this round

* `run.universities` — every scan now answers "which university", not only "which person".
* `scan --compare-to <prev.json>` — a re-scan reports what moved.
* `profile.contested_fields` + a `CONTESTED` line in coverage — a field two sources disagreed
  about no longer displays exactly like one they agreed on.
* `supervisorly ingest-md` — the human rung's reply has somewhere to go.
* `--institution-types` — the institution pool is selectable (see `CLI_RUNBOOK.md`), replacing
  the `--all-institution-types` on/off switch.

28 new tests in `tests/test_wiring_round.py`. Each pins a *connection*, so it fails if the
call is removed even though the module underneath stays correct and tested — which is the
failure mode this whole audit existed to catch.
