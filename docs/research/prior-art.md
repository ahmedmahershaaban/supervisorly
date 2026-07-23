# ProfScout — Prior Art & Competitive Review

**Date of research:** 2026-07-22
**Method:** GitHub REST/Search API (unauthenticated, live star counts), web search, registry checks (npm, PyPI).
**Verification note:** every repo name, star count and `pushed_at` date below was read from the GitHub API on 2026-07-22. Items marked *unverified* were not confirmed directly.

---

## TL;DR — the uncomfortable headline

1. **The name `ProfScout` is already taken on GitHub by a project with almost exactly this idea.**
   `satyam-thakur/profscout` (★0, JavaScript, pushed **2026-07-19**, three days before this review): *"Open-source platform to discover 34,000+ professors, match research interests, compare PhD stipends, and automate outreach — built for international grad school applicants."* This is a direct name **and** concept collision. The name must change.
2. **The general idea is not novel and is currently being reinvented roughly once a month.** Between November 2025 and July 2026 at least **eight** independent open-source "find my PhD advisor with an LLM" projects appeared. None has traction (highest is 13 stars).
3. **Almost every one of them is a CSRankings wrapper.** That is the actual, defensible gap — see Section B.

---

## 1. Supervisor / advisor finding services (commercial & institutional)

| Tool | URL | What it does | Data source / open? | Coverage | Price | Maintained | Key weakness for an applicant |
|---|---|---|---|---|---|---|---|
| **FindAPhD** | findaphd.com | Advertised PhD projects & studentships; also a dedicated **Supervisor Search** letting you search individual supervisors by research interest | Proprietary; **advertiser-paid listings**. Not open | UK/Europe-heavy, all disciplines | Free to students | Yes | Only shows supervisors/projects at institutions that **paid to advertise**. Silence ≠ not recruiting. No metrics, no lab size, no funding signal |
| **PhDPortal / Mastersportal** | phdportal.com, mastersportal.com | Compare ~15,000+ PhD programmes worldwide | Proprietary, university-submitted | Global, all disciplines | Free (universities pay) | Yes | **Programme-level, not person-level.** Tells you a department exists; never tells you which professor to email |
| **ProFellow** | profellow.com | Fellowship + fully-funded programme directory, plus paid advising/course | Curated editorial DB | Global, all disciplines | Free tier + **paid** course/advising | Yes | Funding-opportunity directory, not a faculty database. Advice content, not data |
| **EURAXESS** | euraxess.ec.europa.eu | EU-official research job/vacancy portal, 25,000+ active positions incl. doctoral | Employer-posted, free to post; open portal | 40 European countries, all disciplines | Free | Yes (EC-funded) | Vacancy-driven. A professor who would take you but hasn't posted a vacancy is invisible |
| **Nature Careers** | nature.com/naturecareers | Academic job board incl. PhD positions | Employer-posted (paid ads) | Global, sciences | Free to browse | Yes | Same vacancy-only blind spot; skewed to well-funded labs |
| **AcademicPositions** | academicpositions.com | ~20,000 academic roles | Employer-posted | Europe-heavy | Free to browse | Yes | Same as above |
| **jobRxiv** | jobrxiv.org | Free/low-cost life-science academic job board | Employer-posted | Global, life sciences | Free/cheap | Yes | Narrow discipline; vacancy-only |
| **University "Find a Supervisor" tools** | e.g. UNSW, UTS, Macquarie, Murdoch, Western Sydney, UBC, Canberra | Institution-hosted keyword search over their own academics; some (UBC, Canberra) explicitly flag **who is accepting HDR students** | Institutional CRIS/profile system, open to browse, no API | **One university each** | Free | Yes | **The fragmentation problem.** Every university has its own; there is no cross-institution search. Comparing 20 universities means 20 different search UIs. This is the single strongest justification for a tool like ProfScout |
| **ProspectiveProfessors / GradTrail / ThinkSwap-like** | — | — | — | — | — | — | *Unverified.* Web search returned no substantive evidence these operate as supervisor-finding platforms. Do **not** cite them as competitors without confirming |

---

## 2. Ranking / faculty-index sites

