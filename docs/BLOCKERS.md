# Blockers and recorded deviations

The contract (`IMPLEMENTATION_GOAL.md` §1, §7) says: when the build hits a genuine
ambiguity, or when the shipped code diverges from a written plan, **record it here with
evidence — never silently deviate**. This file had never been created; the entry below
is the first, found during the W8 verification round.

Open items are listed first. An item is closed by recording the decision that resolved
it, not by deleting it.

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
