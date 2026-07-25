"""The discovery ladder (D-028) — a confirmed SearchPlan → professor targets (Round 1).

Generate, don't look up (D-038): institutions come from ROR by country, topic IDs from OpenAlex
by field, professors from OpenAlex authors-by-institution — **no hardcoded list**. Fragmented
author identities are reconciled here (D-057) so a split profile becomes one target, not two or
none. Nothing is dropped for missing data. Login-walled *institutional* pages are handled later
by the deep-dive fetcher + roster triage + human rung (D-052/D-044) — never scraped here.

Round 2 (deep-dive) reuses the existing ``Fetcher`` on each target's own pages; that lives in the
live driver (Phase L2), not here.
"""

from __future__ import annotations

import re
import unicodedata


def _norm(s: str | None) -> str:
    """Case/diacritic-insensitive fold: NFKD-decompose, drop combining marks, casefold — so an
    accentless user spelling ("Universite de Montreal", "Universitat Munchen") still matches the
    accented ROR name ("Université de Montréal", "Ludwig-Maximilians-Universität München")."""
    nfkd = unicodedata.normalize("NFKD", s or "")
    return "".join(c for c in nfkd if not unicodedata.combining(c)).casefold().strip()


def _country_of(plan: dict) -> str | None:
    return plan.get("country") or (plan.get("countries") or [None])[0]


def resolve_topic_ids(plan: dict, oa) -> list[str]:
    """The plan's topic IDs, or resolve them from the free-text field via OpenAlex (D-058)."""
    ids = list(plan.get("resolved_topic_ids") or [])
    if ids:
        return ids
    field = plan.get("field") or plan.get("subfield")
    return oa.topic_ids(field) if field else []


def _matches(inst: dict, w: str) -> bool:
    """One named-university token against one institution: word-boundary match on the name (so
    "york" ≠ "yorkshire") + exact ROR-id segment match, not naive substring containment (audit
    finding). A genuinely ambiguous single token (e.g. "york" vs "New York") may still match
    both — the user should name it more fully."""
    name, rid = _norm(inst.get("name")), _norm(inst.get("ror_id"))
    rid_seg = rid.rsplit("/", 1)[-1] if rid else ""
    if re.search(r"\b" + re.escape(w) + r"\b", name):
        return True
    return bool(rid_seg) and rid_seg == w


def select_institutions(plan: dict, ror, *, warnings: list[str] | None = None) -> list[dict]:
    """Institutions for the plan's country, honouring ``university_mode`` (all/prioritise/only, D-045).

    ``all`` (default) = everything ROR finds; ``only`` = just the named universities; ``prioritise``
    = the named ones first, then the rest (nobody dropped).

    When a ``warnings`` list is passed and NONE of the named universities matched anything ROR
    returned (only/prioritise), a "0 of N" warning is appended — a typo'd or diacritic-mismatched
    name must surface, not silently narrow the scan (the run still continues).
    """
    country = _country_of(plan)
    insts = ror.institutions_in_country(country) if country else []
    mode = plan.get("university_mode", "all")
    if mode not in ("all", "prioritise", "only"):
        # Fail loud (D-002): falling through to "all" would silently INVERT the scope a plan
        # asked for ("only these universities" -> the whole country). The CLI validates plan
        # values up front; this is the defense-in-depth net for direct callers.
        raise ValueError(f"unrecognized university_mode {mode!r} - expected one of: "
                         "all, prioritise, only")
    wanted = [_norm(u) for u in (plan.get("universities") or []) if _norm(u)]

    def matches(inst: dict) -> bool:
        return any(_matches(inst, w) for w in wanted)

    if warnings is not None and wanted and mode != "all":
        if not any(matches(i) for i in insts):
            warnings.append(
                f"0 of {len(wanted)} named universities matched the ROR institutions for "
                f"{country} - check the spellings against ROR names; run continues "
                f"(university_mode={mode!r}).")

    if mode == "only":
        return [i for i in insts if matches(i)]
    if mode == "prioritise":
        return [i for i in insts if matches(i)] + [i for i in insts if not matches(i)]
    return insts


