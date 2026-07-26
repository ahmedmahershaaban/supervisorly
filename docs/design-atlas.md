# Supervisorly — Design Atlas

One place that connects everything: the skill, its agents and tools, the two run modes, the
scan-setup flow from free text to a confirmed plan, the pipeline, the fetch ladder with its
browser tier and human-rung fallback, the data model, the claim/provenance lifecycle, the
rules, and how the 67 decisions cluster. Each map ends with the documents and decisions that
govern it.

**Colour key** — the diagrams use one consistent scheme:

| Colour | Means |
|---|---|
| **Indigo** | the tool fetches or does this automatically |
| **Violet** | the browser tier — your own session, driven by the agent |
| **Rose** | the human rung — the classic MD method (Claude for Chrome), now the fallback |
| **Grey** | skipped on purpose |
| **Amber** | a data store or artifact |
| **Green** | verified / reliable |
| **Teal** | a rule / enforcement gate |

---

## CONTEXT — the boundary of the tool

What Supervisorly is, and where the line runs between what the tool does, what the
agent-driven browser does in your session, and what still falls back to you.

```mermaid
%%{init:{'theme':'base','themeVariables':{'fontFamily':'ui-sans-serif,system-ui,sans-serif','fontSize':'14px','primaryColor':'#e6edfb','primaryBorderColor':'#3f5bc4','primaryTextColor':'#18203a','lineColor':'#95a0b5','secondaryColor':'#eef1f6','tertiaryColor':'#f6f8fb','clusterBkg':'#f6f8fb','clusterBorder':'#cbd3e2','edgeLabelBackground':'#ffffff'}}}%%
flowchart LR
  S["Student"]
  subgraph HOST["Agent host — Kimi Code · Claude Code"]
    SK["Supervisorly skill<br/>SKILL.md + agents + tools"]
  end
  S -->|"country · field · subfield<br/>need · universities"| SK

  subgraph TR["Tool fetches directly"]
    API["Structured sources<br/>OpenAlex · ROR · CRIS<br/>sitemaps · JSON-LD"]
    PUB["Professor's own pages<br/>homepage · openings · lab News"]
    SOC["Open-API social<br/>Bluesky · Mastodon · GitHub"]
  end

  subgraph BT["Browser tier — your session, agent-driven"]
    CHR["Chrome via chrome-devtools-mcp<br/>persistent profile · one-time login"]
    GATED["Walled — advertised profiles only<br/>X/Twitter · LinkedIn · Scholar"]
    CHR --> GATED
  end

  subgraph HR["Human rung — fallback"]
    CFC["Claude for Chrome<br/>classic MD prompt"]
  end

  SK --> API
  SK --> PUB
  SK --> SOC
  SK -->|"paced (D-065)"| CHR
  CHR -.->|"challenge → abort latch"| CFC
  CHR -.->|"staging text → ingest-page<br/>never read into context"| SK
  CFC -.->|"returns MD files"| SK

  subgraph OUT["Outputs — local, never committed"]
    DB["SQLite<br/>source of truth"]
    JSON["JSON export"]
    DASH["Dashboard<br/>one self-contained HTML"]
  end
  SK --> DB --> JSON --> DASH
  DASH <-->|"ask · edit UI"| SKQ["Your agent session"]

  classDef tool fill:#e6edfb,stroke:#3f5bc4,color:#16203c;
  classDef agentv fill:#efe7fa,stroke:#7c4fc4,color:#2a1544;
  classDef human fill:#fbe7ef,stroke:#bd4a66,color:#3a1120;
  classDef store fill:#fdf2e0,stroke:#c58a1a,color:#3a2b0e;
  class API,PUB,SOC tool
  class CHR,GATED agentv
  class CFC human
  class DB,JSON,DASH store
```

*The tool reads public pages and open APIs; it never defeats a login. Everything walled is
reached through your own logged-in session — agent-driven Chrome first, the classic MD rung
as the fallback. The recipe is host-portable: the browser is an MCP server, the seam is the
CLI.* — architecture.md · D-039 · D-042 · D-044 · D-064

---

## MODES — offline demo vs live

