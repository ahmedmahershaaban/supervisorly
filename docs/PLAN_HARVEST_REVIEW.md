# Harvest plan — review: enhancements, edge cases, and staying survivable

Companion to [PLAN_HARVEST.md](PLAN_HARVEST.md). Written 2026-07-29 in answer to: what could
still be better, what will go wrong, and how does each failure avoid breaking or invalidating
the rest of the run.

---

## A. The process change that matters most: measure before building

This session produced three confident estimates in a row, all wrong:

| estimate | reality | why it was wrong |
|---|---|---|
| "ORCID unlocks ~90% of targets" | **0%** | measured ORCID *presence*, not URL presence |
| "~24% carry a researcher URL" | **0 of 11** | sampled an unfiltered cohort, not the one a scan surfaces |
| render rung "fixes the blocked rows" | **3 of 24** | the pages exist; almost nobody has one |

Each cost a build → deploy → measure cycle that a **ten-minute script** would have prevented.

**Every phase is therefore gated by a spike before any product code is written.** Take ~10
institutions the live ladder actually returns, measure the yield, write the number down. If it
disappoints, the phase is redesigned or dropped — not built and then discovered.

- **P0** — of shortlisted professors, how many have an ORCID with a *current* employment?
- **P1** — of institutions, how many publish a findable admissions page in HTML, not PDF?
- **P2** — of institutions, how many expose a crawlable people directory within 3 hops?
- **P4** — on pages known to contain recruiting language, what share does triage keep?
- **P5** — on 20 real pages, what share of model proposals survive the quote gate?

A phase whose spike disappoints is a phase that saved its own build cost.

---

## B. The invariant: no phase may invalidate the run

Every phase can fail completely and the scan still finishes with honest, exportable results.
That is not a hope — it requires five specific things.

1. **Claims are written incrementally**, per professor, never batched to the end. A crash at
   professor 18 keeps 17.
2. **Failure is a state, not an exception.** Every error path ends in `blocked` /
   `searched_absent` / `never_attempted` **with a reason** — no exception crosses a phase
   boundary.
3. **Per-phase checkpoints.** `runs.add_task` / `set_task_status` / `target_stage_done`
   already provide per-target, per-stage resumability. Each new phase registers its own stage
   name, so a re-run skips what completed instead of redoing the scan.
4. **Per-phase budgets** — fetches, tokens, seconds. Exhausting one is a *reported truncation*,
   never a crash and never silence.
5. **Coverage names what each phase did not reach**, extending the `truncated_sources`
   pattern, so *"we did not look"* stays distinguishable from *"we looked and found nothing"*.

---

## C. Edge cases per phase

### P0 — ORCID employments

| edge case | handling |
|---|---|
| **Employment carries an `end-date`** — they left in 2019 | Split current from past. Presenting a former post as current is a correctness bug, not a cosmetic one |
| **Several concurrent appointments** — joint posts are common | Show all. Picking "the" institution is a guess the data does not support |
| **Org name disagrees with ROR/OpenAlex** — measured: `"Egyptian Government"` | Do not reconcile. Cite ORCID for what ORCID said; the conflicts table already records disagreement between sources |
| Record visibility limited, fields private | Absent is not false → `searched_absent`, never an inferred value |
| ORCID 429 or 5xx | Back off, skip that professor, continue. One registry hiccup costs one profile |

### P1 — Institution admissions pages

| edge case | handling |
|---|---|
| **Deadlines differ per faculty and per programme** | The dangerous one. One institution-wide deadline applied to every professor is fabrication-adjacent. Attach at the **narrowest scope actually discovered**, record that scope, and never inherit across faculties |
| **An undergraduate page found instead of postgraduate** | Wrong level is worse than nothing. Capture programme level explicitly; if it cannot be determined, refuse the claim |
| **Last cycle's page still published** | A past date shown as a live deadline is a serious error. Compare against today — a past date becomes *historical evidence* for P6, never a current deadline |
| **Admissions info published only as PDF** — common, and **the extractor cannot see PDFs at all today** (verified: no PDF handling anywhere in the engine) | Detect the PDF link and mark the field `blocked` with the reason "published as a PDF", routed to the human rung. Silent invisibility is the failure to avoid; PDF text extraction is a separate, later decision |
| Rolling admissions — no deadline exists | `searched_absent`. The correct answer, not a miss |

