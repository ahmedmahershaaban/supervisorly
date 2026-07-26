# Decision Log

Append-only record of design decisions, why they were made, and what would reverse them.
Newest decisions are added at the bottom. Each entry is numbered so other documents can
cite it as `D-007`.

Status values: **locked** (agreed, build on it) · **provisional** (chosen to keep moving,
cheap to reverse) · **open** (needs a human decision) · **superseded** (replaced, kept for
history).

---

## D-001 — Repository location

**Status:** locked (Ahmed, 2026-07-22)

The project lives at `D:\AndroidStudioProjects\how_to_get_proffessor\`. The folder was
empty apart from a stray copy of an unrelated `CLAUDE.md`.

---

## D-002 — v1 targets any country, not one region

**Status:** locked (Ahmed, 2026-07-22)

Generic from the start: the user names a country and a set of universities.

**Trade-off accepted:** correctness is much harder to verify when output can come from any
country. Mitigation proposed — build the country/university layer as pluggable adapters,
and ship a golden-dataset regression test built from records Ahmed already verified by
hand, so changes are checked against known-true data. Ahmed has not yet responded to the
mitigation; it is recorded as [D-011](#d-011--validation-strategy).

---

## D-003 — Dashboard ships as a single self-contained HTML file

**Status:** locked (Ahmed, 2026-07-22)

No install step, no dev server, opens in any browser, works offline, easy to share.
Consistent with the two dashboards Ahmed already built (`dashboard.html`,
`mila-mission-control.html`).

**Implication:** the scan must emit clean structured data as a separate artifact, so the
HTML file is a *view* over it rather than the only place the data exists.

---

## D-004 — Public open-source, MIT, portfolio-grade

**Status:** locked (Ahmed, 2026-07-22)

The repository is intended to double as evidence of independent research and engineering
capability for a PhD application. Engineering quality is therefore a hard requirement, not
a nice-to-have.

**Implication:** readable code, explanatory comments, real tests, honest documentation,
and a defensible reason to exist.

---

## D-005 — Scan output is never committed

**Status:** locked

Output contains personal data about identifiable living people (names, institutional
emails, affiliations, career history). Committing it to a public repository would publish
a personal-data aggregation with no consent, no retention policy, and no correction
mechanism.

Encoded in `.gitignore`. Revisit only with an explicit, documented consent and takedown
process.

---

## D-006 — The working name "ProfScout" is abandoned

**Status:** locked (prior-art review, 2026-07-22)

`satyam-thakur/profscout` already exists on GitHub (pushed 2026-07-19) and describes
almost exactly this product. `phd-scout` and `ProfRadar` are also taken.

Candidates verified free on npm, PyPI and GitHub: **Supervisorly**, **AdvisorScope**,
**ProfAtlas**. Final choice is [D-012](#d-012--project-name), pending Ahmed.

**Implication for code:** the product name must live in exactly one constant so renaming
is a one-line change.

---

## D-007 — Positioning: the gap is non-CS, non-US, and relationship data

**Status:** locked (prior-art review, 2026-07-22)

Every comparable tool found is a wrapper around CSRankings, which restricts them to
computer science and to conference publications. The defensible gaps are:

1. Disciplines beyond CS
2. Countries beyond the US/UK
3. Country-first workflow with user-supplied university ranking
4. Students, lab size, and industry links — no existing tool covers these
5. Evidence provenance, including honest "unknown" rather than a confident guess

**Claims we must not make**, because they are already served: "runs on a local/private
LLM", "Claude-Code-first", and "detects whether a professor is recruiting" as a simple
boolean.

---

## D-008 — Curation is a first-class feature, not a fallback

**Status:** locked (prior-art review, 2026-07-22)

**Evidence:** the highest-starred applicant-facing project found
(`Rex-7/Prof-List-For-10043-Student`, ★60) is a hand-curated spreadsheet with a
community-maintained recruiting-quota column. It outperformed every automated competitor
because the decisive facts — is this professor taking students, is the funding real, what
are they like to work with — are not present in any API.

**Therefore:** the system must support a human-maintained overlay that takes precedence
over harvested data, is diffable, and can be contributed back by other users. A tool that
only automates will lose to a spreadsheet.

---

## D-009 — Deterministic collection, LLM interpretation

**Status:** provisional

Scripts fetch, parse, normalise and cache; language models are used only where judgement
is genuinely required (classification, summarisation, ambiguous matching).

**Rationale:** cost and reproducibility. An LLM call per professor across several hundred
professors is expensive and non-reproducible. This also mirrors the pattern in Ahmed's
existing skill (`collect_facts.py` produces facts, agents interpret them).

---

## D-010 — Every field carries provenance and confidence

**Status:** provisional

No value is stored bare. Each carries its source URL, retrieval timestamp, method, and a
confidence level, and "unknown" is a valid, displayed state.

**Rationale:** the failures in Ahmed's manual corpus were all confidently-wrong automated
data — a citation count off by 5x, an unverified co-authorship, a fabricated credential.
The dashboard must let a user see *why* it believes something.

---

## D-011 — Validation strategy

**Status:** locked (Ahmed, 2026-07-23) — **superseded by [D-035](#d-035--the-corpus-is-a-methodology-reference-not-a-data-source)**

The original proposal — a regression fixture built from the 104 hand-verified professor
records — is **rejected**. Ahmed will not allow any harvested professor data into the
project ([D-035](#d-035--the-corpus-is-a-methodology-reference-not-a-data-source)).

Validation instead comes from data the project acquires itself:
- **Recorded HTTP cassettes** — live public pages the tool fetches during a test run,
  saved as fixtures. These are the tool's own captures, not Ahmed's notes.
- **Synthetic records** — hand-authored professor/program fixtures with no real person, to
  exercise the schema, the honest-null UX, and the scoring gates.
- **A small set of clearly-public, self-published pages** fetched live in an integration
  test, chosen for being unambiguously public.

The "validated against N verified records" credibility line is dropped, because its source
would have been the corpus. Correctness is demonstrated on cassettes and synthetic data
instead.

---

## D-012 — Project name

**Status:** locked (Ahmed, 2026-07-23) — **Supervisorly**

Chosen over AdvisorScope and ProfAtlas. Verified free on npm, PyPI and GitHub at decision
time. The word "supervisor" is itself the non-US signal — "advisor" is the North American
term; most of the world says "supervisor" — which aligns the name with the project's
defensible gap ([D-007](#d-007--positioning-the-gap-is-non-cs-non-us-and-relationship-data)).

Per [D-006](#d-006--the-working-name-profscout-is-abandoned), the name lives in exactly one
constant. All doc placeholders reading `profscout` are to be read as **Supervisorly** /
package `supervisorly` until the code is scaffolded.

---

## D-013 — API-first spine; page scraping is enrichment only

**Status:** locked (data-source research, 2026-07-22)

**Evidence:** six real faculty pages were fetched across five countries. Zero had
schema.org `Person` markup, two URLs returned 404, one was a JavaScript single-page app
with no server-rendered content, and one returned "Account Suspended". Faculty-page
scraping degrades worst in exactly the non-Anglo countries this project exists to serve.

**Architecture:**

| Layer | Source | Role |
|---|---|---|
| L0 | ROR + OpenAlex `/institutions` (joined on ROR ID) | enumerate universities in a country |
| L1 | **OpenAlex `/authors`** | the spine — the canonical researcher record |
| L2 | ORCID, DBLP | identity confirmation, role/employment, CS precision |
| L3 | Crossref funders, OpenAlex `/awards`, arXiv, OpenAIRE, CORE | pluggable enrichment |
| L4 | Targeted single-page fetch | only for a shortlisted professor, never bulk |

---

## D-014 — Country-scale reads use the OpenAlex snapshot, not the API

**Status:** locked (data-source research, 2026-07-22)

**Evidence:** OpenAlex has moved to a credit model. Verified response header
`x-ratelimit-limit-usd: 0.1` unauthenticated; a free API key raises it to $1/day. List
calls cost ~$0.0001 and search calls ~$0.001. Sweeping every professor in a country is
not affordable through the API.

The bulk snapshot is **CC0** (verified from the S3 `LICENSE.txt`) and is the correct
substrate for country-scale work; the API is for targeted lookups and refreshes.

**Implication:** the tool needs two modes — a *targeted* mode that works immediately with
no setup, and a *bulk* mode that requires a one-time snapshot download. This must be
explicit in the cost model and the README.

---

## D-015 — Semantic Scholar is not a primary source

**Status:** locked (data-source research, 2026-07-22)

**Evidence:** the undercount Ahmed hit in his manual research is reproducible and is
caused by author-entity **fragmentation**, not missing works. One researcher was split
across 12 S2 author entities (309/20/13/10/4 papers …) where DBLP held a single record.
Separately, 8 of 8 unauthenticated requests returned HTTP 429.

Usable only as an optional cross-check, never as the identity spine.

---

## D-016 — "Students" is not obtainable; ship `recent_collaborators` instead

**Status:** locked (data-source research, 2026-07-22) — **contradicts an explicit user request**

Ahmed asked for a professor's students as a headline dashboard entity. It cannot be
sourced:

- OpenAlex holds ~11M dissertations, but the records carry **no supervisor field**
- ORCID education sections were empty on both records tested
- ProQuest Dissertations holds the data but is paid and closed

**What ships instead:** `recent_collaborators` — frequent recent co-authors at the same
institution with a short publication history. This proxy was built and tested during
research. It correlates with lab membership but is not equivalent.

**Naming is a hard rule:** the field, the UI label, and the docs must all say
*collaborators*, never *students*. Presenting inference as fact is the exact failure mode
that produced the bad data in Ahmed's manual corpus.

---

## D-017 — Industry links: build affiliations, degrade funders, drop placements

**Status:** locked (data-source research, 2026-07-22)

| Sub-feature | Verdict | Basis |
|---|---|---|
| Professor's own industry affiliations | **build** | OpenAlex types company affiliations (833k company-affiliated authors in Germany alone) |
| Companies funding the lab | **degrade gracefully** | Crossref funder DOIs are global, but OpenAlex `/awards` has no `lead_investigator.id` filter and coverage is thin — Egypt has 104 awards in total |
| Student/alumni placements | **do not build** | no open source exists |

---

## D-018 — "Recruiting" is a tiered, evidence-cited signal — never a boolean

**Status:** locked (data-source research, 2026-07-22)

No structured source records whether a professor is accepting students. The signal lives
in lab-page prose, job boards (EURAXESS and national equivalents), and inference from
newly-started grants.

Ships as a 3-tier signal, each tier carrying its evidence and a "last checked" timestamp.
A competitor already implements this as a regex boolean ([D-007](#d-007--positioning-the-gap-is-non-cs-non-us-and-relationship-data));
the defensible version is multi-signal, evidenced, and honest about staleness.

---

## D-019 — Legal and ethical posture

**Status:** locked (data-source research, 2026-07-22)

Professors are identifiable living people, many in the EU, so this is personal-data
processing and GDPR applies.

- Legitimate-interests basis, with a written Legitimate Interests Assessment in the repo
- Article 14 transparency notice (data obtained from third parties, not the subject)
- A working `optout.txt` honoured at build time, plus a documented takedown route
- `robots.txt` parsed and obeyed in code, not merely promised in the README
- Honest User-Agent carrying a contact address; aggressive caching to minimise requests
- **Never scrape Google Scholar** — verified `Disallow: /scholar`, and `cstart=`
  pagination is blocked even on the `/citations?user=` carve-out
- ORCID Public API is **non-commercial use only** per its ToS; the CC0 Public Data File
  is the escape hatch if that ever binds
- CSRankings is **CC BY-NC-ND** — link to it, never redistribute its data
- **No bulk-email or automated-outreach feature**, ever ([D-007](#d-007--positioning-the-gap-is-non-cs-non-us-and-relationship-data))

---

## D-020 — Enumerating universities per country is viable

**Status:** locked (data-source research, 2026-07-22)

ROR and OpenAlex agree to within 84–102% on institution counts across Egypt, Germany,
Japan, Brazil, India, the US, Great Britain, Nigeria, Indonesia and Iran — so the
country-first premise holds.

**Trap:** ROR `types:education` includes primary and secondary schools; the first Egyptian
result during testing was an international school. Filter on `works_count > 100`.

---

# Round 2 — after corpus discovery and adversarial review

The following supersede or refine earlier entries. Sources: `requirements.md`,
`domain-model.md`, `parameter-catalog.md`, `critiques.md`.

---

## D-021 — Three-tier pipeline, shortlist formed on research fit

**Status:** locked — **supersedes the two-stage reading of [D-009](#d-009--deterministic-collection-llm-interpretation)**

Two independent critics found the same circularity: a "cheap enumerate → user approves
shortlist → expensive deep dive" design asks the user to filter on recruiting status,
funding and eligibility — **fields that only exist after the deep dive.**

Resolved with three tiers, where the shortlist is formed on **research fit and activity**
(cheaply available from OpenAlex) rather than on recruiting status (not available yet).
T1 adds a no-LLM pass over everyone — one cached page fetch, boilerplate strip, regex —
so the shortlist decision is informed. Full table in
[cost-and-performance.md §3b](cost-and-performance.md).

---

## D-022 — The flagship field is ~20% populated, and the product must say so

**Status:** locked — **corrects an assumption in [D-018](#d-018--recruiting-is-a-tiered-evidence-cited-signal--never-a-boolean)**

The synthesis assumed recruiting status would be obtainable at ~80% coverage. **Ahmed's
own corpus refutes it: only 20 of 104 professors had a verbatim recruiting quote, and an
institutional accepting-students checkbox existed at exactly one school.** The realistic
populated rate is ~20%.

**Therefore:** "no signal found" is the majority state and must be designed as the
default UI case, not an edge case. A dashboard that looks broken when 80% of its
headline column is blank is a dashboard that fails on real data. Sort and display must
make an empty recruiting field *useful* (fall back to activity, funding, cycle timing)
rather than merely empty.

---

## D-023 — Nationality and export-control are never a hard filter

**Status:** locked

The parameter catalogue proposed nationality/export-control eligibility as a hard gate
that removes professors from view. The product critic identified this as **the
highest-harm error the system can make**: nationality-based exclusion, computed
unreliably (the field's own confidence is `hard`), silently deleting viable options a
user would have pursued.

The same reasoning applies to every gate built on an unreliable normalisation — grade
scales ([genericity #5](requirements.md), explicitly unsolved), language-band conversion,
and `availability_status`.

**Rule:** unreliable fields may **sort, warn, and annotate**. They may never **filter
rows out of view.** An excluded row is invisible, so its caveat is never read. Hard gates
are reserved for facts with `reliable` confidence and a cited source.

---

## D-024 — Evaluative judgements about individuals stay local and unexported

**Status:** locked

The model included LLM-generated judgements about named academics: `bandwidth_risk_note`,
`lab_wellbeing`, `junior_first_authorship_ratio`, staleness verdicts, fit narratives.

These are published evaluative claims about identifiable people, produced by a model,
with no right of reply. Aggregated into a shareable export they are defamation-adjacent
and a guaranteed source of takedown mail.

**Therefore:** such fields are computed locally, displayed locally, and **excluded from
every export and share path.** Facts with citations export; judgements do not.
`junior_first_authorship_ratio` is dropped entirely — author order is meaningless in
alphabetical-authorship fields (theoretical CS, cryptography, maths, much of economics),
so the metric is not merely risky but frequently wrong.

---

## D-025 — Past students *are* obtainable; current students still are not

**Status:** locked — **refines [D-016](#d-016--students-is-not-obtainable-ship-recent_collaborators-instead)**

D-016 said no source records supervision. That is true of the sources examined, but the
scraping critic identified a category that was missed: **national doctoral thesis
registries** — `theses.fr`, DART-Europe, NDLTD, and national equivalents — which publish
completed dissertations **with the supervisor named**, structured and legally reusable.

| Question | Verdict |
|---|---|
| Who did this professor supervise, historically? | **obtainable** in countries with a thesis registry |
| Who is in this lab *right now*? | still **not obtainable** — registries are retrospective |
| Where did those graduates go? | partial — ORCID employments, OpenAlex affiliation-over-time |

**Therefore:** ship `former_doctoral_students` as a *sourced, dated* field where a
registry covers the country, keep `recent_collaborators` as a clearly-separate inference,
and continue to make no claim about current lab membership. The naming rule from D-016
stands.

---

## D-026 — SQLite is the source of truth; JSON is the export

**Status:** locked

The corpus failed because prose files cannot join, dedupe or diff — the same funding
table was hand-retranscribed into four separate files and drifted.

SQLite gives real joins, full-text search, and an append-only claim history in a single
zero-install file. Deterministic JSON export feeds the dashboard and is what gets
reviewed in diffs, since SQLite is binary and git cannot diff it.

**Guard against the failure mode the critics named:** per-field claim history over
10⁵ people would reach 10⁷+ rows, and archived page snapshots would make the file
multi-gigabyte. Snapshots therefore live on the filesystem addressed by content hash,
never as blobs in the database, and the DB is never committed.

---

## D-027 — DirectoryAdapters are data files, not code

**Status:** locked

Per-institution adapters (rendering mode, endpoint, selectors, pagination, slug pattern)
are the genericity mechanism *and* the community contribution surface. If adding Germany
means editing Python, nobody contributes.

Adapters are YAML validated against a JSON Schema, with a test that runs each adapter
against a recorded fixture.

**Honest caveat the critics raised:** adapters scale with *institutions*, not countries,
and a country can hold 4,000+ institutions. Adapters alone are therefore not a scaling
answer — they are the fallback when the generic paths fail. The generic paths must come
first (see [D-028](#d-028--generic-discovery-before-per-site-adapters)).

---

## D-028 — Generic discovery before per-site adapters

**Status:** locked

Guessing directory paths (`/people`, `/faculty`, …) was the plan's discovery mechanism.
The critics supplied a far better ordered ladder, every rung of which is standards-based
and works without per-site work:

1. **CRIS portals** — Elsevier Pure, Converis, Symplectic. In the UK, Nordics, NL, DE, AU
   and much of Asia the faculty directory *is* a Pure portal with a uniform, documented
   API. This is the single biggest miss in the original plan.
2. **`sitemap.xml`** via the `robots.txt` `Sitemap:` directive — authoritative URL
   inventory, plus `hreflang` alternates for multilingual sites.
3. **Schema.org / JSON-LD `Person` markup** — emitted by many university CMSes, with
   `name`, `jobTitle`, `affiliation` and `sameAs[]` (which is literally the profile-link
   table, pre-built).
4. **Certificate Transparency logs** (crt.sh) for subdomain discovery — this directly
   solves the corpus's own failure where `eecs.yorku.ca` 404s and the real host is
   `lassonde.yorku.ca`.
5. **OpenAlex as an enumeration source**, not only enrichment.
6. Per-site adapter, only when 1–5 all fail.

---

## D-029 — Resumability and extraction caching are schema, not afterthoughts

**Status:** locked

Every prior session in the corpus died at context exhaustion mid-run. Resumability must
come from `SELECT` on persisted job state, not from an agent remembering where it was.

- **`Run` / `Task` / `Checkpoint` entities** — run id, params, budget, status; task keyed
  by (target × stage) with its own status.
- **`ExtractionCache`** keyed by `(snapshot_content_hash, prompt_version, model_id,
  schema_version)` — the dominant cost lever ([cost-and-performance.md §3b-i](cost-and-performance.md)).
- **Field→extractor mapping**, so a prompt change invalidates only the affected claims.

---

## D-030 — Identity: internal ID first, external IDs as evidence

**Status:** locked

Nothing is ever keyed on a display name. An internal UUID is minted at first sight;
ORCID / OpenAlex / DBLP IDs attach when confirmed and a match is decisive for merging.
`name_variants[]` is retained.

**Important caveat, and it lands close to home:** OpenAlex author disambiguation is fully
automated and demonstrably weak for common Chinese, Korean and Arabic names — producing
both split profiles and merged profiles that fuse two people's citation counts. Ahmed's
own Semantic Scholar discrepancy was this exact failure class, not a coverage gap.

**Therefore** OpenAlex is the enumeration spine but **not** a trusted identity authority
for non-Western names. Where an ORCID exists it wins; where names collide, the record is
flagged rather than silently merged. This matters disproportionately for the non-Anglo
coverage that is the project's whole reason to exist.

---

## D-031 — The product must model the user's actions, not only the world

**Status:** locked

93 catalogued parameters model professors, programs and funding — and **zero** model what
the applicant has actually done. The real daily loop is *who have I emailed, who owes me
a reply, who do I chase Monday, which applications are half-finished.*

Adds two entities:

- **`Outreach`** — status (not_contacted / drafted / sent / follow_up_due / replied /
  declined), dates, thread notes.
- **`Application`** — keyed to a program: materials checklist, fee paid, portal URL,
  reference-letter state.

Plus **user-owned record state** — pin, dismiss-with-reason, snooze-until — without which
a country-scale list re-presents the same 400 rejected rows every session and never
shrinks.

**Program-as-the-unit-of-cost:** the user cannot buy professors, they buy *applications*.
Two professors in one department cost one fee; two in different schools cost two. Ranking
must roll up to programs for the budget decision to make sense.

---

## D-032 — Scale is an ethical constraint, not just a performance one

**Status:** locked — strengthens [ethics-and-compliance.md](ethics-and-compliance.md)

Banning automated sending is necessary but not sufficient. A tool that emits 200 ranked
professors with per-person talking points is an industrial cold-email generator regardless
of who presses send — and mass templated outreach is exactly what makes faculty stop
reading cold email, harming every future applicant.

**Therefore:** the outreach brief is generated **one professor at a time, on explicit
request**, and there is no "generate all" path. This is a deliberate friction, and the
README should say why it exists.

---

## D-035 — The corpus is a methodology reference, not a data source

**Status:** locked (Ahmed, 2026-07-23) — a governing constraint on the whole project

> "I do not want to use any data I got from the professors in my files. They are only
> references — to see how to create filters, how to search on them, what the best keywords
> to extract are, and so on."  — Ahmed

The ~90 corpus files teach the project its **method**: which parameters matter, how
filters are structured, what vocabulary to extract, how a good per-professor record reads.
They do **not** supply the project any **content** about real people.

**What may be carried forward (structure and method):**
- the parameter catalogue, entity model and field lists ([parameter-catalog.md](parameter-catalog.md), [domain-model.md](domain-model.md))
- the extraction-keyword vocabulary and the recruiting-signal taxonomy
- the filter/sort/facet design and the dashboard layout ideas
- the provenance and verification discipline

**What may not (content about real people):**
- no harvested professor facts — citation counts, quotes, lab rosters, emails
- no seed data, demo data, or test fixtures built from the corpus
- no "validated against N verified records" claim sourced from it

This is stronger than [D-005](#d-005--scan-output-is-never-committed) (which forbade
committing *new* scan output): it also forbids importing the *existing* corpus as data,
even locally, even for tests. Every real fact the project shows must be one the project
fetched itself, live, from a public source it can cite.

**Practical consequence:** the corpus stays where it is, in `Documents\Downloads`, read by
humans and by the design process — never read by the pipeline, never copied into the repo,
never a runtime input. It reinforces the clean-room posture that makes the repo publishable
([ethics-and-compliance.md](ethics-and-compliance.md)).

---

# Round 3 — the generic, agent-driven flow (Ahmed, 2026-07-23)

Ahmed restated the product vision in detail. It is captured narratively in
[product-flow.md](product-flow.md); the decisions it forces are below.

---

## D-036 — Intent interpretation is Stage 0

**Status:** locked (Ahmed, 2026-07-23)

The agent must **understand the purpose behind the student's input before searching**, not
search literally for what was typed. The student's selections — country, field, subfield,
and *what they need* (training / pre-master / pre-PhD / mentor / Master's / PhD / postdoc) —
are interpreted into a search *plan*, which the student confirms before the expensive work
runs.

"Pre-PhD in causal NLP, Canada" is a plan (look for pre-doc/RA positions in that subfield at
Canadian institutions; check openings and lab pages, not degree-admission pages), not three
query strings. **The "what they need" selection changes where the agent looks and what
counts as a hit** — a postdoc seeker and a Master's applicant searching the same professor
want different signals.

---

## D-037 — Per-professor capture is dynamic, not templated

**Status:** locked (Ahmed, 2026-07-23) — reinforces [D-022](#d-022--the-flagship-field-is-20-populated-and-the-product-must-say-so)

There is no fixed per-professor schema the agent must fill exactly. It captures whatever it
can find — work, papers (count, recency, titles), position availability, contact route,
students and their links — and marks everything else **"no data found."**

**Hard rule: a professor is never dropped for missing data.** A thin record still appears,
with its gaps shown honestly. This is the inversion of the corpus's failure, where
low-information professors silently fell off the list. Absence of data is displayed, never
hidden by omission.

---

## D-038 — Queries and keywords are generated per search, never looked up

**Status:** locked (Ahmed, 2026-07-23) — the strongest form of [D-035](#d-035--the-corpus-is-a-methodology-reference-not-a-data-source)

> "I don't want you to learn the exact keywords, I want you to know how to make them."
> — Ahmed

The project ships **no keyword dictionary and no university list.** The agent *derives* the
search vocabulary — field terms, venue names, synonyms, the phrasings that signal a
recruiting statement or a pre-doc position — from the chosen field, subfield and intent, at
search time.

**Implication for the docs:** [parameter-catalog.md](parameter-catalog.md) and the keyword
examples throughout are illustrations of the *kinds* of parameters and terms to generate —
teaching material for the generation strategy — **not** a lookup table to embed. The tool
carries a *query-generation capability*, not a corpus of queries.

**The structure/dictionary boundary, stated explicitly** (so a builder doesn't blur it): a
**fixed enum of field names** — e.g. the recruiting-signal taxonomy buckets, `ContentItem`
types, the confidence levels — is *schema structure* and is allowed; it is the shape of the
data. A **fixed list of the words to search for in a given research field** is a *keyword
dictionary* and is forbidden — that must be generated per search. Enum of categories: yes.
Dictionary of a field's search terms: no.

---

## D-039 — Agent-driven web navigation is first-class; APIs are the fast path

**Status:** locked (Ahmed, 2026-07-23) — reconciles Ahmed's vision with [D-013](#d-013--api-first-spine-page-scraping-is-enrichment-only)

**The tension, stated plainly.** Ahmed's mental model is Claude navigating the web itself
(via the Claude web/Chrome surface) to read pages and pull data. The data-source research
found the opposite: raw faculty-page scraping failed on 0 of 6 real pages across 5
countries, while APIs and CRIS portals were reliable
([research/data-sources.md](research/data-sources.md)).

**Resolution — a three-phase escalation ladder, batched** (Ahmed, 2026-07-23). Each phase
runs across the whole target set and *marks* what it could not resolve; the next phase runs
only on that residual. This keeps the slow and expensive rungs off everything that already
succeeded.

**Phase 1 — structured sources (automatic, no human).** API / CRIS / sitemap / JSON-LD /
OpenAlex-ROR. Fast, cheap, reliable, and runs while the student is away. **Every source
that returns 404, an error, or nothing usable is marked** and carried to Phase 2.

**Phase 2 — automated web navigation (automatic, no human).** The tool browses the marked
pages directly — find the department page, read the roster, pull the missing field. This is
Stage 1's "if the page can't be found, search for it" and part of Stage 3's gap-fill.
Whatever automated browsing *still* can't resolve is marked for Phase 3.

**Phase 3 — human-assisted retrieval (human in the loop).** For the residual gaps, the tool
**generates a ready-to-paste prompt** the student runs in the **Claude for Chrome
extension**, in their own logged-in browser session. The student's session can reach what
the tool cannot — Google Scholar, Twitter/X, Cloudflare- or login-gated pages. The extension
produces **MD files**; the student hands them back; the tool **ingests them to fill the
missing data and continues** ([D-043](#d-043--human-assisted-retrieval-and-md-ingestion)).

**Why this ordering is right, and why Phase 3 is the elegant part:**
- Web-navigation-first would be the most expensive and least reliable default, and it fails
  hardest in exactly the non-Anglo countries this project serves. So structured-first.
- Phase 3 is Ahmed's *original* method — the Chrome-extension deep-dive prompt that produced
  the `Zhijing Jin profile/` MD files — turned into the tool's escape hatch. The corpus's
  method becomes the fallback rung.
- **It is also the cleanest ethics posture** ([ethics-and-compliance.md](ethics-and-compliance.md)):
  the *tool* never fetches blocked, authenticated, or login-walled content and never
  defeats a bot wall — the *human* reads those pages in their own browser, which is just a
  person using their browser. The hardest-to-reach data arrives without the tool ever
  violating a robots directive or a ToS.

If even Phase 3 can't fill a field, it ends as an honest "we looked, found nothing"
([D-037](#d-037--per-professor-capture-is-dynamic-not-templated)) — the professor is still
never dropped.

---

## D-040 — University targeting: default all, optional prioritise or restrict

**Status:** locked (Ahmed, 2026-07-23)

The student may name specific universities in a form field, with three modes:

- **All** (default) — search every university in the country.
- **Prioritise these, then the rest** — the named ones first, the rest after.
- **Only these** — restrict to the named set.

Dropdowns and suggestions help the student discover options rather than type blind.

---

## D-041 — The dashboard is Claude-interactive

**Status:** locked (Ahmed, 2026-07-23)

The dashboard is not a frozen report. Because the scan also writes the data as clean JSON,
the student's Claude session can read it and:

- answer plain-language questions about the professors ("who is taking students in vision?"),
- modify or extend the dashboard UI on request (add a filter, change a view).

The dashboard is a living artifact the student and Claude keep working on. This is why the
JSON export is mandatory and why the dashboard is a single editable file, not an opaque
bundle.

---

## D-042 — The deliverable is the skill/agent/tool package

**Status:** locked (Ahmed, 2026-07-23) — makes [profscout-project-brief] explicit

Supervisorly is a **Claude Code skill package**, not an application anyone runs as a
service. A student adds it to their Claude Code — "read this repo's README and add these
skills" — and Claude installs the tools, reads `SKILL.md`, and drives the whole flow in
[product-flow.md](product-flow.md).

**Consequence:** the README and `SKILL.md` are load-bearing product surfaces, not
documentation afterthoughts — they are the entire install-and-run interface. The centre of
gravity of the build is skills + agents + tools; the pipeline and dashboard are what those
produce.

---

## D-043 — Human-assisted retrieval and MD ingestion

**Status:** locked (Ahmed, 2026-07-23) — Phase 3 of [D-039](#d-039--agent-driven-web-navigation-is-first-class-apis-are-the-fast-path)

The mechanics of the human-in-the-loop rung.

**The gap queue.** After Phases 1–2, the tool holds a precise list of `(entity, field)`
pairs still missing, each with the target's known anchor links (homepage, Scholar, ORCID,
lab, social). This is not "everything about professor X" — it is exactly the fields that are
still blank, so the human is asked for the minimum.

**The generated prompt.** The tool *generates* the Chrome-extension prompt
([D-038](#d-038--queries-and-keywords-are-generated-per-search-never-looked-up)), in the
shape Ahmed's own deep-dive prompt already proved: provenance/ethics preamble → target block
→ anchor links ("start here, follow outward") → a strict output contract → rules
("cite a URL + date for every fact; if you can't access it say so; never invent"). It is
**parameterised** with the target and its specific missing fields, and **consolidated** so
the student runs few prompts (grouped per professor, or fewer), never one per field.

**The MD ingestion contract.** Returned MD must carry, per filled field: the entity it
belongs to, the field name, the value, the **source URL**, the **date observed**, and a
**verbatim quote** where possible. The tool parses these into the same `Claim` structure as
everything else ([architecture.md §3](architecture.md)), with
`extractor = "human-assisted (Claude for Chrome)"` and full provenance. Human-retrieved data
is not privileged or trusted blindly — it is a claim with a source, like every other claim.

**Async and resumable.** Phase 3 spans time and possibly sessions — the student goes away,
runs prompts, returns later. The run therefore has a first-class **`awaiting_human_input`**
status ([D-029](#d-029--resumability-and-extraction-caching-are-schema-not-afterthoughts));
ingesting the MD **resumes the run**, fills only the gapped fields, re-runs scoring, and
regenerates the dashboard. Nothing already collected is re-fetched.

**Honest terminus.** Fields the human also couldn't find become "we looked, found nothing,"
distinct from a never-attempted blank ([D-037](#d-037--per-professor-capture-is-dynamic-not-templated)).

---

## D-044 — The professor's own channels are a first-class recruiting-signal source

**Status:** locked (Ahmed, 2026-07-23) — corrects an overstatement in earlier framing

**Correction being made:** an earlier summary said "the tool never fetches Twitter/Scholar."
That was wrong and it under-valued the highest-signal source. Recruiting status lives in
prose on the professor's own channels far more than in any structured field — Ahmed's own
`zhijing_twitter_5yr.md` had an entire bucket of "I'm recruiting" posts. The tool must
**actively pursue** these channels for recruiting signal, not treat them as optional.

**The distinction that resolves it — public vs walled, per channel:**

- **The professor's own linked pages are public and are fetched directly** (Phases 1–2):
  homepage, a dedicated openings / "joining my lab" / "prospective students" page, lab
  "News", personal blog, ORCID biography, group and mailing-list pages, GitHub profile
  READMEs and lab/advice repos. This is where recruiting status most often appears in plain
  text, and it is fully tool-fetchable. These get first-class treatment, not "enrichment."
- **Open-API social is fetched directly** — **Bluesky** (AT Protocol public AppView) and
  **Mastodon** (per-instance public REST) both **verified 2026-07-23** as reachable with no
  auth: Bluesky `resolveHandle` + `getAuthorFeed` + `getProfile` (text at `post.record.text`,
  bio and pinned post on the profile); Mastodon `accounts/lookup` + `accounts/:id/statuses`.
  These are the cleanest social sources and many academics who left X now post recruiting
  calls here. Tested endpoints and limits in
  [research/social-sources.md](research/social-sources.md).
- **X / Twitter is human-rung only — verified, not a preference.** Empirical testing on
  2026-07-23 found **no** public path that enumerates a professor's timeline: the syndication
  endpoint returns 200 with 0 bytes (dead), `tweet-result` needs a tweet ID you already have,
  every Nitter instance is dead or bot-walled, the official API has been pay-per-use with no
  free read tier since 6 Feb 2026 (~$10k/mo at the cap), and the ToS forbids scraping "in any
  form." So the tool does **not** attempt X directly. X recruiting signal is delivered by the
  human rung ([D-043](#d-043--human-assisted-retrieval-and-md-ingestion)): the student reads
  their own logged-in timeline via Claude for Chrome and returns pinned/recent recruiting
  posts with date + permalink + verbatim text. This is not avoiding Twitter — it is the *only*
  clean way to read it in 2026, and it is exactly the human rung Ahmed designed.
- **LinkedIn — human-rung or skip.** Login-walled and ToS-restricted; hiQ v. LinkedIn ended
  in a $500k judgment and a permanent injunction for breaching the User Agreement, even though
  the CFAA did not bar public scraping. The tool never touches it.
- **Google Scholar** stays skip/human-rung (robots `Disallow: /scholar`) and rarely carries
  recruiting signal anyway.

**Extraction is pointed at every reachable channel**, and the reading method — which phrases
signal a recruiting call, how negation ("not this cycle") and cycle-dating ("for Fall 2027")
are handled — is *generated per field and intent*
([D-038](#d-038--queries-and-keywords-are-generated-per-search-never-looked-up)), modelled on
the corpus's 5-bucket taxonomy but never hardcoded from it.

**The bright line (unchanged and now stated precisely):** the *tool* reads public pages and
open APIs; it never defeats a login or a bot-wall. The *human*, in Phase 3, reads their own
logged-in timeline in their own browser and copies public posts — which is a person using
their browser, categorically different from the tool scraping a walled endpoint. Per-channel
verdicts and the tested endpoints land in
[research/social-sources.md](research/social-sources.md).

---

# Round 4 — resolving the pre-build audit (2026-07-23)

An independent 6-dimension audit of the doc set found nine blocking gaps and several
contradictions to fix before `SKILL.md` and the schemas. These decisions resolve the design
questions; the field-table and worked-example work they reference is the first schema-phase
task. Source: the audit synthesis (scratchpad `audit.json`).

---

## D-045 — Intent interpretation and query generation are orchestrator-inline, producing a SearchPlan

**Status:** locked — resolves audit B1

The atlas mis-filed `intent-interpreter` and `query-generator` under "deterministic tools,"
which contradicts D-036/D-038 (they are open-ended LLM reasoning). Resolved: **these are done
by the SKILL.md orchestrator (Claude) inline**, not by deterministic tools and not by separate
agents. They run once per search, are conversational (the student confirms the plan), and are
exactly the judgement the orchestrator is best placed to do.

Their output is a first-class **`SearchPlan`** artifact that the deterministic tools consume:

```
SearchPlan {
  plan_id, applicant_id,
  countries[], field, subfield,
  intent_kind,            -- enum: training | pre_master | pre_phd | mentor | master | phd | postdoc
  resolved_topic_terms[], -- generated per field (D-038)
  resolved_venues[],      -- generated: the conferences/journals that signal the subfield
  target_opportunity_kinds[],
  target_source_types[], excluded_source_types[],
  hit_criteria,           -- what counts as a match for this intent
  languages[],            -- for original-language extraction (D-044)
  university_mode,        -- enum: all | prioritise | only  (D-040)
  universities[],
  confirmed_by_user,      -- bool; the expensive work does not start until true
  created_at
}
```

The atlas is corrected to show intent/query as orchestrator reasoning, not tools.

---

## D-046 — The JSON export contract is the system's interchange format, with a four-state value envelope

**Status:** locked — resolves audit B3 (full worked example is the first schema-phase deliverable)

The JSON the dashboard reads (D-003, D-026, D-041) is specified as a real contract, not left
implicit. Three parts:

1. **A per-field value envelope** carrying provenance and an explicit **state**:
   ```
   { state, value, quote, source_url, snapshot_hash, observed_at, confidence, extractor }
   ```
   `state` ∈ **`value`** (we have it) · **`searched_absent`** ("we looked, found nothing" — a
   `NOT_FOUND` claim exists) · **`never_attempted`** (no claim, not yet reached) · **`blocked`**
   (a source failed / awaiting human). These four states are derived *deterministically* from
   the claim store and `CoverageRecord`, and the dashboard renders each distinctly
   ([D-022](#d-022--the-flagship-field-is-20-populated-and-the-product-must-say-so), [D-037](#d-037--per-professor-capture-is-dynamic-not-templated)).
2. **A field-metadata descriptor array** — `{ id, label, kind (filter|sort|facet|score-input),
   datatype, unit, facet_domain }` — so the *generic* dashboard adapts to whatever fields the
   search actually produced ([D-038](#d-038--queries-and-keywords-are-generated-per-search-never-looked-up)),
   rather than assuming fixed columns.
3. **The HTML-is-regenerated-from-JSON rule** — the JSON is written to a fixed sibling path
   with a documented schema, so the student's Claude session can open it, answer questions, and
   rebuild the dashboard ([D-041](#d-041--the-dashboard-is-claude-interactive)).

**Exports honour [D-024](#d-024--evaluative-judgements-about-individuals-stay-local-and-unexported):**
LLM judgements about people and bare email lists are excluded from the export path; only cited
facts serialise.

---

## D-047 — One canonical confidence model

**Status:** locked — resolves audit B5

Three confidence vocabularies coexisted and the hard-gate rule referenced a fourth word
("reliable") that belonged to none. Canonicalised:

- **`Claim.confidence`** — the per-fact value: `quoted_official | derived | inferred |
  unconfirmed | action_needed`.
- **Gate-eligibility** — a hard eligibility gate ([D-023](#d-023--nationality-and-export-control-are-never-a-hard-filter))
  may fire **only** on a claim whose confidence is `quoted_official` **or** `derived` from
  quoted-official inputs. `inferred` / `unconfirmed` may sort and warn, never gate.
- **Field obtainability** (`reliable | partial | hard | manual-only` in domain-model) is a
  *design-time* estimate of how gettable a field is — not a runtime value. Renamed in prose to
  "obtainability" to stop the collision.
- **`WebSource.source_tier`** describes the *source*, not the fact; it is an input to
  `Claim.confidence`, not a synonym for it.

**Monotonicity rule:** a derived field's confidence may never exceed the lowest confidence of
its inputs. (This is why `distinct_coauthor_count`, derived from a possibly-incomplete works
list, is downgraded to `partial` — quick-fix applied to domain-model.)

---

## D-048 — Dashboard delivery: pre-transpiled JSX, vendored inline, no runtime toolchain

**Status:** locked — resolves audit B7

"Single self-contained HTML with embedded JSX" ([D-033](#d-033--dashboard-technology)) has a
concrete, realistic mechanism:

- The **exporter pre-transpiles** the JSX to plain JS at build time and inlines it — **no
  runtime Babel** (a ~3 MB standalone Babel would blow the <1 s render budget).
- **React and a small virtualiser are vendored inline** (bundled with the skill, not fetched
  from a CDN — the offline/no-CDN constraint), so the file is genuinely self-contained.
- A **readable JSX source block is retained** in the file (as text) so the student's Claude
  session can edit the UI ([D-041](#d-041--the-dashboard-is-claude-interactive)) and re-export.
- The **data is inlined** into the HTML *and* written to the sibling JSON
  ([D-046](#d-046--the-json-export-contract-is-the-systems-interchange-format-with-a-four-state-value-envelope)).

This meets self-contained + offline + virtualised + editable simultaneously; the earlier "how
does JSX run with no build step" hand-wave is closed.

**Clarification (independent review):** because the exporter is what pre-transpiles the JSX,
"the student keeps editing the dashboard with Claude"
([D-041](#d-041--the-dashboard-is-claude-interactive)) means **inside Claude Code**, where the
exporter can re-transpile and re-export — not by hand-editing JSX in a bare browser (a browser
has no transpiler). Editing the *rendered* HTML/JSON in Claude Code is the supported loop; the
retained JSX source block is what makes that loop possible.

---

## D-049 — Terminal run states: the dashboard is never blocked on the human

**Status:** locked — resolves audit B8 (a genuinely important catch)

The most common real outcome is that the student **never returns the Phase-3 MD**. The naive
flow ("dashboard generated at the end," Phase 3 inside Stage 3) implied a run stuck forever
with no output. Corrected:

- **The dashboard is generated/refreshed after Phase 2**, with unfilled gaps marked distinctly
  (`blocked / awaiting-human` vs `searched_absent` vs `never_attempted`). The student gets a
  usable dashboard immediately; the human rung is an *optional enrichment*, not a gate.
- A run reaches **`finalized_with_open_gaps`** and stays **resumable** — if the MD arrives
  later, ingestion fills the gaps and re-exports ([D-043](#d-043--human-assisted-retrieval-and-md-ingestion)).
- **Zero results** short-circuits Stages 2–4 and renders a *coverage/empty-state* dashboard
  that distinguishes "no professors matched the field" from "the country's sources returned
  nothing" ([CoverageRecord](domain-model.md)).

---

## D-050 — Recruiting classification is normalised against the student's target cycle

**Status:** locked — resolves audit B6 (full agent contract in the schema phase)

The `recruiting-analyst` needs more than the `RecruitingSignal` enum. Its essential contract:

- **Inputs:** the verbatim quote *in its original language*, `observed_at`, today's date, the
  student's `target_cycle`, and the resolved country **intake calendar**.
- **Normalisation:** raw status → `state` *relative to the target cycle* — "not taking students
  this year" observed in 2025 is not evidence about Fall 2027. Negation and modality are handled
  **in the original language** ([D-044](#d-044--the-professors-own-channels-are-a-first-class-recruiting-signal-source)),
  never after machine translation.
- **The intake calendar is generated per country** (fall-with-December-deadline is not
  universal — southern hemisphere, multiple intakes) with a documented default and a confidence
  flag when inferred.

Guards against the corpus hazard where an "applications" page for a *degree program* was
misread as an individual professor's recruiting signal.

---

## D-051 — One shared Markdown grammar for the human rung

**Status:** locked — resolves audit B9 (worked example is a first schema-phase task)

The MD the student returns from Claude for Chrome is the seam between the human and the
pipeline, so its grammar is **one schema, authored once**: the `chrome-prompt-generator`
embeds it as the prompt's output contract, and the `md-ingester` parses exactly it. Per filled
field it carries **entity, field, value, source URL, date, verbatim quote**; each parsed unit
becomes a `Claim` with `extractor = "human-assisted (Claude for Chrome)"`. A single worked
example block is the source of truth for both tools — they can never drift, because they read
the same spec.

---

## D-052 — The human rung also enumerates login-walled rosters

**Status:** locked — resolves audit H4

Phase 3 fills `(entity, field)` gaps — but it must also handle the case where an entire
**faculty directory is login-walled**, so the tool cannot even get the *list* of professors.
The gap queue gains a **roster-enumeration task type**: the generated prompt asks the student
to read the walled directory in their own session and return the professor list + links as MD,
which the tool ingests to *mint the entities*. Units get a `LOGIN_WALL` coverage marker so this
is visible, not silent.

---

## D-053 — optout.txt match keys are stable public identifiers

**Status:** locked — resolves audit H6

The build-time opt-out filter ([ethics-and-compliance.md §3](ethics-and-compliance.md)) matches
on **canonical homepage URL, ORCID iD, and/or institutional email** — identifiers a person can
actually supply. Never the internal UUID (a third party can't know it) and never the display
name (the design forbids name-keying, [D-030](#d-030--identity-internal-id-first-external-ids-as-evidence)).
The filter normalises before comparing (URL canonicalisation, ORCID format, lowercased email),
and the failing test asserts a record matching any key never survives into output.

---

## D-054 — The community overlay is structural and local, never shared personal data

**Status:** locked — resolves audit H8, reconciles [D-008](#d-008--curation-is-a-first-class-feature-not-a-fallback) with [D-005](#d-005--scan-output-is-never-committed)/[D-035](#d-035--the-corpus-is-a-methodology-reference-not-a-data-source)

D-008 called curation a first-class feature; D-005/D-035 forbid committing or sharing personal
data. Reconciled: the human-maintained overlay a user keeps is **local to that user** and holds
their own corrections and annotations. What *may* be contributed back to the public repo is
**structural only** — DirectoryAdapters, query-generation improvements, intake-calendar
defaults, source lists. **A shared overlay of professors' recruiting status is exactly the
unconsented personal-data aggregation D-005 forbids, and is out of scope.**

---

## D-055 — One orchestration vocabulary, with a crosswalk

**Status:** locked — resolves audit H7

Four numbering schemes collided (Stages 0–4, Phases 1–3, Tiers T0–T2, Tools T1–T10 — with "T1"
meaning both a tier and a tool). Canonical vocabulary:

- **Stages 0–4** — the student's journey (intent → roster → deep-dive → gap-fill → students).
- **Phases 1–3** — the fetch escalation (structured → automated browse → human rung).
- **Tiers** — renamed **enumerate / signal / deep-dive** (no T-numbers).
- **Tools** — referred to by **name**, never `T1`–`T10`.

A single crosswalk table lives in `SKILL.md` (and the atlas) mapping tier ↔ phase ↔ stage ↔
tool. The atlas is updated to drop the `T1`–`T10` labels.

---

## D-056 — The shortlist gate is explicit; "never dropped" is about display, "deep-dive" is about the shortlist

**Status:** locked — resolves audit B4 (a load-bearing contradiction)

`product-flow.md` implied deep-diving *every* professor; cost and architecture assume a ~40
shortlist. These are reconciled by naming the gate:

- The **enumerate** and **signal** tiers run over the **full roster** (~400) — cheap, no LLM.
- A **shortlist gate** promotes ~40 to the **deep-dive** tier, on **research-fit signal**
  (topic match + recent activity), which is available before the deep dive
  ([D-021](#d-021--three-tier-pipeline-shortlist-formed-on-research-fit)).
- **"Never dropped" applies to *display*** — every enumerated professor appears in the
  dashboard, thin record and all. **"Deep-dive" applies to the *shortlist*** — only the promoted
  ~40 get the expensive multi-source pass. A non-shortlisted professor is shown with enumerate/
  signal-tier data and a "not deep-dived" marker, never omitted.

The single cached page fetch of the signal tier over the full roster is reconciled with the
robots/rate-limit posture: it is one polite, cached GET per professor's own homepage, inside
the per-host budget ([cost-and-performance.md §5](cost-and-performance.md)), not a crawl.

---

# Round 5 — independent builder's-eye review (2026-07-23)

A fresh Opus review traced a concrete example ("pre-PhD in causal NLP, Canada") end to end.
Its verdict: build on it — but four issues land on the non-CS/non-US promise and one locked
decision contradicts our own research. These resolve them.

---

## D-057 — Fragmented works lists are reconciled before scoring, not just flagged

**Status:** locked (review, 2026-07-23) — extends [D-030](#d-030--identity-internal-id-first-external-ids-as-evidence)

[D-030](#d-030--identity-internal-id-first-external-ids-as-evidence) flags OpenAlex split/merged
profiles for common Chinese/Korean/Arabic names. But **flagging identity does not repair the
fragmented works list** — and that list feeds `topic_match` and recent-activity, the exact
inputs the shortlist gate ranks on ([D-021](#d-021--three-tier-pipeline-shortlist-formed-on-research-fit),
[D-056](#d-056--the-shortlist-gate-is-explicit-never-dropped-is-about-display-deep-dive-is-about-the-shortlist)).
So the professors most likely to be wrongly dropped from the ~40 are the **non-Anglo names the
project exists to serve.** That is the worst possible failure for this product.

**Resolution:**
- For flagged or low-ORCID-coverage authors, **reconcile works before scoring**: anchor on
  ORCID where present; otherwise cluster candidate OpenAlex author-ids by shared venues,
  co-authors and institution, and score over the union.
- Disambiguation risk lowers the **score confidence** ([D-047](#d-047--one-canonical-confidence-model)),
  never silently understates activity — a fragmented profile must not read as "inactive."
- Genuinely ambiguous identity routes to the human rung: the student recognises their target.

---

## D-058 — Research-fit matching is on OpenAlex topic IDs, resolved in the SearchPlan

**Status:** locked (review, 2026-07-23) — makes the three-tier cost model actually work

The whole three-tier cost argument ([cost-and-performance.md §3b](cost-and-performance.md))
rests on research-fit being computable **cheaply, no-LLM, before the deep dive.** But
`resolved_topic_terms` is generated *free text* ([D-045](#d-045--intent-interpretation-and-query-generation-are-orchestrator-inline-producing-a-searchplan))
and the scorer is deterministic arithmetic — nothing said how free text matches a professor's
*structured* OpenAlex topics. Naive string overlap drops the interdisciplinary case: a "causal
NLP" seeker misses a professor tagged "NLP" + "causal inference" separately.

**Resolution:** the orchestrator resolves the field/subfield to **OpenAlex topic/concept IDs
inside the SearchPlan** (one-time inline reasoning — permitted, [D-045](#d-045--intent-interpretation-and-query-generation-are-orchestrator-inline-producing-a-searchplan)),
and the scorer computes **deterministic ID-overlap**, not text match. `SearchPlan` gains
`resolved_topic_ids[]` alongside `resolved_topic_terms[]`. This is the *feature-computation
method*, not the next-phase scorer formula.

---

## D-059 — Hard gates are intent-aware

**Status:** locked (review, 2026-07-23) — fixes the pre-PhD trace at its last step

`FitAssessment.eligibility_verdict` gates on degree route, language bands and enrolment
requirement — **PhD/Master admission facts.** But a `pre_phd` / RA / `postdoc` search should
gate differently: an RA seeker must not be blocked by direct-entry-from-bachelor's rules that
don't apply to them. `intent_kind` is carried through the `SearchPlan` but the scorer never
consumed it, so the pre-PhD example — the whole reason the product exists for Ahmed — breaks at
the final step.

**Resolution:** hard-gate selection is a **function of `intent_kind`**. Each intent has its own
gate set — `pre_phd`/RA/mentor: availability + remote-ok, no degree/language gate unless the
opportunity itself states one; `phd`/`master`: the full admission gates; `postdoc`: PhD-in-hand
+ funding. The scorer reads `intent_kind` from the `SearchPlan`.

---

## D-060 — Country-source preflight

**Status:** locked (review, 2026-07-23) — enhancement; turns the D-034 risk into upfront expectation-setting

Before the expensive run, **probe whether the chosen country actually has the spine** — CRIS
presence, an advisor-bearing thesis registry, a national vacancy portal (EURAXESS and
equivalents), OpenAlex depth — and show the student a short "what will be thin here" summary
*before* Stage 1. This converts the accepted fully-generic risk ([D-034](#d-034--v1-breadth-fully-generic-risk-accepted))
from a post-hoc coverage report into upfront expectation-setting, and directly addresses the
"adapters scale with institutions — 4,000+ per country" limit ([D-027](#d-027--directoryadapters-are-data-files-not-code)).

---

## D-061 — A deadline / urgency view

**Status:** locked (review, 2026-07-23) — high applicant value, near-zero new data cost

The applicant's real first question is "what closes soon." The data already exists —
`ApplicationCycle` carries `deadline_domestic` / `deadline_international`, `deadline_raw_text`,
`state`, `watch_url`, and `related_funding_deadlines[]` — but no cross-professor
soonest-deadline sort or calendar was specified. Add a **deadline view**: a cross-professor
sort by soonest relevant deadline, the domestic/international split (months apart) shown
prominently, and `.ics`-style export. **It is a view/join over existing fields, not new
collection** — professors join to a cycle via the `Person → GraduateProgram` admitting-route
edge.

**Two honesty rules the view must obey — a deadline is high-stakes:**
- A **`projected_from_prior_cycle` or `not_yet_published`** deadline is rendered as exactly
  that ("watch from Oct 2026", "last year's date — unconfirmed"), **never as a firm date.**
  Missing a real, changed deadline because the UI showed a stale one as solid is the worst
  failure this view can cause.
- Coverage is `partial` — a professor whose cycle isn't published yet sorts into a "not yet
  known / watching" bucket, an honest state, not the bottom of a firm-date list.

---

## D-062 — `former_doctoral_students` is a per-registry, advisor-verified capability — not a universal headline

**Status:** locked (review, 2026-07-23) — **corrects [D-025](#d-025--past-students-are-obtainable-current-students-still-are-not)**, which contradicted our own research

[D-025](#d-025--past-students-are-obtainable-current-students-still-are-not) presented national
thesis registries as publishing "the supervisor named." **The project's own research says the
opposite** ([research/data-sources.md](research/data-sources.md)): registries vary wildly and
**mostly lack advisor fields**; the one source that reliably carries advisors (ProQuest) is
paid and closed. So the feature works for **theses.fr (France) and little else** — and for
**Canada, the first test country, the advisor field is unverified.**

**Resolution:**
- `former_doctoral_students` is enabled **per registry, only where that registry is confirmed
  to expose an advisor field.** Elsewhere it is simply absent (honest null), never inferred.
- It is **not** a Stage-4 headline for any country whose registry hasn't been verified.
- Before relying on it for the Canada demo, **verify Theses Canada / LAC actually exposes
  advisors**; if not, the demo makes no former-students claim for Canada.
- `recent_collaborators` ([D-016](#d-016--students-is-not-obtainable-ship-recent_collaborators-instead))
  remains the always-available proxy, always labelled as *not* students.

---

## D-063 — The eval set is hand-labelled cassettes, and it is a named deliverable

**Status:** locked (review, 2026-07-23) — hardens [D-011](#d-011--validation-strategy)

"Cassettes + synthetic instead of a golden fixture" ([D-011](#d-011--validation-strategy)) is
under-mitigated as written: cassettes are **unlabelled** HTTP recordings, so the per-model pass
thresholds ([architecture.md §8](architecture.md)) have nothing to grade against until someone
hand-labels the expected extractions.

**Resolution:** a small **hand-labelled cassette eval set** is a named schema-phase deliverable
— labels authored from the tool's **own live captures** (permitted under [D-035](#d-035--the-corpus-is-a-methodology-reference-not-a-data-source),
since they are the tool's fetches, not the corpus), covering **≥3 directory shapes across ≥3
countries**, with a per-field expected extraction and **explicit label ownership** (who authors
them). This is what the per-model thresholds grade against.

---

## D-033 — Dashboard technology

**Status:** locked (Ahmed, 2026-07-23) — **refines [D-003](#d-003--dashboard-ships-as-a-single-self-contained-html-file)**

**React + Vite app** for the working dashboard, with a **single self-contained HTML file
retained as a "share a snapshot" export.** Ahmed took the recommendation over his original
single-file-only choice.

The working app gets virtualised lists, which country-scale results require — Ahmed's own
`dashboard.html` re-renders every card via `innerHTML` on each filter change and does not
survive thousands of rows. The exported HTML snapshot preserves the clone-and-open
property for sharing a shortlist.

**Implication:** the scan always emits clean JSON as the interchange layer
([D-003](#d-003--dashboard-ships-as-a-single-self-contained-html-file)); the React app and
the HTML exporter are both views over that JSON, so neither is the sole home of the data.

**Revised 2026-07-23 (Ahmed):** drop the separate Vite project. Ship a **single
self-contained HTML file with embedded JSX/React** — component model and virtualised lists
without a build toolchain. Ahmed's reasoning: this is not a production site, it is
regenerated per student, and a single file costs the AI less context and power to produce
and edit than a multi-file project. This reconciles D-033 with
[D-003](#d-003--dashboard-ships-as-a-single-self-contained-html-file): one file, but
component-based rather than `innerHTML`-based, so it survives large lists. The scan still
writes JSON separately so the file is a view, not the only copy of the data.

---

## D-034 — v1 breadth: fully generic, risk accepted

**Status:** locked (Ahmed, 2026-07-23) — confirms [D-002](#d-002--v1-targets-any-country-not-one-region)

Ahmed held his original choice: **fully generic, any country, from the start** — declining
the depth-first-content recommendation.

**Risk accepted, and it must be managed rather than ignored:** correctness is hard to
verify when output can come from any country, and several normalisation problems are
genuinely unsolved (grade scales, degree structures, funding models, recruiting culture —
[requirements.md genericity #4–#7](requirements.md)). Because the golden-fixture safety net
is also declined ([D-011](#d-011--validation-strategy),
[D-035](#d-035--the-corpus-is-a-methodology-reference-not-a-data-source)), the mitigations
carry more weight:

1. **Fail loud, never silent.** Where a country lacks a source (no thesis registry, no
   vacancy portal, no CRIS), the coverage report says so per-country. No blank field is
   ever presented as "nothing to report."
2. **Confidence travels with every value** ([D-010](#d-010--every-field-carries-provenance-and-confidence))
   so a user can see that a German record is thinner than a Canadian one.
3. **Unsolved normalisations sort and warn, never filter**
   ([D-023](#d-023--nationality-and-export-control-are-never-a-hard-filter)).
4. **Cassette + synthetic tests** exercise more than one country's directory shape from the
   start, so genericity is tested, not assumed.

---

## D-064 — Browser-primary live fetch is agent-driven; page content enters only through the ingest-page snapshot seam

**Status:** locked (Ahmed, 2026-07-25) — refines [D-039](#d-039--api-first-public-sources-human-rung-for-the-walled), hardens [D-009](#d-009--deterministic-collection-llm-interpretation), [D-010](#d-010--every-field-carries-provenance-and-confidence)

Ahmed chose the browser (chrome-devtools-mcp, agent-driven) as the **primary** page fetch for
live scans — the agent launches and controls Chrome; the user does nothing after a one-time
login in the persistent profile. This does **not** move fetching into the LLM layer:

1. **The Python layer stays LLM-free** ([D-009](#d-009--deterministic-collection-llm-interpretation)).
   Browser-collected content enters the engine only through the deterministic
   `ingest-page` seam: in-page JS extraction produces cleaned, capped main text; the CLI
   stores it as a normal content-addressed snapshot; the existing extractors and the
   quote-in-snapshot gate ([D-010](#d-010--every-field-carries-provenance-and-confidence))
   run unchanged. A browser page is just another snapshot.
2. **Raw HTML/DOM never enters the agent's context.** Extraction happens in-page and in
   Python; the agent handles only file paths, byte counts, and one-line results. This is a
   cost rule (tokens) and a hygiene rule (untrusted content).
3. **APIs stay API-first** (ROR/OpenAlex over httpx — JSON endpoints need no browser), and
   the agent may skip the browser for pages already fresh in the warm cache. "Primary"
   means the default page tier, not the only tier.
4. **Host-portable:** the same recipe runs under any MCP host (Kimi Code, Claude Code,
   etc.) — the browser is an MCP server, the seam is the CLI.

## D-065 — Social pacing policy: the anti-ban rules are code, not vibes

**Status:** locked (Ahmed, 2026-07-25) — hardens [D-039](#d-039--api-first-public-sources-human-rung-for-the-walled), [D-043](#d-043--the-human-rung-claude-for-chrome), [D-044](#d-044--non-english-pages--social-sources)

Scraping X/Twitter, LinkedIn, or Scholar through the user's own logged-in session is done
**per-target, read-only, and politely** so no account is ever flagged. The rules are
deterministic and testable, enforced before every browser page:

1. **Jittered minimum intervals per host class** (social hosts wait tens of seconds to
   minutes between pages, randomised; never a fixed metronome).
2. **Per-session page caps** (a handful of profiles per site per run — never bulk).
3. **Human-like in-page scrolling** (incremental scroll steps with randomised pauses,
   capped) instead of instant full-page reads.
4. **Abort-on-challenge:** a captcha, soft-block, or unexpected login redirect latches the
   host as aborted for the session; the field becomes `blocked` and routes to the human
   rung ([D-043](#d-043--the-human-rung-claude-for-chrome)). Never retry harder.
5. **Scholar is minimal-use:** profile pages only, no search pagination — it is the most
   aggressive blocker.
6. Only the **specific advertised profile** is ever visited — the URL the professor
   themselves published — never search/graph enumeration of people.

## D-066 — The subject-map stage: field understanding is API-derived and user-confirmed

**Status:** locked (Ahmed, 2026-07-25) — refines Stage 0 of the skill flow, hardens [D-038](#d-038--generate-dont-look-up)

Before any scan, the student's free-text field is mapped to a **hierarchical subject map**
(OpenAlex topics → subfields → fields → domains) built **from the OpenAlex API** — never
from a hardcoded keyword dictionary ([D-038](#d-038--generate-dont-look-up)). The map is
presented as a **multi-select** (checkbox tree in the Scan Studio, or a numbered list in
conversation); the student keeps the topics they want and skips the rest. The selected
topic IDs become the plan's `resolved_topic_ids`. **Nothing expensive runs before this
confirmation** — the map step is the plan review made concrete.

## D-067 — Scan Studio: the rich front-end is a self-contained Atlas-language plan wizard

**Status:** locked (Ahmed, 2026-07-25) — refines [D-033](#d-033--dashboard-technology), [D-048](#d-048--the-dashboard-is-self-contained-and-offline)

The interactive scan setup (intent, country, universities + mode, subject-map checkbox
tree, named professors, contact email) ships as **one self-contained, offline HTML file**
in the binding Atlas "Living" design language — same rules as the dashboard
([D-048](#d-048--the-dashboard-is-self-contained-and-offline)): no external requests,
inline CSS/JS, reduced-motion honoured, keyboard-operable, injection-safe. It consumes a
subject-map JSON and exports a plan JSON (browser download — a static file cannot write
to disk). The **conversational numbered multi-select remains the fallback** in every
agent host, so the tool is fully usable even where opening HTML is awkward.

---

## D-068 — The LLM may generate queries, never claims

**Status:** locked (Ahmed, 2026-07-26) — refines [D-009](#d-009--deterministic-collection-llm-interpretation), hardens [D-038](#d-038--generate-dont-look-up)

The deterministic layer stays LLM-free for *facts*. The one sanctioned exception: an
**optional query-expansion** step may use an LLM to turn a student's raw phrasing ("NLP",
"natural language procssisng") into candidate *search strings* (canonical forms, acronym
expansions, synonyms). Guardrails, all in code:

1. **Queries, never claims.** Expansion output is a validated list of ≤8 short strings
   (≤120 chars each, deduped); anything else is discarded. It is only ever sent to search
   endpoints as URL parameters. A wrong expansion yields zero topics — it can never mint a
   professor, a deadline, or a recruiting status; every fact still passes the
   [D-010](#d-010--every-field-carries-provenance-and-confidence) quote gate.
2. **Fail-closed.** No key, any error, or a timeout → expansion is silently skipped and the
   raw query proceeds. Nobody is ever blocked by a missing LLM.
3. **Server-side only.** The key lives in server config, is never logged, returned, or
   client-overridable; model and base URL are server constants.

## D-069 — The hosted web product: honesty, privacy, and user control

**Status:** locked (Ahmed, 2026-07-26) — hardens [D-005](#d-005--ethics-in-code), [D-037](#d-037--honest-emptiness)

The hosted page + endpoints (the Firebase web app) follow the same ethics as the engine:

1. **Read-only, rate-limited endpoints.** The shared OpenAlex budget is protected, not
   spent for strangers: per-IP throttles, one active scan job per email, server-side caps.
2. **Job ids are unguessable UUIDs and are the access token** — status is readable only by
   id and never listable.
3. **Results are personal data** ([D-005](#d-005--ethics-in-code)): private bucket, 15-min
   signed URLs re-issued on request, 7-day auto-delete of results AND job docs. No personal
   data is stored client-side (no localStorage/cookies for plan or email).
4. **The hosted page is a new artifact class** — unlike the dashboard/Studio
   ([D-048](#d-048--dashboard-delivery-pre-transpiled-jsx-vendored-inline-no-runtime-toolchain)/[D-067](#d-067--scan-studio-the-rich-front-end-is-a-self-contained-atlas-language-plan-wizard))
   it MAY call the API, but ships no other external resource and no tracking.
5. **The user can always stop safely and continue.** Cancel is graceful, partial results
   are kept and exportable, and every terminal state is resumable — never a dead end.
