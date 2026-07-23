# Supervisorly — Design Atlas

One place that connects everything: the skill, its agents and tools, the pipeline, the
three-phase fetch with its human rung, the data model, the claim/provenance lifecycle, the
rules, and how the 56 decisions cluster. Each map ends with the documents and decisions that
govern it.

**Colour key** — the diagrams use one consistent scheme:

| Colour | Means |
|---|---|
| **Indigo** | the tool fetches or does this automatically |
| **Rose** | the human rung — the student's own browser (Claude for Chrome) |
| **Grey** | skipped on purpose |
| **Amber** | a data store or artifact |
| **Green** | verified / reliable |
| **Teal** | a rule / enforcement gate |

---

## CONTEXT — the boundary of the tool

What Supervisorly is, and where the line runs between what the tool does and what the
student's own browser does.

```mermaid
%%{init:{'theme':'base','themeVariables':{'fontFamily':'ui-sans-serif,system-ui,sans-serif','fontSize':'14px','primaryColor':'#e6edfb','primaryBorderColor':'#3f5bc4','primaryTextColor':'#18203a','lineColor':'#95a0b5','secondaryColor':'#eef1f6','tertiaryColor':'#f6f8fb','clusterBkg':'#f6f8fb','clusterBorder':'#cbd3e2','edgeLabelBackground':'#ffffff'}}}%%
flowchart LR
  S["Student"]
  subgraph CC["Claude Code"]
    SK["Supervisorly skill<br/>SKILL.md + agents + tools"]
  end
  S -->|"country · field · subfield<br/>need · universities"| SK

  subgraph TR["Tool fetches directly"]
    API["Structured sources<br/>OpenAlex · ROR · CRIS<br/>sitemaps · JSON-LD"]
    PUB["Professor's own pages<br/>homepage · openings · lab News"]
    SOC["Open-API social<br/>Bluesky · Mastodon · GitHub"]
  end

  subgraph HR["Human rung — student's own browser"]
    CFC["Claude for Chrome"]
    GATED["Walled<br/>X/Twitter · LinkedIn · Scholar"]
    CFC --> GATED
  end

  SK --> API
  SK --> PUB
  SK --> SOC
  SK -.->|"generates MD prompt"| CFC
  CFC -.->|"returns MD files"| SK

  subgraph OUT["Outputs — local, never committed"]
    DB["SQLite<br/>source of truth"]
    JSON["JSON export"]
    DASH["Dashboard<br/>HTML + JSX"]
  end
  SK --> DB --> JSON --> DASH
  DASH <-->|"ask · edit UI"| SKQ["Student's Claude session"]

  classDef tool fill:#e6edfb,stroke:#3f5bc4,color:#16203c;
  classDef human fill:#fbe7ef,stroke:#bd4a66,color:#3a1120;
  classDef store fill:#fdf2e0,stroke:#c58a1a,color:#3a2b0e;
  class API,PUB,SOC tool
  class CFC,GATED human
  class DB,JSON,DASH store
```

*The tool reads public pages and open APIs; it never defeats a login. Everything walled is
reached by the human, in their own session.* — architecture.md · D-039 · D-042 · D-044

---

## COMPONENTS — skill, tools, and agents

The deliverable is a skill package. `SKILL.md` orchestrates deterministic **tools** (no LLM)
and, where genuine judgement is needed, **agents** (LLM). Everything writes to SQLite; nothing
returns prose to the orchestrator.

```mermaid
%%{init:{'theme':'base','themeVariables':{'fontFamily':'ui-sans-serif,system-ui,sans-serif','fontSize':'14px','primaryColor':'#e6edfb','primaryBorderColor':'#3f5bc4','primaryTextColor':'#18203a','lineColor':'#95a0b5','secondaryColor':'#eef1f6','tertiaryColor':'#f6f8fb','clusterBkg':'#f6f8fb','clusterBorder':'#cbd3e2','edgeLabelBackground':'#ffffff'}}}%%
flowchart TD
  subgraph ORCH["Orchestrator — Claude, inline (SKILL.md)"]
    SK["run state · budget · tier gating"]
    INT["interpret intent<br/>+ generate queries"]
    PLAN["SearchPlan"]
    INT --> PLAN
  end

  subgraph TOOLS["Tools — deterministic, no LLM"]
    D["discovery-ladder"]
    FE["fetcher — 3 phases"]
    DD["deep-dive collector"]
    GQ["gap-queue"]
    CP["chrome-prompt-generator"]
    MI["md-ingester"]
    SCR["scorer — gates + weights"]
    EXP["exporter — JSON + HTML"]
  end

  subgraph AGENTS["Agents — LLM judgement only"]
    A1["recruiting-analyst"]
    A2["eligibility-analyst"]
    A3["profile-synthesist"]
    A4["evidence-auditor"]
    A5["adapter-author"]
  end

  SK --> INT
  PLAN --> D --> FE --> DD --> GQ --> CP --> MI
  MI -.->|"resume"| DD
  SK --> SCR --> EXP

  DD -->|"classify state"| A1
  DD -->|"admissions/funding"| A2
  DD -->|"narrative"| A3
  D -.->|"on failed fetch"| A5
  SCR -->|"sample claims"| A4

  classDef tool fill:#e6edfb,stroke:#3f5bc4,color:#16203c;
  classDef agent fill:#e4f2e9,stroke:#2f9767,color:#123626;
  classDef orch fill:#fdf2e0,stroke:#c58a1a,color:#3a2b0e;
  class D,FE,DD,GQ,CP,MI,SCR,EXP tool
  class A1,A2,A3,A4,A5 agent
  class SK,INT,PLAN orch
```

