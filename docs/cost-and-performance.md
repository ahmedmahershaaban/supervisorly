# Cost and Performance Budget

Ahmed asked for budget and performance to be designed in, not discovered later. This
document sets the numbers the architecture has to hit, and shows which design choices
actually move them.

**Status of numbers below:** API rate limits and the OpenAlex credit model are
**verified** (see `research/data-sources.md`). Claude pricing is from the current model
table, cached 2026-06-24. Everything labelled *modelled* is arithmetic over an assumed
workload, not a measurement — re-measure once the first real scan runs.

---

## 1. The workload being budgeted

One representative scan, used consistently throughout:

| Parameter | Value |
|---|---|
| Country | 1 |
| Universities selected | 5 |
| Departments per university | 1–2 (e.g. CS, ECE) |
| Professors discovered | ~400 |
| Professors shortlisted for deep analysis | ~40 (10%) |
| Re-scan cadence | monthly |

A whole-country sweep (every university, every discipline) is a different regime and is
addressed in §6.

---

## 2. Data-source cost

Only OpenAlex meters by spend. Everything else is rate-limited but free.

| Source | Cost model | Verified limit |
|---|---|---|
| OpenAlex | credits — `$0.0001`/list call, `$0.001`/search call | `x-ratelimit-limit-usd: 0.1` unauthenticated; **$1/day** with a free key |
| OpenAlex snapshot | free, CC0 | bulk download (S3) |
| ROR | free | 50 req / 5 min without a client ID — **the client ID is required now (as of 2026-07)**, get one at setup |
| Crossref | free | polite pool = 3 req/s |
| ORCID | free, **non-commercial use only** per ToS | — |
| DBLP | free | be polite; no published quota |

**Modelled API spend for the representative scan:**

| Stage | Calls | Unit | Cost |
|---|---:|---|---:|
| L0 — enumerate institutions in country | ~5 | list | $0.0005 |
| L1 — list authors per institution (paginated 200/page) | ~50 | list | $0.005 |
| L2 — per-professor enrichment | ~400 | list | $0.040 |
| **Total** | **~455** | | **≈ $0.05** |

**This is the headline result: a 400-professor scan costs about five cents of OpenAlex
credit** — comfortably inside the **$1/day free-key allowance, with room for ~20 scans a
day.** The credit model does *not* threaten the normal use case.