| Tool | URL / repo | How it works | Open data? | Coverage | Price | Maintained | Weakness |
|---|---|---|---|---|---|---|---|
| **CSRankings** | csrankings.org — `emeryberger/CSrankings` **★3,157**, 3,898 forks, pushed **2026-07-22** (today) | Metrics-only ranking: counts faculty publications in **highly selective conferences**. Publication data from **DBLP** (ODC-BY licensed; ~19 GiB download to run locally). The **faculty↔institution mapping is a set of hand-maintained CSV files** (`csrankings-[a-z].csv`), originally from Papoutsaki et al., since cleaned by hundreds of contributors | **Yes — fully open**, on GitHub, CSVs are the crown jewels | **Computer science only.** Global institution list, but depth/accuracy skews heavily US | Free | **Very actively** | (a) **CS only**; (b) **conference-only** — worthless for fields that publish in journals or books; (c) tenure-track only, so no lecturers/readers/research fellows; (d) the affiliation CSV is manually curated and lags reality — the maintainers themselves note "many universities make it insanely difficult to track down and identify their faculty"; (e) says nothing about recruiting, funding, or lab size |
| **Research.com** (was Guide2Research) | research.com | Ranks individual scientists & institutions by a D-index (discipline h-index) | Proprietary methodology; underlying pubs from third parties | Global, ~24 disciplines | Free to browse | Yes | Threshold-based — only lists already-famous senior people. A prospective student mostly needs *mid-career and junior* PIs who actually have slots |
| **AD Scientific Index** | adscientificindex.com | Ranks ~2.6M scientists across 24,799 institutions / 221 countries on h-index, i10, citations, split **career-total vs last-5-years** | Proprietary; derived largely from Google Scholar profiles | **Genuinely global and all-discipline** — its main virtue | Free tier + paid | Yes | Requires the scientist to **have a public Google Scholar profile**, so coverage is self-selected and uneven. Contested reputation — see ResearchGate threads asking whether it is "reliable or predatory". Pure bibliometrics; no recruiting/funding/lab data |
| **Scilit** | scilit.com | Free bibliographic DB (MDPI-run) with author/institution search | Free, CrossRef/PubMed-derived | Global | Free | Yes | Publisher-owned; author disambiguation is weak |
| **QS / THE / ARWU (Shanghai)** | — | Institution-level reputation + bibliometric rankings | Proprietary, partly survey-based | Global | Free browse, paid data | Yes | **Institution-level only.** Zero use for choosing a person. Widely criticised methodologically |

---

## 3. Scholarly graph explorers — do they already do "researchers by topic + institution"?

| Tool | Researcher-by-topic+institution? | Data source | Open? | Price | Weakness for supervisor-hunting |
|---|---|---|---|---|---|
| **OpenAlex** (openalex.org + API) | **Yes, genuinely.** Filter authors by `last_known_institution` + `topic`/`concept`; ~474M works as of Feb 2026 | Own open graph (MAG successor, Crossref, PubMed, ROR) | **Fully open (CC0)** | Free. **Note: as of Feb 2026 an API key is required**, free key with $1/day credits | Bibliometric only. No email, no homepage-quality data, no "recruiting?" signal, no lab/student info, no programme info. The UI is a bibliographic browser, not an applicant tool. **This is ProfScout's best data backbone, not its competitor** |
| **Semantic Scholar** | Partially — author pages + API; institution filtering is weak | S2 corpus, 200M+ papers | Open API (key-gated) | Free | Author-institution linkage unreliable; no applicant framing |
| **Connected Papers** | No — paper-similarity graphs | S2/OpenAlex | Freemium (**paid** beyond a few graphs/mo) | Paid tier | Paper-centric, not person-centric |
| **ResearchRabbit** | Partially — surfaces "prolific authors" for a topic | OpenAlex + Semantic Scholar + PubMed | Free | Free | Discovery of *papers*; author view is a by-product. No institution-first workflow |
| **Litmaps** | No | S2/OpenAlex/Crossref | Freemium | Paid tier | Paper-centric |
| **Inciteful** (Paper Discovery) | Partially — surfaces prolific authors **and institutions** for a topic network | OpenAlex + Semantic Scholar + Crossref + OpenCitations | Free | Free | Still a literature tool; no faculty-directory grounding, no contactability |
| **Scite** | No — citation-context ("supporting/contrasting") | Own citation-statement DB | **Paid** | Paid | Irrelevant to supervisor choice |
| **Lens.org** | Somewhat — scholarly + patent, with institution facets | Aggregated | Free tier + paid | Freemium | Patent/IP oriented; clunky |
| **Dimensions** | **Yes, strongly** — researchers + institutions + **grants/funding**, which is closest to the "is this lab funded?" question | Digital Science proprietary | **Paid** (limited free web app) | Paid | Institutional subscription; a student typically has no access. Grant coverage is US/UK/EU-skewed |
| **VOSviewer** | No — visualisation of co-authorship/co-citation maps you supply | BYO data | Free, open | Free | Desktop analysis tool, not a discovery service |

