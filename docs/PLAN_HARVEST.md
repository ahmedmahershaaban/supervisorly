# Harvest plan — from "331 professors, zero facts" to a dashboard worth reading

Working plan, 2026-07-29. Supersedes the sketch in [BLOCKERS B-005](BLOCKERS.md#b-005--should-the-browser-work-move-to-the-students-machine-and-is-the-llm-needed).
Nothing here is built yet except where marked **shipped**.

The measurements this plan answers to, all from live runs:

| | |
|---|---|
| OpenAlex authors carrying a homepage | **0 / 50** |
| ORCID records carrying a researcher URL (topic-filtered cohort) | **0 / 11** |
| professors with any readable page (art run, 24 targets) | **3 / 24** |
| pages read by a language model today | **0** |

---

## The three corrections that reshape the plan

### 1. A deadline is not a property of a professor

The current design hunts recruiting signals and deadlines on each professor's page. That is
the wrong unit for most of what a student needs. **Application deadlines, eligibility, language
requirements and funding rules are institutional or departmental** — one graduate-admissions
page governs every professor in that faculty.

Confirmed on the hosts already measured: `aun.edu.eg/academic/admission.htm`,
`aun.edu.eg/agriculture/about/apply`, `alexu.edu.eg/…/Institute of Graduate`.

The consequence is large. Reading 25 professor pages to find a deadline is 25 fetches for a
fact that is not on any of them. Reading **one admissions page per institution** yields it for
all 25 — and those pages are few, stable, and written to be read.

**This is the highest yield-per-fetch change available, and it is not in the plan today.**

### 2. Filter deterministically before spending a model

Ahmed's requirement — *no dummy data, no context overload, be direct* — should be enforced in
code, not requested in a prompt. A page that contains no recruiting cue, no date, and no
application word cannot yield a recruiting claim, and sending it to a model to be told so
costs tokens to learn nothing.

So: capture text → **cheap deterministic triage** → send only candidates. The existing regexes
are exactly the right triage tool even where they are too blunt to be the extractor: they are
excellent at *"this page is worth a closer look"* and poor at *"this sentence means recruiting"*.

### 3. Parallelism must be across hosts, never within one

"10–20 tabs at once" is right about throughput and wrong about targeting. Twenty concurrent
tabs against one university is a small denial-of-service from a residential IP, and doing it
from the student's machine moves the crawler rather than removing it (B-005).

The fix keeps the speed: **N workers, but never two concurrent requests to the same host.**
Twenty tabs across twenty institutions is fast and polite; twenty tabs against one is neither.
Per-host serialisation and robots must live wherever the fetching runs — the existing
`HostRateLimiter` and robots gate already do this server-side, and would have to be
re-implemented, correctly, if the fetching moved to a browser extension.

---

## The phases

### Phase 0 — Harvest the registry facts we already reach *(deterministic, no model)*

ORCID `/employments` returns structured role, department, organisation and dates. Measured:

```
organisation : Ain Shams University Faculty of Medicine
role title   : Professor
department   : Community, Environmental and Occupational Medicine
```

One call per shortlisted professor, alongside the researcher-urls call already made. No model,
no rendering, no hallucination surface — and it fills the "who is this person" half of the
modal today.

**Do not spend a model on this.** A model reading the same record's prose to guess a role is
strictly worse than the field that states it.

### Phase 1 — Institution admissions pages *(the deadline layer)*

For each institution in the scan, find and read its graduate-admissions pages: deadlines,
degree routes, language bands, funding, application steps. Few pages, high value, shared by
every professor there.

- discovery: the institution's own site, robots-gated, rendered where needed (**render rung
  shipped**)
- the result attaches to the *institution*, and every professor inherits it with the
  institution named as the source — never presented as the professor's own statement
- this is where `eligibility-analyst` (the CLI agent that already exists) belongs

### Phase 2 — The directory rung *(find the professor's page at all)*

Institution → faculty/staff directory → the individual's page. `roster.classify_directory` and
`roster.route_directory` exist and **nothing calls them**. This is the bottleneck behind the
3-of-24 number.