def _reconcile_into(target: dict, author: dict, inst_name: str | None) -> None:
    """Merge a duplicate author sighting into an existing target (D-057 — don't split a profile)."""
    if inst_name and inst_name not in target["institution_names"]:
        target["institution_names"].append(inst_name)
    for t in author.get("topic_ids", []):
        if t and t not in target["topic_ids"]:
            target["topic_ids"].append(t)
    target["works_count"] = max(target["works_count"], int(author.get("works_count") or 0))


def _merge_split_profiles(targets: list[dict]) -> list[dict]:
    """Post-pass ORCID reconciliation (D-030/D-057): one person fragmented by OpenAlex into two
    author-ids with the SAME ORCID is a split profile — where an ORCID exists it wins. Merge
    BEFORE scoring: union topics/institutions, SUM works_count (the fragments' works are
    disjoint — unlike ``_reconcile_into``'s max, which is right only for same-id re-sightings),
    and keep every OpenAlex id in ``merged_openalex_ids``. A shared name+homepage WITHOUT an
    ORCID is not decisive identity evidence (OpenAlex disambiguation is weak, D-030) — those
    stay two targets, flagged to the human rung rather than silently merged."""
    by_orcid: dict[str, dict] = {}
    out: list[dict] = []
    for t in targets:
        orcid = (t.get("orcid") or "").strip().lower()
        if orcid and orcid in by_orcid:
            keep = by_orcid[orcid]
            for n in t["institution_names"]:
                if n not in keep["institution_names"]:
                    keep["institution_names"].append(n)
            for tid in t["topic_ids"]:
                if tid not in keep["topic_ids"]:
                    keep["topic_ids"].append(tid)
            keep["works_count"] += t["works_count"]
            ids = keep.setdefault("merged_openalex_ids", [keep["openalex_id"]])
            if t.get("openalex_id") and t["openalex_id"] not in ids:
                ids.append(t["openalex_id"])
            continue
        if orcid:
            by_orcid[orcid] = t
        out.append(t)
    return out


def enumerate_professors(institutions: list[dict], oa) -> list[dict]:
    """Round-1 professor targets across the institutions, de-duplicated/reconciled by identity."""
    seen: dict[str, dict] = {}
    order: list[str] = []
    for inst in institutions:
        oa_inst = oa.institution_by_ror(inst.get("ror_id"))
        if not oa_inst:
            continue
        for a in oa.authors_by_institution(oa_inst):
            key = a.get("short_id") or _norm(a.get("name"))
            if not key:
                continue
            if key in seen:
                _reconcile_into(seen[key], a, inst.get("name"))
                continue
            seen[key] = {
                "id": a.get("short_id") or key,
                "name": a.get("name"),
                "url": a.get("homepage"),           # their own page (may be None → deep-dive handles)
                "openalex_id": a.get("openalex_id"),
                "orcid": a.get("orcid"),
                "ror_id": inst.get("ror_id"),
                "institution_names": [inst.get("name")] if inst.get("name") else [],
                "topic_ids": list(a.get("topic_ids") or []),
                "works_count": int(a.get("works_count") or 0),
                "cited_by_count": int(a.get("cited_by_count") or 0),
            }
            order.append(key)
    return _merge_split_profiles([seen[k] for k in order])


def build_targets(plan: dict, ror, oa) -> dict:
    """Round 1 end to end: {plan (with resolved topics), institutions, targets, truncated, warnings}.

    ``truncated`` lists any source whose enumeration hit the page cap (more results existed), so
    the run coverage can say so honestly rather than claiming completeness while truncating (D-037).
    ``warnings`` carries non-fatal discovery-scope notes (e.g. 0 of N named universities matched)
    that must reach the user instead of silently narrowing the scan.
    """
    plan = dict(plan)
    plan["resolved_topic_ids"] = resolve_topic_ids(plan, oa)
    warnings: list[str] = []
    institutions = select_institutions(plan, ror, warnings=warnings)
    targets = enumerate_professors(institutions, oa)
    truncated = sorted(set(getattr(ror, "truncated_sources", []))
                       | set(getattr(oa, "truncated_sources", [])))
    return {"plan": plan, "institutions": institutions, "targets": targets,
            "truncated": truncated, "warnings": warnings}
