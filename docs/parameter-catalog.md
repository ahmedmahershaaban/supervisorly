# Parameter Catalogue

Every filter, sort, facet, search field and score input the dashboard should support —
merged from every comparison table, decision table and deep-dive in Ahmed's corpus.
93 parameters across 22 entities.

---

## Person (18)

| Parameter | Kind | Why it matters |
|---|---|---|
| professor name search | search | Direct lookup; must handle diacritics, nicknames and surname-first variants. |
| full-text search (areas, notes, quotes) | search | Proven in the existing dashboard as a concatenated haystack; needs field-scoped and relevance-ranked upgrade. |
| topic tag (normalized subfield) | facet | Primary research filter; must be a mapped taxonomy, not the 122 near-duplicate free-text tags of the old dashboard. |
| current direction (recency-weighted topic) | score-input | Ahmed ranks by what is funded NOW, not lifetime themes; distinct from lifetime tags. |
| rank / title normalized | filter | Assistant vs full vs emeritus predicts supervision intensity and availability. |
| is_research_supervising | filter | Teaching-stream, adjunct, status-only and emeriti mostly cannot supervise; a default-on filter. |
| career stage / new lab | score-input | New labs are the best odds for a weak-credential applicant — an explicit corpus heuristic. |
| availability status | filter | Sabbatical, on-leave-at-industry, departing or departed — a hard eliminator independent of fit. |
| bandwidth risk | score-input | Concurrent industry exec or chair role reduces real supervision capacity. |
| has verified email | filter | Actionability: no contact path means no next action. |
| contact protocol | facet | form-only vs email-direct vs do-not-email decides the next action and prevents a harmful cold email. |
| admitting routes count | sort | One supervisor reachable through 3 departments = 3 shots; a real odds multiplier. |
| page freshness / last verified | sort | Everything else on a stale page is untrustworthy; must be sortable and visible. |
| data-quality flags present | filter | 'Hide records with critical flags' and 'show only clean records' are the two most useful hygiene toggles. |
| coverage depth | filter | Distinguishes 'no signal found' from 'never checked' — prevents ranking on uneven data. |
| prior-collaboration preference | score-input | 'More likely to admit students who have already worked with me' reframes the target from December to 12 months earlier. |
| professor can top up (grant capacity) | score-input | Base package is set by the university; the top-up is the part the professor controls. |
| timezone overlap with applicant | score-input | Explicitly used to argue remote-collaboration feasibility. |

## GraduateProgram (10)

| Parameter | Kind | Why it matters |
|---|---|---|
| direct-entry PhD from bachelor's | filter | The hardest eligibility gate for a bachelor's-only applicant; eliminates whole universities. |
| supervisor required before applying | filter | Splits schools into two completely different, different-lead-time strategies. |
| minimum grade (normalized + raw) | filter | Hard admissibility gate; must show the raw requirement plus a flagged normalization. |
| language test thresholds (overall + per band) | filter | The per-band minimum binds more often than the overall score and needs months of lead time. |
| standardized test policy | filter | Determines whether an extra test must be scheduled and paid for. |
| reference letters required (count + source rules) | filter | The letter-quality rule, not the count, is the real blocker for career-changers. |
| application fee + waiver | sort | Direct cash cost per application caps how many schools can be targeted. |
| intakes per year | filter | Fall-only means a full year lost on a miss; multi-intake is risk mitigation. |
| international restrictions | filter | Some programs do not consider international applicants at all. |
| program length / time to degree | sort | Direct-entry lengths differ by a full year between institutions. |

## Opportunity (8)

