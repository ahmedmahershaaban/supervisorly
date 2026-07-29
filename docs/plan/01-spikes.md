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

## Sampling rule

Take the targets **a real scan produces** — country → ROR → OpenAlex authors filtered by topic.
Do not sample the unfiltered author list: it returns the most prominent people, who are exactly
the ones with complete records, and it will flatter every estimate.

## The spikes

| id | file | question | threshold |
|---|---|---|---|
| **SPIKE-0** | `tools/spikes/spike_orcid_employments.py` | Of shortlisted professors, how many have an ORCID with a **current** employment (no `end-date`)? | **≥ 30%** |
| **SPIKE-1** | `tools/spikes/spike_admissions.py` | For ~10 institutions, can an admissions/graduate page be found **by following the site's own links within 3 hops**, and is it HTML rather than PDF? Record: found, HTML vs PDF, language, whether a date is present | **≥ 40% found** |
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