Two ways in. The demo proves the whole pipeline offline against a synthetic cassette; a live
scan needs only a contact email — ROR is keyless, an OpenAlex key just raises limits, and the
browser tier supplies your logged-in session for the walled pages.

```mermaid
%%{init:{'theme':'base','themeVariables':{'fontFamily':'ui-sans-serif,system-ui,sans-serif','fontSize':'14px','primaryColor':'#e6edfb','primaryBorderColor':'#3f5bc4','primaryTextColor':'#18203a','lineColor':'#95a0b5','secondaryColor':'#eef1f6','tertiaryColor':'#f6f8fb','clusterBkg':'#f6f8fb','clusterBorder':'#cbd3e2','edgeLabelBackground':'#ffffff'}}}%%
flowchart LR
  subgraph DEMO["Offline demo — scan --demo"]
    FIX["synthetic cassette fixture<br/>3 directory shapes · 3 countries"]
    NOKEY["no keys · no network<br/>corpus never read (D-035)"]
    NOKEY -.-> FIX
  end

  subgraph LIVE["Live — scan --country --field"]
    EMAIL["contact email required<br/>SUPERVISORLY_CONTACT_EMAIL"]
    ROR["ROR v2 — keyless"]
    OA["OpenAlex — free<br/>--openalex-key optional"]
    BT2["browser tier — your logged-in profile<br/>one-time login, then hands-off"]
  end

  SAME["the same deterministic pipeline<br/>SQLite → JSON → dashboard"]
  RE["--resume — warm cache<br/>+ what-changed delta"]

  FIX --> SAME
  EMAIL --> SAME
  ROR --> SAME
  OA --> SAME
  BT2 --> SAME
  SAME --> RE

  classDef tool fill:#e6edfb,stroke:#3f5bc4,color:#16203c;
  classDef agentv fill:#efe7fa,stroke:#7c4fc4,color:#2a1544;
  classDef verified fill:#e4f2e9,stroke:#2f9767,color:#123626;
  classDef store fill:#fdf2e0,stroke:#c58a1a,color:#3a2b0e;
  class FIX,NOKEY verified
  class ROR,OA,SAME tool
  class BT2 agentv
  class EMAIL,RE store
```

*The demo is the genericity fixture too — three directory shapes across three countries, all
synthetic. Live credentials stay minimal on purpose: an email for the polite pools, nothing
else.* — demo.py · preflight.py · SKILL.md · D-064

---

## COMPONENTS — skill, tools, and agents

The deliverable is a skill package. `SKILL.md` orchestrates deterministic **tools** (no LLM)
and, where genuine judgement is needed, **agents** (LLM). Everything writes to SQLite; nothing
returns prose to the orchestrator.

```mermaid
%%{init:{'theme':'base','themeVariables':{'fontFamily':'ui-sans-serif,system-ui,sans-serif','fontSize':'14px','primaryColor':'#e6edfb','primaryBorderColor':'#3f5bc4','primaryTextColor':'#18203a','lineColor':'#95a0b5','secondaryColor':'#eef1f6','tertiaryColor':'#f6f8fb','clusterBkg':'#f6f8fb','clusterBorder':'#cbd3e2','edgeLabelBackground':'#ffffff'}}}%%
flowchart TD
  subgraph ORCH["Orchestrator — the agent, inline (SKILL.md)"]
    SK["run state · budget · tier gating"]
    INT["interpret intent<br/>+ generate queries"]
    PLAN["SearchPlan"]
    INT --> PLAN
  end

  subgraph TOOLS["Tools — deterministic, no LLM"]
    SM["subject-map — map-field"]
    ST["scan studio — plan wizard"]
    D["discovery-ladder"]
    FE["fetcher — 3 phases"]
    DD["deep-dive collector"]
    GQ["gap-queue"]
    PACE["pacing gate — pace"]
    BR["browser-rung + browser-fill"]
    CP["chrome-prompt-generator"]
    MI["md-ingester"]
    SCR["scorer — gates + weights"]
    EXP["exporter — JSON + HTML dashboard"]
  end

  subgraph AGENTS["Agents — LLM judgement only"]
    A1["recruiting-analyst"]
    A2["eligibility-analyst"]
    A3["profile-synthesist"]
    A4["evidence-auditor"]
    A5["adapter-author"]
  end

  SK --> INT
  INT --> SM --> PLAN
  ST --> PLAN
  PLAN --> D --> FE --> DD --> GQ --> PACE --> BR
  BR -.->|"abort-on-challenge"| CP --> MI
  MI -.->|"resume"| DD
  BR -.->|"fill + resume"| DD
  SK --> SCR --> EXP

  DD -->|"classify state"| A1
  DD -->|"admissions/funding"| A2
  DD -->|"narrative"| A3
  D -.->|"on failed fetch"| A5
  SCR -->|"sample claims"| A4

  classDef tool fill:#e6edfb,stroke:#3f5bc4,color:#16203c;
  classDef agentv fill:#efe7fa,stroke:#7c4fc4,color:#2a1544;
  classDef agent fill:#e4f2e9,stroke:#2f9767,color:#123626;
  classDef gate fill:#e3f2ef,stroke:#1e8c78,color:#0d362e;
  classDef orch fill:#fdf2e0,stroke:#c58a1a,color:#3a2b0e;
  class D,FE,DD,GQ,SM,ST,CP,MI,SCR,EXP tool
  class BR agentv
  class PACE gate
  class A1,A2,A3,A4,A5 agent
  class SK,INT,PLAN orch
```