**Conclusion for category 3:** the *raw capability* "find researchers by topic + institution" is fully solved and free via **OpenAlex**. What is unsolved is turning that into an **applicant-facing decision artifact**.

---

## 4. Open-source GitHub projects — THE most important category

All figures pulled live from the GitHub API on **2026-07-22**.

### 4a. Direct competitors — LLM-era "find my PhD advisor" tools

| Repo | ★ | Created → last push | Lang / licence | What it does | Verdict |
|---|---|---|---|---|---|
| **`satyam-thakur/profscout`** | **0** | pushed **2026-07-19** | JS | *"Open-source platform to discover 34,000+ professors, match research interests, compare PhD stipends, and automate outreach — built for international grad school applicants."* | ⚠️ **Direct name + concept collision.** Brand new, no traction, but the name is claimed |
| **`Joky02/AcademiaReach`** | **13** | 2026-03-26 → 2026-06-13 | TypeScript / MIT | Highest-starred of the cohort. LLM + Serper auto-discovers professors worldwide → deep-researches their papers → composes personalised cold emails → sends → **tracks replies**. FastAPI + React, bilingual EN/中文 | **Closest competitor #1.** But it is an *outreach/CRM* tool. Discovery is a thin Serper-search step, not a rigorous faculty inventory. No dashboard of the field |
| **`alex-yimingyang/csrankings-faculty-finder`** | **8** | created & pushed **2026-05-31** (single-day repo) | Python / MIT | Pulls CSRankings faculty → filter by research area → **custom keyword search with synonym expansion** (`ai4sci` → `AI for science`, `LLM` → `foundation model`) → **auto-detects PhD recruiting** by scanning homepages for "looking for PhD students" / "招博士" → country filter → **Excel export** | **Closest competitor #2.** Proves the "is this professor recruiting?" signal is *already implemented*. CS-only, CLI-only, Chinese-language, one-day project |
| **`NixoN2/phd-scout`** | **0** | created & pushed **2026-03-04** (single-day repo) | Python / MIT | *"Find and research PhD advisor candidates."* Local web app: CSRankings faculty → enrich via **DBLP + OpenAlex + arXiv** → **Claude Haiku** synthesises profile + **checks for PhD openings** → **embedding semantic search** over your stated interests → drag-and-drop ranked shortlist | **Closest competitor #3.** Architecturally this is ~70% of ProfScout's stated design, including the name stem "scout". Abandoned after one day |
| **`martinjingyu/ProfRadar`** | **1** | pushed 2026-06-11 | Python | Discovers + ranks professors from CSRankings by your interests, scrapes faculty homepages, LLM-summarises, generates cold-email tips | Also collides with a candidate name |
| **`kalalsland/SuperviScore`** | **4** | 2026-06-28 → **2026-07-14** | Python | One-click pipeline scoring potential PIs. Scrapes department faculty lists → DBLP-first paper retrieval (arXiv for abstracts) → LLM matches against **your CV** → outputs a list ranked by "likelihood of success" + drafts outreach letters. Chinese-market (直博/保研) | Actively maintained. Ranking/scoring focus, not dashboard |
| **`unknown-eps/AdvisorFinder`** | **0** | 2025-11-17 → 2025-12-05 | Python | RAG architecture: CSRankings CSV + OpenAlex → ChromaDB vector store → Streamlit UI → CV upload → **local LLM via Ollama** → recommendations + email drafts + Playwright scraper | **Important:** already does "run locally with your own LLM, free and private." That angle is **not** a novel gap |
| **`arjunk00/phd-finder`** | **3** | created & pushed 2026-06-16 | Python | **MCP server for Claude.** Mines **oral/spotlight papers** from NeurIPS/ICLR/ICML/CVPR/AAAI via **OpenReview API** → last author = likely PI → enrich with h-index/citations (OpenAlex → Semantic Scholar fallback) → CSV export. Explicitly splits *deterministic data work (server)* from *judgment (agent)* | **Important:** already does "Claude-first / agentic". That angle is **not** novel either. Clever venue-based PI discovery — worth borrowing |
| **`Usaid786467/Global-PhD-Scholarship-Finder-Application-Automator`** | **2** | created & pushed 2025-11-18 (single-day) | Python / MIT | Claims discovery across **50+ countries**, Gemini matching, "10,000+ emails/day" | Ambitious scope, one-day repo, mass-mailing framing is reputationally toxic. Not a serious competitor |
| **`LBruyne/find-relevant-csrankings-professors`** | **5** | 2024-04-04 | Python | CSRankings + Google Scholar keyword matching | Stale |
| **`KiteFlyKid/CustomizedCsrankingCrawler`** | **8** | 2021-01-06 | Python | Crawl CSRankings → professor homepages → emails → **mass mailing** | Stale, ethically questionable |
| **`HungryFlo/prof-finder`** | 2 | 2026-06-09 | Python | *"Your Ideal Professor Awaits."* | Minimal |
| **`tonydavis629/advisor_search`** | 0 | 2026-01-27 | Rust | PhD student–advisor matching service | Minimal |
| **`mani5100/claude-skills`** | 2 | 2026-01-11 | Python | Claude Code **skills** incl. "Professor Finder" + "Professor Email" | Confirms the Claude-Code-native niche is already being probed |