### P2 — Directory discovery

| edge case | handling |
|---|---|
| **Crawl explosion** — calendars, `?page=1..1000`, session ids, faceted search | Normalise URLs, dedupe by **content hash** as well as URL, cap depth, cap pages per institution, cap repeats per URL *pattern* |
| **Wrong person matched** — "M. A. Hassan" vs "Mohamed A. Hassan" | The most dangerous failure in the plan: attributing another person's page is worse than finding nothing. Reuse the existing `resolution: verified / unverified / unchecked`. Require surname + initial + institution agreement for `verified`; anything weaker is `unverified`, and the dashboard says so |
| **Two people with the same name at one institution** | Refuse. Mark ambiguous and route to the human rung — a coin flip here is indistinguishable from a lie |
| Directory behind a search form, or a "Load more" button | Take what rendered; report the rest as unreached |
| Redirect loops, soft 404s (200 with a "not found" body) | Loop guard on the visited set; a soft 404 is caught by the same emptiness detection as any unreadable page |

### P4 — Triage

| edge case | handling |
|---|---|
| **False negatives are invisible** — a relevant page skipped never reaches the model and never appears anywhere | Tune for **recall, not precision**: when in doubt, keep. Log the skip count per run so the miss rate is measurable rather than assumed |
| **Non-English pages** — the cue lists are English | Uncertainty **escalates to the model, never to the bin**. A page we cannot confidently triage is sent, not skipped — otherwise Arabic-language institutions silently return nothing, which reads as "that country has no professors" and is exactly the failure D-038 exists to prevent |

### P5 — Model extraction

| edge case | handling |
|---|---|
| Provider 429 / 5xx / timeout | Retry with backoff, then fail closed **for that batch only** — its pages stay `searched_absent` and the scan continues |
| Batch too large for the context window | Batch by **bytes, not page count**. One enormous page must not silently truncate its neighbours out of the request |
| **Every quote in a batch rejected by the gate** | A signal, not a shrug — log it. A model whose quotes stop matching has degraded or changed, and the symptom is otherwise indistinguishable from "these pages had nothing" |
| **Prompt injection in page content** | Bounded, not eliminated, and worth stating plainly: the entity is fixed by *which page we fetched* and is never chosen by the model, so injected text cannot move a claim onto a different professor. Injected text that is quoted gets reported as *"this page says X"* with the quote and URL shown — which is precisely what a reader can check |
| Cost runaway on a large scan | A hard per-scan token budget. Exhausting it truncates and **reports** — "N pages not read (budget)" — it never fails the run |
| Same page, different answers on re-run | Already handled: the conflicts table records disagreement rather than overwriting (D-010) |

### P6 — Historical cycles

| edge case | handling |
|---|---|
| Fewer than 3 archived cycles | **No projection.** Two points are not a pattern; report what was found and stop |
| Archive slow or unavailable | Skip. Historical enrichment is never load-bearing |
| Archived page contradicts the live one | The live page wins for "current"; the archive supplies only the *pattern*, labelled `watch · projected` |

### P7 — Bring-your-own key

| edge case | handling |
|---|---|
| **Browser → Gemini may be blocked by CORS** | **Unverified — spike this before designing around it.** If the browser cannot call it directly, the "we never hold the key" property is lost, and the design must change rather than quietly proxying the key through us |
| Invalid or revoked key | Fail closed to the student's own words with a clear message. Never a broken scan |
| Quota exhausted mid-scan | Partial results, honestly labelled; the deterministic layer completes regardless |
| Key leaking into logs or errors | Never logged, echoed, or placed in a `note`. The existing D-068 rule, applied to a key we do **not** own — which raises the stakes rather than lowering them |

---

## D. Risks that can only be bounded, not removed

