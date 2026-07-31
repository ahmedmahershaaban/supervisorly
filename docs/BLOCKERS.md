# Blockers and recorded deviations

The contract (`IMPLEMENTATION_GOAL.md` §1, §7) says: when the build hits a genuine
ambiguity, or when the shipped code diverges from a written plan, **record it here with
evidence — never silently deviate**. This file had never been created; the entry below
is the first, found during the W8 verification round.

Open items are listed first. An item is closed by recording the decision that resolved
it, not by deleting it.

---

## B-008 — CC-4.1 asks to store the field and country in `localStorage`; D-069 forbids it

**Status:** OPEN, small, and already handled conservatively in code — recorded so the choice
is Ahmed's rather than mine. Found 2026-07-29 building CC-4 / FE-1.

### The contradiction

- **CC-4.1** (`plan/10-cross-cutting.md`): "Keep a **local list** of past job ids + field /
  country / date in `localStorage`."
- **[D-069](DECISIONS.md#d-069)** item 3: "No personal data is stored client-side (**no
  localStorage/cookies for plan or email**)."

The field and country *are* the plan. A locked decision outranks a plan task, so the shipped
list stores **the job id and the date only** and nothing else. A test pins the stored shape
and fails if `state.email`, `state.fields`, `state.country` or the plan ever appears in a
`localStorage.setItem` line.

### What that costs, honestly

The panel reads *"29 July 2026, 14:05 · 7a3df6…"* instead of *"cardiovascular disease —
Egypt · 29 July"*. With several past searches that is materially harder to tell apart, which
is most of FE-1's point. The feature works; it is just less legible than intended.

### The decision needed from Ahmed

Is a **field name and country** personal data in the sense D-069 means?

They describe the *search*, not the student, and they are already in the URL bar during the
session. The risk D-069 addresses is a shared or seized device revealing who the user is and
what they are applying for — a country plus a niche field could contribute to the second half
of that.

1. **Keep it as shipped** (id + date). Safest; least useful.
2. **Amend D-069** to permit non-identifying search labels in `localStorage`, and restore
   CC-4.1 as written. This is a *decision change*, so it belongs in `DECISIONS.md` with a
   dated note — not a quiet edit here.
3. **Middle option:** store the field but not the country, or truncate the field. Probably
   the worst of both — it complicates the rule without clearly reducing the risk.

Whichever is chosen, `10-cross-cutting.md` CC-4.1 and D-069 must end up agreeing, so this
cannot resurface.

---

## B-007 — The deep-dive has no supply of pages that could contain a recruiting claim

**Status:** OPEN. Measured 2026-07-29 while trying to run SPIKE-4. Needs a sequencing
decision, not code. Closely related to B-003 and B-006 but distinct from both, and it is the
reason **two** gated phases (P4, P5) cannot be evaluated at all.

### What was measured

`tools/spikes/spike_page_supply.py` takes the professors a real scan shortlists, resolves each
to the URL `pipeline._page_url_for` would deep-dive, and classifies it. For
**GB · machine learning, 49 shortlisted professors**:

| what the deep-dive aims at | share |
|---|---|
| no page at all | **88%** |
| registry profile (ORCID, Publons) | 12% |
| **a page the professor controls** | **0%** |

`tools/spikes/spike_triage.py` then read 16 pages from that cohort (15 needed the browser) and
asked an independent model whether any stated something about recruiting or supervising.
**Zero did.** Same for a 4-page Egyptian cohort.

### Why this is a supply problem, not a triage or extraction problem

"I am recruiting PhD students for 2027" is a sentence a person writes on **their own page**.
ORCID has no field for it; Publons has no field for it. So:

- **P4 (triage)** is a gate on a stream that contains nothing to gate. Its spike has no
  positive set and therefore no recall to measure — reported as INCONCLUSIVE, deliberately
  not as a MISS.
- **P5 (model extraction)** would be asked to find claims on registry profiles. Its spike
  would return a number about nothing.

Neither phase can fix this, because neither chooses which page is read.

### Why it is not simply B-003

