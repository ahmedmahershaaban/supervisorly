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

## MI-1 · Multi-select intents in the wizard `[ ]`

**Files**: `src/supervisorly/export/webapp.py`, `tests/test_webapp.py`

- [ ] MI-1.1 Step 1 intent cards become **checkboxes**, not radios (`name="intent"` → a checkbox
      group). Keep the existing card styling
- [ ] MI-1.2 At least one must be chosen — the error says which step and what to do
- [ ] MI-1.3 `gatherYou()` collects an array; `state.intents`
- [ ] MI-1.4 A previously saved single value still loads (a returning student's session)
- [ ] MI-1.5 Tests: two ticked → both in the plan; none ticked → a clear error, never a silent
      default

**Review** `[ ]`

## MI-2 · The plan carries a list `[ ]`

**Files**: `src/supervisorly/cli.py`, `src/supervisorly/webapi.py`, `tests/test_multi_field.py`

- [ ] MI-2.1 Plan gains `intent_kinds: [str]`; **`intent_kind` stays** as the first element,
      derived — the same "list is the truth, scalar is derived" rule as `fields` / `field`
- [ ] MI-2.2 `_plan_value_errors` validates every entry against `PLAN_INTENT_KINDS`; an unknown
      value fails loud
- [ ] MI-2.3 Empty list → reject. A search for nothing is a mangled intent, not a wide search
- [ ] MI-2.4 `ladder.plan_intents(plan)` reads both shapes, exactly like `plan_fields` — one
      reader serves old plans and new
- [ ] MI-2.5 Tests: the derived scalar never becomes a phantom eighth intent (the bug
      `plan_fields` had, where merging the list with its own join invented a field nobody works in)

**Review** `[ ]`

## MI-3 · Tell the model what the student is looking for `[ ]`

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

> **Do not build a synonym dictionary for levels.** "Assistant", "candidate", "doctoral
> researcher" and their equivalents in every language are exactly the lookup table
> [D-038](../DECISIONS.md) forbids — it would work for the phrasings someone thought of and fail
> silently for the rest. The model reads the prose; the enum is only the shape of its answer.

**Review** `[ ]`

## MI-4 · Filter the dashboard by level `[ ]`

**Files**: `src/supervisorly/export/dashboard.py`, `tests/test_dashboard_actions.py`

- [ ] MI-4.1 Filter chips above the table, one per level, plus **Unknown**
- [ ] MI-4.2 The student's chosen intents are pre-selected; everything is still reachable
- [ ] MI-4.3 Counts on each chip — "phd 14 · master 6 · unknown 203"
- [ ] MI-4.4 Filtering is client-side over the existing `DATA.professors`; no new request
- [ ] MI-4.5 Works with the existing text filter (they compose, not conflict)

**Review** `[ ]`

## MI-5 · The honesty rule for the filter `[ ]`

The dangerous part of any filter is what it **hides**.

- [ ] MI-5.1 A professor with **no `supervises` claim is `unknown`, never "no"**. We did not
      find a statement; that is not the same as the person not taking PhD students
- [ ] MI-5.2 **`unknown` is shown by default.** A student filtering to "phd" must not silently
      lose 203 professors we simply have no statement about — which, on today's data, would hide
      almost everyone
- [ ] MI-5.3 The empty state says which empty it is: *"No professor is confirmed to supervise at
      this level. 203 have no statement either way — clear the filter to see them."*
- [ ] MI-5.4 Tests: filtering never removes an `unknown` unless the student explicitly unticks it

**Acceptance** — a level filter narrows the visible list, states how many are unknown rather
than hiding them, and can always be cleared back to everything.

**Review** `[ ]`

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
