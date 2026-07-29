# Why the dashboard says NOT_FOUND, and what actually fixes it

**Status:** analysis for Ahmed, 2026-07-29. Answers three proposals: a *server vs my device*
toggle, a *Google top-40 + 10-level crawl per topic*, and *send it all to AI for extraction*.
No code written yet. Related: [B-005](BLOCKERS.md), [B-007](BLOCKERS.md), D-039/D-043/D-073.

---

## First, the diagnosis — it is a supply problem, not a reading problem

`tools/spikes/spike_page_supply.py`, on a real GB · machine-learning scan, 49 shortlisted
professors:

| what the deep-dive aims at | share |
|---|---|
| **no page at all** | **88%** |
| registry profile (ORCID, Publons) | 12% |
| **a page the professor controls** | **0%** |

Then 16 of those pages were read (15 needed Chromium) and an independent model was asked
whether any said anything about recruiting. **Zero did.**

So the fields come back `NOT_FOUND` because **there is no page to read**, not because the
reader is weak. "I am recruiting PhD students for 2027" is a sentence a person writes on
**their own page**. ORCID has no field for it. Any fix that does not end in *the professor's
own URL* changes nothing.

This is the right instinct behind the proposal. The mechanism needs to change.

---

## Proposal 1 — a "run it on my device" button

### What is already true
The product already has **two surfaces over one engine**. The Claude-Code skill + CLI runs the
entire scan on your machine today (`python -m supervisorly …`). "Run on my device" is not a
missing button; it is the other surface.

For the **hosted web app**, a device-side scan cannot work, for a reason that is not a
budget or effort problem:

**The same-origin policy.** A page on `supervisorly.web.app` cannot `fetch()` a university
site. The browser blocks it unless that university sends `Access-Control-Allow-Origin`, and
essentially none do. A browser-side scan would need a CORS proxy — which is our server again,
doing the same work, with an extra hop.

Getting past that needs a **browser extension or a desktop app**: a distribution, update,
signing and trust burden. That is exactly why D-043 names *Claude for Chrome* rather than
inventing one.

### The reach argument is real — and already shipped
The genuine advantage of the student's machine is not cost, it is **reach**: their own
logged-in session can see pages the server must never touch. That is the **human rung**, and
it exists: `extract/chrome_prompt.py` generates the prompt, `extract/page_extract.js` reads the
text in-page, `browser_rung.ingest_page` stores it as a normal snapshot, and the D-010 quote
gate runs on it unchanged. It is the "Copy research prompt" button on the dashboard.

### The line that must not move
Ten automated tabs hitting universities from a laptop is **still automated bulk retrieval** —
now from a residential IP, with our robots discipline and rate limiting only if we
re-implement both, correctly, in client JavaScript. D-039/D-043 permit *a person reading their
own session*. They do not permit automation-at-scale wearing that person's IP address.

**Verdict:** no toggle. The CLI already is the device surface; the human rung already is the
device *reach*; a device *crawler* relocates the crawler without removing it.

---

## Proposal 2 — top 30–40 Google results per topic, then 10 levels deep

Two separate problems, one fatal and one arithmetic.

### (a) Google cannot be queried this way

`google.com/robots.txt` contains `Disallow: /search`. Scraping the results page is exactly the
thing D-039 forbids, and Google's terms forbid it independently. This is not a "be careful"
— it is the same rule that sends walled rosters to the human rung.

**But a search rung is legitimate** through a paid/consented API:

| API | free tier | note |
|---|---|---|
| Google Custom Search JSON | 100 queries/day, then $5/1k | official, sanctioned |
| Brave Search API | 2,000/month free | independent index |
| Tavily | free tier, LLM-oriented | already available as an MCP tool here |

That is a real, buildable **rung 7: resolve a person to their own page**. It does not
contradict D-038 either — asking a search engine a *generated* query is the opposite of
shipping a lookup table.

### (b) 10 levels deep is not a slow crawl — it is "mirror the university"

A university page carries 50–150 links. Same-domain with dedup, depth 10 from any homepage
reaches **effectively every page on the domain**. A mid-size university site is ~200,000 pages.
At one request per second — the polite rate — that is **≈55 hours for one university.**

The web scan's whole budget is 30–90 seconds. 50 topics × 50 institutions makes it years, and
it is bulk retrieval at a scale no university consented to.

Depth is not a tuning knob here. The fix is **not deeper, but pointed**.

### (c) The unit is wrong: professor, not topic

A topic search returns *pages about machine learning*. The product does not need those — it
needs *the page of one named person*. Searching per topic is 50 queries returning the wrong
kind of page; searching per professor is a query that can only return the right kind.

### What to build instead — bounded, ~5–20 pages per professor

```
for each SHORTLISTED professor (not all, not per-topic):
  1. one search query:  "<name>" <institution> (faculty OR "research group" OR lab)
  2. keep the top 3–5 hits on institution/lab domains       -> candidates
  3. crawl depth <= 2 from each candidate, same domain,
     following ONLY links whose text matches join / lab / group /
     people / vacancies / positions / prospective / PhD
  4. cap: 20 pages per professor, robots.txt obeyed at every hop
  5. the existing wall detector + render rung run unchanged
```

That is bounded by design: 200 shortlisted professors × 20 pages = 4,000 fetches worst case,
versus "10 levels" which has no upper bound at all. And unlike depth, every page it reaches is
one a human would have opened.

---

## Proposal 3 — combine it and send it to AI for extraction

**Already decided, already built, and — this is the important part — not switched on.**

`src/supervisorly/extract/llm_claims.py` exists, is tested, and **nothing calls it**. Under
D-073 it is shortlist-only, fail-closed, and it may propose `(field, value, quote)` and nothing
else: any claim whose quote is not found verbatim in the stored snapshot is **dropped in code**
before it can become a claim. The model reads; it never asserts.

Your batching instinct is right and should be taken: one call per professor is wasteful when
one call can carry several pages and return one array.

Where the model earns its place, measured:

| field | regex | model |
|---|---|---|
| `social` (URLs) | **sufficient** | unnecessary |
| `deadline` (date + cue in one clause) | **sufficient and safer** | unnecessary |
| `recruiting_signal` in prose | misses anything not phrased with a cue word | **needed** |
| affiliation, role, supervision level | not attempted at all | **needed** |

A run this week produced 27,357 characters of biography and `searched_absent` on all five
fields, because the page never used the word "recruiting". *"I will be reviewing applications
for the 2027 intake"* means recruiting and matches no cue.

---

## Recommended order

1. **Wire `extract/llm_claims.py`** (batched, shortlist-only, quote-gated). Zero new fetching,
   zero new ethics surface, and today **no page is read by a model at all** — which is the
   single biggest reason dashboards are thin.
2. **Build rung 7 — search-API page resolution, per professor.** This is the real fix for
   the 88%, and it is where Proposal 2's instinct belongs.
3. **Bounded lab crawl, depth ≤ 2, link-text filtered, 20-page cap.** Only after (2) supplies
   the entry points.
4. **Leave walled pages to the human rung.** That keeps the one advantage of the student's
   machine — reach — without turning them into a crawler.

Steps 1 and 2 are independent and could run in parallel. Step 1 needs no new API key, no new
budget, and no decision from anyone.