B-003 was "the ORCID profile is a JavaScript app we cannot read", and the render rung (D-073)
solved that — the pages here **were** read, 15 of 16 via Chromium. The remaining problem is
that having read them, there is nothing on them to find. B-003 was about access; this is about
whether the accessible thing can answer the question.

### The sequencing decision needed

**P2, the directory rung, is the phase that would create this supply** — staff directories
lead to real faculty pages. The plan orders P4/P5 *before* P2
([`plan/README.md`](plan/README.md)), which now looks like the wrong order: it builds a token
gate and an extractor for a page stream that P2 has not yet produced.

1. **Should P2 move ahead of P4/P5?** Still the right order — P2 is the only phase that could
   create a page supply — but SPIKE-2 did **not** settle whether P2 works. It scored
   **4/14 = 29% pooled against a 30% gate**, and the two cohorts disagree sharply: Egypt
   2/10 with **5 robots refusals**, the UK 2/4 with **none**. One more find would pass it.
2. **Robots refusal is country-specific, not universal.** An earlier draft of this entry
   generalised Egypt's 50% refusal rate into "half of institutions forbid crawling" and drew a
   product-shape conclusion from it. The UK cohort refuted that within the hour. The claim is
   withdrawn; what stands is that refusal is real, legitimate, obeyed — and varies by country.

### What is actually decided, and what is not

**Decided:** registries (ORCID/Publons) carry no recruiting statement, so P4 and P5 cannot be
evaluated on today's page supply whatever happens with P2.

**Not decided:** whether a directory crawl can supply professor pages at a useful rate. 14
institutions across 2 countries is too thin for an `L`/high-risk phase, and the sample is thin
*because of B-006* — the UK cohort was 4 institutions, all the education-typed ones ROR's
first 100 GB rows contain.

### The cheap next step, before any P2 decision

Re-run `tools/spikes/spike_directory.py` on 2–3 more countries. It needs **no OpenAlex** (ROR
is keyless), so it is not blocked by the daily budget, and it costs minutes. If B-006 is fixed
first the cohorts get wider and the number gets trustworthy in the same run.

Only then is the real question answerable: **is the human/browser rung the product's main path
to a professor's own page, or its fallback?** The product already has that rung (D-043/D-064,
and the dashboard already routes blocked rows to it with a generated prompt and a search
link), so this is a question about emphasis and roadmap, not about missing machinery.

---

## B-006 — The institution enumeration returns almost no universities, and P1 cannot be measured until it does

**Status:** OPEN. Found 2026-07-29 while running SPIKE-1; needs a decision before P1 or a
re-run of that spike. No code changed — this is recorded, not silently worked around.

### What was measured

`ror.institutions_in_country` paginates ROR's country filter to **5 pages × 20 = 100**
institutions and records an honest truncation marker when more exist. `select_institutions`
then returns **all** of them for `university_mode="all"`. Counting how many of those 100 are
ROR type `education`:

| country | education-typed institutions in the enumeration |
|---|---|
| Egypt | **41 / 97** |
| Canada | **5 / 100** |
| Germany | **1 / 98** |

Germany has hundreds of universities. The one educational institution in its first 98 rows is
a clinical-drug-research organisation. Canada's five are massage, osteopathy and naturopathy
colleges — Toronto, UBC and McGill are not in the set at all.

This is not a ROR outage. ROR's country filter returns thousands per country in an order that
is not relevance, and the first 100 are effectively an arbitrary slice.

### Why it matters beyond P1

The cohort a real scan produces inherits this directly. Running the **real ladder** for
`CA` + "machine learning", the shortlisted professors' institutions were Nexen, Purdue Pharma
(Canada), Nutrition International and the Royal Canadian Military Institute. For
`EG` + "cardiovascular disease" they were Boehringer Ingelheim, the National Heart Institute
and four university *hospitals*. Those are real organisations with real authors — but a
student asking for a PhD supervisor is not being shown universities.

It is also a plausible contributor to the thin dashboards this plan keeps diagnosing: an
organisation that grants no degrees has no admissions page (P1), often no public staff
directory (P2), and no reason to publish recruiting language (P4/P5).

