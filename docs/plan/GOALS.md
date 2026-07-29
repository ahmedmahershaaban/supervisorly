# GOALS — paste-ready `/goal` strings, in order

← back to [`README.md`](README.md)

One goal per **shippable slice**. Do not set a single goal for the whole plan: seven phases
with spike gates cannot complete in one run, two spikes may come back under threshold and
change the plan, and the 5-scans-per-hour throttle bounds how much can be verified in a
session. A goal that cannot finish simply loops.

Copy a block below and paste it after `/goal`.

---

## What makes these goals verifiable

Three properties, worth keeping if you write your own:

1. **Name the artefact, not the intent.** *"the modal visibly shows role and department, with a
   screenshot"* is checkable. *"P0 is done"* is not.
2. **Include the spike as a stop condition.** Without it a phase gets built against a yield
   nobody measured — which is exactly how three estimates went wrong in one session (90%, 24%,
   "fixes the blocked rows" → 0%, 0/11, 3/24).
3. **Require both tiers deployed and the worker digest changed.** `firebase deploy` does not
   rebuild the worker; an unchanged sha256 means the scanner did not change, whatever the
   deploy said.

## The shared tail

Every goal below ends with this. It is repeated in each block so a block can be pasted alone.

> Done means ALL of: `python -m pytest` green with `TMPDIR` outside the repo; both tiers
> deployed per `docs/plan/90-ops-deploy.md` OPS-1..OPS-7 including the worker image digest
> actually changing; one real scan run end to end and verified with headful Chrome via
> `tools/e2e/record_flow.js` with every check passing; a screenshot of the new surface; and the
> completed subtasks marked `[x]` and `[R]` in the plan file. If the 5-scans-per-hour throttle
> blocks testing, lift it as its own commit and revert it in the same session, as in
> `a6fd713` / `2e80d7d`.

---

# GOAL 1 — ledger, flags, and the first real content

*Slice: CC-1, FLAG, SPIKE-0, P0. Ends with role + department visible in the modal.*
*Do this first: CC-1 and FLAG make every later phase safe to ship half-finished.*

```
Implement docs/plan/10-cross-cutting.md CC-1 (phase ledger) and FLAG (phase feature
flags), then run SPIKE-0 from docs/plan/01-spikes.md and record the measured number in
docs/plan/20-p0-orcid.md. If SPIKE-0 is at or above 30%, implement P0-1, P0-2 and P0-3
in full. If it is below 30%, STOP and report the number instead of building P0.

Rules: obey the seven invariants in docs/plan/00-invariants.md. Every failure is a state
with a reason, never an exception. No cross-session cache. No seeded URLs —
tests/test_no_seed_urls.py stays green. A former ORCID employment must never be shown as
current.

Done means ALL of: python -m pytest green with TMPDIR outside the repo; both tiers
deployed per docs/plan/90-ops-deploy.md OPS-1..OPS-7 including the worker image digest
actually changing; one real scan run end to end and verified with headful Chrome via
tools/e2e/record_flow.js with every check passing; the professor modal visibly showing
role and department from ORCID for at least one professor, with a screenshot; and the
completed subtasks marked [x] and [R] in the plan files. If the 5-scans-per-hour throttle
blocks testing, lift it as its own commit and revert it in the same session, as in
a6fd713 / 2e80d7d.
```

---

# GOAL 2 — multiple intents and the level filter

*Slice: MI-1, MI-2, MI-4, MI-5. Standalone — no spike, touches only the wizard and dashboard.*

```
Implement docs/plan/31-multi-intent.md: MI-1 (multi-select intent checkboxes at step 1),
MI-2 (plan carries intent_kinds as a list with intent_kind derived as the first element,
plus ladder.plan_intents reading both shapes), MI-4 (dashboard filter chips per
supervision level with counts, composing with the existing text filter), and MI-5 (the
honesty rules for the filter). Do MI-3 only if P5 is already shipped; otherwise mark it
[!] blocked-on-P5 and say so.

Hard rules from docs/plan/00-invariants.md:
- NO synonym dictionary for levels. A page saying "research assistant" maps to a level
  because a model read the sentence, never because we shipped a lookup table (D-038).
  tests/test_no_seed_urls.py stays green.
- A professor with no supervises claim is `unknown`, NEVER "no". `unknown` is shown by
  default and the empty state says which empty it is.
- The derived scalar must never become a phantom eighth intent — the same bug plan_fields
  had when it merged a list with its own join. Pin it with a test.
- Failure is a state with a reason, never an exception.

Done means ALL of: python -m pytest green with TMPDIR outside the repo; both tiers
deployed per docs/plan/90-ops-deploy.md OPS-1..OPS-7 including the worker image digest
actually changing; one real scan run end to end and verified with headful Chrome via
tools/e2e/record_flow.js, extended to tick two intents at step 1 and to assert the filter
chips appear, carry counts, and never hide `unknown` professors unless explicitly
unticked — every check passing; a screenshot of the filter in use; and the completed
subtasks marked [x] and [R] in docs/plan/31-multi-intent.md. If the 5-scans-per-hour
throttle blocks testing, lift it as its own commit and revert it in the same session, as
in a6fd713 / 2e80d7d.
```