> **The ~20-scans figure assumes a free OpenAlex API key.** Without a key the ceiling is
> $0.10/day (~2 scans), and ROR without its now-required client ID throttles to 50 req/5 min.
> Both credentials are free and are a setup step ([§2 table above](#2-data-source-cost); the
> first-run check fails loud without them — see architecture §9). Provision both, or the
> numbers here don't hold.

It threatens exactly one thing: whole-country sweeps (§6).

---

## 3. LLM cost — where the real money is

Current pricing (per 1M tokens):

| Model | Input | Output |
|---|---:|---:|
| Claude Opus 4.8 | $5.00 | $25.00 |
| Claude Sonnet 5 | $3.00 ($2.00 intro through 2026-08-31) | $15.00 ($10.00 intro) |
| Claude Haiku 4.5 | $1.00 | $5.00 |

Assume a per-professor analysis call of ~3,000 input / ~600 output tokens.

### 3a. The naive design — LLM on every professor

| Model | Per professor | × 400 |
|---|---:|---:|
| Opus 4.8 | $0.0300 | **$12.00** |
| Sonnet 5 | $0.0150 | $6.00 |
| Haiku 4.5 | $0.0060 | $2.40 |

$12 per scan is not catastrophic for one user, but it is the wrong shape: it scales
linearly with professors discovered, so it punishes exactly the broad searches the tool
exists to enable.

### 3b. The tiered design — and the circularity trap it must avoid

The obvious move is "cheap enumeration for everyone, expensive LLM deep-dive only for a
user-approved shortlist." Two independent critics caught the flaw: **the fields a user
would shortlist on — recruiting status, funding, eligibility — only exist after the
deep-dive.** Enumeration returns name, title and research areas, which is not enough to
approve anything. A naive two-stage gate asks the user to filter on data that does not
exist yet.

The fix is three tiers, where the shortlist is formed on **research fit**, which *is*
cheaply available, rather than on recruiting status, which is not.

| Tier | Population | What it produces | Method | LLM? |
|---|---:|---|---|:--:|
| **T0 — enumerate** | all (~400) | identity, affiliation, topics, recency, seniority, lab URL | ROR + OpenAlex, API only | no |
| **T1 — cheap signal** | all (~400) | recruiting *candidate* sentences, contact route, lab-page presence | one cached page fetch + boilerplate strip + regex/heuristics | no |
| **T2 — deep dive** | shortlist (~40) | classified recruiting state, funding, eligibility, evidence, fit narrative | multi-source + LLM extraction with quote verification | yes |

T1 is the tier the naive design was missing. It costs HTTP and disk, not tokens, and it
is what makes the shortlist decision informed rather than blind. The user narrows on
research fit and activity — which is how applicants actually work — and only then does
the expensive pass resolve whether those people are reachable and funded.

**LLM cost, T2 only (~40 professors):**

| Model | × 40 |
|---|---:|
| Opus 4.8 | **$1.20** |
| Sonnet 5 | $0.60 |
| Haiku 4.5 | $0.24 |

10× reduction against the naive per-professor design, with the shortlist now formed on
data that actually exists at that point in the pipeline.

### 3b-i. The dominant cost lever is caching extraction, not choosing a model

Model tiering and the shortlist gate are real but secondary. The largest lever is an
**extraction cache keyed on `(snapshot_content_hash, prompt_version, model_id,
schema_version)`**. If a page has not changed and the prompt has not changed, the
extraction is not re-run at all — a monthly re-scan of a stable department should issue
close to zero LLM calls.

**This holds only if the content hash is computed over *stable* content.** A faculty page's
volatile chrome — a news sidebar, a "last updated" timestamp, a visitor counter, a rotating
banner — changes the raw bytes every day and would make every re-scan a cache *miss*,
re-firing extraction and quietly breaking the number above. So the hash is taken over
**boilerplate-stripped, normalised main content**, and that normalisation (strip nav/footer/
timestamps/counters, collapse whitespace, canonicalise) is a **tested property**, not a hope —
a fixture with injected volatile chrome must hash identically across two captures.

Three rules that matter more than model choice:

1. **Never send raw HTML to a model.** Boilerplate-stripped text, hard byte cap.
2. **Skip the LLM entirely when the *normalised* content hash is unchanged.**
3. **Map fields to extractors**, so changing the recruiting prompt re-extracts only
   recruiting claims — not the whole corpus.

Without rule 3, every prompt edit is a full re-scan, and the cost model above stops
holding on the second week.

### 3c. Two further levers, both large

**Batch API — 50% off.** A scan is not latency-sensitive; a user starting a country-wide
search expects to come back later. Batches complete within an hour (24h ceiling), accept
up to 100,000 requests, and support every feature used here.

**Prompt caching — cache reads cost ~0.1× input.** The classifier's instructions, schema,
and few-shot examples are identical across all 400 professors; only the record varies.

> **Design constraint, not an optimisation:** the minimum cacheable prefix on Opus 4.8 and
> Haiku 4.5 is **4,096 tokens**. A short system prompt silently will not cache — no error,
> just `cache_creation_input_tokens: 0`. The classifier prompt must be deliberately built
> to exceed that threshold (schema + rubric + worked examples), with the per-professor
> record placed *after* the cache breakpoint. Getting this wrong costs ~10× on input
> tokens and produces no warning.

**Stacked, on the shortlist design with Opus 4.8:**

| Configuration | Cost per scan |
|---|---:|
| Naive (LLM per professor) | $12.00 |
| + tiered shortlist | $1.20 |
| + Batch API (−50%) | $0.60 |
| + prompt caching on the shared prefix | **≈ $0.35** |

A ~34× reduction from three decisions, none of which trade away output quality.

### 3d. Model selection

Default to **Opus 4.8**. The per-scan delta between Opus and Haiku after tiering, batching
and caching is roughly **$0.35 vs $0.07** — cents, on a decision (which supervisor to
spend a year of your life pursuing) where being wrong is expensive.

Model choice is exposed as configuration so a user running a whole-country sweep can pick
a cheaper tier deliberately. The default is not downgraded to save cents.

---

## 4. Two execution modes, two cost profiles

| Mode | How it runs | Who pays |
|---|---|---|
| **Skill mode** (primary) | as a Claude Code skill — the agent orchestrates the local scripts | covered by the user's existing Claude Code subscription; **no API key needed** |
| **Headless mode** | `python -m profscout scan …` calling the API directly | user's own API key, costs per §3 |

Skill mode is the default and the reason the project is Claude-Code-first: a student with
a Claude Code subscription pays nothing extra. Headless mode exists for automation and for
the later portability-to-other-LLMs phase.

---

## 5. Performance budget

Wall-clock targets for the representative scan.

| Stage | Target | Bound by |
|---|---|---|
| L0 — enumerate institutions | < 5 s | ROR + OpenAlex latency |
| L1 — discover professors | < 60 s | OpenAlex pagination, ~50 sequential calls |
| L2 — enrich | < 90 s | concurrency-capped HTTP |
| L3 — rank and shortlist | < 2 s | pure local computation |
| L4 — deep analysis (40) | 2–10 min | LLM latency, or ≤ 1 h in batch mode |
| Dashboard render | < 1 s | single self-contained HTML file |
| **Cold scan, end to end** | **< 5 min** interactive · ≤ 1 h batched | |
| **Warm re-scan (cached)** | **< 30 s** | cache hits on unchanged records |

**Concurrency ceilings** are set by the politest source, not the fastest:

- Crossref polite pool: **3 req/s** — the binding constraint
- ROR: **50 req / 5 min** without a client ID
- Global default: **4 concurrent requests**, per-host token bucket, exponential backoff
  with jitter on 429/5xx

**Caching is what makes re-scans cheap.** Every HTTP response is cached on disk keyed by
URL + ETag, with a per-source TTL (institutions: 30 days; author records: 7 days; lab
pages: 24 h). A monthly re-scan should re-fetch only what actually changed, which also
makes the staleness display in the dashboard honest rather than decorative.

---

## 6. The one regime that breaks

**Whole-country sweep** — every university, every discipline, no shortlist:

| | Representative scan | Country sweep |
|---|---:|---:|
| Professors | 400 | 100,000+ |
| OpenAlex list calls | ~455 | ~250,000 |
| OpenAlex credit cost | $0.05 | **~$25 — exceeds the $1/day cap** |
| LLM cost, tiered + batched + cached | ~$0.35 | ~$90 |

The API path is not viable at this scale, and no amount of tuning fixes it. This is what
the CC0 bulk snapshot is for ([D-014](DECISIONS.md#d-014--country-scale-reads-use-the-openalex-snapshot-not-the-api)).

**Therefore the product has two honest modes, and the README must say so plainly:**

- **Targeted mode** — a country plus a set of universities. Works immediately, no setup,
  costs cents. This is what almost every user wants.
- **Bulk mode** — whole-country or whole-discipline. Requires a one-time snapshot
  download and local indexing. Documented as an advanced path, not the default.

Promising frictionless whole-country sweeps through the API would be a promise the
architecture cannot keep.

---

## 7. What gets measured

The scan emits a machine-readable cost and timing report alongside its results, so these
projections get replaced by measurements rather than trusted indefinitely:

- API calls per source, cache hit rate, bytes fetched
- OpenAlex credits consumed (read from response headers, not estimated)
- LLM input/output tokens, split by cached vs uncached (`cache_read_input_tokens` vs
  `cache_creation_input_tokens`) — a cache-read figure of zero means the 4,096-token
  minimum was silently missed
- Wall-clock per stage
- Professors discovered / shortlisted / deeply analysed

If a bound is exceeded, the run says so in its summary. No silent truncation: if coverage
was capped, the report states what was dropped and why.
