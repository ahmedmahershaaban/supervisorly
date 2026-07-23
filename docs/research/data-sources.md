# ProfScout — External Data Source Landscape

**Status:** research report
**Date of investigation:** 2026-07-22
**Question being answered:** should ProfScout scrape university faculty webpages, or anchor on structured scholarly APIs and use scraping only for enrichment?

---

## 0. Headline answer

**Anchor on structured scholarly APIs. Scrape only as a per-professor, opt-in enrichment step.**

Scraping cannot be the spine because faculty directories have no shared structure, no shared URL convention, and no machine-readable markup. I tested six real faculty/department pages across five countries and found **zero** `schema.org/Person` markup (see §12). Two of the six URLs 404'd, one was a client-rendered SPA, and one — the Faculty of Computers & AI at Cairo University — returned **"Account Suspended."** A scraping-first architecture is a per-university engineering project that rots continuously, and it fails hardest exactly in the countries ProfScout claims to serve.

By contrast, OpenAlex returned 117 Egyptian universities and 43,746 authors affiliated to Cairo University in two API calls, with ROR IDs, ORCIDs, h-indices, topic vectors and homepage URLs attached.

---

## 1. Method and evidence marking

Every claim below is tagged:

| Tag | Meaning |
|---|---|
| **[V]** | **Verified** — I called the live API/URL on 2026-07-22 and observed this |
| **[D]** | **Documented** — read in official docs; not independently reproduced |
| **[?]** | **Uncertain** — could not confirm; treat as an open question |

All API probes were unauthenticated (no API keys held), which is itself informative: it establishes the anonymous floor a new open-source user hits on first run.

---

## 2. Source-by-source findings

### 2.1 OpenAlex — **the spine**

Base URL: `https://api.openalex.org` **[V]**

#### Scale (all **[V]**, live counts)

| Entity | Count |
|---|---:|
| `works` | 320,975,210 |
| `authors` | 120,185,256 |
| `institutions` | 131,275 |
| `funders` | 45,640 |
| `awards` | 17,278,150 |
| `topics` | 4,516 |
| `keywords` | 65,004 |
| `subfields` | 252 |
| `fields` | 26 |
| `domains` | 4 |

#### Pricing / rate limits — **THIS HAS CHANGED, AND IT MATTERS**

OpenAlex is no longer the "just send a mailto" polite pool it was. It is now a **freemium credit-metered API**.

**[V]** Response headers on an unauthenticated call:

```
x-ratelimit-limit: 1000
x-ratelimit-limit-usd: 0.1
x-ratelimit-remaining-usd: 0.0999
x-ratelimit-cost-usd: 0.0001
x-ratelimit-reset: 18599
```

**[D]** From `developers.openalex.org/guides/authentication`:

> "The API is a freemium service with free daily usage—$0.10/day with no key, or 10× that ($1/day) with a free API key—and after that you pay for what you use."

| Action | Cost | Free-key daily allowance |
|---|---|---|
| Get single entity (`/works/W123`) | Free | Unlimited **[D]** |
| List + filter | $0.0001 | 10,000 calls / 1,000,000 results **[D]** |
| Search (`?search=`) | $0.001 | 1,000 calls / 100,000 results **[D]** |
| Content download (PDF) | $0.01 | 100 files **[D]** |

Get a key at `openalex.org/settings/api` (free) **[D]**.

> **Documentation conflict:** `developers.openalex.org/llms.txt` states *"Rate limit: $1/day free usage with key, $0.01/day without"*, while the guides page and the live headers both say **$0.10/day** without a key. The observed headers (`x-ratelimit-limit-usd: 0.1`) are authoritative. **[V]**

**Practical consequence for ProfScout:** a free key buys ~10,000 list calls/day. Enumerating one mid-sized department (≈100 professors, ~5 calls each) costs ~500 calls. That is comfortable for interactive use and completely inadequate for "all universities in Germany" in one run. **The architecture must therefore be snapshot-capable, not API-only, for country-scale sweeps.**

The old `mailto=` polite-pool convention still works and is still accepted **[V]** (my calls with `mailto=` succeeded), but it no longer buys a separate high-rate pool — `api_key` is the mechanism now. Keep sending `mailto=` in the User-Agent anyway as courtesy and for support triage.

#### Bulk snapshot

- **[D]** Full snapshot in gzipped JSON Lines **and** Apache Parquet; ~330 GB compressed, ~1.6 TB decompressed. JSON Lines and Parquet are separate copies of the same data.
- **[D]** Free public snapshot refreshed **quarterly**. Daily-refreshed snapshots and daily change files require a paid plan.
- **[V]** Latest snapshot release observed: `2026-06-25` (from `https://openalex.s3.amazonaws.com/RELEASE_NOTES.txt`).
- **[D]** Official CLI for filtered subsets: `pip install openalex-official`, then `openalex download --api-key KEY --filter "..."`. **This is the right tool for ProfScout's country-scale ingest** — it avoids both the $1/day cap and the 330 GB full snapshot.

#### Licence

**[V]** `https://openalex.s3.amazonaws.com/LICENSE.txt` returns the full text of **CC0 1.0 Universal**. An open-source tool may freely redistribute derived data, including commercially, with no attribution obligation. (Attribution is still the decent thing to do.)

#### Author disambiguation quality — **the single most important reliability question**

**[V]** Searching `Mohamed Elhoseny`:

| Source | Distinct author entities | Papers on largest entity |
|---|---:|---:|
| OpenAlex | 18 | 401 |
| Semantic Scholar | 12 | 309 |
| DBLP | **1** | 171 |

OpenAlex's top entity `A5000985289` (ORCID `0000-0001-6347-8368`, 401 works, 18,013 citations) is broadly right, but a second entity `A5110872469` carries an ORCID too (`0000-0001-9348-5999`) with 10 works and the same `last_known_institutions`. **Splitting still happens even between ORCID-bearing records.** Verdict: OpenAlex disambiguation is the best of the free open sources but is not clean. ProfScout must (a) prefer `has_orcid:true` records, (b) merge candidate entities that share an ORCID or a `block_key`, and (c) surface a "possible duplicate profile" affordance rather than pretending the merge is exact.

#### `last_known_institutions` — useful but noisy **[V]**

It is an **array**, not a scalar, and it can be stale or contain a visiting/secondary affiliation:

- `Foad Abd-Allah` → `["Cairo University", "Ajman University"]`
- `Shaimaa I El-Jaafary` → `["Cairo University", "Trinity College Dublin"]`, while her `affiliations[]` show Cairo 2023–2025 and University of Washington 2020–2022

The richer signal is `affiliations[]`, which is an array of `{institution, years[]}` derived per-work. For "is this professor at university X *right now*", the correct query is not `last_known_institutions` alone — it is `affiliations` with a recent year, cross-checked against ORCID employment. Recommended filter for a department sweep:

```
/authors?filter=last_known_institutions.id:I145487455&sort=cited_by_count:desc
```
**[V]** → `meta.count = 43746` for Cairo University. Note that this number includes every co-author ever affiliated, not just faculty. **OpenAlex has no concept of "professor".** Faculty-vs-student separation must be inferred (see §14, question B).

#### Verified author object fields

```
id, orcid, display_name, raw_author_names, full_name, works_count,
cited_by_count, summary_stats{h_index, i10_index, 2yr_mean_citedness},
ids, affiliations[{institution, years[]}], last_known_institutions[],
topics[{display_name, count, field, subfield, domain}], topic_share,
x_concepts, counts_by_year, display_name_alternatives, block_key,
works_api_url, updated_date, created_date
```

#### Verified institution object fields

```
id, ror, display_name, country_code, type, type_id, lineage, homepage_url,
image_url, display_name_acronyms, display_name_alternatives, repositories,
works_count, cited_by_count, summary_stats, ids, geo, international,
associated_institutions, counts_by_year, roles, topics, topic_share,
is_super_system, status, works_api_url
```

`display_name_alternatives` includes **native-script names** — e.g. Cairo University carries `"جامعة القاهرة"` and `"Université du Caire"` **[V]**. This is essential for a non-Anglophone tool and is a real advantage over naive scraping.