---

# GOAL 3 — deadlines on the dashboard

*Slice: CC-3, CC-5, SPIKE-1, P1. The biggest yield per fetch, and the highest risk.*

```
Implement docs/plan/10-cross-cutting.md CC-3 (host pool — concurrency across DOMAINS,
never two in-flight requests to one host, async pages not threads) and CC-5 (PDF text
extraction). Then run SPIKE-1 from docs/plan/01-spikes.md and record the number in
docs/plan/21-p1-admissions.md. If SPIKE-1 is at or above 40%, implement P1-1, P1-2 and
P1-3 in full. If below, STOP and report.

Hard rules:
- A deadline attaches at the NARROWEST scope actually discovered, records that scope, and
  never inherits across faculties. One institution-wide date applied to every professor is
  fabrication-adjacent.
- A PAST date is historical evidence, never a live deadline.
- Programme level undeterminable → refuse the claim. Wrong level is worse than none.
- Admissions info in a PDF that has no text layer blocks WITH A REASON, never silently.
- Paths are extracted from pages we fetched, never predicted.

Done means ALL of: python -m pytest green with TMPDIR outside the repo; both tiers
deployed per docs/plan/90-ops-deploy.md OPS-1..OPS-7 including the worker image digest
actually changing; one real scan run end to end and verified with headful Chrome via
tools/e2e/record_flow.js with every check passing; a screenshot of a professor modal
showing an inherited deadline WITH its scope and source; and the completed subtasks marked
[x] and [R]. If the 5-scans-per-hour throttle blocks testing, lift it as its own commit
and revert it in the same session, as in a6fd713 / 2e80d7d.
```

---

# GOAL 4 — recruiting signals from prose

*Slice: SPIKE-4, P4, SPIKE-5, P5. The judgement layer, gated by two spikes.*

```
Run SPIKE-4 from docs/plan/01-spikes.md and record the number in docs/plan/22-p4-triage.md.
If recall is at or above 90%, implement P4-1. Then run SPIKE-5 and record it in
docs/plan/23-p5-model.md; if at or above 60% of proposals survive the quote gate,
implement P5-1 and P5-2. STOP and report on any spike that misses.

Hard rules:
- A model PROPOSES; it is never the evidence. Every proposal goes through
  claims.record_claim — do not re-implement the gate.
- The quote is in the SOURCE language; only the value may be normalised.
- Triage is tuned for RECALL. Non-Latin or unknown-language text is `uncertain` and
  escalates to the model, NEVER `empty` — otherwise Arabic-language institutions silently
  return nothing.
- Batch by BYTES, not page count. Isolated context per batch, no conversation history.
- Every quote in a batch rejected → log it as a signal, do not shrug.
- Token budget exhaustion truncates and REPORTS; it never fails the run.
- With the model disabled, output must be byte-identical to today's.

Done means ALL of: python -m pytest green with TMPDIR outside the repo; both tiers
deployed per docs/plan/90-ops-deploy.md OPS-1..OPS-7 including the worker image digest
actually changing; one real scan run end to end and verified with headful Chrome via
tools/e2e/record_flow.js with every check passing; a screenshot of a professor modal
showing a recruiting or supervises claim WITH its verbatim quote and source; and the
completed subtasks marked [x] and [R]. If the 5-scans-per-hour throttle blocks testing,
lift it as its own commit and revert it in the same session, as in a6fd713 / 2e80d7d.
```

---

# GOAL 5 — the front end, finished

*Slice: CC-4, FE-1…FE-6, T-1. Independent of the harvest chain — can run any time.*

