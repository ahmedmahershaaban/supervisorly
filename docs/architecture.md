# Architecture

How the system is put together, and why each boundary sits where it does. Every
non-obvious choice links to its entry in [DECISIONS.md](DECISIONS.md).

Read [requirements.md](requirements.md) first — this document is the answer to the pain
points recorded there.

---

## 1. The shape of the thing

```
                       ┌──────────────────────────────────────────┐
   country +           │            ORCHESTRATOR                  │
   universities   ───▶ │  (Claude Code skill, or plain CLI)       │
   + priorities        │  owns: run state, budget, tier gating    │
                       └───────────────┬──────────────────────────┘
                                       │  never sees per-professor prose
        ┌──────────────────────────────┼──────────────────────────────┐
        ▼                              ▼                              ▼
 ┌─────────────┐              ┌─────────────────┐            ┌────────────────┐
 │ T0 ENUMERATE│              │ T1 CHEAP SIGNAL │            │ T2 DEEP DIVE   │
 │  all (~400) │─────────────▶│   all (~400)    │───────────▶│ shortlist (~40)│
 │  APIs only  │              │ 1 page + regex  │            │ multi-src + LLM│
 │   no LLM    │              │     no LLM      │            │  LLM, cached   │
 └──────┬──────┘              └────────┬────────┘            └───────┬────────┘
        │                              │                             │
        └──────────────┬───────────────┴─────────────────────────────┘
                       ▼
              ┌──────────────────┐        ┌──────────────────────────┐
              │  SQLite (truth)  │───────▶│ deterministic JSON export│
              │  claims + runs   │        └────────────┬─────────────┘
              └────────┬─────────┘                     ▼
                       │                         ┌───────────┐
              ┌────────▼─────────┐               │ DASHBOARD │
              │ snapshots/ (fs,  │               └───────────┘
              │ content-hashed)  │
              └──────────────────┘
```

Four properties this shape buys, each answering a specific corpus failure:

| Property | Failure it fixes |
|---|---|
| Tiered, gated at T1→T2 | the corpus abandoned a 649-person roster on volume grounds |
| SQLite + claims | the same funding table hand-retranscribed into four drifting files |
| Content-hashed snapshots | citations that could not be re-verified after the page changed |
| Run/Task state in the DB | every prior session died at context exhaustion mid-run |

---

## 2. The layered collector