*Intent interpretation and query generation are done by the orchestrator (Claude) inline — they
are the "generate, don't look up" judgement — producing a SearchPlan the deterministic tools
consume. Agents are defined by what needs judgement; workers return a task id and status, never
prose.* — architecture.md §4 · D-042 · D-045 · D-055

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

*A professor is never dropped for missing data — the gap is shown, not hidden.* —
product-flow.md · D-021 · D-022 · D-037

---

## FETCH — three phases and the human rung

The map Ahmed emphasised. Each phase runs across the target set, marks its failures, and hands
only the residual to the next. Phase 3 is his original Chrome-extension method, turned into the
tool's escape hatch.

```mermaid
%%{init:{'theme':'base','themeVariables':{'fontFamily':'ui-sans-serif,system-ui,sans-serif','fontSize':'14px','primaryColor':'#e6edfb','primaryBorderColor':'#3f5bc4','primaryTextColor':'#18203a','lineColor':'#95a0b5','secondaryColor':'#eef1f6','tertiaryColor':'#f6f8fb','clusterBkg':'#f6f8fb','clusterBorder':'#cbd3e2','edgeLabelBackground':'#ffffff'}}}%%
flowchart TD
  G["gap: an entity + field to fill"]
  P1["Phase 1 — structured sources<br/>API · CRIS · sitemap · JSON-LD"]
  P1OK{"resolved?"}
  P2["Phase 2 — automated browse<br/>the marked pages"]
  P2OK{"resolved?"}
  P3["Phase 3 — generate MD prompt<br/>for the residual gaps"]
  HUMAN["Student runs it in Claude for Chrome<br/>own logged-in session"]
  MD["returns MD files<br/>value · source · date · quote"]
  INGEST["md-ingester → Claim<br/>extractor = human-assisted"]
  P3OK{"found?"}
  CLAIM["Claim stored, run resumes"]
  NONE["'we looked, found nothing'<br/>professor still shown"]

  G --> P1 --> P1OK
  P1OK -->|"yes"| CLAIM
  P1OK -->|"404 / error → mark"| P2 --> P2OK
  P2OK -->|"yes"| CLAIM
  P2OK -->|"still blocked → mark"| P3 --> HUMAN --> MD --> INGEST --> P3OK
  P3OK -->|"yes"| CLAIM
  P3OK -->|"no"| NONE

  classDef tool fill:#e6edfb,stroke:#3f5bc4,color:#16203c;
  classDef human fill:#fbe7ef,stroke:#bd4a66,color:#3a1120;
  classDef store fill:#fdf2e0,stroke:#c58a1a,color:#3a2b0e;
  classDef skip fill:#edeff3,stroke:#98a2b4,color:#565f6e;
  class P1,P2,P3,INGEST tool
  class HUMAN,MD human
  class CLAIM store
  class NONE skip
```

*The run carries an `awaiting_human_input` status so Phase 3 can span sessions and resume
without re-fetching.* — architecture.md §2 · D-039 · D-043

---

## SOURCES — where recruiting signal comes from

Verified 2026-07-23. Recruiting status lives in prose on the professor's own channels.
Everything reachable feeds one generated recruiting-signal read.