### 4b. CSRankings ecosystem (data layer everyone reuses)

| Repo | ★ | Last push | Note |
|---|---|---|---|
| `emeryberger/CSrankings` | **3,157** (3,898 forks) | 2026-07-22 | The upstream. DBLP-derived, hand-curated affiliation CSVs |
| `mutiann/speech_rankings` | **35** | 2024-10-16 | "CSRankings-like index for speech researchers" — proof that *cloning CSRankings into a new field* is a recognised, valued move |
| `dynaroars/cspicks` | **3** | 2026-06-14 | Web app over CSRankings + DBLP + OpenAlex: professor search, publication-area breakdown, activity graph, homepage/Scholar/DBLP links, school area-rank trends. Companion to the *PhD Demystify* book |
| `YHQpkueecs/vis_csrankings` | 4 | 2020-01-10 | Stale visualisation |

### 4c. Faculty scrapers (all single-institution, all tiny)

| Repo | ★ | Last push | Scope |
|---|---|---|---|
| `WillaLee/facultyScraper` | 13 | 2024-11-22 | Go |
| `barc-iitkgp/faculty-scraper` | 12 | 2022-09-20 | QS Top 30 institutes (Ruby) |
| `jlumbroso/princeton-scraper-seas-faculty` | 9 | 2022-10-29 | Princeton SEAS → static JSON feeds |
| `jlumbroso/princeton-scraper-cos-people` | 7 | 2022-10-29 | Princeton CS |
| `pChitral/University-at-Buffalo-Faculty-Web-Scraper` | 6 | 2023-05-26 | U. Buffalo |
| `kishore-narendran/FacultyInformationScraper` | 6 | 2017-04-06 | VIT University |
| `mohamedshakir3/find-my-professor-scraper` | 1 | 2026-03-29 | **Faculty directories across Canada** — closest to a multi-institution non-US scraper |
| `bgulseren/Faculty_Crawler`, `kushalkrishnappa/husky-hunter`, `ThomasCaneday/facultyWebScraper`, `HeisenbergHK/UT-ECE-Faculty-Email-Scraper`, `Mark051116/Crawler-BeautifulSoup` | 0 each | 2020–2025 | One department each |

**Pattern:** there is **no** maintained, general, multi-country faculty-directory crawler. Every scraper is bespoke to one department. This is a genuine, unglamorous, high-effort gap.

### 4d. Curated professor databases (no code, high value)

| Project | ★ | Last push | Note |
|---|---|---|---|
| **`Rex-7/Prof-List-For-10043-Student`** | **60** — the **highest-starred applicant-facing** project found | 2025-11-26 | A **community-curated Google Sheet** of professors in **Hong Kong / Macau / Singapore**, aimed at Chinese students affected by Presidential Proclamation 10043. Covers HKUST, PolyU, HKU, CUHK, CityU, HKBU, U. Macau etc. Explicitly aims for **all** professors in covered departments, with a community-updated "notes" column carrying **recruiting quota and policy-friendliness** intel |

**This is the most important lesson in the whole review.** The most successful artifact in this space is *not* an AI agent — it is a **spreadsheet with a human-maintained "is this person actually taking students" column**, in a **non-US region**, serving a **specific underserved applicant population**. Automation lost to curation because the decisive facts are not in any API.

### 4e. Application trackers (open source)

| Repo | ★ | Last push | Note |
|---|---|---|---|
| `Joky02/AcademiaReach` | 13 | 2026-06-13 | Tracks outreach replies (see 4a) |
| `YuZh98/academic-application-tracker` | 2 | **2026-07-20** | Local Streamlit dashboard: "what do I do today?" across deadlines + recommendation letters |
| `RahulShastri003/application-tracker` | 1 | 2026-06-26 | **Local-first**, AGPL-3.0. Statuses, documents, reminders, profiles, "Discover" job-source search, bring-your-own-AI |
| `faithopia21/grados` (GradOS) | 1 | 2026-06-30 | React/TS per-school workspace: requirements, documents, deadlines, recommenders |
| `zxcgzx/phd-application-tracker`, `arvalletta03/Grad-App-Tracker` | ≤1 | 2025 | Personal projects |