*Intent interpretation and query generation are done by the orchestrator inline — they are the
"generate, don't look up" judgement — producing a SearchPlan the deterministic tools consume.
The browser seam (pace → browser-rung → browser-fill) is the default walled path; the
chrome-prompt-generator + md-ingester pair is the classic human rung it falls back to. Agents
are defined by what needs judgement; workers return a task id and status, never prose.* —
architecture.md §4 · D-042 · D-045 · D-055 · D-064 · D-065 · D-066 · D-067

---

## SCAN SETUP — from free text to a confirmed plan

Nothing expensive runs before the student confirms the plan. The free-text field becomes an
API-derived subject map; the student multi-selects topics — in the Scan Studio's checkbox
tree, or as a numbered list in conversation — and the confirmed plan (or a file of named
professors) drives the scan.

```mermaid
%%{init:{'theme':'base','themeVariables':{'fontFamily':'ui-sans-serif,system-ui,sans-serif','fontSize':'14px','primaryColor':'#e6edfb','primaryBorderColor':'#3f5bc4','primaryTextColor':'#18203a','lineColor':'#95a0b5','secondaryColor':'#eef1f6','tertiaryColor':'#f6f8fb','clusterBkg':'#f6f8fb','clusterBorder':'#cbd3e2','edgeLabelBackground':'#ffffff'}}}%%
flowchart TD
  FREE["free text<br/>intent · country · universities · field"]
  MF["map-field — discover/subjects.py<br/>OpenAlex topics → domain/field/subfield<br/>works-count sorted · truncation-honest"]

  subgraph STUDIO["Scan Studio — one self-contained offline HTML (D-067)"]
    SI["intent picker"]
    SC["country"]
    SU["universities + mode chips<br/>all · prioritise · only"]
    STREE["tri-state subject tree<br/>domain → field → subfield → topic"]
    SP["named professors"]
    SE["contact email"]
  end

  CHAT["conversational fallback<br/>numbered multi-select in chat"]
  PLANJ["supervisorly_plan.json<br/>Blob download → move out of Downloads"]
  TGT["targets JSON<br/>name + optional affiliation, or OpenAlex URLs"]
  SCAN["scan --plan / --targets<br/>identity_resolution: verified / unverified / unchecked"]
  DASHO["dashboard.html<br/>+ reexport after browser fills"]

  FREE --> MF
  MF --> STREE
  FREE --> CHAT
  SI --> PLANJ
  SC --> PLANJ
  SU --> PLANJ
  STREE --> PLANJ
  SP --> PLANJ
  SE --> PLANJ
  SP -.-> TGT
  CHAT -->|"resolved_topic_ids confirmed"| SCAN
  PLANJ --> SCAN
  TGT --> SCAN
  SCAN --> DASHO

  classDef tool fill:#e6edfb,stroke:#3f5bc4,color:#16203c;
  classDef human fill:#fbe7ef,stroke:#bd4a66,color:#3a1120;
  classDef store fill:#fdf2e0,stroke:#c58a1a,color:#3a2b0e;
  class MF,SI,SC,SU,STREE,SP,SE,SCAN tool
  class CHAT human
  class FREE,PLANJ,TGT,DASHO store
```