- **Name matching.** `unverified` reduces the harm; it does not eliminate wrong matches.
  Whether an `unverified` match is shown at all is a product decision, not a technical one.
- **Sites change.** Every extraction is best-effort against a moving target. The stored
  snapshot and the observation date are what make a stale claim auditable rather than invisible.
- **Injection.** Bounded as above. The mitigation is that every claim carries its quote and its
  source, so a reader can see exactly what the page said.

---

## E. Two enhancements this review adds to the plan

### E1 — Institution-level caching — ~~proposed~~ **REJECTED** (Ahmed, 2026-07-29)

I proposed caching the institution layer (admissions pages, directory structure, discovered
professor URLs) so a hundred students searching one country would cost a few dozen fetches
instead of a few thousand. Ahmed rejected it, and the reason is better than my proposal.

**A cached deadline is worse than no deadline.** Institution pages change on their own
schedule — an hour, a day, a week — and *there is no way to know a page changed without
fetching it again*. So a cache cannot be invalidated correctly, only hopefully. For a product
whose entire promise is verifiable, current facts, serving a stale application deadline can
cost a student an admissions cycle. That harm is unrecoverable; the load saving is not worth
it.

The decision, in full:

- **No cross-session cache of institution or page data.** Ever.
- **No local cache on the student's machine either.** A new session or a new search starts
  from nothing and re-fetches everything, exactly as it would for a student who had never used
  the tool before.
- **Within one run, reuse is expected** — if twenty professors share an institution, its
  admissions page is fetched once for that scan, not twenty times. Ahmed's "we might use the
  response for this session" is precisely this, and it is not a cache in the sense rejected
  above: nothing survives the run.
- The **student's own finished result** may be kept; it is theirs, already dated, and already
  governed by the 7-day delete (D-069).

**Accepted cost, stated once so it is not rediscovered as a bug:** every scan pays full fetch
time, and a student re-running the same search waits the same duration again. That is the
price of never showing them something that quietly went out of date.

**Open question, my reading noted:** the existing 30-day `expand_cache` (Firestore) stores
*LLM phrasings per field*, not page data or facts about the world — "machine learning" expands
the same way this week and next. I read the no-cache rule as scoped to page/institution data
whose freshness matters, so the expansion cache stays. Easy to overrule.

### E1b — Where collection runs, and what that makes non-negotiable

Ahmed's decision (2026-07-29): **each student's own machine may do the fetching**, and the
resulting volume — three thousand requests across three thousand students rather than thirty
from one server — is accepted. His reasoning: a university already serves far more traffic
than this from its own logged-in users, and one bounded scan per student, once, is a diligent
applicant doing by tool what they would otherwise do by hand.

I argued the other side (a blocked student loses access to a university they are applying to;
a shared cache would make an order of magnitude fewer requests). That argument was heard and
overruled, and the freshness reason above is why. Recorded, not re-litigated.

What the decision does **not** change — and these become engineering requirements rather than
preferences, because the polite behaviour no longer has a server to live on:

1. **robots.txt is honoured wherever the fetching happens.** A client that skips it is a
   crawler wearing a student's IP.
2. **Per-host pacing travels with it** — the shipped `HostRateLimiter` interval and
   `ethics/pacing.py` jitter, re-implemented correctly, not approximated.
3. **Abort-on-challenge matters more, not less.** A captcha or soft-block means stop and route
   to the human rung — never retry harder. On a student's own address, "retry harder" is how a
   temporary throttle becomes a lasting block.
4. **Parallelism stays across hosts, never within one.** Twenty tabs means twenty
   institutions; two concurrent requests to one host is the thing that actually triggers a ban.
5. **Provenance drops a tier.** Client-collected pages are `agent_browser` (rank 2), because we
   observed the fetch second-hand. The dashboard should show that, not hide it.

### E2 — A phase ledger in the export

Each phase records what it attempted, what it reached, what it skipped and why, and what it
cost. Surfaced in the run summary, it turns "the dashboard looks thin" into a specific,
answerable question — which is the difference between the diagnosis in this session taking ten
minutes and taking an afternoon.