---

## 5. What applicants actually use today

Verified from search results:

- **Spreadsheets** — overwhelmingly the default. Google Sheets / Excel with columns for professor, university, deadline, email sent, reply.
- **Notion templates** — a real cottage industry. Official Notion Marketplace "Graduate School Applications Tracker"; numerous **Gumroad** paid templates (e.g. `notiongradphd.gumroad.com`, `scholarsquare.gumroad.com`, `shesciencesblog.gumroad.com`, `guzzo.gumroad.com` academic job market tracker). Notably, users request **supervisor/professor contact tracking** as a missing feature in these templates.
- **The GradCafe** (thegradcafe.com) — **840,000+** submitted admission results. The de-facto community source for "did this program admit anyone this cycle, and when."
- **Google Scholar** — the manual method. ProFellow publishes a guide literally titled *"How to Find Your Ideal PhD Supervisor Using Google Scholar."*
- **Cold-email templates** — the universal final step.
- **Field-specific community sheets** — e.g. the OSF-hosted Clinical Psychology PhD wiki listing which mentors are accepting students.

**The workflow gap is clear:** applicants do *discovery* manually in Google Scholar + 20 different university sites, then hand-copy into a spreadsheet/Notion. Trackers assume you already have the list. Nothing produces the list well outside CS.

---

## 6. AI / LLM academic agents

| Tool | What it does | Targets supervisor-finding? | Price |
|---|---|---|---|
| **Elicit** | Systematic-review assistant; screens & extracts structured data from up to ~500 papers | **No** — paper-centric | Freemium, paid tiers |
| **Consensus** | Yes/no answers synthesised from study findings | **No** | Freemium |
| **Undermind** | Deep search agent; iterative/adaptive semantic + keyword + citation multi-hop search, models how an experienced researcher expands a search | **No** — but its recursive search pattern is a good architectural model | Freemium/paid |
| **STORM** (Stanford) | LLM writes Wikipedia-style articles from web research | No | Open source, free |
| **GPT-Researcher** & variants | Generic autonomous web-research agents | No | Open source |
| **PaperQA** | RAG QA over your own paper corpus | No | Open source |
| **Scite / SciSpace / Scinito** | Citation context, paper chat | No | Paid |

**Finding:** the mainstream AI-research-agent ecosystem is **entirely literature-oriented**. Not one of the well-funded tools targets *people discovery for applicants*. That job is being done exclusively by ★0–13 hobby repos (Section 4a). The demand is real; the supply is amateur and abandoned.

---

# ANSWERS

## A. Does ProfScout already exist?

**Yes — plainly, and more than once. Saying otherwise would be false.**

There are currently **at least eight** open-source projects that overlap ProfScout's description, all created between Nov 2025 and Jul 2026, plus one that has already **taken the exact name**.

**The three closest competitors:**

1. **`NixoN2/phd-scout`** (★0, MIT, single-day repo 2026-03-04) — *"Find and research PhD advisor candidates — browse CSRankings, AI-synthesized profiles, semantic search."* Local web app, CSRankings → DBLP + OpenAlex + arXiv enrichment → Claude synthesises profiles **and checks for PhD openings** → embedding semantic search → ranked shortlist. This is the same architecture and nearly the same name. It is abandoned and has zero traction, but it exists.
2. **`alex-yimingyang/csrankings-faculty-finder`** (★8, MIT, 2026-05-31) — CSRankings faculty, synonym-expanded topic search, **automatic recruiting-status detection** from homepages, country filter, Excel export. Proves the "is this professor recruiting?" signal is already built.
3. **`Joky02/AcademiaReach`** (★13, MIT, active to 2026-06-13) — the most-starred and most polished: worldwide LLM professor discovery, per-professor deep research, personalised cold emails, send + reply tracking, web UI, EN/中文.

Honourable mentions that pre-empt specific "novel" claims: **`unknown-eps/AdvisorFinder`** already runs on a **local Ollama LLM** (kills the "free & private local LLM" angle as a differentiator), and **`arjunk00/phd-finder`** is already an **MCP server for Claude** (kills "Claude-Code-first" as a differentiator). **`satyam-thakur/profscout`** claims 34,000+ professors and **PhD stipend comparison** — the one feature no one else has.

**The reassuring half of the verdict:** every one of these is a hobby project. Median star count ~2. Four of them were built and abandoned in a single day. None is maintained past a few weeks. Nobody has *won* this space — they have all bounced off it. The reason they bounce off is Section B.