```mermaid
%%{init:{'theme':'base','themeVariables':{'fontFamily':'ui-sans-serif,system-ui,sans-serif','fontSize':'14px','primaryColor':'#e6edfb','primaryBorderColor':'#3f5bc4','primaryTextColor':'#18203a','lineColor':'#95a0b5','secondaryColor':'#eef1f6','tertiaryColor':'#f6f8fb','clusterBkg':'#f6f8fb','clusterBorder':'#cbd3e2','edgeLabelBackground':'#ffffff'}}}%%
flowchart LR
  OWN["Own pages · openings · News<br/>#1 signal density"]
  BSKY["Bluesky<br/>public API — verified"]
  MASTO["Mastodon<br/>public API — verified"]
  GH["GitHub READMEs"]
  X["X / Twitter<br/>no 2026 public path"]
  LI["LinkedIn<br/>ToS + login wall"]
  GS["Google Scholar<br/>robots Disallow"]

  RS["recruiting-signal read<br/>buckets generated per field + intent"]
  HUMAN["human rung"]

  OWN --> RS
  BSKY --> RS
  MASTO --> RS
  GH --> RS
  X --> HUMAN --> RS
  LI --> HUMAN
  GS -.->|"skip"| RS

  classDef tool fill:#e6edfb,stroke:#3f5bc4,color:#16203c;
  classDef verified fill:#e4f2e9,stroke:#2f9767,color:#123626;
  classDef human fill:#fbe7ef,stroke:#bd4a66,color:#3a1120;
  classDef skip fill:#edeff3,stroke:#98a2b4,color:#565f6e;
  class OWN,GH tool
  class BSKY,MASTO verified
  class X,LI,HUMAN human
  class GS skip
```

*The reading method — which phrases signal recruiting, how negation and cycle-dating are
handled — is generated, never a hardcoded keyword list.* — research/social-sources.md · D-038 · D-044

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
  F["fetch"] --> SNAP["snapshot<br/>content-hashed"]
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
page. The page itself can still be wrong or stale.* — architecture.md §3 · D-010 · D-043

---

## RULES — where each rule actually bites

Rules are enforced in code at specific points, not asserted in a preamble. This is the map of
enforcement gates.

```mermaid
%%{init:{'theme':'base','themeVariables':{'fontFamily':'ui-sans-serif,system-ui,sans-serif','fontSize':'14px','primaryColor':'#e6edfb','primaryBorderColor':'#3f5bc4','primaryTextColor':'#18203a','lineColor':'#95a0b5','secondaryColor':'#eef1f6','tertiaryColor':'#f6f8fb','clusterBkg':'#f6f8fb','clusterBorder':'#cbd3e2','edgeLabelBackground':'#ffffff'}}}%%
flowchart TD
  subgraph FETCH["at fetch"]
    R1["robots.txt checked — fail closed"]
    R2["public vs walled routing"]
    R3["no login, no bot-wall defeat"]
  end
  subgraph BUILD["at build"]
    R4["optout.txt filter — with a test"]
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
  class R1,R2,R3,R4,R5,R6,R7,R8,R9,CORPUS gate
```

*Nationality never gates visibility. Scale is an ethical constraint, not just a performance
one.* — ethics-and-compliance.md · D-005 · D-023 · D-024 · D-032 · D-035

---

## DECISIONS — how the 56 cluster

Every decision belongs to one of seven themes. This shows the shape of the design space, and
which clusters still carry the most risk. (56 decisions after the pre-build audit round; the
map names representative ones per theme, not all.)

```mermaid
%%{init:{'theme':'base','themeVariables':{'fontFamily':'ui-sans-serif,system-ui,sans-serif','fontSize':'14px','primaryColor':'#e6edfb','primaryBorderColor':'#3f5bc4','primaryTextColor':'#18203a','lineColor':'#95a0b5','secondaryColor':'#eef1f6','tertiaryColor':'#f6f8fb','clusterBkg':'#f6f8fb','clusterBorder':'#cbd3e2'}}}%%
flowchart TD
  ROOT["56 decisions"]
  ROOT --> SCOPE["Scope & identity<br/>D-001·02·04·06·07·12·34·42"]
  ROOT --> SRC["Data sources<br/>D-013·14·15·16·20·25·28·39·44"]
  ROOT --> DATA["Data model<br/>D-009·10·26·29·30·37"]
  ROOT --> PROD["Product & flow<br/>D-021·22·31·36·38·40·41"]
  ROOT --> DASH["Dashboard<br/>D-003·33"]
  ROOT --> ETH["Ethics<br/>D-005·19·23·24·32·35·43"]
  ROOT --> COST["Cost & perf<br/>D-011"]

  SCOPE --> RISK["risk accepted:<br/>generic v1 with no golden fixture<br/>D-34 + D-11"]

  classDef tool fill:#e6edfb,stroke:#3f5bc4,color:#16203c;
  classDef human fill:#fbe7ef,stroke:#bd4a66,color:#3a1120;
  class SCOPE,SRC,DATA,PROD,DASH,ETH,COST tool
  class RISK human
```

*The one flagged risk: fully-generic v1 (D-034) without a corpus-sourced regression fixture
(D-011/D-035). Managed by fail-loud coverage, per-value confidence, and cassette + synthetic
tests.* — DECISIONS.md

---

*This atlas is a view over the design documents, not a replacement for them. When a diagram and
a document disagree, the document wins — tell me and I'll fix the diagram.*
