# P1 — Institution admissions pages *(biggest yield per fetch)*

← [`README.md`](README.md) · [`00-invariants.md`](00-invariants.md) · gate: **SPIKE-1** in [`01-spikes.md`](01-spikes.md)

**Size: L · Risk: HIGH.** Together with P2 this carries most of the plan's risk.

## Why this exists

**A deadline is not a property of a professor.** Application deadlines, eligibility, language
bands and funding rules are institutional or departmental — one graduate-admissions page governs
every professor in that faculty.

Reading 25 professor pages to find a deadline is 25 fetches for a fact on none of them. Reading
one admissions page yields it for all 25, and those pages are few, stable, and written to be
read.

**Gate**: SPIKE-1 must show **≥ 40%** of institutions expose a findable admissions page in HTML.

---

# SPIKE-1 RESULT, 2026-07-29 — **MISS (0% on the real cohort)**. P1 is NOT built.

`tools/spikes/spike_admissions.py`. Starts at the homepage ROR gave us and walks links that
exist on pages it actually fetched — never a guessed `/admissions` (D-038). Depth ≤ 3, 20
fetches per institution, robots-gated and rate-limited like any other visitor.

**Two cohorts, because they answer different questions.**

| cohort | found | share |
|---|---|---|
| **the cohort a real scan produces** (the sampling rule: ladder → shortlist → those professors' institutions) | | |
| EG · cardiovascular disease | 0/10 | 0% |
| CA · machine learning | 0/4 | 0% |
| **pooled — the number that gates P1** | **0/14** | **0%** |
| | | |
| *education-typed institutions only* (a different question) | | |
| EG | 4/10 | 40% |
| DE | 0/1 | n=1, not meaningful |

**The gate fails, but not because admissions pages are hard to find.** Where a university
exists and permits crawling, its postgraduate page was **one hop from the homepage**:
`asu.edu.eg/postgraduate` (Ain Shams) and `must.edu.eg/academic_programs/graduate-studies`
(Misr University) were both found at depth 1, in HTML, in a handful of fetches. P1-2's premise
is sound.

**The gate fails because the institutions a scan currently surfaces are not universities.**
Running the real ladder for CA + machine learning, the shortlisted professors' institutions
were Nexen, Purdue Pharma (Canada), Nutrition International and the Royal Canadian Military
Institute. For EG + cardiovascular disease they were Boehringer Ingelheim, the National Heart
Institute and four university *hospitals*. None of those grants degrees, so none has an
admissions page — 0% is the correct answer to the question as asked, and it says nothing
about P1.

Root cause measured and recorded as **[B-006](../BLOCKERS.md)**: `institutions_in_country`
takes ROR's first 100 per country in an order that is not relevance, and
`select_institutions` filters nothing. Education-typed institutions in that slice: **41/97
for Egypt, 5/100 for Canada, 1/98 for Germany.**

**Do not build P1 yet, and do not re-run this spike first.** Re-running it before B-006 is
resolved measures the same wrong cohort again. The order is: decide B-006 → re-run SPIKE-1 on
a cohort that contains universities → then this gate means something.

**Two things worth keeping from the run:**
- Robots refusal is common and legitimate: Cairo University, Port Said University and El
  Shorouk Academy all answer `Disallow: /` to our agent. P1's ledger row must count those
  separately from "no admissions page found" — they are different states and only one is a
  coverage gap we could close.
- Not one page found carried a *parseable* date (`has_date` 0/4). If P1 is eventually built,
  the deadline yield may be well below the page-discovery yield, and that deserves its own
  measurement rather than an assumption.

Every task below stays `[!]`.

---

## P1-1 · Institution-scoped claims `[!]` blocked — SPIKE-1 = 0% on the real cohort; see B-006

Claims are person-scoped today. This is the schema work that lets a fact belong to an
institution, a faculty or a programme.

**Files**: `src/supervisorly/model/schema.sql`, `src/supervisorly/model/claims.py`,
`tests/test_claims_institution.py` *(new)*

- [ ] P1-1.1 Confirm `entity_kind` supports `"institution"` — it is already a column, so this is
      an **additive migration only**; existing rows are not rewritten
- [ ] P1-1.2 Add a **scope** to the claim: `institution` / `faculty` / `programme`, plus the
      scope's own name
- [ ] P1-1.3 Tests: an institution-scope claim never silently becomes a person claim

**Review** `[ ]`

---

## P1-2 · Find the admissions pages `[!]` blocked — see the SPIKE-1 result above

**Files**: `src/supervisorly/discover/admissions.py` *(new)*, `tests/test_admissions.py` *(new)*

- [ ] P1-2.1 Start from the institution URL the ladder discovered, **extract links**, never
      guess paths (see [`00-invariants.md`](00-invariants.md) §2 — layouts differ per site and
      per country)
- [ ] P1-2.2 Classify a **fetched** page as admissions-relevant **from its text**, not its address
- [ ] P1-2.3 Depth ≤ 3, page budget per institution, robots, per-host serial (CC-3)
- [ ] P1-2.4 PDF → CC-5
- [ ] P1-2.5 Non-English → **do not skip**; hand to triage/model (P4/P5)

**Review** `[ ]`

---

## P1-3 · Extract and scope the facts `[!]` blocked — see the SPIKE-1 result above

**Files**: `src/supervisorly/pipeline.py`, `src/supervisorly/export/dashboard.py`,
`src/supervisorly/export/json_export.py`

- [ ] P1-3.1 Deadline / eligibility / language / funding recorded at the **narrowest scope
      actually discovered**
- [ ] P1-3.2 **A past date is historical, never a live deadline** — compare against today
- [ ] P1-3.3 Programme level undeterminable → **refuse the claim**. Wrong level is worse than none
- [ ] P1-3.4 Professors inherit it with the **institution named as the source and the scope
      shown** — never presented as the professor's own statement
- [ ] P1-3.5 Tests: a faculty-scope deadline never leaks to another faculty; a past date never
      renders as current

**Acceptance** — an institution deadline appears on its professors, labelled with its scope and
source, and is never shown as something the professor said.

**Review** `[ ]`

---

## Edge cases

| case | handling |
|---|---|
| **Deadlines differ per faculty and programme** | The dangerous one. One institution-wide deadline on every professor is fabrication-adjacent. Narrowest scope discovered; record it; never inherit across faculties |
| **An undergraduate page found instead of postgraduate** | Capture programme level explicitly; if undeterminable, refuse the claim |
| **Last cycle's page still published** | A past date shown as live is a serious error. It becomes historical evidence for P6 |
| **Admissions info published only as PDF** | CC-5. A scanned PDF blocks *with a reason* — silent invisibility is the failure to avoid |
| **Rolling admissions, no deadline exists** | `searched_absent` — the correct answer, not a miss |
| Institution has no website in ROR | Skip honestly; ledger row with the reason |