| Parameter | Kind | Why it matters |
|---|---|---|
| opportunity kind | facet | PhD opening vs pre-PhD project vs internship vs fellowship vs mentorship are different products. |
| enrolment required | filter | The decisive gate for a non-enrolled applicant; it eliminated an entire city's professors in the corpus. |
| remote allowed | filter | For an applicant with no visa, an in-person-only route is worthless regardless of prestige. |
| paid / stipend amount | sort | Determines how long an applicant can sustain the route. |
| time commitment / min duration | filter | Labs reject low-hour applicants outright; the user must filter to what they can actually offer. |
| application window state | filter | open / closed / not yet open / rolling — a missed window is unrecoverable for a year. |
| produces paper / rec letter | score-input | For a no-publication applicant, an artifact and a referee are the whole point of a pre-PhD route. |
| nationality / export-control eligibility | filter | A perfect-fit professor may be legally unable to take the applicant; a first-class hard filter. |

## FundingItem (7)

| Parameter | Kind | Why it matters |
|---|---|---|
| guaranteed funding amount (per year) | sort | The only quantitative comparison axis in the prior dashboard and its single chart. |
| funding guarantee duration | score-input | Amount x duration is the true package value; direct-entry often carries the longest guarantee. |
| net after tuition | sort | The only honest cross-university comparison; gross figures hide very different tuition charges. |
| funding covers international students | filter | 'Funding to each domestic thesis student' is a silent disqualifier for the target user. |
| funding application mode | facet | automatic vs apply vs nomination-only changes what the user must do and when. |
| external award interaction | score-input | Offset-vs-top-up decides whether winning a scholarship is worth money at all. |
| funding verification state | filter | Quoted-official vs third-party vs exists-but-unpublished must never look alike. |

## RecruitingSignal (6)

| Parameter | Kind | Why it matters |
|---|---|---|
| recruiting state | filter | The single highest-value gate: actively recruiting / closed this cycle / no signal / unreadable. |
| has verbatim recruiting quote | filter | Only 20 of 104 professors in the prior dashboard had one; it is the strongest possible evidence. |
| recruiting quote datedness | score-input | A dated 2027-cycle statement outweighs an evergreen 'always looking for students'. |
| target cycle match | filter | A 'closed' status usually refers to the previous intake; without cycle normalization every professor reads as not-recruiting. |
| levels sought | filter | PhD vs MSc vs postdoc vs intern vs RA — the user only cares about their own level. |
| changed since last check | filter | The re-verification delta (unchanged / NEW / CHANGED / disappeared) is what makes monitoring valuable. |

## Lab (6)

| Parameter | Kind | Why it matters |
|---|---|---|
| lab size / roster headcount | sort | Attention-per-student proxy and evidence the lab is funded and growing. |
| new students joined recently | score-input | The strongest indirect proof a lab is actually taking people when no statement exists. |
| roster currency | filter | Current vs stale vs absent roster is a per-lab data-quality flag for the students feature. |
| lab news recency | sort | Substitute evidence of activity when no recruiting signal exists. |
| lab industry funders | facet | Signals stipend security and an industry pipeline; a headline requirement of the new tool. |
| has named alumni outcomes at all | filter | Only a minority of labs publish this; the filter separates evidenced from unknown. |

## Appointment (5)

| Parameter | Kind | Why it matters |
|---|---|---|
| company relationship type | filter | A professor employed at a company is a different signal from an alumnus landing there. |
| industry tie freshness | score-input | 'Left DeepMind ~June 2025' means fresh ties; a 2015 stint means little. |
| institute affiliation + tier | facet | Core member vs affiliate confers different funding, compute and scholarship access. |
| named chair / CRC tier | score-input | Proxy for funding security and seniority; also a gap-finder that surfaces professors the directory pass missed. |
| hospital / clinical affiliation | facet | Health-AI supervision often hangs off a hospital, not the university. |

## FitAssessment (5)

| Parameter | Kind | Why it matters |
|---|---|---|
| eligibility verdict | filter | Hard gates first: show only professors the user can actually apply to. |
| fit score | sort | The default ordering, computed and explainable rather than hand-typed. |
| confidence of score | sort | A professor scored on 3 of 12 inputs must not silently outrank one scored on 12. |
| portfolio bucket | facet | The output is a reach/realistic/fallback portfolio, not a single winner. |
| has an actionable next step | filter | Every record must end in a concrete action; those without one are research debt. |

## LabMember (4)