*Selected topic IDs become the plan's `resolved_topic_ids`, so research-fit is deterministic
ID-overlap, not string match. The Studio is a static file — it cannot write to disk, so the
plan arrives as a browser download; the conversational numbered list remains the fallback in
every agent host. Unresolved named professors are reported as skips, never silently dropped.* —
discover/subjects.py · export/studio.py · scan --help · D-058 · D-066 · D-067

---

## PIPELINE — the student's journey, in stages

Intent is understood before anything is searched. The shortlist is formed on **research fit**
(cheaply available), not on recruiting status (which only exists after the deep dive).

```mermaid
%%{init:{'theme':'base','themeVariables':{'fontFamily':'ui-sans-serif,system-ui,sans-serif','fontSize':'14px','primaryColor':'#e6edfb','primaryBorderColor':'#3f5bc4','primaryTextColor':'#18203a','lineColor':'#95a0b5','secondaryColor':'#eef1f6','tertiaryColor':'#f6f8fb','clusterBkg':'#f6f8fb','clusterBorder':'#cbd3e2','edgeLabelBackground':'#ffffff'}}}%%
flowchart TD
  ST0["Stage 0 — interpret intent<br/>understand the purpose, build a plan"]
  CONF{"student confirms<br/>the plan?"}
  ST1["Stage 1 — full roster (all ~400)<br/>find dept page · else search for it<br/>links to everything"]
  T1["T1 cheap signal (all)<br/>1 cached page · regex · no LLM"]
  SHORT["shortlist on research fit<br/>+ activity"]
  ST2["Stage 2 — deep dive (~40)<br/>papers · availability · contact · students"]
  ST3["Stage 3 — gap-fill<br/>3-phase fetch ladder"]
  ST4["Stage 4 — students<br/>public links · sortable"]
  SC["score — gates + weights"]
  DASH["dashboard + JSON"]

  ST0 --> CONF
  CONF -->|"yes"| ST1
  CONF -->|"refine"| ST0
  ST1 --> T1 --> SHORT --> ST2 --> ST3 --> ST4 --> SC --> DASH

  classDef tool fill:#e6edfb,stroke:#3f5bc4,color:#16203c;
  classDef store fill:#fdf2e0,stroke:#c58a1a,color:#3a2b0e;
  class ST0,ST1,T1,SHORT,ST2,ST3,ST4,SC tool
  class DASH store
```

*A professor is never dropped for missing data — the gap is shown, not hidden. Stage 0's plan
confirmation is now concrete: the subject map (SCAN SETUP map) is the review.* —
product-flow.md · D-021 · D-022 · D-037 · D-066

---

## FETCH — three phases, the browser tier, and the human-rung fallback

Each phase runs across the target set, marks its failures, and hands only the residual to the
next. Phase 3 is now the agent-driven browser tier (D-064); the original Chrome-extension
method — turned into the classic MD human rung — remains as the fallback when the browser is
denied or challenged.

