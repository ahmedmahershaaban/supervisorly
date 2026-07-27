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

### If this is revisited

The trigger to revisit is the throttle arithmetic: if students hit the 30/h map cap in
normal use, move the merge behind `/api/map` (accept `queries[]`, delegate to
`subject_map_multi`), keep per-variant failure reporting in the response body so the
page's honest "N phrasings could not be mapped" note survives, and retire the JS merge.
