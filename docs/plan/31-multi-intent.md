# MI — Multiple intents, and filtering the dashboard by supervision level

← [`README.md`](README.md) · [`00-invariants.md`](00-invariants.md)

**Size: M · Risk: low–med.** No spike needed for MI-1…MI-2; MI-3 rides on P5's spike.

## What Ahmed asked for

A student is rarely looking for exactly one thing. Someone may be open to a **PhD**, a
**pre-PhD** position, or a **master's** — and today step 1 makes them pick one. Let them tick
several, and then let them **filter the dashboard** by which levels each professor actually
supervises.

## What makes this feasible now

The vocabulary already lines up. `extract/llm_claims.SUPERVISION_LEVELS` and
`cli.PLAN_INTENT_KINDS` are the **same seven values**:

```
training · pre_master · pre_phd · mentor · master · phd · postdoc
```

So "I want a PhD supervisor" and "this person takes PhD students" are already expressed in one
language, with no translation layer between them. That was designed in deliberately.

## What is honest to say about today

**`intent_kind` is currently carried but never read.** It is validated, stored in the plan and
logged by the worker; nothing in `discover/` or `pipeline.py` uses it to change what is searched
or scored. Two consequences:

- making it a list is **low-risk** — nothing downstream can break, because nothing downstream
  consumes it
- the feature's value is entirely in **MI-3** (telling the model what to look for) and **MI-4**
  (the filter). MI-1/MI-2 alone would change nothing a student can see

---

## MI-1 · Multi-select intents in the wizard `[x]`

**Files**: `src/supervisorly/export/webapp.py`, `tests/test_webapp.py`

- [x] MI-1.1 Step 1 intent cards become **checkboxes**, not radios (`name="intent"` → a checkbox
      group). Keep the existing card styling
