# Client-side crawling: what I'll build, what a flag covers, what I won't automate

**Status:** plan for Ahmed, 2026-07-29. Response to: *move it client-side, open many pages,
remove restricting rules for now, Chrome extension or the Chromium driver already in the
project.* Related: [B-005](BLOCKERS.md), [PAGE_SUPPLY_PROPOSAL.md](PAGE_SUPPLY_PROPOSAL.md).

---

## Good news first: most of this is already in the repo

| what you asked for | state today |
|---|---|
| runs on the user's machine | **done** — the CLI *is* the client surface (`python -m supervisorly`) |
| a real Chromium driver, installed locally | **done** — `fetch/render.py`, Playwright, `ChromiumRenderer` |
| drive many pages at once | **half done** — `render_many_async()` exists; `fetch/pool.py` has the `asyncio.Semaphore` |
| render every page, not just fallbacks | **not done** — today it renders only wall-suspects |
| more pages per professor | **not done** — this is the real gap |

So this is not "rewrite the project as a crawler". It is: turn the renderer from a fallback
into the main path, raise concurrency, and feed it more URLs.

---

## Sorting the "rules" — they are not one thing

Three different kinds got lumped together. They have very different costs to remove.

### A. Not a restriction at all — leave it alone

**D-010, the quote gate.** Every claim must carry a verbatim quote found in the stored
snapshot, or it is dropped in code.

This does not stop you reaching a single page. It stops the model **inventing** professors,
deadlines and recruiting statements. Remove it and the scan does not return more data — it
returns more *fiction*, indistinguishable from the real rows, on a dashboard whose entire
value is that a student can click through to the source.

That is a correctness rule wearing an ethics costume. Keep it.

### B. Genuinely restricting — and I'll put both behind flags

**1. Render-only-if-walled.** `pipeline.py` calls Chromium only when a page fetched OK but
reads like a login wall or JS shell. Sensible on a shared server, pointless on your laptop.
→ `--render-all`.

**2. robots.txt.** This one is real, and here is the honest cost/benefit:

*What it buys:* measured, robots refusals hit **5 of 10 Egyptian institutions** and **0 of 4
UK ones**. So it unblocks maybe half of one country's directories.

*What it does not buy:* **nothing at all against the 88%.** The measured reason fields come
back `NOT_FOUND` is that 88% of shortlisted professors have **no page on record to fetch** —
not that a page was robots-refused. Turning robots off does not create a URL that isn't there.

*What it costs you, specifically:* robots is how sites publish "don't automate me". Ignoring it
at 8 concurrent tabs from a residential or campus IP gets that IP rate-limited then blocked —
and university acceptable-use policies generally treat it as a violation by **the student
running it**, not by us. That is a cost you'd be moving onto the user.

→ `--ignore-robots`, **off by default**, prints a loud one-line banner when on. Your call per
run, not a silent default for everyone.

### C. Won't automate — and it's narrower than it sounds

**Bulk extraction through the student's logged-in session on sites that gate access.**

Not because of a doc. Because it is the one item on the list that is *circumvention* rather
than *impoliteness*: it uses credentials to take content the site decided that account may
read one page at a time, at a rate no human could. The account that gets terminated is the
student's.

The nearest thing that works is already shipped: the **human rung** — they open the page
themselves, click "Copy research prompt", and `browser_rung.ingest_page` stores it as a normal
snapshot through the same quote gate. One page, human-paced, their own eyes. That stays.

Everything public — which is nearly all faculty pages, lab sites and directories — is in
scope for the driver and always was.

---

## Chrome extension vs the driver already installed

**Recommendation: the Playwright driver. It is hours; the extension is weeks.**

| | Playwright (`fetch/render.py`) | Chrome extension |
|---|---|---|
| exists today | **yes** | no |
| install | `playwright install chromium` | unpacked dev-install or Web Store review |
| talk to the CLI | direct, same process | needs a native-messaging host |
| updates | `pip install -U` | store resubmission |
| drives many tabs | yes, `render_many_async` | yes |
| **uses the logged-in session** | no | **yes** |

That last row is the extension's only real advantage — and it is exactly the capability in
group **C** that I'm not going to automate. Which makes the extension weeks of work to unlock
the one thing I'd decline anyway. If you want it later for a *human-paced* assist, that's a
different and much smaller build.

---

## STATUS — all six built, 2026-07-29

| # | What | Where | Flag / switch |
|---|---|---|---|
| 1 | Chromium as the **main reader** | `pipeline._deep_dive_one` | `--render-all` |
| 2 | Batch concurrency | `pipeline._prerender_batch` + `render.BatchRenderer` | `--concurrency N` (8) |
| 3 | **Rung 7** — search-API page resolution | `discover/websearch.py` | `SUPERVISORLY_SEARCH_KEY` |
| 4 | Bounded lab crawl | `discover/sitecrawl.py` + `pipeline._crawl_more` | `--crawl` |
| 5 | robots override | `Fetcher.obey_robots` | `--ignore-robots` |
| 6 | D-073 model extraction wired | `pipeline._model_claims` + `extract/llm_client.py` | `SUPERVISORLY_EXTRACT_KEY` |

Every one is **off by default** and **fail-closed**: no key, no Playwright, no flag → the scan
behaves exactly as it did before. 63 new tests; suite green.

Two things the build changed from the plan above:

- **The model pass fills gaps, it does not overrule.** Where a regex already found a value that
  value stands; the model is asked only about the remaining fields. That also shrinks the
  prompt. Model claims are recorded `confidence="derived"`, never `quoted_official` — the
  sentence is the page's, the reading is the model's.
- **`--ignore-robots` cannot lie about itself.** `robots_verdict()` is still consulted and the
  real answer stored per source, so an export never claims consent that was not given. The run
  also carries a `robots_override` phase row and a warning, so the fact survives the terminal.

---

## What I'd build, in order

1. **`--render-all`** — Chromium becomes the main reader, not the fallback. (small)
2. **Concurrency N, default 8** — wire `pool.py`'s semaphore into `render_many_async`, with
   per-host politeness kept even when robots is off, so one university isn't hammered by all 8
   at once. `--concurrency N`. (small)
3. **Rung 7: search-API page resolution per professor** — the actual fix for the 88%.
   Brave/Tavily/Google-CSE, one query per shortlisted professor. (medium — needs an API key)
4. **Bounded lab crawl** from those hits: depth ≤ 2, same domain, link-text filtered
   (join / lab / group / people / vacancies / PhD), 20-page cap per professor. (medium)
5. **`--ignore-robots`**, off by default, banner when on. (tiny)
6. **Wire `extract/llm_claims.py`** — batched, shortlist-only, quote-gated. Built and tested,
   currently called by nothing. (small, and the single biggest win per hour spent)

Steps 1, 2, 5 and 6 need no API key and no decision. Steps 3 and 4 need one search-API key.

**If the aim is "stop being just a dashboard", steps 1+2+6 get you there this session** — a
local Chromium reading every page in parallel and a model actually reading the text, which
today nothing does.