## B. The genuine, defensible gap

Testing each candidate angle honestly:

| Angle | Verdict | Reasoning |
|---|---|---|
| **Non-CS coverage** | ✅ **REAL — the strongest gap** | Every single competitor above (`phd-scout`, `csrankings-faculty-finder`, `ProfRadar`, `AdvisorFinder`, `cspicks`, `LBruyne/…`, `KiteFlyKid/…`) bootstraps from **CSRankings**, which is **computer science only** and **conference-publication only**. An applicant in chemistry, materials science, economics, public health, civil engineering, linguistics or history has *nothing*. The existence of `mutiann/speech_rankings` (★35) purely to clone CSRankings into one adjacent subfield shows how valuable escaping that ceiling is |
| **Non-US coverage** | ✅ **REAL** | CSRankings' affiliation CSVs are deepest for US institutions. FindAPhD is UK/EU and advertiser-gated. Institutional "find a supervisor" tools are per-university silos. The ★60 `Prof-List-For-10043-Student` succeeded *precisely* by covering HK/Macau/Singapore — a region nothing else served. Germany, Netherlands, Nordics, Japan, Korea, Australia, Canada, Gulf states are all badly served for person-level discovery |
| **Country-first, user-ranked university selection** | ✅ **REAL (workflow gap)** | Every competitor starts from *topic* or *ranking*. Real applicants start from **"I can get a visa to X and I can afford Y"**, then pick institutions, then look for people. No tool models "pick a country → pick/rank universities → enumerate *all* relevant faculty." This is exactly what the Google-Sheet project did manually and why it won |
| **"Is this professor recruiting?"** | ⚠️ **PARTLY SERVED** | Already implemented in `csrankings-faculty-finder` (homepage keyword scan incl. Chinese) and `phd-scout` (LLM check), and UBC/Canberra expose it institutionally. **Do not claim it as novel.** The *defensible* version is doing it **rigorously and with provenance** — multi-signal (homepage + recent-student turnover + open funded positions + group-page changes + vacancy portals), with a confidence level and the quoted evidence and date, instead of a boolean from one regex |
| **Students & industry-links view** | ✅ **REAL — genuinely unserved** | Nothing found does this. Lab size / current PhD-student roster / where alumni landed / company affiliations & consulting / industry-funded chairs — no tool surfaces it, yet it is decisive (does this PI have 3 students or 30? do their students finish? do they place into industry?). Partially derivable from OpenAlex co-authorship + lab pages. High-effort, high-payoff |
| **Local LLM, free & private** | ❌ **ALREADY SERVED** | `AdvisorFinder` uses Ollama; `SuperviScore`, `phd-scout`, `AcademiaReach` are all bring-your-own-key and run locally. Fine as a *property*, worthless as a *pitch* |
| **Claude-Code-first / agentic** | ❌ **ALREADY SERVED** | `arjunk00/phd-finder` is an MCP server for Claude; `mani5100/claude-skills` ships a "Professor Finder" Claude skill. An implementation choice, not a differentiator |
| **Evidence / provenance rigour** | ✅ **REAL — and it is the actual moat** | This is why all eight competitors died. LLM-scraped faculty data is silently wrong, and a wrong "he's recruiting!" costs an applicant a wasted email and real hope. Nobody in this space does source URLs, retrieval timestamps, confidence scores, or "we could not determine this" as a first-class value. For a **PhD-application portfolio piece**, methodological rigour is also the single most legible signal of research capability |
| **Self-contained HTML dashboard artifact** | ✅ **REAL (modest)** | Competitors output CSV/Excel (`phd-finder`, `csrankings-faculty-finder`), a Streamlit app (`AdvisorFinder`), or a full client-server stack (`AcademiaReach`, needs FastAPI + React + Serper key). A **single portable HTML file** you can keep, diff, re-share and open in two years with no server is a real usability edge — and matches how applicants actually work (they keep the spreadsheet) |

### The one-sentence gap

> Everything that exists is either **CS-only** (CSRankings derivatives), **advertiser-gated** (FindAPhD), **single-university** (institutional tools), **paper-centric** (OpenAlex/Elicit/Undermind), or a **weekend project that was abandoned** — and none of them treats a professor's *recruiting status, funding, lab size, students and industry ties* as evidenced, sourced, timestamped facts.

**Recommended positioning priority:** (1) discipline-agnostic + country-first coverage, (2) evidence/provenance rigour, (3) the students-and-industry-links view. Deprioritise (or mention only in passing) local-LLM and Claude-native, which are already commodity.

