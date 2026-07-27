# Blockers and recorded deviations

The contract (`IMPLEMENTATION_GOAL.md` §1, §7) says: when the build hits a genuine
ambiguity, or when the shipped code diverges from a written plan, **record it here with
evidence — never silently deviate**. This file had never been created; the entry below
is the first, found during the W8 verification round.

Open items are listed first. An item is closed by recording the decision that resolved
it, not by deleting it.

---

## B-001 — The multi-phrasing subject-map merge is client-side, not `subject_map_multi`

**Status:** resolved by decision (Ahmed, 2026-07-27) — documented, not refactored.
**Found:** W8 verification round, while auditing the web surface.

### What the plan said

`docs/FIREBASE_WEB_PLAN.md` §7 step 2 asked for:

> `subject_map_multi` + ladder `max_institutions` + tests (merge/rank/`found_by`, cap honesty)

### What shipped

`subject_map_multi()` exists in `src/supervisorly/discover/subjects.py` and is correct
and unit-tested (4 tests in `tests/test_subjects.py`), but **nothing calls it**. Step 5
(`export/webapp.py`) instead does the merge in the browser: the page calls
`POST /api/expand` once, then `GET /api/map` **once per phrasing**, and merges the
results in JS by `topic_id` with `found_by` tags (`export/webapp.py` §"step 2", the
`mergeMaps` function). `/api/map` still takes a single `field`.

So the capability the plan named was built twice — once in Python, unused, and once in
JavaScript, shipped — and the Python half became dead code.

### The trade-off (why this is a real decision, not a cleanup)

Client-side merge (what ships):

- **Graceful per-variant failure.** One phrasing failing does not fail the click; the
  page continues with the rest and says so ("N phrasings could not be mapped —
  continuing with the rest"). `subject_map_multi` has no equivalent — a failing variant
  would either contribute nothing silently or take the whole call down.
- Per-variant progress feedback while the maps come back.

Server-side merge (`subject_map_multi`):

- **Cheaper for the student's budget.** Each `/api/map` call spends one unit of the
  30/h throttle, so one *Understand* click with 8 phrasings costs 8/30 of the hourly
  allowance — fewer than 4 clicks an hour. Server-side it would cost 1.
- One cold start instead of N (§5.1 flags cold starts as a real cost).
- The merge logic would live in tested Python rather than in the page.

### Decision

**Document, do not refactor.** Moving the merge server-side changes the `/api/map`
contract and requires rewriting step 2 and its tests — not work that belongs in a
verification round, and not a change to make silently when the shipped behaviour is
correct and covered. Recorded as [D-070](DECISIONS.md#d-070--the-multi-phrasing-subject-map-merge-is-client-side)
so the divergence is a choice on the record rather than an accident.

`subject_map_multi` is **kept** as the server-side counterpart, with its docstring
saying plainly that it is currently unused and pointing here — so nobody reads it as
live code, and nobody rewrites it from scratch if the throttle cost above ever makes
the server-side merge worth doing.

### If this is revisited (B-001)

The trigger to revisit is the throttle arithmetic: if students hit the 30/h map cap in
normal use, move the merge behind `/api/map` (accept `queries[]`, delegate to
`subject_map_multi`), keep per-variant failure reporting in the response body so the
page's honest "N phrasings could not be mapped" note survives, and retire the JS merge.

---

## B-002 — Stage 4 ("people around the professor") is unbuilt, and two docs disagree on whether it may be exported

**Status:** OPEN — needs Ahmed. Implementation deliberately **not** started.
**Found:** 2026-07-28, while closing the last node the atlas code-map showed as unbuilt.

### What is missing

Stage 4 appears in `product-flow.md`, in the PIPELINE map of both atlases, and in
`SKILL.md` prose. **No module implements any of it.** Two distinct fields are specified:

- **`recent_collaborators`** ([D-016](DECISIONS.md#d-016--students-is-not-obtainable-ship-recent_collaborators-instead)) —
  frequent recent co-authors at the same institution. The always-available proxy. The
  naming rule is hard: *collaborators*, never *students*.
- **`former_doctoral_students`** ([D-025](DECISIONS.md#d-025--past-students-are-obtainable-current-students-still-are-not),
  [D-062](DECISIONS.md#d-062--former_doctoral_students-is-a-per-registry-advisor-verified-capability--not-a-universal-headline)) —
  registry-sourced, advisor-verified, only where a national registry confirms an advisor
  field (France's theses.fr does; most do not; Canada unverified). An honest null elsewhere.

### The contradiction

`product-flow.md` §"Stage 4" says the panel is **"display-only and never exported"**.

[D-024](DECISIONS.md#d-024--evaluative-judgements-about-individuals-stay-local-and-unexported)
draws the line differently: *"Facts with citations export; judgements do not."* A co-author
list derived from OpenAlex is a cited fact, not a model judgement, so by D-024 it exports.

Both cannot be followed. And the choice is not cosmetic: the dashboard is **built from the
export**, so "never exported" effectively means "cannot be shown in the dashboard either",
which would make the whole stage pointless as specified.

`LabMember` is *not* the ambiguous case — `domain-model.md` marks it display-only and
never exported explicitly, and that is unambiguous.

### Why this was not resolved by picking the safer reading

The subject is **lists of named third parties** — mostly early-career researchers who never
asked to appear in a supervisor-search tool and have no right of reply. D-024's own
rationale is that aggregating claims about identifiable people into a shareable artifact is
"defamation-adjacent and a guaranteed source of takedown mail"; the same reasoning applies
to aggregation even when each item is individually factual, and it engages the GDPR posture
in `ethics-and-compliance.md`.

Choosing an interpretation here decides what personal data the product publishes about
people who are not its users. That is a product and legal call, not an implementation
detail, and the contract is explicit: *never contradict a locked decision; record it here
instead of silently deviating.*

### The decision needed from Ahmed

1. **Does `recent_collaborators` leave the machine?** In the JSON export and the dashboard
   (D-024's "facts with citations export"), or strictly local like `LabMember`
   (product-flow's "never exported")? Whichever is chosen, the *other* document must be
   corrected in the same change so this cannot resurface.
2. **Is Stage 4 wanted at all in v1?** It is the only stage with no code. The product works
   without it; the shipped dashboard simply has no people panel.
3. If yes: **which registries** for `former_doctoral_students`? Only theses.fr is confirmed.
   Shipping France-only is honest; shipping it as a headline feature would not be.

Until then the atlas keeps `people search` labelled **not built**, which is accurate.