#### Topic taxonomy

**[V]** 4 domains → 26 fields → 252 subfields → 4,516 topics, plus 65,004 free keywords. Every author carries a ranked `topics[]` vector with per-topic work counts. **This is ProfScout's research-interest filter and it is available for every author in every country with zero scraping.** Note `/concepts` is **deprecated** — use `/topics` **[D]**.

#### `/awards` — a new and underappreciated entity

**[V]** 17,278,150 awards. Verified field set:

```
id, display_name, description, funder_award_id, funder, funded_outputs,
funded_outputs_count, amount, currency, funding_type, funder_scheme,
start_date, end_date, start_year, end_year, landing_page_url, doi,
provenance, lead_investigator, co_lead_investigator, investigators,
works_api_url, primary_topic, topics, institution_awarded
```

**[V]** Verified filter fields include `institution_awarded.{id,ror,country_code,type,lineage}`, `funder.{id,ror,doi}`, `lead_investigator.{orcid,given_name,family_name,affiliation.name,affiliation.country}`, `start_year`, `end_year`, `amount`, `currency`, `funding_type`.

Two hard limits found by testing:
1. **[V]** There is **no `lead_investigator.id`** — investigators are *not* linked to OpenAlex author IDs. Joining an award to a professor must go through ORCID or fuzzy name+affiliation matching.
2. **[V]** Coverage skews heavily to EU/US. `institution_awarded.country_code:EG` returns **104 awards total**. A sample award had `lead_investigator.given_name = null, family_name = null, orcid = null` — only an uppercase affiliation string `"HELSINGIN YLIOPISTO"`.

Verdict: `/awards` is genuinely valuable for Europe/North America and near-useless for Egypt, and ProfScout must present it as such.

---

### 2.2 ROR (Research Organization Registry) — **the institution ID backbone**

Base URL: `https://api.ror.org/v2/organizations` (v1 at `/organizations` still live) **[V]**

- **Auth:** none currently required **[V]** (all my calls succeeded anonymously).
- **Rate limit:** **[D]** 2,000 requests per 5-minute period per IP. Documented warning that traffic is heavy around midnight UTC.
- **⚠ Upcoming change — [D], from the ROR REST API docs:** *"Beginning sometime in the third quarter of 2026, ROR API requests will need to use a client ID in order to receive the current rate limit of 2000 requests per 5 minute period. Requests without identification will receive a lower rate limit of 50 requests per 5 minute period."* Registration is free. **ProfScout should ship with a client-ID config slot now.**
- **Licence:** **[V]** ROR's own about page: *"ROR data is freely and openly available without any restrictions under the Creative Commons CC0 1.0 Universal Public Domain dedication. ROR code is openly available on GitHub under a MIT License."* Redistribution of derived data is unambiguously fine.
- **Bulk:** **[D]** public data dump available (published to Zenodo); docs explicitly recommend the dump over heavy API use.

#### Can it enumerate "all universities in country X"?

**[V]** Yes — `?filter=country.country_code:EG,types:education` → `number_of_results: 125`.

Verified type facets (`types` filter values): `education, company, facility, funder, healthcare, nonprofit, other, government, archive` **[V]** (facet counts observed on Germany: company 2040, facility 840, funder 774, healthcare 667, nonprofit 663, education 618, other 481, government 294, archive 181).

**Caveat that matters: `types:education` is not "universities".** **[V]** The first result for Egypt was *"American International School in Egypt"* — a K-12 school. `types:education` covers schools, institutes, colleges and conservatories alongside research universities. ROR has no "is a degree-awarding research university" flag.

#### Verified ROR v2 record shape

```
id, names[{value, types[ror_display|label|acronym|alias], lang}],
types[], status, established, links[{type: website|wikipedia, value}],
locations[{geonames_details{country_name, name, lat, lng}}],
external_ids[{type: grid|isni|wikidata|fundref}], relationships[], domains[], admin
```

`names[]` carries native-script labels with language tags (`جامعة عين شمس`, lang `ar`) **[V]** — same multilingual advantage as OpenAlex. `external_ids` gives free crosswalks to **GRID** (legacy), ISNI, **Wikidata**, and **Crossref Funder DOIs (fundref)** — the last of these is the join key from an institution to funding data.

---

### 2.3 ORCID — researcher-supplied employment/education

Base URL: `https://pub.orcid.org/v3.0/` **[V]**

- **Auth:** **[V]** read access worked with **no token at all** — `GET /v3.0/{iD}/record` with `Accept: application/json` returned 200. (ORCID documents an OAuth public-client flow; anonymous read evidently still works for public data.)
- **Rate limits:** **[V]** a 15-request burst returned 15× HTTP 200 with **no rate-limit headers exposed**. **[?]** I could not verify the published numeric limit. Do not hard-code a figure; implement adaptive backoff on 429/503.
- **Search:** **[V]** `GET /v3.0/expanded-search/?q=affiliation-org-name:"Cairo University"&rows=3` → `num-found: 15152`. Returns `orcid-id, given-names, family-names, credit-name, other-name, email, institution-name`.

#### ⚠ Licence problem — read this carefully

**[V]** ORCID **Public APIs Terms of Service** (`info.orcid.org/public-client-terms-of-service/`):

> "We grant you a limited royalty-free license to make **non-commercial** use of the Public APIs... By 'non-commercial' we mean that you may not charge any re-use fees for the Public APIs, and you may not make use of the public APIs **in connection with any revenue-generating product or service**."

This is a **real constraint**. An open-source, non-monetised ProfScout is fine. The moment anyone runs a hosted paid tier, offers it as a paid service, or bundles it into a commercial product, the **live Public API is off-limits**. The escape hatch is the **ORCID Public Data File**, which is released annually under CC0 **[D]** — ProfScout should treat the data file as the commercially-safe path and the live API as the non-commercial convenience path, and say so in its README.

#### What you actually get — and how sparse it is

**[V]** Employment summaries carry: `organization.name`, `organization.address.{city, country}`, `organization.disambiguated-organization`, `department-name`, `role-title`, `start-date.year`, `end-date.year`.

Real example **[V]** (`0000-0001-6347-8368`): 6 employments, e.g. `University of Sharjah / "Computers and Informatics" / "Associate Professor" / 2022–present / AE`. **This is the only free structured source of an actual job title.**

But the sparsity is severe **[V]**:

| Observation | Result |
|---|---|
| Employments on a random Cairo-affiliated researcher (`0000-0001-8308-5756`) | **0** (`affiliation-group` empty) |
| Educations on both records I fetched | **0** |
| Public email addresses on both records | **0** |
| `disambiguated-organization.disambiguation-source` | **`RINGGOLD`**, not ROR |

Two consequences: (1) **role/title coverage is opt-in and probably minority-coverage globally** — never build a required field on it; (2) org disambiguation is Ringgold, so ROR joining needs a name/Ringgold crosswalk rather than a direct ID match.

`person.keywords`, `person.researcher-urls` (personal/lab homepage!) and `person.name.credit-name` are also present when filled in **[V]**.

---

### 2.4 Crossref — works metadata + funder registry

Base URL: `https://api.crossref.org` **[V]**

- **Auth:** none. `mailto=` puts you in the polite pool **[V]**.
- **Rate limits: [V] observed headers in the polite pool:** `x-rate-limit-limit: 3`, `x-rate-limit-interval: 1s`, `x-concurrency-limit: 3`. That is **3 requests/second, 3 concurrent** — far more restrictive than folklore suggests. Respect it.
- **Licence:** **[D]** Crossref metadata is openly available; the docs note that *abstracts* contained in the metadata may be subject to publisher/author copyright. Bibliographic metadata is redistributable; treat abstracts more carefully.
- **Bulk:** **[D]** annual public data file + REST snapshots.

**Coverage/quality for ProfScout:** **[V]** author objects are `{given, family, sequence, affiliation:[{name}], role}` — affiliation is a **raw unnormalised string** with no ROR ID in the record I sampled. Crossref is therefore *worse* than OpenAlex for the affiliation join; OpenAlex ingests Crossref and adds exactly the normalisation ProfScout needs. **Do not use Crossref as a primary author source.**