- [x] MI-1.2 At least one must be chosen — the error says which step and what to do
- [x] MI-1.3 `gatherYou()` collects an array; `state.intents`
- [x] MI-1.4 A previously saved single value still loads (a returning student's session)
      — *the wizard keeps NO client-side state (D-069: no localStorage, no cookies), so there
      is no saved session to restore. The "single value still loads" case is real but lives in
      the **plan shape**: `ladder.plan_intents` reads a scalar-only plan, Scan Studio's
      `defaults.intent_kind` prefill still works, and the CLI's `--plan` path is covered.*
- [x] MI-1.5 Tests: two ticked → both in the plan; none ticked → a clear error, never a silent
      default

**Done, 2026-07-29.** The group's ARIA role changed with it: a checkbox group announced as a
`radiogroup` tells a screen-reader user to pick exactly one, which is the opposite of the
change. Ordering is **card order**, not tick order — the DOM is the only stable ordering the
page has, so the derived scalar does not depend on which box was clicked first. Both MI-1.5
cases are driven through the page's own listeners in the click-through harness; asserting the
source contains the right lines would only prove it was typed.

**Review** `[R]`

## MI-2 · The plan carries a list `[x]`

**Files**: `src/supervisorly/cli.py`, `src/supervisorly/webapi.py`, `tests/test_multi_field.py`

- [x] MI-2.1 Plan gains `intent_kinds: [str]`; **`intent_kind` stays** as the first element,
      derived — the same "list is the truth, scalar is derived" rule as `fields` / `field`
- [x] MI-2.2 `_plan_value_errors` validates every entry against `PLAN_INTENT_KINDS`; an unknown
      value fails loud
- [x] MI-2.3 Empty list → reject. A search for nothing is a mangled intent, not a wide search
- [x] MI-2.4 `ladder.plan_intents(plan)` reads both shapes, exactly like `plan_fields` — one
      reader serves old plans and new
- [x] MI-2.5 Tests: the derived scalar never becomes a phantom eighth intent (the bug
      `plan_fields` had, where merging the list with its own join invented a field nobody works in)

**Done, 2026-07-29.** `cli.normalize_plan_intents` **re-derives** the scalar rather than
trusting the one it was sent, and both entry paths call it — the CLI where it builds a plan,
and `webapi.scan_start` **before** the job key is computed, so a plan arriving with a stale
scalar produces the same idempotency key as the corrected one. Trusting a client-sent scalar
would have meant `scorer.gates_for` scoring a run for a level the student did not pick.

A test pins that `cli.PLAN_INTENT_KINDS` and `llm_claims.SUPERVISION_LEVELS` remain the same
seven words. If they ever diverge, something has to map between them — and that mapping is the
synonym table D-038 forbids.

**Review** `[R]`

## MI-3 · Tell the model what the student is looking for `[!]` blocked on P5

**Files**: `src/supervisorly/extract/llm_claims.py`, `src/supervisorly/pipeline.py`

- [ ] MI-3.1 `build_prompt(..., wanted_levels)` — name the levels the student cares about so
      extraction is aimed, not exhaustive
- [ ] MI-3.2 The output vocabulary stays the **fixed enum**. A page saying "research assistant",
      "graduate assistant" or "PhD candidate positions" maps to a level **because the model read
      the sentence**, never because we shipped a synonym table
- [ ] MI-3.3 The quote still governs: a `supervises` claim needs a verbatim sentence like any
      other field
- [ ] MI-3.4 Levels outside the student's selection are still recorded if the page states them —
      the student asked what to *prioritise*, not what to *hide*

**Depends on** P5 ([`23-p5-model.md`](23-p5-model.md)).

> **`[!]` Not built, 2026-07-29 — P5 has not shipped.** There is no model-extraction call to
> pass `wanted_levels` into, so `build_prompt` has no caller that could use it. The plumbing
> it needs is already in place and waiting: `ladder.plan_intents(plan)` returns exactly the
> list MI-3.1 wants, and the export already carries it as `run.intents`. Do MI-3 in the same
> change as P5-1, not before.

> **Do not build a synonym dictionary for levels.** "Assistant", "candidate", "doctoral
> researcher" and their equivalents in every language are exactly the lookup table
> [D-038](../DECISIONS.md) forbids — it would work for the phrasings someone thought of and fail
> silently for the rest. The model reads the prose; the enum is only the shape of its answer.

**Review** `[ ]`

## MI-4 · Filter the dashboard by level `[x]`

**Files**: `src/supervisorly/export/dashboard.py`, `tests/test_dashboard_actions.py`

- [x] MI-4.1 Filter chips above the table, one per level, plus **Unknown**
- [x] MI-4.2 The student's chosen intents are pre-selected; everything is still reachable
- [x] MI-4.3 Counts on each chip — "phd 14 · master 6 · unknown 203"
- [x] MI-4.4 Filtering is client-side over the existing `DATA.professors`; no new request
- [x] MI-4.5 Works with the existing text filter (they compose, not conflict)

**Done, 2026-07-29.** Which chips render: every level anyone actually states, **plus** every
level the student asked for (so their own choice is always visible and untickable even when
nothing has matched it yet), plus `unknown`, always. Pre-selection needed the plan's intents
on the dashboard, which the export did not carry — `_build_result` now emits `run.intents`.
A professor stating two levels counts in both chips and matches either.

**Review** `[R]`

## MI-5 · The honesty rule for the filter `[x]`

The dangerous part of any filter is what it **hides**.

- [x] MI-5.1 A professor with **no `supervises` claim is `unknown`, never "no"**. We did not
      find a statement; that is not the same as the person not taking PhD students
- [x] MI-5.2 **`unknown` is shown by default.** A student filtering to "phd" must not silently
      lose 203 professors we simply have no statement about — which, on today's data, would hide
      almost everyone
- [x] MI-5.3 The empty state says which empty it is: *"No professor is confirmed to supervise at
      this level. 203 have no statement either way — clear the filter to see them."*
- [x] MI-5.4 Tests: filtering never removes an `unknown` unless the student explicitly unticks it

**Acceptance** — a level filter narrows the visible list, states how many are unknown rather
than hiding them, and can always be cleared back to everything.

**Done, 2026-07-29.** `unknown` is not merely *included* in the default selection — any
non-`value` state (`searched_absent`, `blocked`, `never_attempted`) is read as unknown too,
because none of them is a statement that the person does not supervise at that level.

Two decisions the tests pin:
- **Today, `supervises` is not even a declared export field** (it arrives with P5), so every
  professor is `unknown` and the chip row carries an explicit note saying so. A filter that
  silently rendered seven zero chips would look broken; one that dropped unknowns would show
  an empty dashboard for a scan that found 428 people.
- The chips can be unticked to **nothing**. That is a state the student chose, and the empty
  message names it and how to undo it — silently re-ticking would override their instruction.

The filter runs against the page's REAL embedded JavaScript in Node (the
`test_webapp_clickthrough.py` pattern), not a Python re-description of the same logic, which
could drift from what ships.

**Review** `[R]`

---

## Edge cases

| case | handling |
|---|---|
| **No level claims exist yet** (before P5 ships) | Every professor is `unknown`; the filter renders with one chip and an honest note. It must not look broken |
| A page states a level the student did not select | Recorded and shown; the selection is a priority, not a censor |
| A page states several levels | All recorded — `supervises` is already a comma list over the enum |
| Contradictory statements across sources | The conflicts table already handles it (D-010); the filter reads the winning head |
| A student ticks every level | Identical to no filter — allowed, not an error |

## Why this is not just a UI nicety

Once `supervises` is populated, it is the **first field that answers the student's actual
question** — not "is this person recruiting" in the abstract, but "do they take people at my
level". The filter is where the whole harvest chain becomes usable rather than merely complete.