```mermaid
%%{init:{'theme':'base','themeVariables':{'fontFamily':'ui-sans-serif,system-ui,sans-serif','fontSize':'14px','primaryColor':'#e6edfb','primaryBorderColor':'#3f5bc4','primaryTextColor':'#18203a','lineColor':'#95a0b5','secondaryColor':'#eef1f6','tertiaryColor':'#f6f8fb','clusterBkg':'#f6f8fb','clusterBorder':'#cbd3e2','edgeLabelBackground':'#ffffff'}}}%%
flowchart TD
  G["gap: an entity + field to fill"]
  P1["Phase 1 — structured sources<br/>API · CRIS · sitemap · JSON-LD"]
  P1OK{"resolved?"}
  P2["Phase 2 — automated browse<br/>the marked pages"]
  P2OK{"resolved?"}
  P3["Phase 3 — browser tier (primary)<br/>agent-driven Chrome · your session"]
  PACE{"pace gate<br/>exit 0 = allow · 3 = deny"}
  SNAPB["staging text → ingest-page<br/>snapshot tier agent_browser"]
  FILLB["browser-fill — pipeline extractors<br/>D-010 quote-verified claims"]
  P3OK{"found?"}
  HUMAN["fallback: classic human rung<br/>MD prompt in Claude for Chrome"]
  MD["returns MD files<br/>value · source · date · quote"]
  INGEST["md-ingester → Claim<br/>extractor = human-assisted"]
  CLAIM["Claim stored, gap task closes"]
  NONE["'we looked, found nothing'<br/>professor still shown"]

  G --> P1 --> P1OK
  P1OK -->|"yes"| CLAIM
  P1OK -->|"404 / error → mark"| P2 --> P2OK
  P2OK -->|"yes"| CLAIM
  P2OK -->|"still blocked → mark"| P3 --> PACE
  PACE -->|"allow"| SNAPB --> FILLB --> P3OK
  PACE -->|"deny / abort latch"| HUMAN --> MD --> INGEST --> P3OK
  P3OK -->|"yes"| CLAIM
  P3OK -->|"no"| NONE

  classDef tool fill:#e6edfb,stroke:#3f5bc4,color:#16203c;
  classDef agentv fill:#efe7fa,stroke:#7c4fc4,color:#2a1544;
  classDef human fill:#fbe7ef,stroke:#bd4a66,color:#3a1120;
  classDef gate fill:#e3f2ef,stroke:#1e8c78,color:#0d362e;
  classDef store fill:#fdf2e0,stroke:#c58a1a,color:#3a2b0e;
  classDef skip fill:#edeff3,stroke:#98a2b4,color:#565f6e;
  class P1,P2,FILLB,INGEST tool
  class P3,SNAPB agentv
  class PACE gate
  class HUMAN,MD human
  class CLAIM store
  class NONE skip
```

*The run carries an `awaiting_human_input` status so gap-filling can span sessions and resume
without re-fetching — `ingest-page --entity … --run …` fills a target from a browser page and
closes its gap tasks, then `reexport` rebuilds the dashboard.* —
architecture.md §2 · D-039 · D-043 · D-064 · D-065

---

## BROWSER TIER — the D-064/D-065 recipe, page by page

The exact loop for every browser page. **Raw HTML/DOM never enters the agent's context** —
extraction happens in-page and in Python; the agent handles only file paths, byte counts, and
one-line results. A browser page is just another snapshot.

```mermaid
%%{init:{'theme':'base','themeVariables':{'fontFamily':'ui-sans-serif,system-ui,sans-serif','fontSize':'14px','primaryColor':'#e6edfb','primaryBorderColor':'#3f5bc4','primaryTextColor':'#18203a','lineColor':'#95a0b5','secondaryColor':'#eef1f6','tertiaryColor':'#f6f8fb','clusterBkg':'#f6f8fb','clusterBorder':'#cbd3e2','edgeLabelBackground':'#ffffff'}}}%%
flowchart TD
  NEXT["next page to fetch"]
  WARM{"fresh in the warm cache?"}
  SKIPF["reuse the cache — no fetch"]
  PACE{"pace --host<br/>exit 0 = allow · 3 = deny"}
  DENY["sleep the printed wait= and re-check,<br/>or skip the host on cap/abort"]
  POLICY["policy in code (D-065)<br/>x/twitter/linkedin 45–120 s · 15 pages/session<br/>scholar.google.* 60–180 s · 5/session, profiles only<br/>advertised profile URLs only — never people-search"]
  CHR["Chrome via chrome-devtools-mcp<br/>headful · persistent profile<br/>one-time user login on first run"]
  EXT["evaluate_script(page_extract.js)<br/>main text capped at 60 KiB in-page<br/>scroll mode = human-like jittered scroll"]
  STAGE["staging file<br/>NEVER read into agent context"]
  ING["ingest-page --url FINAL --file STAGING<br/>+ --entity kind:ref --run id to fill a target"]
  SNAP["content-addressed snapshot<br/>tier agent_browser · final-URL provenance"]
  FILL["browser-fill — the pipeline's own extractors<br/>D-010 quote-verified claims<br/>never clobbers a human-assisted value"]
  GAPS["awaiting_human gap tasks close<br/>run status recomputed"]
  REEXP["reexport — dashboard regenerated"]
  ABORT["pace --abort — host latched for the session<br/>field = blocked → classic human rung"]

  NEXT --> WARM
  WARM -->|"yes"| SKIPF
  WARM -->|"no"| PACE
  PACE -->|"0 — allow"| CHR
  PACE -->|"3 — deny"| DENY
  PACE -.-> POLICY
  CHR --> EXT --> STAGE --> ING --> SNAP --> FILL --> GAPS --> REEXP
  CHR -.->|"captcha · soft-block · login redirect"| ABORT

  classDef tool fill:#e6edfb,stroke:#3f5bc4,color:#16203c;
  classDef agentv fill:#efe7fa,stroke:#7c4fc4,color:#2a1544;
  classDef human fill:#fbe7ef,stroke:#bd4a66,color:#3a1120;
  classDef gate fill:#e3f2ef,stroke:#1e8c78,color:#0d362e;
  classDef store fill:#fdf2e0,stroke:#c58a1a,color:#3a2b0e;
  classDef skip fill:#edeff3,stroke:#98a2b4,color:#565f6e;
  class NEXT,ING,SNAP,FILL,GAPS,REEXP tool
  class CHR,EXT agentv
  class PACE,POLICY gate
  class STAGE store
  class SKIPF,DENY skip
  class ABORT human
```