**Where Crossref is uniquely valuable:** the **Funder Registry** and funder data on works. **[V]** `/funders?query=National Science` → 384 results with `{id, name, location, uri: https://doi.org/10.13039/...}`. **[V]** Work-level funder objects look like:

```json
{"DOI":"10.13039/501100010426",
 "name":"UGC-DAE Consortium for Scientific Research, University Grants Commission",
 "doi-asserted-by":"publisher",
 "award":["1266"],
 "award-info":[{"award-number":["1266"]}]}
```

This is the cleanest free path from a paper → a named funding body → an award number, and it works globally (the sample was Indian). It is the backbone of design question C(ii).

---

### 2.5 DBLP — CS-only, best-in-class quality

- Search: `https://dblp.org/search/author/api?q=...&format=json` **[V]**
- Person record: `https://dblp.org/pid/{pid}.xml` **[V]**
- **Auth:** none **[V]**. **Rate limit: [?]** none documented that I could confirm; the search endpoint was **slow (4.2 s)** in my test, so treat it as a low-QPS courtesy service.
- **Licence:** **[V]** from `dblp.org/db/about/copyright.html`: *"The metadata provided by dblp on its webpages, as well as their XML, JSON, RDF, RIS, BibTeX, and text export formats... is released under the **CC0 1.0 Public Domain Dedication** license. That is, you are free to copy, distribute, use, modify, transform, build upon, and produce derived works from our data, **even for commercial purposes**, all without asking permission."* Best licence terms of any source here.
- **Bulk:** **[V]** XML dump and RDF dump linked from the site.

**Why it matters:** **[V]** the person XML (157 KB for one prolific researcher) contains a *single, human-curated* person entity with full co-author graph plus **cross-links to ORCID, Wikidata, ResearcherID and GND**:

```xml
<dblpperson name="Mohamed Elhoseny" pid="173/3758" n="171">
  <url>https://orcid.org/0000-0001-6347-8368</url>
  <url>https://www.wikidata.org/entity/Q87321989</url>
  <url>https://www.researcherid.com/rid/Q-5591-2017</url>
  <url>https://d-nb.info/gnd/1201095948</url>
```

**Coverage limit:** computer science only, and within CS it is publication-venue-driven — strong on conferences/journals, weak on interdisciplinary or applied work published outside CS venues. Useless for medicine, chemistry, humanities, engineering outside CS. **Verdict: an outstanding *optional* enrichment plug-in for CS; a disqualifying choice as a spine.**

---

### 2.6 Semantic Scholar Academic Graph — **Ahmed's undercount is real and explained**

Base URL: `https://api.semanticscholar.org/graph/v1/` **[V]**

**The undercount is confirmed and its cause is author-entity fragmentation, not missing papers.**

**[V]** `author/search?query=Mohamed Elhoseny` returns `total: 12` distinct author entities:

| S2 authorId | name | paperCount | citationCount | hIndex |
|---|---|---:|---:|---:|
| 49282672 | M. Elhoseny | 309 | 15,666 | 73 |
| 2021023083 | M. Elhoseny | 20 | 582 | 11 |
| 2238961560 | Mohamed Elhoseny | 13 | 14 | 2 |
| 2311392553 | Mohamed Elhoseny | 10 | 14 | 2 |
| 2367460437 | Mohamed Elhoseny | 4 | 14 | 1 |

Same person, five-plus profiles. If a lookup lands on entity `2021023083` you see 20 papers for someone with 400. **This is exactly the 34-vs-163 failure mode.** The corpus has the papers; the author-to-paper linkage is split. Contributing factors: initialised name forms (`M. Elhoseny` vs `Mohamed Elhoseny`) are treated as distinct, and **[V]** `affiliations` came back as `[]` on *every one* of the five entities — S2 has no affiliation signal to merge on.

**Additional disqualifiers found:**
- **[V] Unauthenticated access is effectively unusable.** A burst of 8 sequential requests returned **429 on all 8**. Not "throttled after N" — immediately, every time.
- **[D]** S2's own docs: *"Most Semantic Scholar endpoints are available to the public without authentication, but they are rate-limited to **1000 requests per second shared among all unauthenticated users**."* A single global bucket for the entire internet. An API key is effectively mandatory.
- **[V]** `author/{id}/papers` works fine once you have a valid ID (returned data with `next` cursor), so the API itself is sound.
- **[?]** Dataset licence: the S2 API landing page links an "API License Agreement" but I could not retrieve its text (`api.semanticscholar.org/corpus/legal/` redirected back to the product page). **Do not assume the S2 bulk datasets are freely redistributable — verify before shipping anything derived from them.**

**Verdict: not viable as a primary author source. Optional enrichment at best, behind an API key, and only for citation-context/influence features OpenAlex lacks.**

---

### 2.7 arXiv API — recent preprints, but **not** affiliations

Base URL: `http://export.arxiv.org/api/query` **[V]** — returns Atom XML, not JSON.

- **Auth:** none **[V]**. **[D]** ToU asks for a delay between requests and single-connection usage; treat ~1 request per 3 seconds as the safe ceiling.
- **Licence:** **[V]** from the API ToU: *"You are free to use descriptive metadata..."*, but *"arXiv is not the copyright holder on any of the e-prints available through the API... The vast majority of e-prints are submitted under the arXiv.org non-exclusive right to distribute."* **Metadata redistributable; full texts are not.**
- **Bulk:** **[D]** bulk metadata and full text via S3 (requester-pays) and OAI-PMH.

**The killer finding — [V]:** across 20 `cs.CL` entries containing dozens of authors, exactly **1** `<arxiv:affiliation>` tag appeared. The typical author element is bare:

```xml
<author>
  <name>Shota Horiguchi</name>
</author>
```

**arXiv cannot be used to determine affiliation.** Its genuine value for ProfScout is different and still real: **recency and topical currency**. A professor with three `cs.LG` preprints in the last six months is visibly active in a way that a citation count doesn't show. Use arXiv for a "recent activity / current direction" panel, resolved *from* OpenAlex author IDs, never as an entry point.

---

### 2.8 Google Scholar — **no API, and scraping is prohibited. Plainly.**

**There is no official Google Scholar API. There never has been. Google has explicitly declined to provide one.**

**[V]** `https://scholar.google.com/robots.txt` reads, verbatim:

```
User-agent: *
Disallow: /search
Disallow: /index.html
Disallow: /scholar
Disallow: /citations?
Allow: /citations?user=
Disallow: /citations?*cstart=
Disallow: /citations?user=*%40
Disallow: /citations?user=*@
Allow: /citations?view_op=list_classic_articles
...
User-agent: PetalBot
Disallow: /
```

Read this correctly. `Disallow: /scholar` and `Disallow: /search` block **all search-result scraping**. The narrow `Allow: /citations?user=` permits fetching a profile's first page — but `Disallow: /citations?*cstart=` **blocks the pagination parameter**, so you cannot walk a full publication list even on the "allowed" path. The carve-out is engineered to permit indexing, not harvesting.

Beyond robots.txt, automated querying violates the Google Terms of Service, and in practice Google Scholar deploys aggressive anti-bot measures — IP blocks and CAPTCHA interstitials arrive quickly and escalate to sustained blocks. Every "Google Scholar API" on the market is a third-party scraping proxy (SerpApi, ScraperAPI, Scholarly and friends) that shifts the ToS violation onto someone else's infrastructure; it does not make it lawful, and it is a paid dependency.

**Recommendation: ProfScout must not scrape Google Scholar, must not bundle a Scholar scraper, and must not ship a third-party Scholar-proxy integration by default.** The acceptable use is to **link out**: store the `scholarid` where one is already published in an openly-licensed dataset (CSRankings publishes them — see §2.11) or in an ORCID `researcher-urls` entry, and render it as a hyperlink the user clicks. Zero requests, full utility, no ToS exposure.

---

### 2.9 Wikidata / SPARQL — great for institutions, useless for faculty coverage