Honest scope, unchanged from B-003: per-institution work, and it will never cover Cairo
University, whose TLS chain is broken at their server and whose scholar subdomain 403s bots.

### Phase 3 — Capture text, not DOM *(shipped, reused)*

`extract/page_extract.js` already produces cleaned main text in-page and mirrors
`normalize.main_text`, so a captured page is byte-compatible with a fetched one and the D-010
quote gate runs on it unchanged. Text, never HTML — exactly as Ahmed described.

### Phase 4 — Deterministic triage *(the token gate)*

Before any model sees a page: does it contain a recruiting cue, a date near an application
word, a supervision term, an email/contact block? No → the page is stored and marked
`searched_absent` with its snapshot, and **no tokens are spent**. Yes → it becomes a candidate.

This is what makes Phase 5 affordable, and it is the mechanical form of "be direct".

### Phase 5 — Model extraction, batched, isolated *(D-073, built, not wired)*

`extract/llm_claims.py` is written and tested: the model returns `(field, value, quote)` and
anything whose quote is not verbatim in the snapshot is dropped before it becomes a claim.

Enhancements over the current contract:

- **batch** several candidate pages per call and return one array — Ahmed's point, and the
  cheapest correct shape
- **isolated context per batch**: no conversation history, no accumulated transcript. Each
  call carries only the pages it must read, so cost stays linear and a long scan cannot drag a
  growing context behind it
- **fail-closed per batch**: one bad batch costs those pages, never the scan

### Phase 6 — Historical cycles *(what the deadline was last year)*

Ahmed asked for "the old versions of the acceptance". The Wayback CDX API answers it and is
free and open — verified: `aun.edu.eg` admissions pages archived from **2003** to 2023.

Reading the same admissions URL across past years gives the *pattern* — "applications have
opened in May for the last four cycles" — which is exactly the `watch · projected` confidence
the dashboard already renders and distinguishes from a `firm` published date. Projected dates
must keep saying so.

### Phase 7 — Bring your own model key *(and never hold it)*

The intended feature is each student supplying their own Gemini key. The safe shape:

**the browser calls Gemini directly; the key never reaches our server.** Gemini's REST endpoint
is callable from a page, so the key stays in the student's own storage and our logs, our
Firestore and our support burden never contain a third-party credential. A key posted to us is
a key we are then responsible for.

This also answers the cost question honestly: with BYO keys the expansion and extraction
budget stops being ours, which is what makes wide expansion and Phase 5 affordable at all.

---

## What NOT to build, and why

**Do not ask students to install a coding agent (Gemini CLI, an MCP host, an autonomous
browser agent).** Three reasons: the install/update/trust burden is larger than the product;
handing an autonomous agent a browser on someone's machine is a serious safety surface for a
supervisor search; and it would still need robots and per-host rate limiting re-implemented on
the client to be defensible.

**The "run it on my own machine" product already exists.** It is the CLI plus the agents in
`.claude/agents/` — `recruiting-analyst`, `eligibility-analyst`, `evidence-auditor`,
`profile-synthesist`, `adapter-author`. If the local-power-user path is wanted, the work is to
make *that* easy to run, not to rebuild it inside a browser extension.

**Do not move bulk fetching to the student's IP.** Reach is the only genuine advantage of their
browser — pages their own session can see. That is the human rung, it is shipped, and it should
stay human-paced.

---

## Order of work, by value per unit of effort

1. **Phase 0** — small, deterministic, immediate content in the modal
2. **Phase 1** — largest yield per fetch; deadlines are what students actually need
3. **Phase 4** — cheap, and required before any model spend is defensible
4. **Phase 5** — the judgement layer, now aimed at pages that contain judgement-worthy prose
5. **Phase 2** — the expensive, unglamorous per-institution grind
6. **Phase 6 / 7** — once the above works

Phases 2 and 5 are the ones most likely to be over-promised. Both should report what they
could NOT reach, per institution, so coverage stays honest rather than implied.