Discovery is a **ladder**, not a scraper. Each rung is standards-based and works without
per-site effort; per-site adapters are the last resort, not the mechanism
([D-028](DECISIONS.md#d-028--generic-discovery-before-per-site-adapters)).

| Rung | Source | Why it's high on the ladder |
|---|---|---|
| 1 | **CRIS portals** — Pure, Converis, Symplectic | In the UK, Nordics, NL, DE, AU and much of Asia the faculty directory *is* a Pure portal with a uniform documented API. One integration, hundreds of institutions. |
| 2 | **`sitemap.xml`** (via `robots.txt`) + `hreflang` | Authoritative URL inventory instead of guessing `/people`, `/faculty`, `/staff` |
| 3 | **Schema.org / JSON-LD `Person`** | Many CMSes emit it; `sameAs[]` is the profile-link table pre-built |
| 4 | **Certificate Transparency** (crt.sh) | Solves the corpus's own `eecs.yorku.ca` 404 → real host `lassonde.yorku.ca` |
| 5 | **OpenAlex / ROR** as enumeration | Country → institutions → authors, no crawling at all |
| 6 | **DirectoryAdapter** (YAML) | Per-institution fallback when 1–5 fail |

**Honest limit:** adapters scale with *institutions*, not countries, and a country can
hold 4,000+ institutions. Rungs 1–5 are what make "any country" tractable; rung 6 is what
makes specific important institutions correct. If the ratio inverts, the project has a
scaling problem, and the coverage report is designed to make that visible early.

### The three-phase fetch, and the human rung

The ladder above is *what to try*; the escalation across phases is *in what order, and who
does the fetching* ([D-039](DECISIONS.md#d-039--agent-driven-web-navigation-is-first-class-apis-are-the-fast-path)).
Each phase runs across the whole target set, marks its failures, and hands only the residual
to the next:

| Phase | Who | What | On failure |
|---|---|---|---|
| 1 | tool, automatic | structured sources (rungs 1–5) | mark 404 / error / empty → Phase 2 |
| 2 | tool, automatic | browse the marked pages (rung 6, direct navigation) | mark still-unresolved → Phase 3 |
| 3 | **human**, in the loop | run a generated prompt in **Claude for Chrome**, return MD files | field ends "we looked, found nothing" |

Phase 3 is the mechanism that reaches what no automated tool can — Scholar, Twitter/X,
Cloudflare- and login-gated pages — because the *student* reads those pages in their own
logged-in session. It is Ahmed's original Chrome-extension deep-dive method, turned into the
tool's escape hatch, and it is why the tool itself never needs to fetch a blocked or
authenticated property. The gap queue, the generated prompt, the MD ingestion contract, and
the `awaiting_human_input` resume are specified in
[D-043](DECISIONS.md#d-043--human-assisted-retrieval-and-md-ingestion), and the single shared
Markdown grammar both the prompt-generator and the ingester obey is
[D-051](DECISIONS.md#d-051--one-shared-markdown-grammar-for-the-human-rung).

**The human rung also unlocks whole rosters, not just fields.** When a *faculty directory
itself* is login-walled — so the tool cannot even get the list of professors — Phase 3 gains
a **roster-enumeration** task: the generated prompt asks the student to read the walled
directory in their own session and return the professor list with links as MD, which the tool
ingests to mint the entities. The unit is marked `LOGIN_WALL` so the gap is visible, never
silent ([D-052](DECISIONS.md#d-052--the-human-rung-also-enumerates-login-walled-rosters)).

**Ethics consequence:** the split — tool does APIs and public pages, human does the gated
pages in their own browser — is not just pragmatic. It is what keeps the tool clear of the
robots/ToS/anti-bot lines that a scrape-everything design would cross
([ethics-and-compliance.md](ethics-and-compliance.md)).

### Enrichment sources beyond the directory

| Need | Source | Confidence |
|---|---|---|
| Identity, works, affiliations | OpenAlex, ORCID, DBLP | reliable — but see [D-030](DECISIONS.md#d-030--identity-internal-id-first-external-ids-as-evidence) on non-Western names |
| Employment history, dated | ORCID employments (self-asserted; organisations are **Ringgold**-coded, so a Ringgold→ROR crosswalk is needed to join to the institution spine — not directly ROR-linked) | partial |
| **Past doctoral students** | thesis registries — theses.fr, DART-Europe, NDLTD | partial, country-dependent ([D-025](DECISIONS.md#d-025--past-students-are-obtainable-current-students-still-are-not)) |
| Grant funding, PI, amounts | NIH RePORTER, NSF, UKRI GtR, Crossref Funder Registry | partial |
| Advertised positions | EURAXESS + national portals | partial — the answer for countries with no personal "joining page" culture |
| Recruiting prose, lab roster | the professor's own pages | ~20% populated ([D-022](DECISIONS.md#d-022--the-flagship-field-is-20-populated-and-the-product-must-say-so)) |

The vacancy-board rung matters more than it looks: the plan originally assumed a
North-American culture where professors publish personal openings pages. In much of the
world positions are advertised centrally instead, and without EURAXESS-class sources a
country-scoped run would report "no signal" for an entire country that is actively hiring.

---

## 3. Claims, not fields

Nothing stores a bare value. Every fact is a **Claim**:

```
Claim {
  entity_id, field, value,
  quote,                    -- verbatim supporting sentence
  source_url, snapshot_hash, quote_offsets,
  observed_at, extractor{agent, model, prompt_version, schema_version},
  confidence, superseded_by
}
```

This is the structural answer to pain point P1 — provenance existed in the corpus only as
prose, so it could not be filtered, joined, diffed or validated.

**Verification is structural, not prose.** The model returns an exact quote; deterministic
code locates that quote in the stored snapshot. If it isn't there, the claim is rejected
before it reaches the database. The corpus's "never invent, cite a URL and date" preamble
was in force when it produced a hallucinated co-authorship — prose instructions are
documentation, not a control.

**Two limits stated plainly:**

- Verification proves *fidelity*, not *truth*. It confirms the model didn't invent text
  relative to the fetched page. The page itself can be wrong or stale — the corpus
  contains a professor's own page asserting a years-out-of-date leave.
- Quote offsets are into *normalised extracted text*, so they are valid only for a given
  extractor version. The extractor version is therefore part of the claim, and changing it
  invalidates offsets rather than silently shifting them.

**Conflicts are first-class.** When two sources disagree, both claims are kept and a
`Conflict` records the disagreement. The corpus tracked conflicts by hand in
`06_Conflicts_Risks_SourceIndex.md`; here it is a table with a resolution state.

**`NOT_FOUND` is a required value in every extraction schema**, distinct from null. A model
that cannot abstain will guess, and with recruiting status ~20% populated, abstention is
the majority correct answer.

---

## 4. Where the LLM is allowed to act

The governing rule, stated precisely rather than as a slogan:

> **The model may classify, extract and summarise from text placed in front of it. It may
> never originate a number, a name, a URL or a date that does not appear in its input.**

The looser "the model never originates a number" is wrong — fit scoring is inherently
model-derived — and shipping a rule the system breaks on day one is worse than shipping
none.

| Stage | LLM? | Rationale |
|---|:--:|---|
| Directory / link discovery | no | href extraction + host classification — regex and a dict |
| Bibliometrics | no | API clients; the model must never touch a citation count |
| Deduplication, identity | no | deterministic on IDs, flagged for review on collision |
| Recruiting-sentence *candidate* detection (T1) | no | regex over stripped text; high recall, low precision by design |
| Recruiting **state** classification (T2) | **yes** | negation, modality, tense, cycle-scoping — genuinely linguistic |
| Eligibility and funding extraction (T2) | **yes** | prose rules into structured fields, with quote verification |
| Fit narrative | **yes** | explicitly a judgement, local-only, never exported ([D-024](DECISIONS.md#d-024--evaluative-judgements-about-individuals-stay-local-and-unexported)) |
| Scoring arithmetic | no | transparent weighted components the user can re-weight |

**Translation caveat.** Machine translation damages exactly the constructs recruiting
classification depends on — negation, modality, tense (*"I will not be accepting"*, *"I may
be able to consider"*). So: classify in the **original language**, store the original as
evidence, and translate only for display. Translate-then-extract inverts the error into
the field that matters most.

### Agent topology

Agents are defined by **what needs judgement**, not by what produced a file in the
prototype. The prototype's five output files were a *document* structure; promoting them
to agent boundaries would be agents-for-the-sake-of-agents.

| Agent | Model tier | Job |
|---|---|---|
| `recruiting-analyst` | high | classify state, target-cycle and datedness from verbatim text — see note below |
| `eligibility-analyst` | high | admissions rules, degree routes, language bands, funding conditions |
| `profile-synthesist` | high | per-professor narrative for the shortlist, from verified claims only |
| `evidence-auditor` | high | adversarial re-verification; risk-weighted sampling, not 100% |
| `adapter-author` | mid | propose a DirectoryAdapter YAML from a failed fetch |

**Workers return a task id and a status enum. Nothing else.** All output goes to the
database. Ten lines × 300 professors is 3,000 lines back into the orchestrator; the budget
has to be per-run, not per-agent.

**Auditor sampling is budget-aware and risk-weighted.** Auditing 100% of every claim with
the most expensive model plausibly costs more than the rest of the pipeline combined. 100%
applies only to claims that flip an eligibility gate or a deadline; everything else is
sampled.

**Recruiting classification is normalised against the student's target cycle.** The
`recruiting-analyst` does not just read "am I recruiting" off a page — it takes the verbatim
quote *in its original language*, `observed_at`, today's date, the student's `target_cycle`,
and a per-country **intake calendar**, and resolves the raw statement into a `state` *relative
to that cycle*. "Not taking students this year," observed in 2025, is not evidence about Fall
2027. Negation and modality are handled in the original language, never after machine
translation. The intake calendar is generated per country (fall-with-December-deadline is not
universal) with a documented default and a confidence flag when inferred
([D-050](DECISIONS.md#d-050--recruiting-classification-is-normalised-against-the-students-target-cycle)).

### Tool roster

The deterministic tools, named canonically ([D-055](DECISIONS.md#d-055--one-orchestration-vocabulary-with-a-crosswalk)). These are the names used in the atlas and `SKILL.md`; the module paths are in §7. No LLM runs inside any of them.

| Tool | Module | Does |
|---|---|---|
| `discovery-ladder` | `discover/` | rungs 1–6 (§2) — enumerate professors per targeted university |
| `fetcher` | `fetch/` | the three-phase fetch (§2) — robots, rate-limit, cache, snapshot |
| `deep-dive` | `extract/` | per-shortlisted-professor collection; calls the analyst agents |
| `gap-queue` | `extract/` | tracks the exact `(entity, field)` pairs still missing |
| `chrome-prompt-generator` | `extract/` | emits the Phase-3 prompt with the shared MD contract ([D-051](DECISIONS.md#d-051--one-shared-markdown-grammar-for-the-human-rung)) |
| `md-ingester` | `extract/` | parses the returned Markdown into Claims; resumes the run |
| `scorer` | `score/` | hard gates + weighted components (§5) |
| `exporter` | `export/` | the four-state JSON ([D-046](DECISIONS.md#d-046--the-json-export-contract-is-the-systems-interchange-format-with-a-four-state-value-envelope)) + the self-contained dashboard |

Intent interpretation and query generation are **not** tools — they are done by the
orchestrator (Claude) inline, producing the `SearchPlan`
([D-045](DECISIONS.md#d-045--intent-interpretation-and-query-generation-are-orchestrator-inline-producing-a-searchplan)).

---

## 5. Ranking

Hard gates, then a transparent weighted score, then the user's own weights.

1. **Hard gates** fire only on **gate-eligible** claims — a `Claim.confidence` of
   `quoted_official`, or `derived` from quoted-official inputs
   ([D-047](DECISIONS.md#d-047--one-canonical-confidence-model)). `inferred` and `unconfirmed`
   claims may sort and warn, never gate. A blocked professor is shown as **blocked with the
   reason and its source**, never removed from view.
   **Which gates apply depends on `intent_kind`** ([D-059](DECISIONS.md#d-059--hard-gates-are-intent-aware)):
   a `pre_phd`/RA/mentor search is gated on availability and remote-OK, *not* on degree-route
   or language bands (those are Master/PhD admission facts); `phd`/`master` get the full
   admission gates; `postdoc` gets PhD-in-hand + funding. Gating an RA seeker on
   direct-entry-from-bachelor's rules — as an intent-blind scorer would — breaks the pre-PhD
   case the product exists for.
2. **Unreliable fields sort and warn — they never filter**
   ([D-023](DECISIONS.md#d-023--nationality-and-export-control-are-never-a-hard-filter)).
   This covers nationality, grade-scale conversion, language-band mapping, and
   `availability_status`.
3. **Score components are visible and re-weightable.** The corpus's dashboard documented
   its blend in prose and never implemented it — `tier` was hand-typed and the shortlist
   was 20 hardcoded name strings, so a typo silently dropped a professor.
4. **Sparse evidence lowers score confidence, not score.** A professor with two claims and
   a professor with twenty should not be ranked as if equally known. **Author-disambiguation
   risk is a first-class score-confidence penalty** — a fragmented OpenAlex profile must lower
   confidence, never silently read as "inactive" ([D-057](DECISIONS.md#d-057--fragmented-works-lists-are-reconciled-before-scoring-not-just-flagged)).

**Research-fit is matched on topic IDs, not text.** The shortlist gate's `topic_match` compares
the professor's structured OpenAlex topics against the **`resolved_topic_ids[]`** the
orchestrator put in the `SearchPlan` — deterministic ID-overlap, not brittle string matching,
so a "causal NLP" seeker still matches a professor tagged "NLP" + "causal inference" separately
([D-058](DECISIONS.md#d-058--research-fit-matching-is-on-openalex-topic-ids-resolved-in-the-searchplan)).
This is what makes "research-fit is cheap and available before the deep dive" actually true.

**Reconcile before you rank.** For flagged or low-ORCID-coverage authors, the works list is
reconciled (ORCID anchor, else venue/co-author/institution clustering) *before* topic-match and
activity are computed — otherwise the professors most likely to be wrongly dropped from the ~40
are the non-Anglo names the project exists to serve
([D-057](DECISIONS.md#d-057--fragmented-works-lists-are-reconciled-before-scoring-not-just-flagged)).

**Rolls up to programs.** The user cannot buy professors; they buy applications. Two
professors in one department cost one fee, two in different schools cost two
([D-031](DECISIONS.md#d-031--the-product-must-model-the-users-actions-not-only-the-world)).

---

## 6. Freshness

Freshness is the product. The corpus's 9-day manual recheck found real changes — a new
recruiting line, a status flipping to "no openings at the moment", a professor leaving the
country.

Per-field TTLs by volatility: recruiting 7–14 days · deadlines weekly in season · rosters
and news monthly · bibliometrics quarterly · admissions rules once per cycle.

**The crawl-budget arithmetic has to be done, because it does not close naively.** One
university with 500 monitored professors at a courteous 1 request per 5–10 seconds is
40–80 minutes of sustained traffic to a single host, per cycle. Ten universities on a
7-day TTL is a permanently-running crawler against ten institutions.

Therefore re-verification is **watch-list-first**: full TTL sweeps apply to the user's
pinned and shortlisted professors, not to the whole enumerated set. Everything else
refreshes on demand. This keeps the tool a research assistant rather than a crawler, and
it is a politeness constraint before it is a performance one.

---

## 7. Repository layout

```
supervisorly/                     # name locked — D-012 (was profscout)
├─ .claude/
│  ├─ skills/supervisorly/SKILL.md # orchestrator; trigger description + phases
│  └─ agents/*.md                 # the five agents above
├─ src/supervisorly/
│  ├─ discover/                   # the ladder: cris, sitemap, jsonld, ct, openalex, adapter
│  ├─ fetch/                      # robots, rate limit, cache, snapshot store
│  ├─ extract/                    # deterministic parsers + LLM extraction w/ verification
│  ├─ model/                      # entities, claims, conflicts, migrations
│  ├─ score/                      # gates + weighted components
│  ├─ export/                     # four-state JSON (§10) + self-contained dashboard
│  └─ cli.py                      # every stage independently runnable
├─ adapters/<country>/<inst>.yaml # data, not code — the contribution surface
├─ dashboard/                     # single self-contained HTML + JSX — D-033, D-048
├─ tests/fixtures/                # recorded cassettes + synthetic records — D-011
├─ docs/                          # this directory
└─ optout.txt                     # enforced at build time, with a test — D-053
```

**Every stage is independently runnable from the CLI**, exactly as `career-scan`'s scripts
are. That is what makes the pipeline debuggable, testable, and portable to other hosts:
the deterministic layer has no LLM in it at all, and the LLM layer sits behind one
provider adapter ([D-007 in the synthesis](requirements.md)).

---

## 8. What "portable to other LLMs" actually requires

Claude Code gives permission enforcement for free. **No other host does.** The day this
runs under a different runner, `settings.json` enforces nothing.

So safety lives in the Python layer, not in host configuration:

- An allowlisted HTTP client — GET/HEAD only, no auth headers, no form posts, no mail
- `robots.txt` checked in the fetch path, failing closed
- `optout.txt` applied at build time, with a test that fails if an opted-out record
  survives into output

Portability also needs what an aspiration doesn't: a **golden eval set with per-model pass
thresholds**, plus **recorded LLM cassettes** so tests run offline and deterministically. That
eval set is built from **recorded HTTP cassettes** (public pages the tool fetches during a test
run) and **hand-authored synthetic records** — never from the corpus
([D-011](DECISIONS.md#d-011--validation-strategy), [D-035](DECISIONS.md#d-035--the-corpus-is-a-methodology-reference-not-a-data-source)).
The corpus is a methodology reference only; no harvested professor record, including any
"verified" file, is imported as test data.

**A raw cassette is not an eval — it must be labelled.** A recorded HTTP capture proves the
pipeline *runs*; it says nothing about whether the extraction was *right*. The per-model pass
thresholds have nothing to grade against until someone writes the **expected extraction** for
each cassette. So the eval set is a **named schema-phase deliverable**
([D-063](DECISIONS.md#d-063--the-eval-set-is-hand-labelled-cassettes-and-it-is-a-named-deliverable)):
hand-labelled captures over **≥3 directory shapes across ≥3 countries**, each field's expected
value authored from the tool's own live capture (permitted — it is the tool's fetch, not the
corpus), with explicit ownership of who writes the labels.

---

## 9. Honest install story

"Clone the repo, run one command, open a dashboard" is not achievable as stated. The real
requirements differ by mode ([cost-and-performance.md §4](cost-and-performance.md)):

- **Skill mode (default)** — the student runs it inside Claude Code, so the LLM work is
  covered by their existing subscription: **no separate API key.** They still need Python,
  optionally Playwright binaries, and network access.
- **Headless mode** — running the pipeline outside Claude Code needs the student's own LLM API
  key, on top of the same Python and network requirements.

**Both modes need two free data-source credentials, and the setup fails loud without them:**
a **ROR client ID** (required *now* as of 2026-07 — without it ROR drops to 50 requests / 5
minutes) and a **free OpenAlex API key** (without it the daily credit ceiling is $0.10 ≈ ~2
scans, not the ~20 the cost model assumes with a key). Both are free and take a minute; the
first-run check refuses to proceed silently on the throttled tiers and tells the student
exactly what to get ([cost-and-performance.md §2](cost-and-performance.md);
[D-014](DECISIONS.md#d-014--country-scale-reads-use-the-openalex-snapshot-not-the-api),
[D-020](DECISIONS.md#d-020--enumerating-universities-per-country-is-viable)).

Two things fix the clone-and-run gap without overpromising:

1. **State the real install honestly** in the README.
2. **Ship `--offline --demo`** backed by fixtures, so clone-and-run genuinely works and a
   stranger sees a populated dashboard in under a minute.

The demo data is the **non-personal layer** — program deadlines, funding rules, application
cycles — plus **synthetic professor records** and, at most, a handful of **clearly-public,
self-published pages the demo fetches live**. It is **never** the harvested corpus: the corpus
is a methodology reference, not a data source, so no harvested record ships as demo or fixture
data ([D-035](DECISIONS.md#d-035--the-corpus-is-a-methodology-reference-not-a-data-source),
[D-011](DECISIONS.md#d-011--validation-strategy)). Scan output stays local and uncommitted
([D-005](DECISIONS.md#d-005--scan-output-is-never-committed)).

---

## 10. The output surface — export contract and dashboard

The scan's real deliverable is a **JSON export**; the dashboard is a view over it
([D-026](DECISIONS.md#d-026--sqlite-is-the-source-of-truth-json-is-the-export),
[D-046](DECISIONS.md#d-046--the-json-export-contract-is-the-systems-interchange-format-with-a-four-state-value-envelope)).
Three parts make it a real contract rather than an afterthought.

**1. A per-field value envelope with an explicit state.** No field is a bare value; each is:

```
{ state, value, quote, source_url, snapshot_hash, observed_at, confidence, extractor }
```

`state` ∈ **`value`** (we have it) · **`searched_absent`** ("we looked, found nothing" — a
`NOT_FOUND` claim exists) · **`never_attempted`** (no claim yet) · **`blocked`** (a source
failed, or it is awaiting the human rung). The four states are derived *deterministically*
from the claim store and `CoverageRecord`, and the dashboard renders each distinctly — a blank
recruiting field, the ~20% populated norm, must read as an honest state, not a bug
([D-022](DECISIONS.md#d-022--the-flagship-field-is-20-populated-and-the-product-must-say-so),
[D-037](DECISIONS.md#d-037--per-professor-capture-is-dynamic-not-templated)).

**2. A field-metadata descriptor.** `{ id, label, kind (filter|sort|facet|score-input),
datatype, unit, facet_domain }` per field, so the **generic** dashboard adapts to whatever the
search produced instead of assuming fixed columns — the columns are data, not code
([D-038](DECISIONS.md#d-038--queries-and-keywords-are-generated-per-search-never-looked-up)).

**Exports honour the personal-data rules:** LLM judgements about people and bare email lists
never serialise ([D-024](DECISIONS.md#d-024--evaluative-judgements-about-individuals-stay-local-and-unexported)).

**3. The dashboard, concretely** ([D-033](DECISIONS.md#d-033--dashboard-technology),
[D-048](DECISIONS.md#d-048--dashboard-delivery-pre-transpiled-jsx-vendored-inline-no-runtime-toolchain)).
A single self-contained HTML file with embedded JSX/React — **no build toolchain, no CDN,
offline-capable**:

- the exporter **pre-transpiles** the JSX to plain JS at build time (no ~3 MB runtime Babel);
- **React and a small virtualiser are vendored inline** (virtualisation is what lets it survive
  thousands of rows);
- a **readable JSX source block is retained** so the student's Claude session can edit the UI
  and re-export ([D-041](DECISIONS.md#d-041--the-dashboard-is-claude-interactive));
- the data is **inlined into the HTML and also written to the sibling JSON**, so the file is a
  view, not the only copy.

**Terminal states — the dashboard is never blocked on the human**
([D-049](DECISIONS.md#d-049--terminal-run-states-the-dashboard-is-never-blocked-on-the-human)).
It is generated/refreshed **after Phase 2**, with unfilled gaps marked distinctly
(`blocked`/awaiting-human vs `searched_absent` vs `never_attempted`). If the student never
returns the Phase-3 Markdown — the common case — the run reaches `finalized_with_open_gaps`
and stays resumable; if the MD arrives later, ingestion fills the gaps and re-exports. A
zero-result run short-circuits Stages 2–4 and renders a coverage/empty-state dashboard that
distinguishes "no professors matched the field" from "the country's sources returned nothing."