Endpoint: `https://query.wikidata.org/sparql?format=json&query=...` **[V]**

- **Auth:** none **[V]**. **[D]** Query Service enforces a 60-second query timeout and throttles by user agent; a descriptive UA is required in practice.
- **Licence:** **[D]** Wikidata content is **CC0**. Fully redistributable.
- **Bulk:** **[D]** full RDF/JSON dumps published regularly.

**[V] Universities per country works well:**

```sparql
SELECT (COUNT(DISTINCT ?u) AS ?n) WHERE {
  ?u wdt:P31/wdt:P279* wd:Q3918 .   # instance of (subclass of) university
  ?u wdt:P17 wd:Q79 .               # country = Egypt
}
```
→ **142** **[V]**. Compare ROR's 125 and OpenAlex's 117 for Egypt. The subclass-transitive query is genuinely useful as a **third opinion** for reconciling institution lists, and Wikidata items carry ROR IDs, GRID IDs, official websites and native-language labels.

**[V] Faculty coverage is hopeless.** Counting humans with `P108 (employer)` pointing at a university:

| Country | Wikidata people with university employer |
|---|---:|
| Germany | 77,766 |
| Japan | 51,040 |
| Brazil | 30,123 |
| India | 14,409 |
| **Egypt** | **3,182** |

For scale: **OpenAlex lists 43,746 authors at Cairo University alone** **[V]**. Wikidata's 3,182 covers *all of Egypt*, and skews to the historically notable — my query for employees of Cairo University returned Boutros Boutros-Ghali, Essam Sharaf (a former Prime Minister) and Arthur Looss (d. 1923). Wikidata answers "who is famous", not "who could supervise my PhD".

**Verdict: use Wikidata for the institution layer and for enriching a handful of eminent professors. Never for faculty enumeration.**

---

### 2.10 Aggregators — brief viability notes

| Source | Base URL | Auth | Verified behaviour | Verdict for ProfScout |
|---|---|---|---|---|
| **OpenAIRE Graph** | `https://api.openaire.eu/graph/v1/researchProducts` | optional token | **[V]** 200 unauth, 332 ms, `numFound: 1224231`, authors as `{fullName, name, surname, rank, pid}` | **Useful pluggable enrichment, esp. Europe.** **[D]** rate limit **60 req/hour unauthenticated, 7,200 req/hour authenticated** — anonymous use is a non-starter; register. Strong on EU project/funding linkage and repository coverage. |
| **CORE** | `https://api.core.ac.uk/v3/search/works` | API key expected | **[V]** returned 200 + data unauthenticated, but **6.6 s latency** — slowest source tested; `totalHits: 4761236` | Optional. Best for OA full text (useful for acknowledgement mining, see Q-B/D). Register for a key. Slow enough that it must be an async/background job. |
| **Scopus (Elsevier)** | `api.elsevier.com` | institutional subscription | not tested | **Excluded.** Requires a paid institutional subscription and an API key tied to it; redistribution of derived data is contractually restricted. Incompatible with an open-source tool that must work for an unaffiliated applicant. |
| **Web of Science (Clarivate)** | `api.clarivate.com` | paid | not tested | **Excluded**, same reasoning. A free "Starter" tier exists but is heavily capped and redistribution-restricted. |
| **Lens.org** | `api.lens.org` | key, application required | **[V]** ToS URL 404'd; could not read current terms | **[?] Do not rely on it.** Historically free for non-commercial academic use *by application*, paid otherwise. Its distinctive asset is **patent–scholarship linkage**, which is genuinely relevant to design question C (industry links) — worth revisiting as an optional plug-in, but its terms must be read before shipping. |
| **Dimensions** | `app.dimensions.ai/api` | subscription | **[V]** product page confirms "Access: Subscription" | Free access is available *by application* for non-commercial scientometric research only. Not usable as a default dependency. Notable for having the best free-world grants + clinical trials + patents linkage — flag as a manual, credentialled plug-in. |

---

### 2.11 Other genuinely useful sources

#### CSRankings (CS only) — **valuable, but the licence is a trap**

**[V]** The underlying data is plain CSV on GitHub:
`https://raw.githubusercontent.com/emeryberger/CSrankings/gh-pages/csrankings-{a..z}.csv`

**[V]** Header and sample rows:
```csv
name,affiliation,homepage,scholarid,orcid
A Min Tjoa,TU Wien,http://www.ifs.tuwien.ac.at/tjoa,x8qCMhcAAAAJ,0000-0002-8295-9252
A. Akbari Azirani,IUST,http://ce.iust.ac.ir/page.php?...,pCil4_cAAAAJ,0000-0000-0000-0000
```

The `a` file alone has **2,768 rows** **[V]**. This is a **human-curated, globally-scoped mapping of CS faculty → institution → homepage → Google Scholar ID → ORCID**. It includes TU Wien and Iran University of Science and Technology in the first two rows — it is not US-only. It is the single best free answer to "which of these authors is actually *faculty*" in CS, and it supplies the Scholar profile link without touching Google.

**⚠ [V] The CSRankings site footer states `CC BY-NC-ND 4.0`.** **NC** blocks commercial use and **ND** blocks distributing *derivatives*. If that licence governs the CSV data, ProfScout may read and link to it but **must not redistribute a transformed copy**. **[?]** I could not fetch a `LICENSE` file from the `gh-pages` branch (404), so it is unresolved whether the footer licence covers the data files or only the website. **Treat as ND until clarified: consume at runtime, do not bundle or republish.** (Note also **[V]** the site states its publication data comes from DBLP, which *is* CC0 — so the DBLP-derived portions can be re-derived cleanly from source.)

#### GRID (legacy)

GRID was retired in favour of ROR and its final releases are frozen. **[V]** ROR records carry `external_ids.type = "grid"`, so legacy GRID IDs found in old datasets can be resolved forward to ROR. **Use only as a crosswalk key; never as a live source.**

#### National / regional registries — **[?] the real gap**

The honest position: there is no global standard, and I did not verify these individually. Known patterns worth a country-plugin interface:
- **US:** IPEDS (NCES) publishes downloadable institution + programme files, public domain.
- **EU:** ETER (European Tertiary Education Register) publishes institution-level data; CORDIS publishes EU-funded project participants (directly relevant to question C).
- **Germany:** Hochschulkompass (HRK) lists accredited institutions and degree programmes — **[?]** open API status unconfirmed.
- **UK:** UKRI Gateway to Research offers an open API of funded projects and named investigators.
- **India:** AISHE / UGC publish recognised-university lists.

**Design implication: make "authoritative national university list" a pluggable interface with ROR as the universal default**, so a contributor in any country can raise the accuracy of their own country without touching the core.

#### University sitemaps / JSON-LD — see §12. Verdict: not a usable convention.

---

## 3. Field-population matrix

Which ProfScout dashboard fields each source can fill:

| ProfScout field | OpenAlex | ROR | ORCID | Crossref | DBLP | S2 | arXiv | Wikidata | Scrape |
|---|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|
| Institution list for country | ✅ | ✅✅ | — | — | — | — | — | ✅ | — |
| Institution ROR/canonical ID | ✅ | ✅✅ | ~ | ~ | — | — | — | ✅ | — |
| Native-script institution name | ✅ | ✅✅ | — | — | — | — | — | ✅ | ✅ |
| Person exists & has an ID | ✅✅ | — | ✅ | ~ | ✅(CS) | ~ | — | ~ | ✅ |
| Current affiliation | ✅ | — | ✅ | ~ | — | ❌ | ❌ | ~ | ✅✅ |
| **Job title / rank ("Professor")** | ❌ | — | ✅ | — | — | — | — | ~ | ✅✅ |
| **Department / school** | ❌ | — | ✅ | ~ | — | — | — | — | ✅✅ |
| Research topics/interests | ✅✅ | — | ~ | — | ~ | ✅ | ✅ | ~ | ✅ |
| Publication list | ✅✅ | — | ✅ | ✅ | ✅✅(CS) | ✅ | ~ | — | ~ |
| h-index / citations | ✅✅ | — | — | — | — | ✅ | — | — | — |
| Recent activity / preprints | ✅ | — | — | ~ | ✅ | ~ | ✅✅ | — | ~ |
| Co-author graph | ✅✅ | — | — | ✅ | ✅✅ | ✅ | ~ | — | — |
| ORCID iD | ✅ | — | ✅✅ | ✅ | ✅ | ~ | — | ✅ | ~ |
| Lab / personal homepage | ~ | — | ✅ | — | ✅ | — | — | ✅ | ✅✅ |
| **Email address** | ❌ | — | ❌ | ~ | — | — | — | — | ✅✅ |
| Funders / grants | ✅(awards) | — | ~ | ✅✅ | — | — | — | — | ~ |
| Industry affiliation | ✅ | ✅ | ✅ | ~ | — | — | — | ~ | ✅ |
| **Current students** | ❌ | — | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ~ |
| **"Accepting students"** | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |

