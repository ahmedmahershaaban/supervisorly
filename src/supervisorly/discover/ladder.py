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


def _norm(s: str | None) -> str:
    return (s or "").strip().lower()


def _country_of(plan: dict) -> str | None:
    return plan.get("country") or (plan.get("countries") or [None])[0]


def resolve_topic_ids(plan: dict, oa) -> list[str]:
    """The plan's topic IDs, or resolve them from the free-text field via OpenAlex (D-058)."""
    ids = list(plan.get("resolved_topic_ids") or [])
    if ids:
        return ids
    field = plan.get("field") or plan.get("subfield")
    return oa.topic_ids(field) if field else []


def select_institutions(plan: dict, ror) -> list[dict]:
    """Institutions for the plan's country, honouring ``university_mode`` (all/prioritise/only, D-045).

    ``all`` (default) = everything ROR finds; ``only`` = just the named universities; ``prioritise``
    = the named ones first, then the rest (nobody dropped).
    """
    country = _country_of(plan)
    insts = ror.institutions_in_country(country) if country else []
    mode = plan.get("university_mode", "all")
    wanted = [_norm(u) for u in (plan.get("universities") or []) if _norm(u)]

    def matches(inst: dict) -> bool:
        name, rid = _norm(inst.get("name")), _norm(inst.get("ror_id"))
        return any(w in name or (rid and w in rid) for w in wanted)

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
    return [seen[k] for k in order]


def build_targets(plan: dict, ror, oa) -> dict:
    """Round 1 end to end: {plan (with resolved topics), institutions, targets}."""
    plan = dict(plan)
    plan["resolved_topic_ids"] = resolve_topic_ids(plan, oa)
    institutions = select_institutions(plan, ror)
    targets = enumerate_professors(institutions, oa)
    return {"plan": plan, "institutions": institutions, "targets": targets}
