# Spikes — measure before building

← back to [`README.md`](README.md)

A spike is a **throwaway script** under `tools/spikes/`, never product code. It measures the
real yield on ~10 institutions the **live ladder actually returns** — not a hand-picked sample.

**If a spike misses its threshold, stop and re-plan. Do not build the phase.**

## Why this rule exists

This session produced three confident estimates in a row, each stated as fact:

| estimate | reality | the error |
|---|---|---|
| "ORCID unlocks ~90% of targets" | **0%** | measured ORCID *presence*, not URL presence |
| "~24% carry a researcher URL" | **0 of 11** | sampled an unfiltered cohort, not the one a scan surfaces |
| "the render rung fixes the blocked rows" | **3 of 24** | the pages exist; almost nobody has one |

Each cost a build → deploy → measure cycle that a ten-minute script would have prevented.
A phase whose spike disappoints is a phase that saved its own build cost.

**It happened again on the very first run of SPIKE-0 (2026-07-29)**, which is why the
sampling rule below is not advice. `--field cardiology` resolves to **zero** OpenAlex topics,
so the enumeration silently fell back to unfiltered and returned the country's most prominent
physicists and oceanographers: **68%**. The correctly filtered cohort for the same country
scored **28%**. Same script, same day, 40 points of difference — entirely from the sample.

**So: check the `topics N` line in a spike's header before you believe its number.** Zero
topics means the filter did not apply and the result is about prominent people, not about
the cohort a student's scan will actually produce.

**And it happened a third time, on SPIKE-1 (2026-07-29), in a new way.** That spike's first
run took ROR's first ten institutions for Egypt and crawled hospitals, a pharmaceutical
company, the WHO regional office and an international K-12 school — one plausible university
in ten. Applying the sampling rule properly (real ladder → shortlist → *those professors'*
institutions) did not rescue it: the cohort became Boehringer Ingelheim and four university
hospitals, and the honest score was 0%.

The lesson is a refinement of the rule, not a repetition of it: **"the cohort a real scan
produces" is only the right sample if the scan itself is sampling the right things.** When a
spike scores zero, ask whether the phase is unviable or whether the *input* is wrong, and say
which — SPIKE-1's zero turned out to be a measurement of [B-006](../BLOCKERS.md), not of
admissions pages. A spike that reports a number without that distinction can kill a phase
that was never tested.

## Sampling rule

Take the targets **a real scan produces** — country → ROR → OpenAlex authors filtered by topic.
Do not sample the unfiltered author list: it returns the most prominent people, who are exactly
the ones with complete records, and it will flatter every estimate.

## The spikes

| id | file | question | threshold |
|---|---|---|---|
| **SPIKE-0** ✗ | `tools/spikes/spike_orcid_employments.py` | Of shortlisted professors, how many have an ORCID with a **current** employment (no `end-date`)? | **≥ 30%** — measured **22%**, 2026-07-29. **MISSED**, P0 not built ([`20-p0-orcid.md`](20-p0-orcid.md)) |
| **SPIKE-1** ✗ | `tools/spikes/spike_admissions.py` | For ~10 institutions, can an admissions/graduate page be found **by following the site's own links within 3 hops**, and is it HTML rather than PDF? Record: found, HTML vs PDF, language, whether a date is present | **≥ 40%** — measured **0%** on the real cohort, 2026-07-29. **MISSED**; the cause is upstream ([B-006](../BLOCKERS.md)), see [`21-p1-admissions.md`](21-p1-admissions.md) |
| **SPIKE-4** | `tools/spikes/spike_triage.py` | On ~20 pages known to contain recruiting language, what share does triage keep (**recall**)? And on 20 known-irrelevant pages, what share does it drop? | **recall ≥ 90%** |
| **SPIKE-5** | `tools/spikes/spike_llm_yield.py` | On 20 real pages, what share of model proposals survive the quote gate, and what does a batch cost? | **≥ 60% survive** |
| **SPIKE-2** | `tools/spikes/spike_directory.py` | For ~10 institutions, is a people directory reachable within 3 hops by following links, and can a named professor be located in it? | **≥ 30%** |
| **SPIKE-6** | `tools/spikes/spike_wayback.py` | For admissions URLs P1 found, how many have **≥ 3** archived cycles? | **≥ 25%** |

## What a spike must output

One line per institution or professor, plus a summary. Write the numbers into the phase file as
a dated note — *"SPIKE-1, 2026-08-02: 6/10 found, 2 of those PDF-only"* — so the next reader
knows what the phase was built against rather than what was hoped.

## Spikes obey the rules too

A spike hits real sites. robots, the per-host interval and abort-on-challenge apply — see
[`00-invariants.md`](00-invariants.md) §5. A throwaway script is still a visitor.