✅✅ best-in-class · ✅ good · ~ partial/unreliable · ❌ not available

**Read the bottom four rows.** Every field that scraping uniquely provides — title, department, email, students, recruiting status — is a *profile detail*, not a *discovery* mechanism. That is the architectural argument in one table: **APIs discover, scraping enriches.**

---

## 4. Reliability problems — consolidated

| Source | Problem | Severity | Mitigation |
|---|---|---|---|
| OpenAlex | Author splitting even between ORCID'd records **[V]** | High | Merge on ORCID/`block_key`; expose duplicate-merge UI |
| OpenAlex | `last_known_institutions` stale/multi-valued **[V]** | Medium | Prefer recent `affiliations[].years`; cross-check ORCID |
| OpenAlex | Authors ≠ faculty (43,746 "at" Cairo) **[V]** | High | Seniority heuristics (§14 B); never label an author "professor" without corroboration |
| OpenAlex | $1/day free cap blocks country sweeps **[V]** | High | Use `openalex-official` CLI / snapshot for bulk |
| OpenAlex | `/awards` sparse outside EU/US (EG=104) **[V]** | Medium | Show as "coverage limited"; never a filter default |
| OpenAlex | `/concepts` deprecated **[D]** | Low | Use `/topics` |
| ROR | `types:education` includes K-12 **[V]** | Medium | Filter on works_count via OpenAlex; heuristics on name |
| ROR | Client ID mandatory ~Q3 2026 **[D]** | Medium | Ship config slot now |
| ORCID | Employment/education frequently empty **[V]** | High | Optional field; never required |
| ORCID | Non-commercial API ToS **[V]** | High | Document it; use Public Data File for any commercial path |
| ORCID | Ringgold not ROR for org IDs **[V]** | Medium | Name-based crosswalk |
| Crossref | 3 req/s, 3 concurrent **[V]** | Medium | Queue + backoff |
| Crossref | Affiliations are raw strings **[V]** | Medium | Don't use for affiliation; use OpenAlex |
| DBLP | CS only; slow (4.2 s) **[V]** | — | Optional plug-in only |
| S2 | Author fragmentation → undercount **[V]** | Critical | Do not use as primary |
| S2 | 429 on 8/8 unauthenticated burst **[V]** | Critical | Require key or omit |
| S2 | Dataset licence unread **[?]** | High | Verify before redistributing |
| arXiv | Affiliation absent (1/20 entries) **[V]** | High | Recency signal only |
| Google Scholar | No API; robots.txt disallows **[V]** | Critical | Link out only |
| Wikidata | Notability bias (EG: 3,182 nationwide) **[V]** | High | Institutions only |
| OpenAIRE | 60 req/hr unauthenticated **[D]** | Medium | Register for token |
| CORE | 6.6 s latency **[V]** | Medium | Async only |
| CSRankings | CC BY-NC-ND on the site **[V]** | High | Link/consume, don't redistribute |

---

## 5. Global coverage outside the US/UK — the decisive comparison

**[V]** Institution counts, `type/types = education`, live on 2026-07-22:

| Country | OpenAlex (education) | OpenAlex (all types) | ROR (education) | Agreement |
|---|---:|---:|---:|---|
| Egypt | 117 | 278 | 125 | 94% |
| Germany | 584 | 5,518 | 618 | 94% |
| Japan | 1,573 | 8,320 | 1,546 | 102% |
| Brazil | 510 | 1,961 | 565 | 90% |
| India | 1,800 | 3,926 | 1,944 | 93% |
| USA | 4,422 | 33,363 | 4,428 | 100% |
| UK | 582 | 7,988 | 586 | 99% |
| Nigeria | 263 | 479 | 315 | 84% |
| Indonesia | 841 | 1,033 | 945 | 89% |
| Iran | 335 | 473 | 356 | 94% |

**OpenAlex and ROR agree within 0–16% in every country tested, including every Global South country.** The two sources are largely mutually validating (OpenAlex ingests ROR), which is why the union — not either alone — is the right enumeration strategy.

Author-side coverage is likewise real, not tokenistic: **43,746 OpenAlex authors** with `last_known_institutions` = Cairo University, and **15,152 ORCID records** self-declaring a Cairo University affiliation **[V]**.

---

## 6. Licence summary — what an open-source tool may redistribute

| Source | Licence | Redistribute derived data? | Commercial use? |
|---|---|---|---|
| OpenAlex | **CC0 1.0** **[V]** | ✅ Yes, freely | ✅ Yes |
| ROR | **CC0 1.0** **[V]** | ✅ Yes, freely | ✅ Yes |
| DBLP | **CC0 1.0** **[V]** | ✅ Yes, freely | ✅ Yes (explicit) |
| Wikidata | **CC0** **[D]** | ✅ Yes | ✅ Yes |
| Crossref metadata | Open **[D]** | ✅ Yes (bibliographic) | ✅ Yes — but abstracts may be publisher-copyright **[D]** |
| ORCID Public API | **Non-commercial only** **[V]** | ~ under ToS | ❌ **No** |
| ORCID Public Data File | CC0 **[D]** | ✅ Yes | ✅ Yes |
| arXiv metadata | Free to use **[V]** | ✅ metadata | ~ ; full texts ❌ **[V]** |
| Semantic Scholar | API License Agreement **[?]** | ⚠ unverified | ⚠ unverified |
| CSRankings | CC BY-NC-ND 4.0 **[V]** | ❌ **ND blocks derivatives** | ❌ No |
| Scopus / WoS / Dimensions | Proprietary | ❌ | ❌ |

**The clean core — OpenAlex + ROR + DBLP + Wikidata — is entirely CC0.** ProfScout can build, cache, transform and republish on that foundation with no licence friction whatsoever. Everything with a licence problem (ORCID API, CSRankings, S2) can be isolated behind an optional plug-in that a user enables knowingly.

---

## 7. What scraping is actually for

Given all the above, the legitimate scraping surface is small, targeted, and **per-professor, not per-country**:

1. Fetch **one page** — the professor's lab/personal homepage, discovered from OpenAlex/ORCID/DBLP, not guessed.
2. Extract only: current title, department, contact email, "prospective students" / "openings" text, current lab members.
3. Do it **on demand**, when a user opens that professor's detail view — never as a bulk crawl.

That is one HTTP request per professor the user is genuinely interested in. It is defensible under any reading of robots.txt and ToS, it costs nothing, and it degrades gracefully to "not available" — which is exactly what a scraping-first design cannot do.

---

# Design questions

## A. Can "all universities in country X" be reliably enumerated?

**Verdict: YES — and this is the strongest result in this report.**

Use the **union of ROR and OpenAlex**, keyed on ROR ID:

```
https://api.ror.org/v2/organizations?filter=country.country_code:{CC},types:education
https://api.openalex.org/institutions?filter=country_code:{CC},type:education&per-page=200&cursor=*
```

Completeness is high and — critically — **uniform across regions**. §5 shows 84–102% agreement across ten countries spanning four continents. Egypt (125 ROR / 117 OpenAlex), Indonesia (945/841) and Nigeria (315/263) are covered as systematically as the US and UK.

