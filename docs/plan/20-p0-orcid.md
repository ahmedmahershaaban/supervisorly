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

# SPIKE-0 RESULT, 2026-07-29 — **MISS (22%)**. P0 is NOT built.

`tools/spikes/spike_orcid_employments.py`, three cohorts, each the real shortlist a scan
produces (country → ROR → OpenAlex authors **filtered by the plan's topics** → the same
`_apply_shortlist` gate):

| cohort | shortlisted | current | no ORCID at all | ORCID but no employment listed | past only | **share** |
|---|---|---|---|---|---|---|
| EG · cardiovascular disease | 40 | 11 | 21 | 7 | 1 | **28%** |
| CA · machine learning | 40 | 11 | 15 | 14 | 0 | **28%** |
| DE · water treatment | 27 | 2 | 23 | 2 | 0 | **7%** |
| **pooled** | **107** | **24** | 59 | 23 | 1 | **22%** |

Zero lookup failures in all three runs, so this is a measurement of the data, not of a bad
network hour.

**The binding constraint is not employments — it is ORCID presence.** 59 of 107 shortlisted
professors (55%) carry **no ORCID at all** on their OpenAlex record. *Given* an ORCID, a
current employment is there 44–58% of the time, which is a perfectly good hit rate; it is
simply applied to half a cohort. Widening the employments parser cannot move this number.

**A fourth run is recorded as a warning, not as evidence.** The first attempt used
`--field cardiology`, which OpenAlex resolves to **zero** topics, so the enumeration was
unfiltered and returned Egypt's most prominent physicists and oceanographers. That cohort
scored **68%** — prominent people have complete records. It is the exact error
[`01-spikes.md`](01-spikes.md) records twice already, reproduced here on the first try.
Anyone re-running this must confirm the `topics N` line in the header is non-zero.

**What P0 would actually have delivered**: role and department for roughly one shortlisted
professor in five. Not nothing — but it is the cheapest phase precisely because it is the
smallest, and 22% does not clear the bar this gate was written to enforce.

**Re-plan directions**, none of them started:
- The honest cheap win may be *institution* (already held from OpenAlex/ROR for everyone),
  not *role/department* from ORCID.
- ORCID's `search` endpoint can resolve a name + affiliation to an iD, which could lift the
  55% who carry none — but that is identity matching, i.e. P2-3's dangerous work, and it
  needs P2-3's `verified`/`unverified`/refuse discipline before it may be presented.
- If P2 lands, re-run this spike: its cohort may carry ORCIDs at a different rate.

Every task below stays `[!]`. Do not build them without a fresh spike that clears 30%.

---

## P0-1 · ORCID employments client `[!]` blocked — SPIKE-0 = 22%, gate is 30%

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

## P0-2 · Wire into the pipeline `[!]` blocked — SPIKE-0 = 22%, gate is 30%

**Files**: `src/supervisorly/pipeline.py`, `tests/test_profile_export.py`

- [ ] P0-2.1 `_attach_employments(targets, orcid_client)` beside the existing
      `_attach_recent_works`
- [ ] P0-2.2 **Shortlist only**, one call per professor, with an attempted flag in the same
      style as `works_checked` — so "not looked up" is distinguishable from "looked, none there"
- [ ] P0-2.3 `_profile_for` carries `employments_current` and `employments_past`
- [ ] P0-2.4 Ledger row via CC-1

**Review** `[ ]`

---

## P0-3 · Show it `[!]` blocked — SPIKE-0 = 22%, gate is 30%

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
