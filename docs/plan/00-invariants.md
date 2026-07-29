# Invariants — re-check these on EVERY task before marking `[R]`

← back to [`README.md`](README.md)

These are not style preferences. Each one is a property the product's claims depend on, and
each was learned by something going wrong.

## 1. The quote gate (D-010)

No claim exists without a **verbatim quote found in its stored snapshot**. The gate lives in
`model/claims.py` and uses `fetch/normalize.quote_in_snapshot`.

- **Import the gate; never re-implement it.** A second, slightly-different comparison is how a
  gate grows a hole.
- The quote is in the **source language**. The `value` may be normalised English.
- A model may *propose* a claim. It may never *be* the evidence.

## 2. No seeded URLs (D-038)

The engine authors **no institution URL, no university list, no path dictionary**. Paths are
extracted from pages we fetched, never predicted — site layouts differ per site and per
country, and a guessed `/staff` fails silently everywhere it was not designed for.

`tests/test_no_seed_urls.py` must stay green. A **refusal** list (`fetch/walls.py`) is the
inverse of a seed list and is explicitly allowed: it narrows what we automate against, not
where professors may be found.

## 3. Failure is a state, not an exception

Every error path ends in `blocked` / `searched_absent` / `never_attempted` **with a reason**.
Nothing raises across a phase boundary. A phase may fail completely and the run must still
finish with honest, exportable results.

## 4. No cross-session cache

*(Ahmed, 2026-07-29.)* No caching of page or institution data — not server-side, not on the
student's machine. A new search re-fetches everything.

**Why**: pages change on their own schedule and there is no way to know one changed without
fetching it again, so a cache cannot be invalidated correctly — only hopefully. A stale
application deadline can cost a student a cycle.

**Within one run, fetch each URL once.** Nothing survives the run. The student's own finished
result may be kept; it is theirs, dated, and covered by the 7-day delete.

## 5. Per-host politeness

- robots.txt checked before every request, wherever the fetching runs
- `fetch/ratelimit.HostRateLimiter` interval respected
- abort-on-challenge (`ethics/pacing.py`): a captcha or soft-block means **stop and route to
  the human rung**, never retry harder
- **never two concurrent requests to the same host.** Concurrency is across *domains* — one
  university spans several, and sources span domains belonging to no institution

## 6. Coverage honesty (D-037)

Every phase reports what it did **not** reach. "We did not look" must stay distinguishable
from "we looked and found nothing". Truncation announces itself — see the existing
`truncated_sources` pattern and the phase ledger (CC-1).

## 7. Green suite

`python -m pytest` passes, run with `TMPDIR` set **outside the repo** — otherwise the D-005
guard correctly fires on pytest's `tmp_path` and one CLI test fails for the wrong reason.

Tests should describe the **property**, not the implementation. Three times this session a
failing test was the test being wrong, and each time the fastest route to the truth was
looking at the artefact rather than re-reading the assertion.