**Three caveats you must engineer around:**

1. **`education` ≠ university.** **[V]** ROR's first Egyptian result was an international K-12 school. Filter by joining to OpenAlex `works_count` — a real research university has thousands of works; a secondary school has ~0. A threshold of `works_count > 100` cleanly separates them and is country-neutral.
2. **The list is of *institutions*, not *departments*.** Neither source models faculties/schools/departments as first-class entities. OpenAlex's `lineage` and `associated_institutions` capture *some* hospital/institute hierarchy **[V]**, but not "the CS department". Department is a scraped or ORCID-supplied field.
3. **Use ROR as the canonical ID, OpenAlex as the activity signal.** ROR answers "does this org exist"; OpenAlex answers "does it publish". Wikidata (142 for Egypt, **[V]**) is a useful third opinion when the two disagree.

**Recommended fallback chain:** ROR → OpenAlex → Wikidata SPARQL → national registry plug-in (§2.11) → user-supplied CSV.

---

## B. Can a professor's CURRENT STUDENTS be obtained at scale in any country?

**Verdict: NO. Not in any country, from any source, at any scale.**

This is the most important negative result in the report, and ProfScout's product design must accept it rather than fake it.

I checked each candidate path:

| Path | Finding | Verdict |
|---|---|---|
| Structured API field | No source has a supervision relation. OpenAlex, ORCID, Crossref, S2, DBLP: none model advisor→student. | ❌ |
| **Dissertation records** | **[V]** OpenAlex has **11,057,232** works of `type:dissertation`. But **[V]** a fetched dissertation record's `authorships` contained **only the author** — no supervisor, no committee. The schema has no supervisor field. | ❌ |
| Dissertation geography | **[V]** FR 191,504 · US 179,368 · BR 33,527 · GB 28,862 · CA 24,836 · DE 24,606 · NL 14,304 · JP 13,971 · ES 10,558 · AU 9,699. Egypt, India, Indonesia, Nigeria don't reach the top 10. | Also badly skewed |
| **ProQuest / theses DBs** | ProQuest Dissertations records *do* carry advisor names, but ProQuest is a paid, licence-restricted commercial database. Nothing redistributable. National equivalents (theses.fr, DART-Europe, NDLTD) vary wildly and mostly lack advisor fields. | ❌ for open source |
| **ORCID education records** | **[V]** Both ORCID records I fetched had **0 education entries**. Even when present, ORCID education says "I studied at X" — it names the *institution*, not the *supervisor*. | ❌ |
| **Acknowledgement mining** | Acknowledgements do name students, but require OA full text (CORE/OpenAlex PDFs), NLP extraction, and they describe *past* contributions. Extremely high cost, low precision, no currency. | ❌ at scale |
| Lab webpages | Genuinely have current lab members — and are exactly as unscrapable-at-scale as §12 shows. | ~ per-professor only |

### Best available proxy — and it does work

**Recent junior co-authors at the same institution.** I built and tested this **[V]**:

Taking OpenAlex author `A5000985289`, 25 works from 2023 onward → 66 distinct co-authors. Ranking by co-authorship frequency and filtering to shared institution:

| Co-author | Papers together | Institution | Their works | Their citations | First active |
|---|---:|---|---:|---:|---:|
| Ibrahim M. El-Hasnony | 8 | Mansoura University | 33 | 939 | 2015 |
| Mahmoud Abdel-Salam | 6 | Mansoura University | 58 | 1,010 | 2019 |
| Nourmeen Lotfy | 3 | Mansoura University | — | — | — |
| Reham Elshamy | 2 | Mansoura University | — | — | — |

The signal is real: frequent recent co-authors, same institution, short publication history, first-active year within the last few years. That profile is a current or recent PhD student or postdoc with high probability.

**Implement it as:** `recent_collaborators`, with a visible label such as *"Frequent recent co-authors at the same institution — likely current group members (inferred, not confirmed)."*

**Do not call it "students."** It cannot distinguish a student from a postdoc, a technician, or a junior colleague, and mislabelling a named individual's role is both wrong and a GDPR problem (§E). The honest framing is also the more useful one for an applicant: "who is this person actually working with right now" answers the underlying question — *is this a functioning, active group?* — better than a roster would.

---

## C. Can a professor's INDUSTRY / COMPANY links be obtained?

**Verdict: PARTIALLY — and the three sub-questions have sharply different answers.**

### (i) Their own appointments/affiliations — ✅ **FEASIBLE, good coverage**

**[V]** OpenAlex types institutions, and `company` is a first-class type:
- `institutions?filter=country_code:DE,type:company` → **2,022** companies
- `authors?filter=affiliations.institution.type:company,affiliations.institution.country_code:DE` → **833,208** authors with a German company affiliation

So a professor who co-publishes from Google, Siemens or a startup is directly detectable: scan their `affiliations[]` for any institution with `type: company`, and use the attached `years[]` to say whether it's current or historical. ROR's `types` facet corroborates independently **[V]**. ORCID employment adds self-declared industry roles with job titles when the researcher has filled it in **[V]**.

This is a clean, global, CC0-licensed, zero-scraping feature. **Ship it.**

### (ii) Companies funding their lab — ⚠ **PARTIALLY FEASIBLE, heavily region-skewed**

Two joinable paths:

1. **Crossref funder data** **[V]** — work-level `funder[]` with Funder Registry DOI + award numbers (verified shape in §2.4). Global, free, well-populated where publishers deposit it.
2. **OpenAlex `/awards`** **[V]** — 17.2M awards with `amount`, `currency`, `funder`, `institution_awarded`, `funding_type`, `start_year`/`end_year`.

**Two limits found by testing that you must design around:**
- **[V] No `lead_investigator.id` filter exists** — awards do not link to OpenAlex author IDs. The only reliable join to a person is `lead_investigator.orcid`, and the sample award I inspected had `orcid: null`, `given_name: null`, `family_name: null` — just an affiliation string. **PI-level attribution will frequently fail.**
- **[V] Coverage collapses outside EU/US.** `institution_awarded.country_code:EG` → **104 awards in total, for the whole country.**

**Practical design:** compute funding at **institution + topic** level (which works), attribute to a person only via a matched ORCID (which sometimes works), and label the whole panel with its coverage — "no award data available for this country" is a legitimate and necessary state. Note also that most awards are from *government* funders; genuine *corporate* funding is a minority and often undeposited.

**Optional upgrade:** Lens.org's patent–scholarship linkage and Dimensions' grants graph are the two best sources for corporate ties, but both require applications and have unread/restrictive terms (§2.10). Plug-in only.

### (iii) Student placements — ❌ **NOT FEASIBLE**

