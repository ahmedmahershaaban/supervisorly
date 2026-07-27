# Domain Model

Generated from the corpus-discovery pass over Ahmed's existing research files, unified
and deduplicated across 14 clusters. `source_strategy` describes how a **generic**
(any-country) collector would obtain the field; `confidence` is an honest assessment of
whether that works in practice.

Confidence: **reliable** = obtainable at scale · **partial** = works in some countries or
disciplines · **hard** = possible but unreliable · **manual-only** = needs a human or a
curated overlay.

---

## Institution

The university/college a scrape run is scoped to. Root of the crawl and the unit the user ranks ('country + universities + my priority order').

**Relationships:** Institution 1-N Unit · Institution 1-N GraduateProgram · Institution 1-1 DirectoryAdapter · Institution N-N Organization (via Appointment: affiliated institutes, hospitals, networks)

| Field | Type | How a generic collector gets it | Confidence |
|---|---|---|---|
| `id` | slug | deterministic slug from canonical domain (utoronto.ca -> ca-utoronto), never from display name — names collide and are translated | reliable |
| `legal_name / display_name / local_name` | string x3 | national registry or ROR/Wikidata label; local_name kept verbatim for non-Latin scripts | reliable |
| `country / region / city` | string | ROR or Wikidata; country is the top-level run parameter | reliable |
| `canonical_domain + alt_domains[]` | string[] | ROR/Wikidata links field; alt domains matter because departments sit on separate hosts (lassonde.yorku.ca, web.cs.toronto.edu) | reliable |
| `ranking_hint / user_priority` | int | user-supplied per run; optionally seeded from a public ranking table | manual-only |
| `central_grad_body` | ref Unit | crawl for 'graduate studies'/'postgraduate' hub; policy that overrides department pages lives here (UofT SGS) | partial |
| `language(s)` | string[] | HTML lang attribute + language detection over sampled pages; decides whether translation is needed | reliable |
| `headline_counts` | object | scrape site-declared totals ('55 Faculty Members / 106 Faculty Affiliates') and use as a completeness checksum against what was harvested | partial |
| `cost_of_living_ref / tuition_page` | url | link discovery from the grad-studies hub | partial |

## Unit

Department / faculty / school / campus. The real scrape target: policy, deadlines and faculty directories are per-unit, not per-university.

**Relationships:** Unit N-1 Institution · Unit 1-N Person (primary appointment) · Unit 1-N GraduateProgram · Unit 1-1 DirectoryAdapter override

| Field | Type | How a generic collector gets it | Confidence |
|---|---|---|---|
| `id / slug` | slug | institution_id + normalized unit path | reliable |
| `name + type` | enum(department\|faculty\|school\|campus\|institute\|centre) | directory breadcrumb / site nav | reliable |
| `parent_institution / parent_unit` | ref | URL hierarchy + breadcrumb | reliable |
| `faculty_directory_url + pagination_pattern` | url | crawl for /people\|/faculty\|/staff\|/team + language variants; record page/N or ?page= pattern | reliable |
| `directory_richness` | enum(name_only\|name_title\|name_title_areas\|name_title_areas_email\|filterable) | classify the directory after first fetch; determines whether per-professor page visits are mandatory | reliable |
| `builtin_filters[]` | string[] | detect facet/checkbox controls; McMaster exposes an 'Accepting graduate students' checkbox (20 of 52) — a department-verified recruiting signal for free | partial |
| `admissions_email / phone / grad_director` | string | contact block on the grad page; grad director is often a professor record too | partial |
| `application_volume / acceptance_rate` | number | FAQ pages only ('approximately 4,000 applications', '5-10% receive an offer'); rarely published | hard |
| `appointment_class_vocabulary` | string[] | harvest the directory's own section headings (Research Stream / Teaching Stream / Emeriti / Cross-Appointed / Status-Only / Adjunct) — needed to exclude non-supervising faculty | partial |

## Person

The professor. Central record everything else hangs off. Also used (with role=student/alumnus) for lab members so identity resolution is shared.

**Relationships:** Person N-1 Unit (primary) · Person 1-N Appointment (all affiliations, chairs, industry roles) · Person 1-N Lab · Person 1-N RecruitingSignal · Person 1-N Opportunity · Person 1-1 BibliometricProfile · Person N-N Person (CollaboratorEdge, co-supervision edges) · Person 1-N LabMember · Person N-N GraduateProgram (admitting routes) · Person 1-N Claim (every field is claim-backed)