*The Python layer stays LLM-free: browser-collected content enters the engine only through the
deterministic `ingest-page` seam, and the existing extractors plus the quote-in-snapshot gate
run unchanged. State lives at `~/.supervisorly/pacing_state.json` so caps and abort latches
survive the working directory.* — SKILL.md (browser recipe) · fetch/browser_rung.py ·
fetch/browser_fill.py · ethics/pacing.py · D-009 · D-010 · D-064 · D-065

---

## SOURCES — where recruiting signal comes from

Recruiting status lives in prose on the professor's own channels. Everything reachable feeds
one generated recruiting-signal read; the walled profiles are read through your own paced
session.

```mermaid
%%{init:{'theme':'base','themeVariables':{'fontFamily':'ui-sans-serif,system-ui,sans-serif','fontSize':'14px','primaryColor':'#e6edfb','primaryBorderColor':'#3f5bc4','primaryTextColor':'#18203a','lineColor':'#95a0b5','secondaryColor':'#eef1f6','tertiaryColor':'#f6f8fb','clusterBkg':'#f6f8fb','clusterBorder':'#cbd3e2','edgeLabelBackground':'#ffffff'}}}%%
flowchart LR
  OWN["Own pages · openings · News<br/>#1 signal density"]
  BSKY["Bluesky<br/>public API — verified"]
  MASTO["Mastodon<br/>public API — verified"]
  GH["GitHub READMEs"]
  X["X / Twitter<br/>advertised profile only"]
  LI["LinkedIn<br/>advertised profile only"]
  GS["Google Scholar<br/>profile pages only — minimal use"]

  RS["recruiting-signal read<br/>buckets generated per field + intent"]
  BTIER["browser tier — your session<br/>paced per D-065"]
  HUMAN["classic human rung<br/>(fallback)"]
  NEVER["people-search · bulk enumeration<br/>NEVER"]

  OWN --> RS
  BSKY --> RS
  MASTO --> RS
  GH --> RS
  X --> BTIER
  LI --> BTIER
  GS --> BTIER
  BTIER --> RS
  BTIER -.->|"challenge → abort"| HUMAN --> RS

  classDef tool fill:#e6edfb,stroke:#3f5bc4,color:#16203c;
  classDef verified fill:#e4f2e9,stroke:#2f9767,color:#123626;
  classDef agentv fill:#efe7fa,stroke:#7c4fc4,color:#2a1544;
  classDef human fill:#fbe7ef,stroke:#bd4a66,color:#3a1120;
  classDef skip fill:#edeff3,stroke:#98a2b4,color:#565f6e;
  class OWN,GH tool
  class BSKY,MASTO verified
  class X,LI,GS,BTIER agentv
  class HUMAN human
  class NEVER skip
```