### Why SPIKE-1 cannot be read as a verdict on P1

Restricted to education-typed institutions, Egypt scored **4/10** — Ain Shams University and
Misr University for Science and Technology both exposed a postgraduate page **one hop from
the homepage**. So admissions pages *are* findable where a university exists and permits
crawling. On the cohort a real scan actually produces, the score is **0/14**, because none of
those organisations has an admissions page to find. Those two numbers answer different
questions, and only the first is about P1.

### The decision needed from Ahmed

1. **Should `select_institutions` filter to ROR type `education`?**
   `institutions_in_country`'s own docstring already claims "The caller filters to education
   types" — the caller does not. One of the two is wrong. Filtering would exclude research
   institutes (Egypt's National Research Centre is `facility`) that legitimately supervise
   students, so this is a product call, not a typo fix.
2. **How should the 100-institution cap choose *which* 100?** Options: raise `max_pages`
   (ROR is keyless, so cost is time); sort by ROR type before truncating; or drive the
   institution list from OpenAlex by works-in-topic, which orders by actual research output
   in the student's field rather than by ROR's arbitrary order.
3. Until one of those lands, **re-running SPIKE-1 will keep measuring the wrong cohort.**

---

## B-005 — Should the browser work move to the student's machine? (and is the LLM needed at all)

**Status:** analysis for Ahmed, 2026-07-29. Recommendation below; no code written.
**Asked:** run headful Chrome on the student's own laptop, ~10 tabs at a time, gather the
pages there, batch the text to an LLM in one session, populate the results. Cheaper for us,
and possibly more powerful — and does the LLM earn its place at all?

### First: is the LLM necessary? Split by field, and the answer differs

The deterministic extractors are regexes over page text. `_RECRUIT` matches literal cues —
`recruit*`, `looking for`, `accepting`, `seeking`, `join (my|the|our) (lab|group|team)`,
`hiring`, `taking students`. `extract_deadline` is stricter still: a date counts only when a
deadline verb, an application-context word and a full date share ONE clause.

Where that is enough, it is **better** than a model — free, instant, reproducible, and
already quote-gated. Measured this session: a rendered ORCID page yielded a real
`advertised social profile` value (a LinkedIn URL) with a verified quote, from regex alone.

Where it is not enough is prose. The same run: **27,357 characters of biography** —
"Professor of Public Health; Faculty of Medicine, Ain Shams University • Chair of Research
Department" — produced `searched_absent` on all five fields, because the page never says
"recruiting". A page that reads *"I will be reviewing applications for the 2027 intake"* or
*"prospective students should contact me"* means recruiting and matches no cue in that list.
Non-English pages fail the same way, harder.

So the honest split:

| field | regex | model |
|---|---|---|
| `social` (URLs) | **sufficient** | unnecessary |
| `deadline` (date + cue in one clause) | **sufficient and safer** | unnecessary |
| `recruiting_signal` in prose | **misses everything not phrased with a cue word** | needed |
| affiliation, role, supervision level | not attempted at all | needed |

The model is not needed to *extract*; it is needed to *read*. And it is bounded to that:
under D-073 it proposes `(field, value, quote)` and anything whose quote is not verbatim in
the snapshot is dropped before it becomes a claim.

### Second: would moving the browser to the student's machine be better?

**For reach — yes, and this is the real argument, not cost.** A student's own logged-in
session can see pages the server must never touch. That is exactly why D-043 exists, and it
is already built: `extract/chrome_prompt.py` generates the prompt, `extract/page_extract.js`
extracts the text in-page, `browser_rung.ingest_page` stores it as a normal snapshot, and the
D-010 quote gate runs on it unchanged. The dashboard's "Copy research prompt" button is that
path, shipped.

**For cost — no, and this is worth being precise about.** The server browser is not what
costs anything:

- Cloud Run **scales to zero**; a scan is 30–90 s of a 2-CPU container a few times a day.
- The binding constraint is the **shared upstream budget** (OpenAlex/ROR), and moving the
  browser does not change it by one call — those are API requests, not page renders.
- The LLM bill is per *page read*, not per *machine that read it*. Identical either way.

**For the 10-tab automation specifically — two hard problems.**

1. **A web page cannot do it.** A page cannot open ten tabs, drive them, and read their DOM;
   the same-origin policy forbids exactly that. It needs a **browser extension or a desktop
   app** — a real distribution, update and trust burden, and the reason D-043 names Claude for
   Chrome rather than inventing one.
2. **It moves the crawler; it does not remove it.** Ten automated tabs hitting university
   sites from a laptop is still automated bulk retrieval — now from a residential IP, with our
   robots discipline and rate limiting only if we re-implement both on the client, correctly,
   in JavaScript. D-039/D-043 permit *a person reading their own session*; they do not
   silently permit automation-at-scale wearing that person's IP. That distinction is the whole
   ethical basis of the human rung, and this would erase it while keeping the paperwork.

### Recommendation

**Keep the browser on the server; put the model where the value is; keep the student's
browser for what only it can reach.**

1. **Wire the D-073 extraction step** (`extract/llm_claims.py`, built and tested, not called).
   This is the actual missing piece — the render rung already delivers real page text and
   nothing reads it. Shortlist-only, fail-closed, every claim through the quote gate.
2. **Batch it, as Ahmed suggested** — this part of the proposal is right and should be taken:
   one call per professor is wasteful when a call can carry several pages and return one
   array. Fewer, larger calls is the cheapest correct shape.
3. **Leave the walled sources to the human rung**, human-paced, through the prompt already on
   the dashboard. That keeps the one genuine advantage of the student's machine — reach —
   without turning them into a crawler.

Revisit if the LLM bill ever becomes the binding cost. It is not today; **no page is read by a
model at all right now**, which is why dashboards are thin.

---

## B-004 — Rendering JS pages and LLM extraction: what the decisions actually permit

**Status:** OPEN — needs Ahmed, but **less of a reversal than I first told him.**
**Raised:** 2026-07-28, after Ahmed asked why the tool does not drive a browser and hand the
page to an LLM to extract fields as JSON.

### First, a correction I owe the record

I told Ahmed this was forbidden: *"Driving a browser server-side and sending page text to an
LLM to extract fields is what D-009 forbids and what D-043/D-044 assign to your browser."*
I then read the decisions instead of trusting my memory of them, and **two of those three
claims are wrong.**

**D-009 does not forbid it — it describes it, and it is not even locked.** Status:
*provisional*. Text: *"Scripts fetch, parse, normalise and cache; language models are used
only where judgement is genuinely required (classification, summarisation, ambiguous
matching)."* Deciding whether a page means "I am recruiting PhD students" **is
classification**. D-009 is the split Ahmed is asking for, not a prohibition on it. What the
repo enforces today — zero model calls inside `src/supervisorly/{discover,fetch,model,score,
export}` — is one *implementation* of D-009 (the LLM lives in `.claude/agents/`), not the
decision itself.

**D-043/D-044 assign WALLED sources to the human rung, not JavaScript ones.** D-044 is
explicit that the professor's own linked pages "are public and are fetched directly …
first-class treatment, not enrichment", and routes to the human only what is *walled*:
login, bot-wall, X/LinkedIn. An ORCID profile is **public and robots-allowed** — it merely
needs JavaScript to render. That is a limitation of our fetcher, not a wall we are
respecting. I conflated "we cannot read it" with "we are not permitted to read it".

**The one claim that holds is D-068**, and only partly: *"The deterministic layer stays
LLM-free for facts."* That constrains **where** the model may run, not whether it may.

### The two questions are separable — and only one is a decision

**(a) Render JavaScript before extracting.** Needs no reversal of anything. It is a fetcher
capability: same robots gate, same snapshot, same quote gate, same refusal to touch walled
hosts. It would have to be honest about one thing — a rendered snapshot is what the *browser*
built, not bytes the server sent, so the snapshot record should say so.

**(b) Let a model read the snapshot and propose claims.** This is the real question, and
D-009 already answers it in principle. What is missing is not permission but a **place**:
the hosted tier has no interpretation step at all. The CLI surface has one — five agents in
`.claude/agents/` — and the web product simply never got the equivalent.

### The roles, as they exist today

| role | where it lives | what it decides | reaches the student? |
|---|---|---|---|
| discovery ladder | `discover/` | which institutions and people exist | yes, as names |
| fetcher | `fetch/` | what bytes a URL returned, robots-gated | as snapshots |
| deterministic extractors | `pipeline._EXTRACTORS` | regex-shaped signals only | yes, quote-gated |
| **quote gate** | `model/claims.py` | **rejects any claim whose quote is absent from its snapshot** | it is the gate |
| `recruiting-analyst` | `.claude/agents/` | is this person recruiting, for which cycle | **CLI only** |
| `eligibility-analyst` | `.claude/agents/` | admissions rules, funding, language bands | **CLI only** |
| `evidence-auditor` | `.claude/agents/` | re-verifies a risk-weighted sample | **CLI only** |
| `profile-synthesist` | `.claude/agents/` | the per-professor narrative | **CLI only** |
| human rung (D-043) | Claude for Chrome | walled pages, returned as MD with quotes | yes, quote-gated |

The web product ships rows 1–4 and none of 5–8. That is the actual gap Ahmed keeps hitting:
**the hosted tier has no judgement layer, so it can only report what a regex found.**

### What must NOT move, whatever is decided

- **D-010 quote gate.** A model may *propose* a claim; it may never *be* the evidence. The
  quote it returns must be found verbatim in the stored snapshot or the claim is rejected in
  code. This already exists and is the reason an LLM extractor is safe here at all — a
  hallucinated deadline dies at the gate rather than reaching a student.
- **D-024.** Model judgements do not export; facts with citations do.
- **D-039/D-005.** Robots stays; a login or bot-wall is still never defeated. Rendering JS on
  a *public* page is not defeating anything; running a headless browser at ResearchGate to
  get past its 403 would be, and must stay refused.
- **D-068 fail-closed.** No key, any error → the step is skipped and the scan still finishes.
  Nobody's search dies because a model was unavailable.

### Recommendation

**Do (a) now, and do (b) as an explicitly-bounded new decision.** Concretely:

1. **Render-then-extract for public JS pages.** Highest value per unit of risk, and it is
   the direct fix for the ORCID/Cairo class of failure. Note the honest limit found on
   2026-07-28: it will *not* rescue `cu.edu.eg`, whose TLS chain is broken at the server, and
   `scholar.cu.edu.eg` 403s bots — a browser does not fix either.
2. **An interpretation step in the worker**, fail-closed, shortlist-only. The D-009 cost
   rationale ("an LLM call per professor across several hundred professors") was written
   before the shortlist gate existed; the gate already bounds this to ~25 professors per
   scan, which is affordable on Flash-Lite and is the same budget shape as D-068.
3. **Every proposed claim goes through the existing quote gate unchanged.** No new trust
   path, no exemption, no "the model said so" field.
4. Record it as a decision that *supersedes the provisional D-009 wording* rather than
   contradicting it — D-009 is provisional precisely so it can be settled once the real
   shape is known, and this is that moment.

The reason to write it down rather than just build it: the difference between "a model
proposes claims that code verifies" and "a model produces the answer" is one refactor wide,
and only the first is defensible. Ahmed should own that line explicitly, as he did with D-072.

---

## B-003 — Every hosted scan returns zero facts, and the only fix goes through a `Disallow: /`

**Status:** decided and shipped ([D-072](DECISIONS.md#d-072--robotstxt-governs-the-crawler-not-the-documented-api-client),
Ahmed, 2026-07-28) — **and it did not fix the symptom.** See "What shipping it actually
changed" at the end: the cause was correctly identified, the fix is correct, and the data it
depends on does not exist for this cohort. A follow-up is needed and is scoped below.
**Found:** 2026-07-28, from Ahmed's screenshot of run `run_89fc85b70a06` (job
`5d1316cbc8a74b929425fcb5b64c7ebd`) — 331 professors, every cell either "not checked yet"
or "awaiting your browser", not one fact.

### The measured behaviour

Counted from the run's own exported dashboard, all 331 people, all five fields:

| state | count | renders as |
|---|---|---|
| `blocked` | **52** (100% of everything deep-dived) | ⏳ awaiting your browser |
| `never_attempted` | 279 (outside the shortlist gate) | · not checked yet |
| `value` / `searched_absent` | **0** | — |

The 279 are correct and by design (`_shortlist_gate`, D-046). The **52/52 block rate** is
the defect: a 100% failure across 52 professors at 34 institutions is systemic.

### The causal chain, each step verified live

1. **OpenAlex carries no homepage.** Sampled 50 authors at Cairo University
   (`I107720978`, one of the two the run's own `partial_warning` named):
   `homepage_url` present on **0 of 50**; 45 have an ORCID, 5 have nothing.
2. **So `_author_url` falls back to the ORCID profile** (`discover/ladder.py:131`) — a
   fallback added by an earlier round precisely because without it *every* target was
   `url=None`. Its docstring calls the ORCID profile "a public, fetchable page".
3. **It is not fetchable.** `https://orcid.org/<id>` returns 65 KB whose entire
   "visible" text is CSS `@font-face` declarations. ORCID is a JavaScript app; the record
   is not in the HTML.
4. **The wall detector correctly fires.** Ran the shipped
   `roster.detect_login_wall()` against the real page: **`True`**. So
   `_deep_dive_one` takes the `blocked` branch (`pipeline.py:748-756`) and marks every
   field for the human rung. Belt and braces: all five extractors were also run against
   that HTML directly and every one returned `None`, so even without the detector there
   was nothing to extract.

Nothing here is a bug in the sense of broken code — **every component did exactly what it
was designed to do.** The ORCID fallback turned "no URL" into "a URL that is guaranteed to
be walled", which converts an honest `never_attempted` into an honest-looking `blocked`
while producing the same zero facts. The states are individually truthful and the product
outcome is still useless, which is why this needed measuring rather than reasoning about.

### The fix, and why it is blocked

ORCID's **public API** returns exactly what is missing, as structured JSON:
`pub.orcid.org/v3.0/<id>/record` gives `researcher-urls` (the professor's real homepage —
the thing OpenAlex lacks), plus employments and biography. Resolving ORCID → real homepage
would give the deep-dive an actual page to read, for ~90% of enumerated targets.

**But `https://pub.orcid.org/robots.txt` is `User-agent: * / Disallow: /`.**

[D-005](DECISIONS.md#d-005--ethics-in-code) binds the tool to obey robots.txt, and this is
the most explicit possible refusal. The tempting argument — "robots.txt governs crawlers,
not documented API clients, and ORCID publishes this API for exactly this purpose" — is
genuinely arguable and is the mainstream reading. It is still not mine to make.

The existing precedent does **not** settle it, and I checked before assuming it did:

| host | robots.txt | how the code treats it |
|---|---|---|
| `api.openalex.org` | **404 — none served** | raw transport, no robots gate |
| `api.ror.org` | **403 — none served** | raw transport, no robots gate |
| `pub.orcid.org` | **200, `Disallow: /`** | — |
| `orcid.org` (site) | 200, selective — record pages **allowed** | robots-gated fetcher |

So OpenAlex and ROR bypass the robots gate because **there is nothing to obey**, not
because the project decided documented APIs are exempt. That decision has never actually
been made. ORCID would be the first host where the tool overrode an explicit `Disallow`.
Note the irony in the last row: scraping ORCID's *human* page is robots-allowed and
useless, while its *machine* endpoint is useful and disallowed.

### The decision needed from Ahmed

1. **Does "obey robots.txt" (D-005) apply to documented public APIs, or only to crawling?**
   A yes/no here is reusable — it will recur with Crossref, Semantic Scholar, and every
   registry. If APIs are exempt, that belongs in D-005/D-039 as explicit words, not as an
   inference from two hosts that happen to serve no robots.txt.
2. If **exempt**: implement ORCID resolution on the API side (alongside `openalex.py` /
   `ror.py`), with the ORCID iD as identifier, a contact header, and the JSON record as the
   quote-verified snapshot — every D-010 guarantee unchanged.
3. If **not exempt**: then the ORCID fallback in `_author_url` should be **removed**, not
   kept. It currently spends a fetch and a shortlist slot to reach a page known in advance
   to be walled, and dresses the result as "awaiting your browser" — which tells the student
   their browser will finish the job, for 52 pages where a browser would find a real record
   but the tool could simply never use it. Honest emptiness (D-037) is better served by
   `never_attempted` and a shortlist spent on targets that have a real page.

Until this is answered the hosted product enumerates correctly and reports nothing, which
is the state Ahmed is looking at.

### What shipping it actually changed: nothing, and that is the useful result

D-072 was ruled, `discover/orcid.py` was built, and both tiers were deployed (`web-v7`,
worker image `sha256:e2b29f2c…`). Two live scans against the hosted product then measured
the outcome, because "the fix is deployed" is not the same claim as "the student sees data":

| run | targets | deep-dived | `value` cells |
|---|---|---|---|
| `ab3a3041…` (10 institutions) | 6 | 6 | **0** |
| `3f6b3139…` (30 institutions) | 89 | 25 | **0** |

Still 100% `blocked`. The resolution ran and correctly found nothing:

- Run `ab3a3041…`: **0 of 6** deep-dived authors had an ORCID *or* a homepage. There was no
  identifier to resolve, so D-072 could not apply to a single target.
- Run `3f6b3139…`: **11 of 25** had an ORCID — and **0 of those 11** ORCID records list any
  researcher URL. Every record was read; every one was empty.

**The 24% estimate does not hold for this cohort, and the difference is instructive.** The
6-of-25 sample came from an *unfiltered* institution query, which returns the most prominent
authors — exactly the people who fill in an ORCID profile. A real scan filters by
institution **and topic**, surfacing working academics who do not. Sampling the population
you are not going to search tells you nothing about the one you are.

### Where the data for this cohort actually is (measured, 2026-07-28)

Institution sites, not registries — but not uniformly, and Cairo University is the worst case:

| host | with TLS verification | content |
|---|---|---|
| `cu.edu.eg` | **fails** — incomplete certificate chain | 16 visible chars (JS shell) |
| `scholar.cu.edu.eg` | **fails** — incomplete certificate chain | 403 to bots |
| `aun.edu.eg` (Assiut) | 200 | **8,048 visible chars** |
| `alexu.edu.eg` (Alexandria) | 200 | **5,859 visible chars** |
| `mans.edu.eg` (Mansoura) | 200 | **9,577 visible chars** |

Three of five serve real, fetchable HTML. Cairo's TLS chain is broken at the server, so the
worker cannot reach it at all — and disabling verification is not an option worth having.

### The follow-up this points to (not started — needs Ahmed's go-ahead)

Strengthen the **institution directory rung** so faculty pages supply the URL that OpenAlex
and ORCID do not. This is the option offered as "find homepages another way" and not chosen
at the time; the measurements above are the argument for revisiting it. It touches no ethics
boundary — these are ordinary public pages, fetched through the existing robots-gated
fetcher — and it is the only path measured to reach real content for this cohort.

Two things must be honest about it: it is **per-institution work**, not one generic fix; and
it will never cover Cairo University until Cairo fixes its certificate chain, which is
outside this project's control and should be stated to the student rather than papered over.

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

---

## B-009 — `score/programs.py` has no input

**Status: still blocked, and round AM sharpened WHY.**

The first reading was "add a program extractor". That is not enough, and building it
would have produced a worse artifact than the current absence. `group_by_program` groups
on a program **id**, and a name scraped from a professor's own page is not one: "PhD in
Computer Science", "Computer Science PhD" and "Doctoral Programme in CS" are three
strings for one program, so grouping on them either fragments a real shared application
into singletons or merges two genuinely separate ones. Either way the module's whole
claim — *you apply and pay once* — becomes a guess about somebody's money.

**The identity that would actually work is the application URL.** Two professors whose
department pages link the same graduate-application page genuinely do share one
application, a URL is stable enough to be an id, and it is citable — so the claim stays
quote-gated instead of becoming an inference. `sitecrawl` already follows same-site
links and its `links_worth_following` filter is where an "apply"/"admissions" link
would be recognised.

That is the prerequisite: an `application_url` claim, not a `program_name` one.

---

**Original status: blocked upstream, not on a decision.**

`group_by_program` implements D-031's "one application per program, not per professor": two
supervisors in the same department usually share one graduate program — one application, one
fee, one deadline — and presenting them as two applications misleads the student into paying
twice. The module is written, tested, and correct.

Nothing sets a `program` on a professor. There is no `program` field descriptor, and no
extractor produces one. Wiring it today emits N singleton groups, each announcing "One
application", which is noise dressed as insight — so it was deliberately left unwired in
round AK rather than connected for the sake of a green wiring audit.

**What it needs:** an extractor for the graduate program a professor's department belongs to
(the department page's "Graduate programs" link is the usual anchor), recorded as a normal
quote-gated claim. The roll-up then has an input and can be wired in one line.

---

## B-010 — a Wayback deadline projection is not a claim

**Status: RESOLVED and shipped (round AM, 2026-07-31).** The decision is the one this
entry asked for, and it went the strict way: a projection **never enters `fields`**. Not
"carefully", not "with a lower confidence" — at all. There is no snapshot of a future
date for a quote to be verified against, so the D-010 gate has nothing to gate. It ships
in `profile.deadline_projection` beside `match`, carrying `confidence: "watch"`, the
years it was derived from, the dates observed, and — when it refuses — the reason it
refused. Opt-in via `--archive` (and a checkbox on the wizard); off by default, because
it costs the archive up to five extra page reads per professor.

The original text is kept below for the reasoning.

---

**Original status: needs a decision recorded before `discover/archive.py` is wired.**

`archive.cycles_for` / `project_next` read an admissions page's history from the Wayback CDX
API and project roughly when the next cycle opens. This is the highest-value unwired module in
the repo, because `deadline` is the field that comes back `NOT_FOUND` most often.

It cannot be wired without settling one thing: **a projection has no snapshot.** D-010 says
every field is a claim with a quote verified against the page it came from — and no page
exists yet for a future deadline. So a projection must not enter `fields` at all. The proposal
is `profile.deadline_projection`, carrying the observed cycles it was derived from, on exactly
the terms `match` sits beside `fields` rather than inside it.

Two smaller prerequisites: `web.archive.org` needs a `test_no_seed_urls` allowlist entry with
written reasoning, and robots/pacing apply to it like any host.

The module already refuses to project from fewer than three cycles ("two points are not a
pattern"), which is the part that would have been easy to get wrong.


---

## B-011 — a run that dies mid-enumeration re-enumerates from scratch

**Status: OPEN, small, and now honestly reported rather than falsely covered.**

`--resume` skips targets whose deep-dive task is `done` (`runs.target_stage_done`). It does
**not** resume discovery: nothing persists the enumerated institution/target list, so a run
killed while enumerating 300 institutions pays for all 300 again on resume.

This was previously obscured rather than solved. `runs.save_checkpoint`, `latest_checkpoint`
and `incomplete_tasks` sat in the model layer, tested, called by nothing — a stage-cursor API
that read as coverage the product did not have. Round AM removed them: two mechanisms for one
job is how they drift, and dead scaffolding that *looks* like stage-level resume is worse than
an honest gap. The `checkpoint` table stays in the schema (dropping it is a migration, and an
empty table is cheaper than one whose rows nobody reads).

**What it needs:** persist the enumeration result — the institution list and the derived
targets — keyed by run, and have `run_live` load it when `resume=True` instead of re-running
the ladder. The cost of not doing it is bounded (discovery is minutes, the deep dive is the
expensive half), which is why it is recorded rather than rushed.