| Field | Type | How a generic collector gets it | Confidence |
|---|---|---|---|
| `id` | uuid + stable slug | mint internally; NEVER key on name (corpus hit real collisions: Bo Wang vs Boyu Wang; cs.toronto.edu/~anna resolving to an unrelated student) | reliable |
| `name_full / given / family / display_variants[]` | string[] | directory + own page; store variants for diacritics (Juan Felipe Carrasquilla Álvarez), nicknames (Konstantinos (Kosta) Derpanis) and surname-first directories | reliable |
| `name_native_script` | string | local-language page version; required for non-Latin countries | partial |
| `external_ids{orcid, scholar_id, dblp, semantic_scholar, openalex, ror_affil, wikidata}` | object | ORCID public API by name+affiliation, OpenAlex author search, DBLP author lookup; Scholar id only if self-linked (never guessed) | partial |
| `rank_title_raw + rank_normalized` | string + enum(full\|associate\|assistant\|lecturer\|teaching\|emeritus\|adjunct\|status_only\|research_scientist) | directory title string; normalization needs a per-country map (Maître de conférences, Privatdozent, Reader, Docent) | partial |
| `is_research_supervising` | bool | derived: teaching-stream/emeritus/adjunct/status-only usually cannot supervise theses; corpus rule 'treat Teaching Stream as LOW priority', emeriti pages state 'not accepting any new graduate students' | partial |
| `homepage_url / cv_url / lab_url / joining_url` | url | link discovery from the professor's own directory page only — never URL-guessed (guessing produced 404s and a wrong-person page in the corpus) | reliable |
| `email + obfuscation_form` | string | parse mailto:, then de-obfuscate 'fidler at cs dot toronto dot edu' / image-encoded addresses; store the raw form too | partial |
| `profile_links[]` | ref ProfileLink[] | only links the person publishes on their own pages; see ProfileLink | reliable |
| `research_areas_declared[]` | string[] | verbatim from the person's own page ('own words') | reliable |
| `research_areas_department[]` | string[] | directory tags where the directory publishes them; kept SEPARATE from own words because they diverge sharply | partial |
| `topic_tags_normalized[]` | string[] | LLM classification of the two above into a controlled taxonomy; must be a mapped vocabulary, not free text (the old dashboard has 122 near-duplicate tags) | partial |
| `current_directions[]` | string[] | recency-weighted: titles of publications/preprints/posts from the last 18 months, not lifetime themes | partial |
| `career_stage + first_appointment_year` | enum + int | derive from rank + earliest 'joined' news item or first-authored paper; new labs are the highest-yield targets for weak-credential applicants | partial |
| `academic_pedigree{phd_institution, phd_advisor, prior_positions[]}` | object | bio prose + CV PDF parse; advisor extraction is LLM-from-prose | hard |
| `awards[]` | string[] | bio/news sections; unbounded free text, normalize only the big named ones | partial |
| `availability_status` | enum(active\|sabbatical\|on_leave\|departing\|departed\|emeritus\|deceased) | regex + LLM over own page, department news, and destination-institution directory; corpus caught 'moving to NYU in September 2026' and 'ON LEAVE at OpenAI' | hard |
| `bandwidth_risk_note` | string | derived from concurrent Appointments (industry exec, department chair) — 'VP at NVIDIA may limit bandwidth' | partial |
| `contact_protocol` | enum(form_only\|apply_to_dept_name_in_sop\|email_direct\|do_not_email\|watch_and_external_funding\|unknown) + verbatim quote | extract from joining/openings/contact page; store the sentence, not just the enum | partial |
| `intake_quota_per_year` | string | rare explicit statements ('I usually take about 1 graduate student per year', 'I will be taking 1-2 students every year') | hard |
| `admission_odds_statement` | text | verbatim candid FAQ text; extremely high value, extremely rare | hard |
| `admitting_units[]` | ref Unit[] | joining page ('I can admit students through CS, ECE, or Stats'); count-of-routes is a ranking input | partial |
| `page_last_updated / freshness_score` | date + 0-1 | footer date, latest news item, latest teaching year, latest publication year, HTTP Last-Modified, Wayback diff — take the max signal and decay | partial |
| `data_quality_flags[]` | enum[] | derived: STALE_PAGE, DEAD_DOMAIN, SQUATTED_DOMAIN, JS_ONLY, LOGIN_WALL, NAME_COLLISION_RISK, NO_RECRUITING_SIGNAL, CONTRADICTS_DEPARTMENT_PAGE | reliable |
| `coverage_depth` | enum(name_only\|directory\|profile\|deep_dive) | set by the pipeline; deep_dive requires lab site + recruiting-signal check + roster attempt | reliable |
| `meeting_cadence / feedback_style / workload_norms / lab_wellbeing` | text | NOT on the web. Obtainable only by asking current students; dashboard must render these as 'unknown — ask' with a suggested contact list | manual-only |

## ProfileLink

Identity resolution with an anti-hallucination guard: a link counts only if the person publishes it themselves.

**Relationships:** ProfileLink N-1 Person · ProfileLink 1-N WebSource

