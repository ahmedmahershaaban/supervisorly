# P0 — ORCID employments *(cheapest real content)*

← [`README.md`](README.md) · [`00-invariants.md`](00-invariants.md) · gate: **SPIKE-0** in [`01-spikes.md`](01-spikes.md)

**Why this is first**: it is the only phase that produces real professor content with no model,
no rendering and no crawling. ORCID states role, department and organisation as *structured
fields* — asking a model to infer them from prose would be strictly worse.

Measured, live, on a real Cairo professor:

```
organisation : Ain Shams University Faculty of Medicine
role title   : Professor
department   : Community, Environmental and Occupational Medicine
```

**Gate**: SPIKE-0 must show **≥ 30%** of shortlisted professors have an ORCID with a *current*
employment. Below that, P0 is cosmetic — re-plan.

---

## P0-1 · ORCID employments client `[ ]`

**Files**: `src/supervisorly/discover/orcid.py`, `tests/test_orcid.py`

- [ ] P0-1.1 `employments_url(orcid_id)` → `{PUB_API}/{id}/employments`
- [ ] P0-1.2 Parse `<employment:employment-summary>` → organisation, `role-title`,
      `department-name`, start/end date. Namespace-aware, mirroring the existing
      researcher-urls parser
- [ ] P0-1.3 **Split current from past on `end-date` presence.** Showing a post someone left in
      2019 as current is a correctness bug, not a cosmetic one
- [ ] P0-1.4 Keep **all** concurrent appointments — joint posts are common and picking one is a
      guess the data does not support
- [ ] P0-1.5 Failure / 404 / unparseable → `[]` plus `failed_lookups`; never raises
- [ ] P0-1.6 Tests: an end-dated post is past; two concurrent posts are both kept; malformed XML
      yields empty rather than fatal

**Edge cases** (from [`../PLAN_HARVEST_REVIEW.md`](../PLAN_HARVEST_REVIEW.md))
- Record visibility limited or fields private → absent is **not** false → `searched_absent`
- ORCID 429/5xx → back off, skip that professor, continue. One registry hiccup costs one profile
- Organisation name disagrees with ROR/OpenAlex — measured: `"Egyptian Government"`. **Do not
  reconcile.** Cite ORCID for what ORCID said; the conflicts table already records disagreement

**Review** `[ ]`

---

## P0-2 · Wire into the pipeline `[ ]`

**Files**: `src/supervisorly/pipeline.py`, `tests/test_profile_export.py`

- [ ] P0-2.1 `_attach_employments(targets, orcid_client)` beside the existing
      `_attach_recent_works`
- [ ] P0-2.2 **Shortlist only**, one call per professor, with an attempted flag in the same
      style as `works_checked` — so "not looked up" is distinguishable from "looked, none there"
- [ ] P0-2.3 `_profile_for` carries `employments_current` and `employments_past`
- [ ] P0-2.4 Ledger row via CC-1

**Review** `[ ]`

---

## P0-3 · Show it `[ ]`

**Files**: `src/supervisorly/export/dashboard.py`, `src/supervisorly/export/json_export.py`,
`tests/test_dashboard_actions.py`

- [ ] P0-3.1 Modal identity block: role + department + organisation, **current first**
- [ ] P0-3.2 Past appointments collapsed and labelled "former"
- [ ] P0-3.3 Source line: *"from their ORCID record"* — registry metadata, **not** quote-verified
      evidence. Keep the existing disclaimer discipline; this block sits beside quote-gated
      fields and must say which it is
- [ ] P0-3.4 `_redact_profile` covers the new fields

**Acceptance** — a professor with a current post shows role and department; one with only a
former post never shows it as current.

**Review** `[ ]`
