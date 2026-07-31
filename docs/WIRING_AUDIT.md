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
| `discover/archive.cycles_for` | past admissions cycles → next-cycle projection | imported by nothing | **wired** (round AM) → `profile.deadline_projection`, `--archive` |
| `score/programs.group_by_program` | one application per program, not per professor | imported by nothing | **blocked**, and the reason is sharper than it looked — B-009 |
| `model/runs.save_checkpoint` (+`latest_checkpoint`, `incomplete_tasks`) | durable checkpoints | imported by nothing | **removed** (round AM); the real gap is B-011 |
| `model/units.set_unit_coverage`, `get_unit` | store accessors on the unit table | imported by nothing | kept — a store API may have a getter; that is not the same defect |
| `preflight.contact_email` | env accessor | callers read the env directly | **wired** (round AM): three call sites now go through it |
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


---

## Round AM — closing it out

Four of the six findings are now resolved; the two that are not are blocked on things this
audit could not decide alone, and both entries say so precisely.

**`discover/archive.py` is wired.** The question that held it up was answered the strict way:
a projection **never enters `fields`**, not carefully and not at a lower confidence. There is
no snapshot of a future date, so the D-010 quote gate has nothing to gate — the honest place is
`profile`, beside `match`, which is exactly the precedent that block set. `--archive` (and a
wizard checkbox) opt in; it runs only for professors whose page published no deadline, reads at
most five archived captures, refuses below three cycles, and returns its refusal *reason*
rather than silence, because "we looked and could not" and "we never looked" are different
answers and only one of them is a reason to go and check the page yourself.

**The checkpoint API is gone rather than adopted.** `save_checkpoint`/`latest_checkpoint`/
`incomplete_tasks` were a stage-cursor design that resume never used — resume runs entirely on
`target_stage_done`. Keeping both was the condition that produces drift, and the unused one
read as coverage the product did not have: a reader could reasonably conclude a crashed run
resumed its *discovery*, which it does not. Removed, with the real gap written down as B-011.

**`score/programs.py` stays unwired, and the entry now says why properly.** The first reading
was "add a program extractor". Building that would have made things worse: `group_by_program`
groups on a program **id**, and a name scraped off a professor's own page is not one — three
spellings of one programme either fragment a shared application into singletons or merge two
separate ones, and the module's claim is *you apply and pay once*, which is a statement about
somebody's money. The identity that would work is the **application URL**: shared, stable,
citable, and reachable by the crawler that already follows same-site links.

**Still on the list, not yet done:** when rung 7's top-ranked candidate yields nothing,
candidates 2 and 3 are never tried. It is a real quality gap — the Tavily paste that proved
ranking mattered also showed the 2nd and 3rd hits were often the useful ones — but it
multiplies fetch cost per professor, so it wants its own round with the cost measured rather
than a bolt-on here.