| Field | Type | How a generic collector gets it | Confidence |
|---|---|---|---|
| `platform` | enum(personal\|lab\|cv\|scholar\|orcid\|dblp\|semantic_scholar\|openalex\|github\|x\|bluesky\|linkedin\|mastodon\|youtube\|blog\|mailing_list\|other) | classify by host | reliable |
| `url` | url | href on the person's own page | reliable |
| `where_linked_from` | url + section | record the exact page and section ('website header "Research"') — this column IS the guard | reliable |
| `status` | enum(confirmed\|unconfirmed\|not_found\|dead\|hijacked) | confirmed = self-linked; unconfirmed = found elsewhere; not_found = searched and absent (negative cache so later runs don't re-chase) | reliable |
| `link_health{http_status, final_url, redirect_chain, content_hash}` | object | HEAD/GET check; flag off-domain redirects and parked/ad domains (wanglab.ai -> bulsis.net) | reliable |
| `platform_stats{followers, posts, stars, last_activity}` | object | public profile header where readable without login; snapshot with a date | hard |

## Appointment

Unified person<->organisation edge. Deduplicates cross-appointments, institute affiliate tiers, named chairs, hospital roles, industry jobs, sabbaticals and departures into ONE table.

**Relationships:** Appointment N-1 Person · Appointment N-1 Organization · Appointment N-1 Institution/Unit when academic

| Field | Type | How a generic collector gets it | Confidence |
|---|---|---|---|
| `person_id / org_id` | ref | link discovery + institute rosters + bio prose | reliable |
| `kind` | enum(primary_academic\|cross_appointment\|status_only\|adjunct\|institute_member\|institute_affiliate\|named_chair\|hospital\|industry_concurrent\|industry_past\|founder\|advisory\|visiting\|sabbatical_host) | LLM classification of the bio sentence + the roster the person appeared on | partial |
| `title_raw` | string | verbatim ('Canada CIFAR AI Chair', 'VP of AI Research, NVIDIA', 'CRC Tier II Computational Medicine') | reliable |
| `tier / program` | string | national chair registries where they exist (chairs-chaires.gc.ca, CIFAR); every country has an analogue (ERC, DFG, JSPS, ARC Laureate) | partial |
| `start / end / is_current` | date | news posts and bio prose; chairs expire and industry stints end ('From 2018-2024 took leave to serve as VP') | hard |
| `evidence_type` | enum(dedicated_profile\|named_in_news\|self_stated\|third_party) | record how the affiliation was confirmed; site-search with an explicit decision rule ('a dedicated result page = confirmed; "Nothing was found" = not an affiliate') | reliable |
| `confers{funding, compute, scholarships, network}` | object | institute's own pages; explains why an out-of-region professor can still be viable | partial |

## Organization

Any non-home-university org: company, AI institute, hospital, funder, network, student association. One table with a kind enum so 'companies they've worked with' is queryable.

**Relationships:** Organization 1-N Appointment · Organization 1-N FundingItem · Organization 1-N Placement (LabMember destination) · Organization 1-N Opportunity

| Field | Type | How a generic collector gets it | Confidence |
|---|---|---|---|
| `id / canonical_name / aliases[]` | string[] | normalize against Wikidata/Crunchbase-style alias list; aliases are essential for matching ('Google DeepMind' vs 'DeepMind') | partial |
| `kind` | enum(company\|ai_institute\|hospital\|funder\|network\|lab_consortium\|startup\|student_association\|venue) | classification | reliable |
| `country / hq / domain` | string | public registry | partial |
| `relation_roles_seen[]` | enum[](employs_professor\|funds_lab\|funds_student\|partner\|placement_destination\|founded_by\|benchmarked\|hosts_internship) | derived from the edges pointing at it; the same company appears in several roles | partial |
| `evidence_urls[]` | url[] | every edge carries its own source | reliable |

## Lab

The research group. Owns the roster, the joining page and the news feed — the three highest-value sub-pages in the whole domain.

**Relationships:** Lab N-N Person (PI) · Lab 1-N LabMember · Lab 1-N Opportunity · Lab 1-N RecruitingSignal · Lab N-N Organization (funders)

| Field | Type | How a generic collector gets it | Confidence |
|---|---|---|---|
| `id / name` | string | lab site title or 'X Lab' phrase on the professor page | partial |
| `url + subpage_map{people,joining,openings,news,publications,contact}` | object | crawl one hop from the lab root; observed paths are wildly varied (/joining.html, /joining/, /prospective.html, /join-us/, /openings/, /opportunities, /team/, /people, /group/, /members.html, /basic-content-page/open-positions) | reliable |
| `pi_ids[] / co_pi_ids[]` | ref Person[] | lab about page | reliable |
| `sub_teams[]` | string[] | e.g. Toronto / European / Global teams — determines whether a remote sub-team exists | hard |
| `headcount_by_level` | object | count the roster page; store per-level counts and the count date | partial |
| `funder_ids[]` | ref Organization[] | 'Funded by:' block on lab homepages (Intel, AMD, LG, Sony, NSERC, Mitacs) — present on a minority of labs but very high value | hard |
| `news_recency / roster_currency` | date + enum(current\|stale\|absent) | latest dated news item; roster staleness detected by internal inconsistency (2024-25 papers alongside a 2009-2015 roster) | partial |
| `open_positions[]` | ref Opportunity[] | openings page parse | partial |
| `compute_resources` | text | rarely stated; sometimes via institute affiliation | manual-only |

## LabMember

Roster members **a lab publishes on its own page** — current members and alumni-with-destinations. Display-only, never exported, no inferred per-person attributes ([D-024](DECISIONS.md#d-024--evaluative-judgements-about-individuals-stay-local-and-unexported)); this is what the lab itself chose to publish, not an aggregation.

> **Not the same as `former_doctoral_students`.** That is a *separate*, registry-sourced field, and it is **not universally available**: national thesis registries mostly lack advisor fields, so it is enabled **per registry, only where an advisor field is confirmed** — France (theses.fr) works, most do not, and Canada is unverified ([D-062](DECISIONS.md#d-062--former_doctoral_students-is-a-per-registry-advisor-verified-capability--not-a-universal-headline)). Where unavailable it is an honest null, never inferred. `recent_collaborators` ([D-016](DECISIONS.md#d-016--students-is-not-obtainable-ship-recent_collaborators-instead)) is the always-available proxy, always labelled as *not* students.

**Relationships:** LabMember N-1 Lab · LabMember N-1 Person (supervisor) · LabMember N-1 Organization (destination) · LabMember 0-1 Person (self, if resolvable)

| Field | Type | How a generic collector gets it | Confidence |
|---|---|---|---|
| `person_id (weak) / name` | ref\|string | roster page names only; resolve to a Person record opportunistically (many will never resolve) | partial |
| `level` | enum(postdoc\|phd\|msc\|masc\|research_assistant\|predoc\|intern\|undergrad\|visiting\|staff) | roster section headings; absent on some pages entirely (Colin Raffel's list gives names with no level or year) | partial |
| `status` | enum(current\|alumnus\|on_leave\|visiting) | roster section; on-leave flags appear inline ('on leave at 1X', 'on leave at Cursor') | partial |
| `topic` | string | parenthetical after the name on richer rosters | partial |
| `co_supervisor_ids[]` | ref Person[] | '(co-supervised by X)' text; builds the professor-to-professor graph and reveals alternate supervisors | partial |
| `start_year / end_year` | int | published by very few labs ('Anagh Malik (2022-)'); otherwise infer from first co-authored paper — mark as inferred | hard |
| `prior_institution` | string | published by ~1 lab in 6 ('prev KAIST MS, SNU BS'); otherwise unavailable | hard |
| `fellowship_held` | ref FundingItem | roster annotations ('Google PhD Fellowship', 'NSERC CGS', 'Connaught') | hard |
| `concurrent_industry_role` | ref Organization | roster annotation ('Google DeepMind researcher') | hard |
| `destination{org_id, role, is_academic}` | object | alumni section of the lab page; the ONLY reliable public source. LinkedIn is off-limits by the corpus's own rule and by ToS | hard |
| `placement_chain` | string | multi-hop outcomes where published ('postdoc Princeton -> faculty UWaterloo') | hard |
| `public_handles[]` | string[] | occasionally from the PI's own social posts naming and endorsing students | hard |
| `contactability` | enum(no_contact_info\|via_lab_page\|public_email) | observed; corpus found no student emails on any roster page | reliable |
| `nationality` | n/a | DO NOT COLLECT per-person. Only lab-level aggregates where the lab itself publishes them ('30+ nationalities') | manual-only |

## BibliometricProfile

Citation/productivity rollup per professor. Kept separate from Person because it comes from different sources with different reliability and refresh cadence.

**Relationships:** BibliometricProfile 1-1 Person · BibliometricProfile 1-N Publication

| Field | Type | How a generic collector gets it | Confidence |
|---|---|---|---|
| `source` | enum(openalex\|semantic_scholar\|dblp\|orcid\|scholar_manual) | OpenAlex first (open API, global coverage), Semantic Scholar second, DBLP for CS venues; Google Scholar last and only via manual paste. **Author disambiguation is weak for common non-Western names — split/merged profiles (D-030)** | partial |
| `paper_count / citation_count / h_index / i10` | int | OpenAlex author summary_stats; store one row PER source, never a blended number | partial |
| `recent_output{papers_last_18m, venues[], award_flags[]}` | object | OpenAlex works filtered by date; venue prestige needs a per-field venue list | partial |
| `distinct_coauthor_count` | int | count distinct co-authors from the works list; derived from a possibly-incomplete works list, so no higher than its input (monotonicity, D-047) | partial |
| `as_of` | date | stamp every metric; all bibliometrics are point-in-time | reliable |

> **Dropped per [D-024](DECISIONS.md#d-024--evaluative-judgements-about-individuals-stay-local-and-unexported):**
> `first_author_junior_ratio` is removed. Author order is meaningless in alphabetical-authorship
> fields (theoretical CS, cryptography, maths, much of economics), so the metric is frequently
> wrong, and it is an evaluative judgement about identifiable junior people. Do not reintroduce it.

## Publication

Individual paper. Needed for current-direction detection, co-author graph, and student first-authorship evidence.

**Relationships:** Publication N-N Person · Publication N-1 BibliometricProfile · Publication N-N LabMember (first-authorship evidence)

| Field | Type | How a generic collector gets it | Confidence |
|---|---|---|---|
| `doi / arxiv_id / openalex_id` | string | OpenAlex/Crossref/arXiv API | reliable |
| `title / year / venue / venue_type` | string | same | reliable |
| `authors[] (ordered) + author_position_of_person` | array | same; author order is recorded but **carries no evaluative signal** — it is meaningless in alphabetical-authorship fields (D-024) | reliable |
| `citation_count` | int | OpenAlex; note it lags Scholar | reliable |
| `award_or_status` | string | only from the professor's own page or social posts ('ICLR 2025 Spotlight', 'Best Paper') | hard |
| `code_repo` | url | abstract/landing-page link or paperswithcode-style mapping | partial |
| `topic_tags[]` | string[] | OpenAlex concepts + LLM re-tagging into the dashboard taxonomy | partial |

## CollaboratorEdge

Weighted professor-to-professor graph. Powers 'find adjacent/backup supervisors' and co-supervision discovery.

**Relationships:** CollaboratorEdge N-1 Person x2

| Field | Type | How a generic collector gets it | Confidence |
|---|---|---|---|
| `person_a / person_b` | ref | co-authorship from OpenAlex + co-supervision from lab rosters + co-organizer mentions | reliable |
| `edge_type` | enum(coauthor\|co_supervisor\|advisor_alumnus\|co_organizer\|same_institute) | by provenance of the edge | partial |
| `weight / first_year / last_year` | number/int | count and date co-authored works | reliable |
| `is_senior_peer` | bool | derived from relative career stage; prevents showing a mentor as a student | partial |

## RecruitingSignal

Is this professor taking students, right now, for MY cycle? The single highest-value field in the product and the one that decays fastest.

**Relationships:** RecruitingSignal N-1 Person · RecruitingSignal N-1 Lab · RecruitingSignal N-1 WebSource

| Field | Type | How a generic collector gets it | Confidence |
|---|---|---|---|
| `quote_verbatim` | text | exact sentence from the person's own page/openings page/social post — never paraphrased | reliable |
| `state` | enum(actively_recruiting\|open_annual\|closed_this_cycle\|not_recruiting\|no_signal_found\|unreadable_source) | LLM classification of the quote; 'no_signal_found' and 'unreadable_source' MUST be distinct from 'not_recruiting' | partial |
| `target_cycle` | string | parse the year from the quote; if absent mark evergreen. Corpus rule: an 'Applications Closed' page in July usually refers to the PREVIOUS intake — raw status must be normalized against the target cycle or every professor reads as not-recruiting | hard |
| `datedness` | enum(dated\|evergreen\|undated_stale) | presence of an explicit year/date next to the statement | reliable |
| `levels_sought[]` | enum[](phd\|masters\|postdoc\|intern\|ra\|undergrad\|visiting) | from the quote | partial |
| `source_url + observed_at + snapshot_id` | ref WebSource | mandatory | reliable |
| `change_tag` | enum(unchanged\|new\|changed\|disappeared) | diff against the previous snapshot's normalized quote; the corpus did this by hand on a 9-day cycle | reliable |
| `institutional_flag` | bool | some directories publish an 'Accepting graduate students' checkbox — a department-verified signal that beats the personal page | partial |
| `confidence_penalty` | float | derived: downweight by page staleness. A green signal on a 23-month-old page is not a green signal | reliable |

## Opportunity

Everything a professor/lab/program OFFERS that a person can actually apply to: openings, pre-PhD routes, internships, visiting positions, fellowships, mentorship schemes. Merges 'Program/Opening' and 'pre-PhD route'.

**Relationships:** Opportunity N-1 Person/Lab/Unit/Organization · Opportunity N-1 ApplicationCycle · Opportunity N-N FundingItem

| Field | Type | How a generic collector gets it | Confidence |
|---|---|---|---|
| `name / kind` | enum(phd_opening\|postdoc\|ra\|internship\|pre_phd_project\|visiting\|scholars_program\|mentorship\|hackathon\|open_science_community) | openings page + lab news + institute program pages | partial |
| `owner{person\|lab\|unit\|organization}` | ref | page ownership | reliable |
| `application_url / form_url` | url | link on the openings page; note that Google Form content is behind a sign-in wall and its eligibility text is often unreadable | partial |
| `enrolment_required` | bool\|unknown | often stated NOT on the professor page but one hop away on the institutional program page — the funnel must be followed to the terminal program | hard |
| `remote_allowed` | bool\|unknown | explicit statement, or inferred from a past remote member listed on the roster | hard |
| `paid / stipend_amount / currency` | bool + number | page text; frequently absent | partial |
| `time_commitment / min_duration` | string | page text ('full-time or at least 20 hours per week', '6 months-2 years') | partial |
| `window{opens, closes, rolling, review_cadence}` | object | page text; formats vary (rolling, 'reviewed weekly', a 3-week window, 'next cycle ~March 2027') | partial |
| `eligibility{degree_level, nationality_restrictions[], region_preferences[], publications_required}` | object | page text; export-control/nationality clauses are real and legally load-bearing | hard |
| `produces{paper, rec_letter}` | enum(yes\|likely\|possible\|no) | stated outcomes + alumni evidence; never a guarantee | hard |
| `required_materials[]` | string[] | page text (CV, transcript, research statement, references) | partial |
| `selectivity_stats` | string | self-published outcome stats where they exist | hard |
| `status` | enum(open\|closed\|not_yet_open\|unknown) | derived from window vs today, re-checked on the freshness cadence | partial |

## GraduateProgram

The degree you actually apply to, with its admission rules. Must be joined to professors by admitting-route edges — the corpus never had this join key and it broke the whole dataset.

**Relationships:** GraduateProgram N-1 Unit · GraduateProgram N-N Person (admitting routes) · GraduateProgram 1-N ApplicationCycle · GraduateProgram 1-N FundingItem (package)

| Field | Type | How a generic collector gets it | Confidence |
|---|---|---|---|
| `name / degree_level / variant` | enum(phd\|direct_entry_phd\|masters_thesis\|masters_course\|masc\|mphil) | program page | reliable |
| `unit_id / institution_id` | ref | URL hierarchy | reliable |
| `direct_entry_from_bachelors` | enum(yes\|via_masters_switch\|exceptional_only\|no) | program page text; the single hardest eligibility gate for a bachelor's-only applicant | partial |
| `supervisor_required_pre_application` | enum(required\|recommended\|not_required\|required_for_acceptance) | program/admissions FAQ; changes the entire application workflow | partial |
| `min_grade{scale, value, raw_text}` | object | admissions page; scales are incompatible across countries (A-, 3.33/4.33, 75%, B+, 2:1, ECTS) — store raw + a normalization attempt with a confidence | hard |
| `language_requirements[]` | array{test, overall, per_band, exemptions[]} | admissions page; per-band minimums bind more often than the overall score | partial |
| `standardized_test_policy` | enum(required\|optional\|recommended\|not_required) | admissions page | partial |
| `reference_letters{count, source_rules, format_rules}` | object | admissions page; rules like 'institutional email only, PDF only, program-specific' are common and disqualifying | partial |
| `sop_rules{length, structure, must_name_supervisor}` | object | admissions page; length varies 500 words to 2 pages and some programs mandate the first three lines | partial |
| `application_fee + waiver_policy` | money + text | admissions page | partial |
| `intakes[] / program_length / max_completion` | array/int | program page | partial |
| `international_restrictions` | text | admissions page; e.g. a program that does not consider international applicants at all | partial |
| `application_systems[]` | string[] | some programs require TWO submissions (central grad school + departmental system) plus a supplementary form within 48h | hard |
| `decision_window / offer_reply_rule` | string | FAQ; often unpublished ('specified in the individual offer letter') | hard |

## ApplicationCycle

Separates the timeless program from the time-boxed intake. Without this, every scraped 'Applications Closed' is misread.

**Relationships:** ApplicationCycle N-1 GraduateProgram · ApplicationCycle 1-N Opportunity

| Field | Type | How a generic collector gets it | Confidence |
|---|---|---|---|
| `program_id / cycle_label` | ref + string | page text ('Fall 2027') | reliable |
| `opens / deadline_domestic / deadline_international` | date | admissions page; domestic and international deadlines differ by up to 5 months and a single 'deadline' field silently causes a missed application | partial |
| `deadline_raw_text` | string | keep verbatim: real values are hedged ('Opens ~Oct 2026 (exact TBD)') | reliable |
| `state` | enum(open\|closed\|not_yet_published\|projected_from_prior_cycle) | derived from dates vs today; 'projected' when only the prior cycle is published — the corpus used a Wayback snapshot to establish the prior-cycle baseline | partial |
| `related_funding_deadlines[]` | ref FundingItem[] | scholarship pages; internal nomination deadlines often precede the application deadline | hard |
| `watch_url + recheck_after` | url + date | generated automatically for every not_yet_published cycle — this is the monitoring queue | reliable |

## FundingItem

One table for guaranteed packages, scholarships, fellowships, top-ups and research grants, distinguished by kind. Answers 'is this actually payable to me?'

**Relationships:** FundingItem N-1 GraduateProgram / Lab / Person / LabMember · FundingItem N-1 Organization (provider) · FundingItem N-1 ApplicationCycle

| Field | Type | How a generic collector gets it | Confidence |
|---|---|---|---|
| `kind` | enum(guaranteed_package\|entrance_award\|external_fellowship\|top_up\|ta_ra_component\|research_grant\|tuition_waiver) | classification of the source page | partial |
| `name / provider_org_id` | string + ref | funding page | reliable |
| `amount{value, currency, period, raw_text}` | object | funding page; store raw because real values are ranges and formulas ('$5,000/session (up to $15,000/yr)', '$40,792 base + up to $6,706') | partial |
| `gross_vs_net{payroll, fellowship, tuition_charged, net_to_student}` | object | only a few institutions publish this; it is the ONLY way to compare packages across universities honestly | hard |
| `duration_months / guarantee_condition` | int + text | funding page ('60 months for direct entry', 'conditional on satisfactory progress') | partial |
| `eligibility{level, citizenship, program_scope, field_scope, gpa_condition}` | object | funding page; highest error-rate field in the whole corpus — two published corrections came from getting this wrong | hard |
| `application_mode` | enum(automatic\|apply_via_program\|apply_to_funder\|nomination_only) | funding page; 'you don't apply, you're nominated' is a non-obvious and decisive distinction | partial |
| `interaction_rule` | enum(stacks\|offsets_package\|clawed_back\|unknown) + text | the fine print ('the amount of your departmental fellowship may be reduced in whole or in part' vs 'external award >$10,000 can enhance the package up to $60,000') | hard |
| `deadline / cycle` | date | funding page; frequently posted stale | partial |
| `holder{lab_id\|person_id\|member_id}` | ref | for grants and student-held fellowships; some directories publish per-professor grant history, which is a direct funding-security proxy | hard |
| `verification_state` | enum(quoted_official\|third_party\|unpublished_exists\|unverified) | explicit; some amounts are simply not published anywhere and must be marked 'exists but unpublished — ask the department' | reliable |

## ContentItem

Time-stamped public signal: social post, news item, blog post, repo. Where recruiting, deadlines, student endorsements and current directions actually get announced.

**Relationships:** ContentItem N-1 Person/Lab · ContentItem 1-N RecruitingSignal · ContentItem N-N LabMember (endorsements)

| Field | Type | How a generic collector gets it | Confidence |
|---|---|---|---|
| `platform / url / posted_at` | string/url/date | own site news feed and RSS first (no auth); X/Bluesky/Mastodon only if a lawful access path exists | partial |
| `text_verbatim + paraphrase` | text | quote exactly; mark paraphrase explicitly | reliable |
| `bucket` | enum(recruiting\|application_advice\|values_and_traits\|research_now\|mentorship_community\|award\|admin) | LLM classification using the corpus's proven A-E taxonomy | reliable |
| `derived_takeaway` | text | LLM, stored in a separate field from the quote ('=>' convention) so inference never contaminates evidence | reliable |
| `engagement{views, likes, stars}` | object | where visible without auth; used as a relevance weight, snapshot with a date | hard |
| `entities_mentioned{people[], orgs[], deadlines[], amounts[]}` | object | LLM extraction; this is how deadlines and student endorsements are harvested | partial |
| `repo_stats{stars, forks, last_commit}` | object | GitHub REST API (documented, rate-limited, ToS-clean) for kind=repo | reliable |

## WebSource

The evidence substrate. Every claim points here. Replaces career-scan's 'file:LINE' citation with something that survives a mutable, disappearing web.

**Relationships:** WebSource 1-N Claim · WebSource N-1 DirectoryAdapter

| Field | Type | How a generic collector gets it | Confidence |
|---|---|---|---|
| `url / final_url / http_status / content_type` | string/int | fetcher | reliable |
| `fetched_at / fetch_method` | date + enum(static_http\|headless_render\|api\|manual_paste\|archive) | recorded by the fetcher; manual_paste exists precisely for blocked sources | reliable |
| `content_hash / snapshot_ref` | string | hash the normalized extracted text; store the raw HTML/text snapshot so a citation can be re-validated after the page changes | reliable |
| `quote_offsets` | object | character offsets of the cited sentence inside the snapshot — the web analogue of :LINE | reliable |
| `source_tier` | enum(official_institutional\|official_personal\|indexed_api\|semi_reliable\|community_unverified) | classify by host and ownership; drives conflict resolution | reliable |
| `page_last_modified / declared_last_updated` | date | HTTP header + footer text + latest dated item on the page | partial |
| `robots_allowed / tos_note` | bool + text | robots.txt check before fetch; recorded per source | reliable |
| `failure_reason` | enum(none\|404\|403\|login_wall\|bot_block\|js_only\|timeout\|dead_domain\|hijacked_domain\|permission_denied) | fetcher; 'we failed to get it' must be distinguishable from 'it does not exist' so failures are retryable | reliable |
| `extraction_method` | string | record the selector/technique that worked, e.g. main-content innerText with the publications tail stripped, or 'clicked each accordion tab then re-extracted' | reliable |

## Claim

Field-level provenance and confidence. Turns 'cite URL + date on every fact' from prose into something filterable, sortable, joinable and mechanically validatable.

**Relationships:** Claim N-1 WebSource · Claim N-1 any entity/field · Claim N-1 Conflict

| Field | Type | How a generic collector gets it | Confidence |
|---|---|---|---|
| `subject{entity_type, entity_id, field_path}` | object | emitted by every extractor | reliable |
| `value + value_raw` | any + string | normalized value plus the untouched source string | reliable |
| `quote` | text | the exact sentence supporting the value | reliable |
| `source_id + offsets` | ref WebSource | mandatory; a claim without a resolvable source is dropped, not softened | reliable |
| `confidence` | enum(quoted_official\|derived\|inferred\|unconfirmed\|action_needed) | the corpus's own 🟢/🟡/⚠️ legend, promoted to an enum | reliable |
| `extractor{agent, model, prompt_version}` | object | recorded for reproducibility and for LLM-portability testing | reliable |
| `observed_at / superseded_by / status` | date/ref/enum(current\|superseded\|retracted) | append-only history; corrections supersede rather than overwrite (the corpus logged real retractions) | reliable |
| `validation{citation_resolves, quote_still_present, number_traceable}` | object | the web validator: re-fetch, check the quote is still in the snapshot/live page, check every number appears in an extractor output | reliable |
| `conflict_id` | ref Conflict | set when two claims disagree on the same subject | reliable |

## Conflict

Explicit record when sources disagree, with a deterministic resolution policy instead of silent last-write-wins.

**Relationships:** Conflict 1-N Claim

| Field | Type | How a generic collector gets it | Confidence |
|---|---|---|---|
| `subject{entity, field}` | object | detected when two current claims differ | reliable |
| `claims[]` | ref Claim[] | all competing claims retained | reliable |
| `resolution_rule_applied` | enum(higher_tier_wins\|more_recent_official_wins\|self_stated_wins_for_identity\|unresolved) | policy engine; official beats community, newer official beats older community, and where the official text is silent the field stays UNRESOLVED rather than picking a side | reliable |
| `verdict / verdict_text` | enum + text | LLM writes the reasoning, policy sets the winner; unresolved conflicts surface in the UI as a badge | partial |
| `needs_human` | bool | true when unresolved and decision-relevant | reliable |

## DirectoryAdapter

Per-institution scraping profile. THE genericity mechanism: the thing that makes a new country cheap instead of a rewrite.

**Relationships:** DirectoryAdapter 1-1 Institution · DirectoryAdapter 1-N WebSource

| Field | Type | How a generic collector gets it | Confidence |
|---|---|---|---|
| `institution_id / unit_id` | ref | one adapter per institution, optional per-unit overrides | reliable |
| `directory_urls[] + pagination` | url[] | discovered on first run, then cached and version-controlled | reliable |
| `rendering_mode` | enum(static\|js_render\|virtualized_scroll\|accordion\|tabbed\|api) | detected on first fetch; virtualized lists silently truncate and cost the corpus ~50 of 106 records | reliable |
| `api_endpoint` | url | probe for CMS APIs (WordPress /wp-json/wp/v2/..., Drupal JSON:API, Pure/Converis research portals); the corpus pulled a complete 106-row roster from one WP endpoint | partial |
| `profile_url_pattern / slug_convention` | string | learn from observed links only — NEVER guess. Corpus slugs were non-derivable ('mab' for mbrubake), case-inconsistent, and mixed numeric/name within one site | reliable |
| `extraction_selectors{name,title,email,areas,bio}` | object | learned per site, with an LLM fallback when selectors miss | partial |
| `content_selector_hint` | string | a cheap main-content selector to strip nav bloat (one corpus site had ~7,500 chars of menu before the bio) | reliable |
| `quirks[]` | string[] | recorded operationally: navigation-lag races, unstable element refs, filters that don't respond, permission-denied subtrees | reliable |
| `language / translation_needed` | string + bool | detected; drives a translate-then-extract step | reliable |
| `robots_policy / crawl_delay` | object | robots.txt per host | reliable |
| `completeness_checksum` | object | site-declared counts vs harvested counts; a scrape returning 97 when the site claims 106 is provably incomplete | partial |

## CoverageRecord

Honest completeness accounting per target. Makes 'no recruiting signal' distinguishable from 'never checked' and generates the work queue.

**Relationships:** CoverageRecord N-1 any target · CoverageRecord 1-N WebSource failures

| Field | Type | How a generic collector gets it | Confidence |
|---|---|---|---|
| `target{institution\|unit\|person}` | ref | pipeline | reliable |
| `depth_reached` | enum(name_only\|directory\|profile\|deep_dive) | pipeline | reliable |
| `expected_n / harvested_n / coverage_pct` | int/float | checksum vs harvest | reliable |
| `blocked_items[]` | array{url, failure_reason, retryable} | from WebSource failures | reliable |
| `missing_fields[]` | string[] | schema diff per record; drives the 'ask a human' queue | reliable |
| `last_full_run / next_due` | date | scheduler | reliable |
| `deliberate_exclusions[]` | array{target, reason} | explicit: 'excluded, no ML component found', 'not captured by design — 649 people'; a skipped target must never look like a failed one | reliable |

## ApplicantProfile

The user. Turns a generic professor list into a personalised ranking and enables hard eligibility elimination.

**Relationships:** ApplicantProfile 1-N FitAssessment · ApplicantProfile 1-N Institution (user ranking)

| Field | Type | How a generic collector gets it | Confidence |
|---|---|---|---|
| `country / citizenship / residence / timezone` | string | user input; citizenship drives export-control and scholarship eligibility, timezone drives remote-collaboration feasibility | manual-only |
| `highest_degree / has_masters / gpa{scale,value} / institution` | object | user input; grade-scale normalization to a target country is a per-country mapping with real uncertainty | manual-only |
| `publications_count / research_experience` | int/text | user input | manual-only |
| `skills[] / portfolio_links[]` | string[] | user input; can be seeded from a career-scan-style skills.json | manual-only |
| `language_test{test, overall, bands}` | object | user input; checked against per-program per-band minimums | manual-only |
| `target_level / target_cycle / earliest_start` | enum + date | user input; target_cycle is what recruiting signals are normalized against | manual-only |
| `constraints{remote_only, funding_required, relocation_ok, weekly_hours}` | object | user input; remote-only and funding-required are hard eliminators | manual-only |
| `priority_weights{recruiting, funding, fit, prestige, placement, accessibility}` | object | user-set sliders; makes ranking reproducible and adjustable instead of hand-typed | manual-only |

## FitAssessment

The computed, explainable ranking output. Replaces the hand-typed tier and the hardcoded shortlist.

**Relationships:** FitAssessment N-1 Person · FitAssessment N-1 ApplicantProfile · FitAssessment 1-N Claim

| Field | Type | How a generic collector gets it | Confidence |
|---|---|---|---|
| `person_id / applicant_id / computed_at` | ref/date | scoring engine | reliable |
| `eligibility_verdict` | enum(eligible\|blocked\|unknown) + blockers[] | hard gates evaluated first — **but the gate set depends on `SearchPlan.intent_kind`** (D-059): pre_phd/RA/mentor gate on availability + remote-OK only; phd/master gate on degree route, language bands, enrolment requirement, funding; postdoc gates on PhD-in-hand + funding. Nationality/export-control and grade/language normalisations only annotate, never block (D-023). Gate only on gate-eligible claims (D-047) | partial |
| `score_components{recruiting, funding, route_accessibility, topic_match, placement, mentorship_posture, bandwidth, freshness_penalty}` | object | each component computed from claim-backed fields, each with its own confidence; components are shown, not just the total | partial |
| `score_total / tier` | float + enum | weighted sum using ApplicantProfile weights; tier is derived from score bands, never hand-typed | reliable |
| `evidence_refs[]` | ref Claim[] | every component cites the claims that produced it — no unexplained ranking | reliable |
| `confidence_of_score` | float | penalised by missing fields and stale sources; a professor scored on 3 of 12 inputs must not outrank one scored on 12 | reliable |
| `next_action` | text | generated from contact_protocol + open Opportunity + cycle state; the corpus made this a mandatory field on every record | partial |
| `portfolio_bucket` | enum(reach\|realistic\|fallback) | derived from eligibility margin and selectivity | partial |

---

# Pipeline-state and user-action entities

Added 2026-07-23 to close audit gap B2. The 24 entities above model the **world**; these model
the **run** and the **student's own actions**. They were referenced in prose by D-029, D-031,
D-043 and D-045 but had no field tables, so the SQLite schema for the state machine could not
be written. `Confidence` is not meaningful for these (they are internal state, not harvested
facts), so the column is omitted.

`Job` (last in this section) was added 2026-07-27 with the hosted web tier
([D-069](DECISIONS.md#d-069--the-hosted-web-product-honesty-privacy-and-user-control)). It is
the only entity here that does not exist on the CLI surface, and it is stored in Firestore
rather than SQLite — the scan's own state still lives in the run database exactly as before.

## SearchPlan

The interpreted intent that drives a search — produced by the orchestrator inline
([D-045](DECISIONS.md#d-045--intent-interpretation-and-query-generation-are-orchestrator-inline-producing-a-searchplan)),
consumed by every downstream tool. Nothing expensive runs until `confirmed_by_user`.

| Field | Type | Notes |
|---|---|---|
| `plan_id` | pk | |
| `applicant_id` | ref ApplicantProfile | |
| `countries[]` | text[] | |
| `field / subfield` | text | |
| `intent_kind` | enum(training\|pre_master\|pre_phd\|mentor\|master\|phd\|postdoc) | changes where the agent looks and what counts as a hit |
| `resolved_topic_terms[]` | text[] | **generated** per field (D-038), not looked up |
| `resolved_topic_ids[]` | text[] | OpenAlex topic/concept IDs the orchestrator resolves the subfield to, so `topic_match` is deterministic ID-overlap not string match (D-058) |
| `intent_kind` | enum | drives which hard gates apply at scoring (D-059) — already listed above; the scorer must read it |
| `resolved_venues[]` | text[] | generated: the venues that signal the subfield |
| `target_opportunity_kinds[]` | text[] | |
| `target_source_types[] / excluded_source_types[]` | text[] | |
| `hit_criteria` | text | what counts as a match for this intent |
| `languages[]` | text[] | for original-language extraction (D-044/D-050) |
| `university_mode` | enum(all\|prioritise\|only) | D-040 |
| `universities[]` | text[] | |
| `confirmed_by_user` | bool | expensive work gated on this |
| `created_at` | datetime | |

## Run

One invocation of the pipeline. Resumability comes from `SELECT` on this, not from an agent's memory.

| Field | Type | Notes |
|---|---|---|
| `run_id` | pk | |
| `plan_id` | ref SearchPlan | |
| `status` | enum(planning\|enumerating\|signalling\|deep_diving\|gap_filling\|**awaiting_human_input**\|scoring\|finalized\|**finalized_with_open_gaps**\|failed) | D-043 pause state; D-049 terminal states |
| `budget_tokens / budget_spent` | int | the run's cost ceiling (cost-and-performance.md) |
| `started_at / updated_at / finalized_at` | datetime | |
| `counts{enumerated, shortlisted, deep_dived, gaps_open}` | object | drives the coverage report |

## Task

The unit of resumable work — one `(target × stage)`. A crashed run resumes by re-querying incomplete tasks.

| Field | Type | Notes |
|---|---|---|
| `task_id` | pk | |
| `run_id` | ref Run | |
| `target_ref` | ref (Person\|Unit\|Institution) | what this task is about |
| `stage` | enum(enumerate\|signal\|deep_dive\|gap_fill\|roster_enumerate) | `roster_enumerate` = human-rung directory unlock (D-052) |
| `phase` | enum(structured\|browse\|human) | which fetch phase reached (D-039) |
| `status` | enum(pending\|running\|done\|blocked\|awaiting_human\|abandoned) | |
| `attempts` | int | |
| `last_error` | text | 404 / bot-wall / login-wall / timeout |
| `updated_at` | datetime | |

## Checkpoint

A durable marker so a long or paused run resumes at a boundary, not from the top.

| Field | Type | Notes |
|---|---|---|
| `checkpoint_id` | pk | |
| `run_id` | ref Run | |
| `stage` | enum | last completed stage |
| `cursor` | text | opaque resume position (e.g. institution index, pagination token) |
| `created_at` | datetime | |

## ExtractionCache

The dominant cost lever ([cost-and-performance.md §3b-i](cost-and-performance.md)): if the page
and the prompt are unchanged, the extraction is not re-run.

| Field | Type | Notes |
|---|---|---|
| `cache_id` | pk | |
| `snapshot_content_hash` | text | part of the 4-tuple key |
| `prompt_version` | text | " |
| `model_id` | text | " |
| `schema_version` | text | " |
| `result_ref` | ref Claim[] | the claims this extraction produced |
| `created_at` | datetime | |

Unique key = `(snapshot_content_hash, prompt_version, model_id, schema_version)`. Changing any
one re-extracts; a field→extractor map means a prompt change invalidates only affected claims (D-029).

## Outreach

The student's own contact tracking — the daily loop the world-model never captured (D-031). User-owned, never harvested, never exported.

| Field | Type | Notes |
|---|---|---|
| `outreach_id` | pk | |
| `applicant_id` | ref ApplicantProfile | |
| `person_id` | ref Person | |
| `status` | enum(not_contacted\|drafted\|sent\|follow_up_due\|replied\|declined) | |
| `sent_at / follow_up_at / replied_at` | datetime | |
| `thread_notes` | text | user's own notes |
| `record_state` | enum(active\|pinned\|dismissed\|snoozed) | + `dismiss_reason`, `snooze_until` — so a country-scale list shrinks monotonically (D-031) |

## Application

Keyed to a program, because the student buys *applications*, not professors (D-031). Two professors in one department cost one fee.

| Field | Type | Notes |
|---|---|---|
| `application_id` | pk | |
| `applicant_id` | ref ApplicantProfile | |
| `program_id` | ref GraduateProgram | |
| `materials_checklist` | object | SOP, CV, transcripts, test scores — done/not |
| `fee_paid` | bool | |
| `portal_url` | url | |
| `reference_state[]` | array | per-letter: requested / received / submitted |
| `deadline / status` | date + enum(planned\|in_progress\|submitted\|decision) | |

## Job

One hosted scan, from *Start scan* to a downloadable dashboard
([D-069](DECISIONS.md#d-069--the-hosted-web-product-honesty-privacy-and-user-control)). Exists
only on the web surface — the CLI runs the same pipeline in the foreground and needs no Job. It
wraps a `Run`; it does not replace one.

The **`job_id` is the access token**: a random 128-bit id, readable only by whoever holds it,
never listable. The document therefore carries personal data (`email`, the plan) and is deleted
seven days after its last write.

| Field | Type | Notes |
|---|---|---|
| `job_id` | pk (uuid4 hex) | unguessable *by design* — it is the bearer credential (D-069) |
| `job_key` | string | idempotency key over (email, plan): a double-click or refresh returns the EXISTING job, never a duplicate |
| `status` | enum(queued\|running\|cancelling\|done\|failed\|cancelled) | `cancelling` is transitional; the three terminal states are all **resumable** |
| `plan` | object | the confirmed SearchPlan the student assembled in the wizard |
| `email` / `email_ci` | string | polite-pool contact + case-folded form enforcing one active job per person |
| `cancel_requested` | bool | cooperative stop — the engine checks it between units of work, so a cancel keeps everything already gathered |
| `progress[]` | array | phase events (`ts`, `phase`, `data`) driving the live narration; capped to the most recent entries so the doc stays small |
| `heartbeat_at` | datetime | stall watchdog: a stale heartbeat flips the job to `failed` with *"safe to resume"* rather than leaving it spinning |
| `result` | object | pointers to the exported dashboard (HTML/JSON), served via short-lived signed URLs — never a public object |
| `error` | text | honest, stack-free failure reason shown to the student |
| `created_at / updated_at` | datetime | `updated_at` also drives the 7-day TTL delete |

**Relationships:** `Job 1—1 Run` (a resume re-invokes the worker with the same `job_id`, and the
engine's checkpoints continue the existing Run rather than starting over).

> **Entity count:** 24 world-model + 8 pipeline/user (SearchPlan, Run, Task, Checkpoint,
> ExtractionCache, Outreach, Application, Job) = **32 entities**. Earlier docs saying "24" refer
> to the world-model subset only, and ones saying "31" predate the hosted web tier (D-069).