```
Implement docs/plan/10-cross-cutting.md CC-4 (re-openable sessions) and all of
docs/plan/30-frontend.md: FE-1 past searches, FE-2 step-2 polish, FE-3 progress that names
what it is waiting on, FE-4 the final professor modal, FE-5 the optional model-key panel,
FE-6 the accessibility and honest-empty-state sweep, and T-1 translation display.

Hard rules:
- A finished result is kept and re-openable; starting a new search NEVER deletes an old
  one. The job id IS the access token, so the list is localStorage only and jobs stay
  unlistable server-side.
- An expired job says so and offers to run again — never an error.
- T-1: snapshot and quote stay in the SOURCE language and the gate verifies against the
  original. quote_translated travels BESIDE the quote, never replacing it. The translation
  icon's hover says it is machine-translated and the original should be checked. A
  translated quote must never satisfy the gate — pin that with a test.
- No new state renders blank; every empty says which empty it is.
- Every new control is keyboard-reachable, labelled and focus-visible.

Done means ALL of: python -m pytest green with TMPDIR outside the repo; both tiers
deployed per docs/plan/90-ops-deploy.md OPS-1..OPS-7 including the worker image digest
actually changing; one real scan run end to end and verified with headful Chrome via
tools/e2e/record_flow.js extended to assert EVERY new surface — past searches, the cost
preview, the modal sections, the key panel, the translation icon — with every check
passing; screenshots of the past-searches panel and the finished modal; and the completed
subtasks marked [x] and [R]. If the 5-scans-per-hour throttle blocks testing, lift it as
its own commit and revert it in the same session, as in a6fd713 / 2e80d7d.
```

---

# GOAL 6 — find the professor pages at all

*Slice: SPIKE-2, P2. The expensive grind, and it contains the plan's most dangerous failure.*

```
Run SPIKE-2 from docs/plan/01-spikes.md and record the number in
docs/plan/24-p2-directory.md. If at or above 30%, implement P2-1, P2-2 and P2-3 in full.
If below, STOP and report.

Hard rules:
- Paths are EXTRACTED from pages we fetched, never predicted. Layouts differ per site and
  per country; a guessed /staff fails silently everywhere it was not designed for.
- Weak signals ORDER the queue; they never EXCLUDE from it. Budget exhaustion reports what
  went unvisited.
- Dedupe by content hash as well as URL. Cap depth, pages per institution, and repeats per
  URL pattern.
- P2-3 is the most dangerous work in the plan: attributing another person's page is worse
  than finding nothing. Require surname + initial + institution for `verified`; anything
  weaker is `unverified`; two people sharing a name at one institution → REFUSE. An
  unconfirmed match is NEVER presented as a finding, and the student's confirmation is
  recorded as dated evidence.
- Cairo University will not be reachable (broken TLS at their server). Say so in the
  ledger; do not treat it as a failure to fix.

Done means ALL of: python -m pytest green with TMPDIR outside the repo; both tiers
deployed per docs/plan/90-ops-deploy.md OPS-1..OPS-7 including the worker image digest
actually changing; one real scan run end to end and verified with headful Chrome via
tools/e2e/record_flow.js with every check passing; a screenshot of the "Is this them?"
confirmation on an unverified match; and the completed subtasks marked [x] and [R]. If the
5-scans-per-hour throttle blocks testing, lift it as its own commit and revert it in the
same session, as in a6fd713 / 2e80d7d.
```

---

# GOAL 7 — historical cycles and your own key

*Slice: SPIKE-6, P6, P7. Both small and isolated; can be done together.*

```
Run SPIKE-6 from docs/plan/01-spikes.md and record the number in
docs/plan/25-p6-archive.md. If at or above 25%, implement P6-1. Then implement P7-1 from
docs/plan/26-p7-byo-key.md and FE-5 from docs/plan/30-frontend.md if it is not already
done.

Hard rules:
- P6: FEWER THAN 3 archived cycles means NO projection — two points are not a pattern. A
  projection is labelled `watch · projected`, never `firm`. The live page always wins for
  "current". The archive is queried only for URLs P1 discovered, never one we authored.
- P7: the key lives in localStorage and is sent ONLY to Google. It must never reach our
  API, never be logged, never appear in an error message or a note, and the D-071 error
  beacon must not be able to carry it — pin all of that with tests. An invalid or
  quota-exhausted key fails closed to the student's own words, never a broken scan.
  Browser-to-Gemini CORS was verified working on 2026-07-29; if it has changed, STOP rather
  than proxying the key through our server.

Done means ALL of: python -m pytest green with TMPDIR outside the repo; both tiers
deployed per docs/plan/90-ops-deploy.md OPS-1..OPS-7 including the worker image digest
actually changing; one real scan run end to end and verified with headful Chrome via
tools/e2e/record_flow.js with every check passing; a screenshot showing a projected date
labelled as projected, and one showing the key panel; and the completed subtasks marked
[x] and [R]. If the 5-scans-per-hour throttle blocks testing, lift it as its own commit
and revert it in the same session, as in a6fd713 / 2e80d7d.
```

---

## Order

`1 → 2 → 3 → 4 → 5 → 6 → 7`

**Goals 2 and 5 are independent** of the harvest chain and can be pulled forward or run in
parallel if someone is working on the front end. Everything else depends on what came before.

## After each goal

Update the status board in [`README.md`](README.md) so the next person sees the state at a
glance.