## C. What ProfScout should deliberately NOT do

| Don't build | Why | Do this instead |
|---|---|---|
| **A bibliometric/citation engine** | OpenAlex is CC0, 474M works, free, with author+institution+topic filters. You cannot beat it | **Consume the OpenAlex API** as the publication/metrics backbone (note: free API key required since Feb 2026). Link out to OpenAlex, Semantic Scholar, DBLP, Google Scholar profiles |
| **A CS department ranking** | CSRankings owns this, ★3,157, actively maintained, open data | **Ingest CSRankings CSVs** where CS is in scope and cite it. Compete only *outside* CS |
| **Literature review / paper recommendation** | Elicit, Undermind, ResearchRabbit, Connected Papers, Inciteful all do this better and some are free | Link out. Offer at most "here are this PI's 5 most-cited and 5 most-recent papers" |
| **A vacancy/job board** | EURAXESS (25k+ EU positions, free), Nature Careers, jobRxiv, AcademicPositions, FindAPhD already aggregate posted positions | **Link to and optionally ingest** these as *one recruiting signal among several* — never try to replicate the board |
| **Automated mass cold-emailing** | `AcademiaReach`, `ProfRadar`, `SuperviScore` and the "10,000 emails/day" repo already do it — and it is **reputationally radioactive**. Professors publicly complain about LLM spam; associating with it will lose you the audience and undermine a PhD-application portfolio piece | Stop at **"here is the evidence, here is why they fit, here is their email."** Let the human write the email. Make refusing to bulk-send an explicit, stated principle |
| **An application/deadline tracker** | GradOS, `RahulShastri003/application-tracker`, `YuZh98/academic-application-tracker`, plus Notion/Gumroad templates and GradCafe. Crowded and boring | **Export cleanly** — CSV/JSON/Markdown that drops into Notion, Sheets or those trackers. Be the *front* of the funnel, not the whole funnel |
| **Admissions-chance prediction or "will I get in"** | Unverifiable, ethically dicey, destroys the credibility the provenance angle buys you | Present evidence; refuse to predict |
| **Your own faculty-affiliation ground truth for CS** | 3,898 forks of manual curation says you will lose | Contribute corrections upstream to CSRankings; own the *non-CS* mapping nobody has built |

## D. Positioning

**README paragraph:**

> Finding a PhD supervisor is still a manual job. If you work in computer science and want to study in the United States, you have CSRankings and a dozen weekend projects built on top of it. If you work in anything else, or want to study anywhere else, you are back to opening twenty different university "find a supervisor" pages, one at a time, and copying names into a spreadsheet. ProfScout is built for that second case. You choose a country and the universities you care about — or every university in that country — rank them by preference, and ProfScout's agents work through their public faculty directories, publication records and lab pages to build you a single self-contained HTML dashboard of the people you could actually work with. You can filter by research area, seniority, apparent funding, lab size, current students, industry ties, and the programmes they offer. Crucially, every claim in that dashboard carries its source URL, the date it was retrieved, and a confidence level — including an honest "could not determine," because a confidently wrong "this professor is recruiting" costs you a wasted application. ProfScout does not rank universities for you, does not predict your admission chances, and will not send emails on your behalf. It builds the evidence base; you make the decision.

**One-line GitHub description:**

> Pick a country and its universities, get a self-contained HTML dashboard of every professor you could apply to — with sources, dates and confidence on every claim. Any discipline, any country.

## E. Naming

### Verdict on "ProfScout": **collision — change it.**

| Check | Result |
|---|---|
| GitHub | ❌ **`satyam-thakur/profscout`** exists (★0, pushed 2026-07-19) — and is a **direct concept competitor** (professor discovery for international grad applicants). Also `NixoN2/phd-scout` uses the same "scout" stem for the same idea |
| npm | ✅ `profscout` free |
| PyPI | ✅ `profscout` free |
| Web | No commercial product named ProfScout found |

Registries are clear, but sharing a name *and a product category* with a live GitHub repo is the worst kind of collision: users searching for you will find them, and "ProfScout" becomes unusable for SEO and for a PhD-application portfolio narrative about originality. Also note `martinjingyu/ProfRadar` (★1) — "ProfRadar" is likewise burned.

### Five alternatives — all checked 2026-07-22 (npm, PyPI, GitHub name search)