*The reading method — which phrases signal recruiting, how negation and cycle-dating are
handled — is generated, never a hardcoded keyword list. Only the profile URL the professor
themselves advertised is ever visited; on any challenge the field goes `blocked` and routes to
the human rung.* — research/social-sources.md · D-038 · D-044 · D-065

---

## DATA — the core of the model

The spine that lets facts join, dedupe and diff — the thing the corpus's prose files could not
do. 31 entities in total (24 world-model + 7 pipeline/user-action); the core is shown.

```mermaid
flowchart TD
  subgraph SPINE["Institutional spine"]
    INST["Institution"] --> UNIT["Unit"] --> PERSON["Person — the hub"]
  end
  subgraph PPL["People and work"]
    APP["Appointment"] --> ORG["Organization"]
    LAB["Lab"] --> LM["LabMember"]
    BIB["BibliometricProfile<br/>one row per source"]
    RS["RecruitingSignal"]
    CE["CollaboratorEdge"]
  end
  subgraph PROV["Provenance"]
    CLAIM["Claim<br/>every field is one"]
    WS["WebSource"]
    CONF["Conflict"]
    CLAIM --> WS
    CLAIM --> CONF
  end
  subgraph ADM["Admissions and funding"]
    GP["GraduateProgram"] --> AC["ApplicationCycle"] --> FI["FundingItem"]
  end
  subgraph USER["Your own actions"]
    AP["ApplicantProfile"] --> OUT["Outreach"]
    AP --> APL["Application"]
  end
  subgraph RUNS["Pipeline state"]
    RUN["Run"] --> TASK["Task"] --> EC["ExtractionCache"]
  end
  PERSON --> APP
  PERSON --> LAB
  PERSON --> BIB
  PERSON --> RS
  PERSON --> CE
  PERSON --> CLAIM
  PERSON --> GP
  OUT --> PERSON
  APL --> GP
  TASK --> WS
```

*Nothing is keyed on a display name; identity is an internal id with external ids as evidence.
Bibliometrics is one row per source — never a blended number.* — domain-model.md · D-026 · D-030

---

## PROVENANCE — how a value becomes a trusted claim

Every fact carries its source, its quote, and its confidence. Verification is structural — the
model's quote must be found in the stored snapshot — not a prose promise.

```mermaid
%%{init:{'theme':'base','themeVariables':{'fontFamily':'ui-sans-serif,system-ui,sans-serif','fontSize':'14px','primaryColor':'#e6edfb','primaryBorderColor':'#3f5bc4','primaryTextColor':'#18203a','lineColor':'#95a0b5','secondaryColor':'#eef1f6','tertiaryColor':'#f6f8fb','edgeLabelBackground':'#ffffff'}}}%%
flowchart LR
  F["fetch — httpx or the browser seam"] --> SNAP["snapshot<br/>content-hashed"]
  SNAP --> EX{"extract"}
  EX -->|"deterministic"| VAL["value + quote"]
  EX -->|"LLM — may answer NOT_FOUND"| VAL
  VAL --> VER{"quote found<br/>in snapshot?"}
  VER -->|"no"| REJ["reject — hallucination"]
  VER -->|"yes"| CL["Claim<br/>value · quote · source · confidence"]
  CL --> CF{"disagrees with<br/>an existing claim?"}
  CF -->|"yes"| CONFL["Conflict recorded<br/>both kept"]
  CF -->|"no"| STORE["SQLite"]
  CONFL --> STORE

  classDef tool fill:#e6edfb,stroke:#3f5bc4,color:#16203c;
  classDef store fill:#fdf2e0,stroke:#c58a1a,color:#3a2b0e;
  classDef skip fill:#edeff3,stroke:#98a2b4,color:#565f6e;
  class F,SNAP,EX,VAL,VER,CF tool
  class CL,STORE,CONFL store
  class REJ skip
```

*Verification proves fidelity, not truth — that the model didn't invent text relative to the
page. The page itself can still be wrong or stale. A browser-tier page is just another
snapshot: tier `agent_browser`, final-URL provenance, same quote gate.* —
architecture.md §3 · D-010 · D-043 · D-064

---

## RULES — where each rule actually bites

Rules are enforced in code at specific points, not asserted in a preamble. This is the map of
enforcement gates.

