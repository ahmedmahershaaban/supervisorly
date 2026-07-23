# Product Flow

The end-to-end experience, in the student's terms. This is the authoritative statement of
*what Supervisorly does when a student uses it*. The architecture
([architecture.md](architecture.md)) is how; this is what and in what order.

**The deliverable is a Claude Code skill + agents + tools, not a hosted product.** A
student points Claude at this repo — "read the README and add these skills" — and Claude
installs the tools, reads `SKILL.md`, and runs the whole flow below. There is no server,
no account, no site. Everything is generated fresh, per student, per search.

---

## The governing principle: generate, don't look up

Nothing in this project is specialised to a school, a field, or a keyword. The corpus that
informed the design taught the *method*, never the content
([D-035](DECISIONS.md#d-035--the-corpus-is-a-methodology-reference-not-a-data-source),
[D-038](DECISIONS.md#d-038--queries-and-keywords-are-generated-per-search-never-looked-up)).
So:

- The agent does not hold a list of universities — it finds them for the chosen country.
- The agent does not hold a keyword dictionary — it *generates* the search terms, venues,
  and synonyms for the chosen field and subfield.
- The agent does not have a per-professor template — it captures whatever it can find about
  each professor and marks the rest "no data found," dynamically.

If a student picks a field the author never imagined, in a country nobody tested, the tool
still works, because none of it was hardcoded.

---

## Stage 0 — Understand what the student actually needs

**The search is driven by intent, not by literal input**
([D-036](DECISIONS.md#d-036--intent-interpretation-is-stage-0)).

The UI collects, with dropdowns and suggestions so the student knows what's on offer:

| Input | Examples |
|---|---|
| Country | any — one, or "all" |
| Field | any — CS, physics, law, public health, … |
| Subfield | any — free text or suggested from the field |
| **What they need** | training · pre-master · pre-PhD / RA · a mentor · a Master's · a PhD · a postdoc |
| Universities (optional) | a form field to name specific ones |
| University mode | **all** · **prioritise these, then the rest** · **only these** |

Then Claude **interprets** before it searches. "Pre-PhD in causal NLP, Canada" is not three
search strings — it is a plan: *look for professors in NLP/causal-inference who advertise
pre-doc or RA positions, at Canadian institutions, and know that this means checking
openings pages, lab pages, pre-doc programs and RA postings — not degree-admission pages.*
The "what they need" selection changes **where the agent looks and what counts as a hit**.

The student confirms the interpreted plan before the expensive work begins.

**A country preflight runs first.** Before Stage 1's expensive work, the tool probes whether
the chosen country actually has the spine — a CRIS presence, an advisor-bearing thesis
registry, a national vacancy portal, OpenAlex depth — and tells the student *up front* what
will be thin here ("Germany: strong faculty coverage, no personal openings-page culture — I'll
lean on EURAXESS"). This turns the fully-generic risk into honest expectation-setting instead
of a surprise at the end ([D-060](DECISIONS.md#d-060--country-source-preflight)).

---

## Stage 1 — Build the full list of professors

For each targeted university:

1. Find the department for the chosen field.
2. Find the page that lists that department's professors.
3. **If that page can't be found, search for it** — Google, Scholar, the university's own
   search, a research portal — rather than giving up.
4. Capture **every** professor, each with **links to everything** discovered (homepage,
   Scholar, lab, ORCID, social).

The output of Stage 1 is a complete, link-rich roster — breadth first, depth later. This is
the tier that must stay cheap, because it runs over everyone
([architecture.md §1](architecture.md)).

---

## The shortlist gate — between Stage 1 and Stage 2

Deep-diving *every* professor in a country would be slow, expensive, and impolite. A
**shortlist gate** ([D-056](DECISIONS.md#d-056--the-shortlist-gate-is-explicit-never-dropped-is-about-display-deep-dive-is-about-the-shortlist))
promotes roughly the top ~40 to the deep dive, on **research-fit signal** — topic match and
recent activity — which is available cheaply *before* the deep dive. The student can adjust
the shortlist.

Two rules that look contradictory but are not:

- **"Never dropped" is about *display*.** Every enumerated professor appears in the dashboard,
  thin record and all, marked "not deep-dived." None is omitted.
- **"Deep-dive" is about the *shortlist*.** Only the promoted ~40 get the expensive
  multi-source pass below.

---

## Stage 2 — Deep-dive each shortlisted professor

For every professor **on the shortlist** — **dynamically, never from a fixed per-professor
template** ([D-037](DECISIONS.md#d-037--per-professor-capture-is-dynamic-not-templated)):

- what they work on
- their papers — how many, the most recent, dates, titles
- whether they appear to be taking new students / offering positions
- how to contact them
- their **collaborators and former (registry-sourced) doctoral students**, with any public
  links — never a claim about *current* lab membership, which no open source records
  ([D-016](DECISIONS.md#d-016--students-is-not-obtainable-ship-recent_collaborators-instead), [D-025](DECISIONS.md#d-025--past-students-are-obtainable-current-students-still-are-not))

**The absolute rule: a field with no data is filled with "no data found," and the
professor is never dropped.** A professor we know little about still appears — the gap is
shown honestly, not hidden by omission. This is the exact opposite of the corpus's failure,
where thin professors silently fell off the list.

---

## Stage 3 — Fill the gaps, escalating through three phases

Walk each professor's record, find the empty fields, and go after exactly those — but not
all in the same way. The fetch escalates
([D-039](DECISIONS.md#d-039--agent-driven-web-navigation-is-first-class-apis-are-the-fast-path)),
each phase running only on what the previous one couldn't resolve:

1. **Structured sources** — APIs, CRIS portals, sitemaps, JSON-LD. Anything that 404s or
   errors is *marked*, not abandoned.
2. **Automated web navigation** — the tool browses the marked pages itself, finding the
   department page or the missing field directly. What it still can't get is *marked again*.
3. **Human-assisted retrieval** — for the residual, the tool hands the student a
   ready-to-paste prompt to run in the **Claude for Chrome extension**, in their own logged-in
   browser. Their session reaches what the tool can't — Scholar, Twitter/X, gated pages. The
   extension produces MD files; the student hands them back; the tool ingests them and
   continues from where it paused ([D-043](DECISIONS.md#d-043--human-assisted-retrieval-and-md-ingestion)).

This third phase is Ahmed's original Chrome-extension method turned into the tool's escape
hatch — and it is the clean way to get the hardest data, because the *human* reads the gated
pages in their own browser, never the tool.

Where a field can't be filled even after Phase 3, **tell the student we couldn't find it.**
"We looked and found nothing" is a different, more honest statement than a blank cell, and
the dashboard says which one it is. The professor is never dropped.

---

## Stage 4 — People around the professor

Surface the professor's **collaborators** and — **only where the country's thesis registry is
confirmed to name advisors** (France's theses.fr does; most registries do not; Canada is
unverified) — their **former doctoral students**, from public sources only, with links intact.
Where the registry has no advisor field, former-students is simply absent, never inferred, and
`recent_collaborators` stands in, always labelled as *not* students
([D-062](DECISIONS.md#d-062--former_doctoral_students-is-a-per-registry-advisor-verified-capability--not-a-universal-headline)).
This is **display-only and never exported**: no inferred attributes, no evaluative "rating" of
an individual student in any share path, and no claim about who is in a lab *right now*
([D-016](DECISIONS.md#d-016--students-is-not-obtainable-ship-recent_collaborators-instead),
[D-024](DECISIONS.md#d-024--evaluative-judgements-about-individuals-stay-local-and-unexported),
[D-025](DECISIONS.md#d-025--past-students-are-obtainable-current-students-still-are-not)).
The panel can be sorted locally (by recency, by output) to help the student read the lab; that
sort is an annotation, not a judgement that leaves the machine.

---

## The dashboard

**Generated after Phase 2 — never blocked waiting on you**
([D-049](DECISIONS.md#d-049--terminal-run-states-the-dashboard-is-never-blocked-on-the-human)).
The human rung (Phase 3) is optional enrichment, not a gate: you get a usable dashboard
immediately, with any still-open gaps marked. If you return the Markdown later, it fills the
gaps and re-exports; if you never do, the run simply finalises with those gaps shown honestly.
A search that matches no one renders an empty-state view that says *why* — "no professors
matched" vs "the country's sources returned nothing" — rather than a blank page.

It is **generic** — it adapts to whatever fields the search actually produced, rather than
assuming a fixed column set.

- Click any professor → full detail, every link, every source.
- Dynamic filtering and sorting across all fields; custom filters can be added on request.
- Three visible, first-class states per field: a real **value**, **"we looked, found
  nothing"**, and **"not yet reached / awaiting your browser"** — never conflated.
- A **deadline view** answering the applicant's real first question — *what closes soon* — as a
  cross-professor sort by soonest relevant deadline, with the domestic-vs-international split
  (often months apart) shown prominently and an `.ics` export. A not-yet-published or
  projected-from-last-year deadline is shown as a **watch date, never a firm one** — missing a
  changed deadline is the worst thing this view could cause
  ([D-061](DECISIONS.md#d-061--a-deadline--urgency-view)).
- Delivered as a **single self-contained HTML file with embedded JSX/React**
  ([D-033](DECISIONS.md#d-033--dashboard-technology)) — a component model and virtualised
  lists (so thousands of rows stay smooth) without a separate build project. One file the
  student can open, keep, and share.

**The dashboard is Claude-interactive**
([D-041](DECISIONS.md#d-041--the-dashboard-is-claude-interactive)). The scan also writes the
data as clean JSON, so the student's Claude session can read it: ask questions about the
professors in plain language, and ask Claude to change or extend the dashboard UI on the
spot. The dashboard is a living artifact the student and Claude keep working on together,
not a frozen report.

---

## What this means for the build

The project's centre of gravity is the **skill + agents + tools**, exactly as Ahmed framed
it. The pipeline stages above map to agents and tools; the dashboard is a template the
tools fill and Claude then edits. The two honest tensions this flow creates with the
research are recorded in
[D-039](DECISIONS.md#d-039--agent-driven-web-navigation-is-first-class-apis-are-the-fast-path)
(how the agent actually fetches) and the students guardrail above — both resolved in a way
that keeps the vision intact.