There is no open source for "where did this professor's graduates end up". It would require the supervision graph from question B (which doesn't exist) joined to employment histories (which live in LinkedIn, whose ToS categorically prohibits scraping and which has no open API for this).

The only faint proxy: take the `recent_collaborators` from B, look up *their* current `last_known_institutions` in OpenAlex, and observe that some now sit at companies. **[V]** the machinery works — but it is a proxy of a proxy, covers only those who kept publishing, and should be treated as an anecdote generator, not a statistic. **Recommend: do not build.**

---

## D. Is the professor "recruiting / accepting students"?

**Verdict: this signal does not exist in any structured source, anywhere. Zero of the eleven sources investigated carry it.**

That is not an oversight — no scholarly metadata standard models hiring intent, because it is transient (valid for weeks), unverifiable by third parties, and nobody's deposit obligation.

**Where the signal actually lives, ranked by reliability:**

| Rank | Location | Freshness | Machine-readable? | Feasible? |
|---|---|---|---|---|
| 1 | The professor's **own lab/homepage** — "Prospective students", "Openings", "I am recruiting for Fall 2027", "Please read before emailing me" | Days–months | ❌ free text | ✅ single-page fetch + LLM extraction |
| 2 | **Departmental PhD-admissions pages** — per-cycle lists of supervisors with projects | Per cycle | ❌ | ~ per-institution |
| 3 | **Funded-position boards** — EURAXESS (EU), FindAPhD, jobs.ac.uk, ProFellow, national portals | Days | ~ some feeds | ✅ genuinely the best *structured* option |
| 4 | **Twitter/X, Bluesky, Mastodon** — "recruiting PhD students" posts | Days | ❌ | ~ API cost/ToS |
| 5 | **Recently started grant** — a 3–5-year award beginning within 12 months implies hiring | Months | ✅ **[V]** `/awards.start_year` | ✅ **strong inference, EU/US only** |
| 6 | **Growing group size** — `recent_collaborators` count rising year over year | Months | ✅ derived | ✅ weak but global |

### Recommendation

Do **not** present a boolean "accepting students". Present a **transparent, evidence-cited recruiting signal**:

- **Strong** — an explicit recruiting statement was found on their page (quote it, link it, timestamp it).
- **Moderate** — a new grant started within the last 12 months **[V]** (`/awards` with `start_year >= now-1`), and/or their recent co-author count is growing.
- **Weak/Unknown** — active publication record but no direct evidence. **This will be the majority state, and that is fine.**

Always show *why* and *when it was checked*. An applicant can act on "their page said this on 3 July" far better than on an unexplained green tick — and a wrong green tick wastes their application cycle.

This is precisely the case where the **on-demand, single-page fetch** (§7) earns its place: it runs for the ten professors a user shortlists, not the 43,746 at Cairo University.

---

## E. Legally and ethically sound posture

Professors are identifiable natural persons. In the EU, UK, Brazil (LGPD), and increasingly elsewhere, aggregating their names, emails, affiliations and inferred group memberships is **processing of personal data** — regardless of the data being publicly visible. Public ≠ unregulated.

### E.1 Lawful basis and GDPR specifics

- **Basis: legitimate interests (Art. 6(1)(f)).** Helping prospective students find supervisors is a genuine legitimate interest, the data is professional (not private life), and expectations are reasonable — academics publish contact details precisely to be contacted about research. **Document a short Legitimate Interests Assessment in the repo.** Do not claim consent, because you have none.
- **Purpose limitation:** state the purpose narrowly — *academic supervisor discovery*. This forbids repurposing the dataset for recruitment marketing, mailing-list sales, or bulk cold-outreach tooling. **Do not build a "mail all 200 professors" button.** That converts a research tool into a spam cannon and destroys the legitimate-interests basis.
- **Data minimisation:** collect only fields that serve supervisor discovery. **Do not collect** personal phone numbers, home addresses, photographs, birth dates, or anything about a professor's private life. Emails only from pages where the person published them for professional contact.
- **Art. 14 transparency:** you collected data without asking. Publish a plain-language privacy notice at a stable URL, linked from the app and README, covering: what is held, sources, purpose, basis, retention, and how to object.
- **Art. 21 right to object + Art. 17 erasure:** provide a real, working opt-out — an email address and/or a public `optout.txt` in the repo keyed by ORCID/OpenAlex ID that the pipeline **excludes at build time**, so a removal survives the next refresh. Honour requests within 30 days. This single feature does more for the project's legitimacy than any other.
- **Special categories (Art. 9):** never infer or store gender, ethnicity, nationality, religion, health or political views — including as "diversity" features. Do not derive them from names or photographs.
- **Automated decision-making:** ProfScout ranks and scores people. Keep every score **explainable and evidence-linked**, and never present an inference (like `recent_collaborators` or a recruiting signal) as a fact.

### E.2 robots.txt and Terms of Service

- **Obey `robots.txt` — always, in code, not in policy.** Use a real parser (`urllib.robotparser`, `reppy`) fetched and cached per host, evaluated **before** every request. No override flag.
- **Google Scholar: do not scrape.** **[V]** robots.txt disallows `/scholar`, `/search`, and paginated `/citations?*cstart=` (§2.8). Link out only. Ship no Scholar scraper and no third-party Scholar-proxy integration.
- **LinkedIn, ResearchGate, Academia.edu: do not scrape.** All three prohibit automated access in their ToS; ResearchGate additionally hosts publisher-copyright PDFs.
- **Honour `Crawl-delay`** where present, and treat a `noindex`/`nofollow` faculty page as off-limits.
- **Respect the ORCID non-commercial clause [V].** If ProfScout is ever monetised, the live Public API must be swapped for the CC0 Public Data File. Note this in the README *now*, before anyone builds a business on it.
- **Respect CSRankings' ND term [V].** Consume at runtime; do not bundle or republish a transformed copy.

### E.3 Rate limiting and identification

Concrete, verified budgets:

| Source | Limit | Source of number |
|---|---|---|
| OpenAlex | $1/day with free key; list call = $0.0001 | **[V]** headers + **[D]** docs |
| ROR | 2,000 / 5 min per IP; **50 / 5 min from Q3 2026 without client ID** | **[D]** |
| Crossref | **3 req/s, 3 concurrent** (polite pool) | **[V]** headers |
| OpenAIRE | 60/hr anonymous, 7,200/hr with token | **[D]** |
| Semantic Scholar | 1,000 rps shared globally, unauthenticated | **[D]**; **[V]** 8/8 → 429 |
| arXiv | ~1 req / 3 s, single connection | **[D]** |
| ORCID | not exposed | **[?]** — adaptive backoff |
| University sites | **self-imposed: ≤ 1 req / 5 s per host, ≤ 1 concurrent** | policy |

- **Send an honest User-Agent on every request**, including project name, version, a URL, and a contact address:
  `ProfScout/0.1 (+https://github.com/<org>/profscout; mailto:contact@example.org)`
  This is what lets an administrator email you instead of blocking you, and it is the single cheapest good-citizen measure available.
- **Never parallelise across a single host.** Parallelise across *hosts*.
- **Exponential backoff with jitter** on 429/503; honour `Retry-After`; circuit-break a host after repeated failures.

### E.4 Caching and retention

- **Cache aggressively** — it is the main mechanism by which you stop being a burden. Respect `ETag`/`Last-Modified`; serve conditional requests.
- Suggested TTLs: institutions **30 days**; author metrics **7 days**; works **7 days**; scraped pages **7–14 days**; recruiting signals **short — 3–7 days**, because a stale "accepting students" is worse than none.
- **Always show "last checked: <date>"** in the UI. Freshness is a correctness property here.
- **Retention:** re-derive the dataset from source on a schedule and let deleted upstream records disappear rather than persisting forever. Never resurrect a record the source has removed — that is how a right-to-erasure request gets silently undone.
- **Prefer local snapshots over live API hammering** for anything country-scale (OpenAlex CLI/snapshot, ROR dump, DBLP dump). It is faster, kinder, and removes the rate-limit ceiling.

### E.5 Attribution

Even where CC0 imposes no obligation, attribute — it costs nothing and sustains the commons these tools depend on:

> Data from OpenAlex (CC0), ROR (CC0), DBLP (CC0), Crossref, ORCID, and Wikidata (CC0). ProfScout is not affiliated with any of these organisations.

Also display **per-field provenance** in the UI ("h-index — OpenAlex, checked 22 Jul 2026"). It is honest, it is debuggable, and it makes the tool's limits legible to the user, which is the whole ethical game.

### E.6 The two things not to build

1. **Bulk contact/outreach tooling.** No mass email, no mail-merge, no exported email lists. It breaks purpose limitation, it is what makes academics hate tools like this, and it is the fastest route to blocklists.
2. **Any ranking that scores people on inferred personal characteristics.** Rank on research output and topical fit. Nothing else.

---

## F. Recommended source stack

### Layer 0 — Institution spine (CC0, mandatory)

```
ROR  ──canonical org ID, country, types, native names, GRID/ISNI/Wikidata/Fundref crosswalks
  └── OpenAlex /institutions ──activity signal (works_count), homepage, lineage, topics
        └── Wikidata SPARQL ──tie-breaker + enrichment
```
Join key: **ROR ID**. Filter `works_count > 100` to strip K-12 noise **[V]**.

### Layer 1 — People spine (CC0, mandatory)

```
OpenAlex /authors  ── THE SPINE
  filter=last_known_institutions.id:{OA_ID}  (or affiliations.institution.ror:{ROR})
```
Supplies: identity, ORCID, works_count, citations, h-index, i10, 2yr mean citedness, `topics[]` vector, `affiliations[]` with years, co-author graph, `counts_by_year`. **This one endpoint fills most of the dashboard, in every country, under CC0, with no scraping.** **[V]**

**There is no substitute for this layer.** If OpenAlex is unavailable for a country, ProfScout does not work there — which is why coverage was tested across ten countries (§5) and found uniform.

### Layer 2 — Identity resolution & role (free, mandatory-ish)

```
ORCID  ── job title, department, employment dates, lab URL, keywords
       ⚠ non-commercial ToS [V]; frequently empty [V]
DBLP   ── CS only: authoritative single-person entity, ORCID/Wikidata/GND crosswalks, CC0
```
Both are **best-effort**: present when present, absent without breaking anything.

### Layer 3 — Enrichment (optional, pluggable)

| Plug-in | Adds | Enable when |
|---|---|---|
| Crossref | funder + award numbers per work | always (3 req/s) |
| OpenAlex `/awards` | grant amounts, dates, funders, PI | EU/US-heavy targets |
| arXiv | recent preprints, current direction | STEM/CS |
| OpenAIRE | EU project linkage, repository coverage | Europe (needs token) |
| CORE | OA full text for acknowledgement/lab mining | async background only |
| CSRankings | CS faculty ✓, homepage, Scholar link | CS — **link, don't redistribute [V]** |
| Semantic Scholar | citation contexts, influence | needs API key; **fragmentation warning [V]** |
| National registry | authoritative accredited-university list | per-country contributor |
| Lens / Dimensions | patents, corporate ties | credentialled users only |

### Layer 4 — Targeted scraping (on-demand, per-professor, never bulk)

Triggered **only** when a user opens a professor's detail view. One page, robots-checked, ≤1 req/5 s/host, cached 7–14 days, LLM-extracted:

`current title · department · contact email · recruiting statement · current lab members`

Discovered from Layer 1–3 URLs (`homepage_url`, ORCID `researcher-urls`, DBLP `<url>`), **never guessed from URL patterns** — §12 shows why guessing fails.

### Fallback chain when a source is missing for a country

```
Universities:    ROR → OpenAlex → Wikidata → national registry plug-in → user CSV
People:          OpenAlex → (no substitute; degrade to "coverage unavailable")
Title/dept:      ORCID → scraped page → "unknown" (never fabricate)
Topics:          OpenAlex topics → OpenAlex keywords → arXiv categories → DBLP venues
Recent activity: OpenAlex counts_by_year → arXiv → Crossref
Funding:         OpenAlex /awards → Crossref funder → "not available in this country"
Students:        recent_collaborators heuristic only, explicitly labelled inferred
Recruiting:      scraped statement → new-grant inference → growing-group → "unknown"
Scholar profile: CSRankings scholarid / ORCID URL → link out only, never fetch
```

**The governing rule: every layer below Layer 1 must be able to fail silently.** A professor in Egypt with an OpenAlex record and nothing else must still produce a useful dashboard row. That property is what makes ProfScout genuinely multi-country rather than a US/UK tool with an international marketing claim — and it is achievable only with an API-first spine.

---

## 12. Appendix: the scraping-feasibility experiment

Six real faculty/department pages, five countries, fetched 2026-07-22 **[V]**:

| Page | HTTP | JSON-LD blocks | `@type`s found | `schema.org/Person`? | mailto links |
|---|---:|---:|---|:---:|---:|
| MIT EECS faculty | 200 | 1 | WebSite, SearchAction, Organization, CollectionPage, BreadcrumbList | ❌ | 181 |
| TU München CS professors | **404** | 1 | WebPage | ❌ | 0 |
| U Tokyo IST faculty list | **404** | 0 | — | ❌ | 0 |
| Cairo University FCI | 200 | 0 | — | ❌ | 1 |
| IIT Bombay CSE | 200 | 0 | — | ❌ | 0 |
| Universidade de São Paulo | 200 | 0 | — | ❌ | 0 |

**Findings:**
- **0 / 6 pages carried `schema.org/Person` markup**, in JSON-LD or microdata. The "schema.org Person on faculty pages" convention does not exist in practice.
- **2 / 6 URLs 404'd** — plausible, current-looking URLs had already rotted. Any URL-pattern-based crawler carries permanent maintenance debt.
- **Cairo University's Faculty of Computers & AI returned `<title>Account Suspended</title>`** — a live illustration that Global South university web infrastructure cannot be a dependency.
- **IIT Bombay CSE is a client-rendered Angular SPA** (`<base href="/">`, empty shell) — requires a headless browser, multiplying cost per page by 10–50×.
- MIT EECS did expose **181 `mailto:` links** on one page — confirming the one thing scraping is genuinely good at (contact details), and nothing else.

**robots.txt observed [V]:** MIT EECS and TUM both publish permissive robots.txt with sitemaps (`Disallow: /wp-admin/`, `Disallow: /typo3/`), so *polite, targeted* fetching of a specific faculty page is allowed at both. This supports the Layer-4 design — targeted per-professor fetching is legitimate; bulk crawling is what's unjustifiable.

**Conclusion: scraping is viable as per-professor enrichment and non-viable as a discovery spine.** This experiment is the empirical core of the report's recommendation.

---

## 13. Appendix: quick-reference endpoints

```bash
# All universities in Egypt (ROR, canonical)
https://api.ror.org/v2/organizations?filter=country.country_code:EG,types:education

# Same, with activity signal (OpenAlex)
https://api.openalex.org/institutions?filter=country_code:EG,type:education&per-page=200&cursor=*&api_key=KEY

# Authors at Cairo University, most-cited first        [V] 43,746 results
https://api.openalex.org/authors?filter=last_known_institutions.id:I145487455&sort=cited_by_count:desc&api_key=KEY

# Only ORCID-bearing authors (cleaner disambiguation)
https://api.openalex.org/authors?filter=last_known_institutions.id:I145487455,has_orcid:true&api_key=KEY

# Authors at an institution working on a given topic
https://api.openalex.org/authors?filter=last_known_institutions.id:I145487455,topics.id:T10321&api_key=KEY

# Industry-affiliated researchers
https://api.openalex.org/authors?filter=affiliations.institution.type:company,affiliations.institution.country_code:DE

# Grants awarded to institutions in a country          [V] EG = 104 only
https://api.openalex.org/awards?filter=institution_awarded.country_code:EG

# Grants by PI ORCID (the only person-level join available)
https://api.openalex.org/awards?filter=lead_investigator.orcid:0000-0001-6347-8368

# ORCID employment history (title + department + dates)
https://pub.orcid.org/v3.0/0000-0001-6347-8368/employments   # Accept: application/json

# ORCID people claiming an affiliation                 [V] 15,152 results
https://pub.orcid.org/v3.0/expanded-search/?q=affiliation-org-name:%22Cairo+University%22

# DBLP person record (CS) — ORCID/Wikidata/GND crosswalks
https://dblp.org/search/author/api?q=NAME&format=json
https://dblp.org/pid/173/3758.xml

# Crossref funder registry
https://api.crossref.org/funders?query=NAME&mailto=you@example.org

# arXiv recent preprints (recency signal only — no affiliations)
http://export.arxiv.org/api/query?search_query=cat:cs.LG&sortBy=submittedDate&sortOrder=descending

# Wikidata: universities in a country
SELECT ?u ?uLabel WHERE { ?u wdt:P31/wdt:P279* wd:Q3918 . ?u wdt:P17 wd:Q79 . }

# Bulk (recommended for country-scale)
pip install openalex-official
openalex download --api-key KEY --filter "authorships.institutions.country_code:EG"
https://openalex.s3.amazonaws.com/          # full snapshot, CC0 [V]
```

---

*All API probes performed unauthenticated on 2026-07-22 from a single IP. Counts are live values and will drift. Claims marked **[D]** come from official documentation; claims marked **[?]** were not confirmed and should be re-checked before being relied upon.*