```mermaid
%%{init:{'theme':'base','themeVariables':{'fontFamily':'ui-sans-serif,system-ui,sans-serif','fontSize':'14px','primaryColor':'#e6edfb','primaryBorderColor':'#3f5bc4','primaryTextColor':'#18203a','lineColor':'#95a0b5','secondaryColor':'#eef1f6','tertiaryColor':'#f6f8fb','clusterBkg':'#f6f8fb','clusterBorder':'#cbd3e2','edgeLabelBackground':'#ffffff'}}}%%
flowchart TD
  subgraph FETCH["at fetch"]
    R1["robots.txt checked — fail closed<br/>incl. redirect final-URL re-check"]
    R2["public vs walled routing"]
    R3["no login, no bot-wall defeat"]
    R10["pace gate before every browser page<br/>abort-on-challenge latch"]
  end
  subgraph BUILD["at build"]
    R4["optout.txt filter — with a test<br/>re-checked at re-export and mid-scan"]
  end
  subgraph RANK["at ranking"]
    R5["hard gates use reliable claims only"]
    R6["unreliable fields sort + warn,<br/>never filter rows out"]
  end
  subgraph EXPORT["at export"]
    R7["exclude LLM judgements about people"]
    R8["no bare email lists"]
  end
  subgraph OUTREACH["at outreach"]
    R9["one professor at a time — no bulk path"]
  end
  CORPUS["corpus = methodology only<br/>never a runtime data input"]

  classDef gate fill:#e3f2ef,stroke:#1e8c78,color:#0d362e;
  class R1,R2,R3,R4,R5,R6,R7,R8,R9,R10,CORPUS gate
```

*Nationality never gates visibility. Scale is an ethical constraint, not just a performance
one. The pacing rules are code, not vibes — a deny or an abort latch is never retried harder.* —
ethics-and-compliance.md · D-005 · D-023 · D-024 · D-032 · D-035 · D-065

---

## DECISIONS — how the 67 cluster

Every decision belongs to one of eight themes. This shows the shape of the design space, and
which clusters still carry the most risk. (67 decisions after the browser-tier round; the map
names representative ones per theme, not all.)

```mermaid
%%{init:{'theme':'base','themeVariables':{'fontFamily':'ui-sans-serif,system-ui,sans-serif','fontSize':'14px','primaryColor':'#e6edfb','primaryBorderColor':'#3f5bc4','primaryTextColor':'#18203a','lineColor':'#95a0b5','secondaryColor':'#eef1f6','tertiaryColor':'#f6f8fb','clusterBkg':'#f6f8fb','clusterBorder':'#cbd3e2'}}}%%
flowchart TD
  ROOT["67 decisions"]
  ROOT --> SCOPE["Scope & identity<br/>D-001·02·04·06·07·12·34·42"]
  ROOT --> SRC["Data sources<br/>D-013·14·15·16·20·25·28·39·44"]
  ROOT --> DATA["Data model<br/>D-009·10·26·29·30·37"]
  ROOT --> PROD["Product & flow<br/>D-021·22·31·36·38·40·41"]
  ROOT --> DASH["Dashboard<br/>D-003·33·48"]
  ROOT --> ETH["Ethics<br/>D-005·19·23·24·32·35·43"]
  ROOT --> COST["Cost & perf<br/>D-011"]
  ROOT --> FRONT["Browser tier & front door<br/>D-064·65·66·67"]

  SCOPE --> RISK["risk accepted:<br/>generic v1 with no golden fixture<br/>D-34 + D-11"]

  classDef tool fill:#e6edfb,stroke:#3f5bc4,color:#16203c;
  classDef agentv fill:#efe7fa,stroke:#7c4fc4,color:#2a1544;
  classDef human fill:#fbe7ef,stroke:#bd4a66,color:#3a1120;
  class SCOPE,SRC,DATA,PROD,DASH,ETH,COST tool
  class FRONT agentv
  class RISK human
```

*The one flagged risk: fully-generic v1 (D-034) without a corpus-sourced regression fixture
(D-011/D-035). Managed by fail-loud coverage, per-value confidence, and cassette + synthetic
tests.* — DECISIONS.md

---

*This atlas is a view over the design documents, not a replacement for them. When a diagram and
a document disagree, the document wins — tell me and I'll fix the diagram.*