| Parameter | Kind | Why it matters |
|---|---|---|
| student level mix | facet | A lab with no PhD students is a different proposition from one with eight. |
| alumni placement destination (company) | facet | The best available proxy for 'companies the professor works with' and the clearest outcome measure. |
| placement type (academic vs industry) | score-input | Different users optimise for faculty jobs vs industry labs. |
| student holds external fellowship | score-input | Evidence the lab can actually fund international students. |

## BibliometricProfile (4)

| Parameter | Kind | Why it matters |
|---|---|---|
| citations / h-index / paper count | sort | Standard cross-institution ranking axis; must be shown per source, never blended. |
| metrics source | filter | OpenAlex vs Semantic Scholar vs manual Scholar paste differ by 5x on the same person. |
| papers in last 18 months | sort | Activity and currency proxy that is robust when h-index is unavailable. |
| junior first-authorship ratio | score-input | Detects the 'juniors stuck on mundane tasks in big collaborations' authorship risk. |

## Institution (3)

| Parameter | Kind | Why it matters |
|---|---|---|
| country | filter | Top-level run scope and the primary genericity axis. |
| institution | facet | Primary grouping and colour dimension; the old dashboard hardcoded 8 and must be generated dynamically. |
| user_priority_rank | score-input | The user supplies a ranking over universities; it must weight results, not just filter them. |

## Unit (3)

| Parameter | Kind | Why it matters |
|---|---|---|
| unit / department | facet | Deadlines, funding and admission rules are per-unit, not per-university. |
| campus | filter | Satellite campuses have different faculty and commute implications (St. George vs UTM vs UTSC). |
| institutional accepting-students flag | filter | Where a directory publishes it, it is department-verified and beats the personal page. |

## ContentItem (3)

| Parameter | Kind | Why it matters |
|---|---|---|
| mentorship / equity posture | score-input | Explicit outreach to under-resourced regions correlates strongly with accepting non-traditional applicants. |
| social bucket (A-E taxonomy) | facet | Recruiting / advice / values / research-now / mentorship — a proven, reusable classification. |
| open-source output (repo stars) | score-input | Some professors explicitly reward shipped code; it is also the applicant's strongest asset. |

## CollaboratorEdge (2)

| Parameter | Kind | Why it matters |
|---|---|---|
| co-author network size | sort | Lab connectivity and a route to adjacent/backup supervisors. |
| co-supervision partners | facet | Bus-factor safeguard and a source of alternate admission routes. |

## Claim (2)

| Parameter | Kind | Why it matters |
|---|---|---|
| claim confidence | filter | quoted-official / derived / inferred / unconfirmed / action-needed — per-field, not per-record. |
| last verified within N days | filter | The core freshness control; drives both display and the re-verification queue. |

## ApplicationCycle (1)

| Parameter | Kind | Why it matters |
|---|---|---|
| days until deadline | sort | Urgency ordering; the prior corpus had no parseable dates and so no countdown. |

## Organization (1)

| Parameter | Kind | Why it matters |
|---|---|---|
| company (any relationship) | facet | 'Show me professors connected to NVIDIA' across all edge types — employment, funding, placement. |

## Publication (1)

| Parameter | Kind | Why it matters |
|---|---|---|
| venue footprint | score-input | Lab throughput and prestige proxy used when citation metrics are blocked. |

## WebSource (1)

| Parameter | Kind | Why it matters |
|---|---|---|
| source tier | filter | Official / semi-reliable / community; the user must be able to demand official-only. |

## Conflict (1)

| Parameter | Kind | Why it matters |
|---|---|---|
| has unresolved conflict | filter | Surfaces records where the department page and the personal page disagree. |

## CoverageRecord (1)

| Parameter | Kind | Why it matters |
|---|---|---|
| blocked / unreadable sources | filter | Turns failures into a retryable work queue instead of silent absence. |

## ApplicantProfile (1)

| Parameter | Kind | Why it matters |
|---|---|---|
| score component weights | score-input | User-adjustable sliders; the prior dashboard's fatal flaw was that its stated blend was never implemented. |

