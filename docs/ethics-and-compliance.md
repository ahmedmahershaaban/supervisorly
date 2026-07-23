# Ethics and Compliance

This tool processes personal data about identifiable living people — academics, many of
them in the EU. That makes GDPR and equivalent regimes directly applicable, and it makes
the difference between a legitimate research tool and a scraper that gets the repository
taken down.

This document is the project's stated posture. Where it says the code enforces something,
the code must actually enforce it — a promise in a README that the implementation does not
keep is worse than no promise.

Sources for the factual claims here: `research/data-sources.md`.

---

## 1. What this tool does and does not do

**Does:**
- Read publicly published scholarly metadata (authorship, affiliation, topics, funding)
  from open APIs whose licences permit it
- Fetch individual, publicly-linked faculty and lab pages, one at a time, for professors
  the user has explicitly shortlisted
- Present that information to one prospective student making one career decision

**Does not, by design:**
- **No bulk or automated outreach.** No mail-merge, no template emailing, no contact
  export sized for a campaign. This is the single feature most likely to turn the project
  into a spam vector, and it is permanently out of scope
  ([D-007](DECISIONS.md#d-007--positioning-the-gap-is-non-cs-non-us-and-relationship-data))
- **No scraping of Google Scholar.** Verified: `robots.txt` contains `Disallow: /scholar`,
  and `cstart=` pagination is blocked even on the `/citations?user=` carve-out. Scholar
  data reaches the tool only through sources that license it
- **No personal or sensitive inference.** No guessing at nationality, gender, religion,
  age, health, or immigration status; no "likelihood of accepting you" scoring of an
  individual human
- **No credential harvesting, no login-walled content, no CAPTCHA circumvention**
- **No redistribution of scan output.** Results stay on the user's machine and are
  git-ignored ([D-005](DECISIONS.md#d-005--scan-output-is-never-committed))

---

## 2. Lawful basis

Processing rests on **legitimate interests** (GDPR Art. 6(1)(f)): helping a prospective
research student identify a suitable supervisor, using information those academics have
themselves published for precisely that purpose — to be found by people interested in
their research.

A written **Legitimate Interests Assessment** lives at `docs/legal/lia.md` and covers the
three-part test (purpose, necessity, balancing). It is a real assessment, not a checkbox:
the balancing test is what justifies the scope limits in §1.

**Article 14 transparency notice.** The data is obtained from third parties, not from the
subjects, so Art. 14 applies. A public notice at `docs/legal/privacy-notice.md` states who
processes the data, on what basis, which categories, from which sources, for how long, and
how to object — and the repository's public page links to it.

---

## 3. Rights and the opt-out mechanism

**`optout.txt` is enforced in code, at build time.** It is a plain newline-delimited list
of identifiers — ORCID iDs, OpenAlex author IDs, or homepage URLs. Any record matching an
entry is dropped before it reaches the dataset or the dashboard. The check runs on every
build, cannot be disabled by a flag, and is covered by a test that fails if an opted-out
identifier survives into output.

**Takedown route.** A documented contact address in the repository, plus a GitHub issue
template. Requests are honoured without requiring the requester to explain themselves or
prove harm.

**Correction.** Because every field carries its source and timestamp
([D-010](DECISIONS.md#d-010--every-field-carries-provenance-and-confidence)), a person who
believes a fact is wrong can see where it came from — usually an upstream source they can
correct at origin, which fixes it for everyone rather than only here.

---

## 4. Technical conduct

| Rule | Implementation |
|---|---|
| `robots.txt` is parsed and obeyed | in the fetch layer, before any request — not a documented intention |
| Honest User-Agent with a contact URL | every outbound request; never spoofs a browser |
| Rate limits respected | per-host token bucket; Crossref polite pool 3 req/s is the binding constraint; ROR 50 req/5 min |
| Aggressive caching | disk cache keyed by URL + ETag with per-source TTL; a re-scan re-fetches only what changed |
| Backoff | exponential with jitter on 429/5xx; a 429 slows the tool down, it does not retry harder |
| Targeted fetching only | page fetches happen for shortlisted professors, never as a bulk crawl ([D-013](DECISIONS.md#d-013--api-first-spine-page-scraping-is-enrichment-only)) |
| Fail closed | if `robots.txt` is unreachable or ambiguous, the fetch does not happen |

---

## 5. Licence obligations of upstream sources

| Source | Licence / terms | What we may do |
|---|---|---|
| OpenAlex snapshot | **CC0** (verified from S3 `LICENSE.txt`) | use and redistribute freely |
| ROR | open | use freely; client ID required from Q3 2026 |
| Crossref | open metadata | use freely; honour the polite pool |
| ORCID Public API | **non-commercial use only** per ToS | fine for this project; the CC0 Public Data File is the escape hatch if that ever binds |
| DBLP | open | use freely |
| CSRankings | **CC BY-NC-ND** | **link to it; never redistribute or derive from its data** |

The ND clause on CSRankings is why this project cannot take the shortcut every comparable
tool took ([D-007](DECISIONS.md#d-007--positioning-the-gap-is-non-cs-non-us-and-relationship-data)) —
and, usefully, why it is not restricted to computer science.

---

## 6. Honesty about what the data is

Three commitments that are as much about accuracy as ethics, because presenting inference
as fact is how this tool would do real damage — to a user who acts on it, and to an
academic mischaracterised by it.

1. **`recent_collaborators` is never labelled "students."** No open source records
   supervision. The field is an inference from co-authorship and is named as one
   ([D-016](DECISIONS.md#d-016--students-is-not-obtainable-ship-recent_collaborators-instead)).
2. **"Recruiting" is a tiered, evidence-cited signal with a last-checked date**, never a
   boolean ([D-018](DECISIONS.md#d-018--recruiting-is-a-tiered-evidence-cited-signal--never-a-boolean)).
   A stale "yes" that sends someone to email a professor who stopped taking students two
   years ago is a real cost to two real people.
3. **"Unknown" is a first-class, displayed value.** The dashboard shows absence of
   evidence as absence of evidence. It never fills a gap with a plausible guess.

---

## 7. Corrections from adversarial review

Three critics attacked an earlier draft of this posture. The following are their
substantive corrections, kept because they change behaviour rather than wording.

**`robots.txt` compliance is not a lawful basis.** It is a crawling convention. Obeying it
says nothing about a site's Terms of Use, nor about the EU **sui generis database right**,
which can protect a substantial extraction from a faculty directory independently of
copyright. Compliance stays; the claim that compliance is what makes the project lawful is
withdrawn. The lawful basis is the documented legitimate-interests assessment in §2 — and
under GDPR the load-bearing obligations are upstream of takedown: the basis itself, and
Art. 14 notification. The disproportionate-effort exemption at Art. 14(5)(b) is not
automatic and is not assumed here.

**Email addresses are a regulated category, not just a field.** Systematic de-obfuscation
of `name at dept dot edu` forms and storage of the results is exactly what many university
ToS prohibit, and **CASL — in Canada, the project's own first test region — separately
regulates address harvesting.** Therefore: addresses are stored only when published in
plain, machine-readable form; obfuscated addresses are recorded as *"contact route
published on page"* with a link, not de-obfuscated into a mailable string; and no export
path emits a bare address list.

**Students are the sharpest exposure in the dataset.** PhD students, predocs and RAs are
not public figures in the way professors are. Appearing on a lab page is consent to appear
*on that lab page* — not to be aggregated into a queryable, sortable, exportable database
joined to inferred attributes. `LabMember` is simultaneously the least obtainable entity
and the most sensitive. It ships display-only, never in exports, never with inferred
attributes attached ([D-024](DECISIONS.md#d-024--evaluative-judgements-about-individuals-stay-local-and-unexported),
[D-025](DECISIONS.md#d-025--past-students-are-obtainable-current-students-still-are-not)).

**Nationality must never gate visibility.** An LLM classifying a scraped sentence into
"you are legally ineligible because of your citizenship" is the highest-harm error the
system can make: nationality-based exclusion, computed unreliably, silently removing
options the user would have pursued. Eligibility notes annotate; they never filter
([D-023](DECISIONS.md#d-023--nationality-and-export-control-are-never-a-hard-filter)).

**Scale is the ethical constraint, not automation.** Banning automated sending is
necessary but not sufficient — 200 ranked professors with per-person talking points is an
industrial cold-email generator regardless of who clicks send, and mass templated outreach
is precisely what makes faculty stop reading cold mail, harming every future applicant.
Outreach briefs are therefore generated one professor at a time, on explicit request, with
no bulk path ([D-032](DECISIONS.md#d-032--scale-is-an-ethical-constraint-not-just-a-performance-one)).

**A community overlay may share structure, never people.** Curation is a first-class feature
([D-008](DECISIONS.md#d-008--curation-is-a-first-class-feature-not-a-fallback)) — a hand-maintained
overlay outperforms pure automation because the decisive facts aren't in any API. But that
overlay is **local to each user**: it holds their own corrections and annotations. What may be
contributed back to the public repo is **structural only** — DirectoryAdapters,
query-generation improvements, intake-calendar defaults, source lists. A *shared* overlay of
professors' recruiting status would be exactly the unconsented personal-data aggregation the
no-commit rule forbids, and is out of scope
([D-054](DECISIONS.md#d-054--the-community-overlay-is-structural-and-local-never-shared-personal-data),
[D-005](DECISIONS.md#d-005--scan-output-is-never-committed)).

**Evidence verification proves fidelity, not truth.** Re-opening a stored snapshot to
confirm a quote proves only that the model did not invent text relative to what was
fetched. It says nothing about whether the page was accurate, current, or itself wrong —
the corpus contains a professor's own page asserting a leave period years out of date.
Provenance answers *where did this come from*, never *is this true*, and the UI must not
imply otherwise.

---

## 8. Review triggers

Revisit this document when any of the following changes: a source's licence or ToS; the
introduction of any outbound-communication feature (default answer: no); any new inferred
attribute about a person; publication of a hosted or shared instance rather than a
local-only tool.