| # | Name | npm | PyPI | GitHub `in:name` | Notes |
|---|---|---|---|---|---|
| **1** | **Supervisorly** | ✅ FREE | ✅ FREE | ✅ **0 repos** | **Top pick.** Completely unclaimed on all three. Names the exact job ("supervisor"), the `-ly` suffix reads as a tool, phonetically regular for non-native speakers, and — importantly — uses the **international/Commonwealth** word *supervisor* rather than the US *advisor*, which itself signals the non-US positioning |
| **2** | **AdvisorScope** | ✅ FREE | ✅ FREE | ✅ **0 repos** | **Second pick.** Two common English words, no ambiguous spelling. "Scope" carries the evidence/inspection connotation that matches the provenance angle. Slight downside: "advisor" is US-flavoured and has an "adviser" spelling variant |
| **3** | **ProfAtlas** | ✅ FREE | ✅ FREE | ✅ **0 repos** | **Third pick.** "Atlas" is near-universally recognisable and captures the country → universities → people mapping. Very short, easy to type and spell |
| **4** | **SupervisorAtlas** | ✅ FREE | ✅ FREE | ✅ **0 repos** | Maximally descriptive and totally unclaimed; only drawback is length |
| **5** | **LabMatchr** | ✅ FREE | ✅ FREE | ✅ **0 repos** | Unclaimed, and "lab" matches the lab-size/students/industry-links angle. Weaker for humanities/social sciences, and the dropped-`e` spelling is mildly hostile to non-native speakers — rank it last |

**Names checked and rejected for collisions:** `ProfScout` (satyam-thakur/profscout), `ProfRadar` (martinjingyu/ProfRadar ★1), `LabCompass` (yznpku/LabCompass **★212**), `ScholarScout` (neej4/ScholarScout ★36, 22 repos), `LabScope` (14 repos), `AdvisorLens` (3 repos incl. a live domain `advisorlens.com`), `ProfMap` (7 repos), `ProfSeek` (2 repos), `phd-scout` (NixoN2/phd-scout, direct competitor).

**Recommendation: `Supervisorly`** — zero collisions anywhere, and the word "supervisor" itself telegraphs the non-US-centric positioning that is the project's strongest genuine differentiator.

---

## Appendix — sources

- GitHub REST API v3 (`/search/repositories`, `/repos/{owner}/{repo}`, `/repos/{owner}/{repo}/readme`), queried unauthenticated 2026-07-22.
- npm registry `registry.npmjs.org/{name}`; PyPI `pypi.org/pypi/{name}/json`, queried 2026-07-22.
- [CSRankings — emeryberger/CSrankings](https://github.com/emeryberger/CSrankings) · [csrankings.org](https://csrankings.org)
- [FindAPhD](https://www.findaphd.com/) · [FindAPhD Supervisor Search](https://info.findauniversity.com/findaphd-supervisor-search)
- [PhDPortal](https://www.phdportal.com/) · [ProFellow](https://www.profellow.com/)
- [EURAXESS Jobs](https://euraxess.ec.europa.eu/jobs) · [Nature Careers — PhD positions, Europe](https://www.nature.com/naturecareers/jobs/phd-position/europe/)
- [AD Scientific Index methodology](https://www.adscientificindex.com/methodology/) · [Research.com (Wikipedia)](https://en.wikipedia.org/wiki/Research.com)
- [OpenAlex (Wikipedia)](https://en.wikipedia.org/wiki/OpenAlex) · [OpenAlex — TU Hamburg library overview, Feb 2026](https://www.tub.tuhh.de/en/2026/02/10/openalex-an-open-alternative-for-academic-research/)
- [OpenAlex vs Semantic Scholar vs PubMed — IntuitionLabs](https://intuitionlabs.ai/articles/openalex-semantic-scholar-pubmed-comparison)
- [Undermind review 2026](https://www.buildfastwithai.com/ai-tools/undermind) · [Elicit alternatives](https://www.atlasworkspace.ai/blog/elicit-alternatives)
- [The GradCafe results](https://fairfieldstartup.fairfield.edu/pro/grad-cafe-results) · [Notion Graduate School Applications Tracker](https://www.notion.com/templates/graduate-school-applications-tracker)
- Institutional supervisor tools: [UNSW](https://www.unsw.edu.au/research/hdr/find-a-supervisor), [UTS](https://www.uts.edu.au/research/graduate/future-research-students/how-to-find-a-research-supervisor), [Macquarie](https://www.mq.edu.au/research/phd-and-research-degrees/how-to-apply/find-a-supervisor), [Western Sydney](https://www.westernsydney.edu.au/future/study/how-to-apply/higher-degree-research-candidates/find-a-supervisor), [U. Canberra](https://www.canberra.edu.au/future-students/study-at-uc/research-students/finding-a-supervisor), [UBC](https://www.grad.ubc.ca/gradprospect/2023/11/top-tip)
