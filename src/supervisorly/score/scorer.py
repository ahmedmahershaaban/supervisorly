"""Ranking — hard gates, then a transparent weighted score (architecture §5).

Three properties from the independent review are enforced here:

* **Intent-aware gates (D-059)** — which hard gates apply depends on ``intent_kind``.
  A ``pre_phd``/RA seeker is *not* gated on degree-route or language bands (those are
  Master/PhD admission facts); gating them there breaks the pre-PhD case.
* **Topic-ID research-fit (D-058)** — ``topic_match`` is deterministic overlap of
  OpenAlex topic IDs, so "causal NLP" still matches a professor tagged "NLP" + "causal
  inference" separately. No brittle string matching.
* **Reconcile before you rank (D-057)** — a fragmented (non-Western-name) profile is
  reconciled first, and disambiguation risk lowers the *score confidence*, never the
  activity — otherwise the names the project exists to serve are wrongly dropped.

The exact weights are a first cut, tunable later; the *method* is the point.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Which hard gates apply, per intent (D-059).
INTENT_GATES: dict[str, list[str]] = {
    "training":    ["availability"],
    "pre_master":  ["availability", "remote_ok"],
    "pre_phd":     ["availability", "remote_ok"],
    "mentor":      ["availability"],
    "master":      ["degree_route", "language_band", "enrolment", "funding"],
    "phd":         ["degree_route", "language_band", "enrolment", "funding"],
    "postdoc":     ["phd_in_hand", "funding"],
}
# Only these confidences may fire a hard gate (D-047).
GATE_ELIGIBLE_CONFIDENCE = {"quoted_official", "derived"}

DEFAULT_WEIGHTS = {
    "topic_match": 0.40,
    "recruiting":  0.30,
    "funding":     0.15,
    "activity":    0.15,
}


def gates_for(intent_kind: str) -> list[str]:
    return INTENT_GATES.get(intent_kind, ["availability"])


def topic_match(prof_topic_ids, plan_topic_ids) -> float:
    """Fraction of the plan's topics the professor covers (deterministic ID overlap)."""
    plan = set(plan_topic_ids or [])
    if not plan:
        return 0.0
    return len(plan & set(prof_topic_ids or [])) / len(plan)


def reconcile_works(candidate_profiles: list[dict]) -> dict:
    """Merge fragmented author profiles into one works view (union topics, summed works).
    Used when ``disambig_risk`` is high so a split profile is not read as inactive (D-057)."""
    topic_ids: set = set()
    works = 0
    recent = 0
    for p in candidate_profiles or []:
        topic_ids |= set(p.get("topic_ids", []))
        works += int(p.get("works_count", 0))
        recent += int(p.get("recent_works", 0))
    return {"topic_ids": topic_ids, "works_count": works, "recent_works": recent,
            "reconciled": bool(candidate_profiles)}


def evaluate_eligibility(intent_kind: str, facts: dict, confidences: dict) -> tuple[str, list[str]]:
    """Return (verdict, blockers). Only gate-eligible-confidence *failing* facts block;
    unknown or low-confidence facts never block (D-023, D-047) — they sort/warn instead."""
    gates = gates_for(intent_kind)
    blockers = []
    for g in gates:
        val = facts.get(g)  # True pass, False fail, None unknown
        if val is False and confidences.get(g) in GATE_ELIGIBLE_CONFIDENCE:
            blockers.append(g)
    if blockers:
        return "blocked", blockers
    if all(facts.get(g) is not None for g in gates):
        return "eligible", []
    return "unknown", []


@dataclass
class FitResult:
    person_id: str
    eligibility_verdict: str
    blockers: list[str]
    components: dict[str, float]
    score_total: float
    tier: int
    confidence_of_score: float
    reconciled: bool = False
    evidence_count: int = 0


def _tier(score: float) -> int:
    if score >= 0.75:
        return 1
    if score >= 0.55:
        return 2
    if score >= 0.35:
        return 3
    return 4


def score_professor(prof: dict, plan: dict, weights: dict | None = None) -> FitResult:
    """Score one professor against the plan. ``prof`` carries topic_ids/works, optional
    ``candidate_profiles`` + ``disambig_risk``, ``eligibility_facts`` + ``gate_confidences``,
    and precomputed ``recruiting``/``funding`` component signals in [0,1]."""
    weights = weights or DEFAULT_WEIGHTS

    if prof.get("disambig_risk") == "high" and prof.get("candidate_profiles"):
        recon = reconcile_works(prof["candidate_profiles"])
        topic_ids, works = recon["topic_ids"], recon["works_count"]
        reconciled = True
    else:
        topic_ids = set(prof.get("topic_ids", []))
        works = int(prof.get("works_count", 0))
        reconciled = False

    activity = min(1.0, works / 40.0)  # simple, monotonic first cut
    components = {
        "topic_match": topic_match(topic_ids, plan.get("resolved_topic_ids")),
        "recruiting":  float(prof.get("recruiting", 0.0)),
        "funding":     float(prof.get("funding", 0.0)),
        "activity":    activity,
    }
    total = sum(components[k] * weights.get(k, 0.0) for k in components)

    # confidence-of-score: sparse evidence and disambiguation risk lower it, never the score
    evidence = int(prof.get("evidence_count", 0))
    conf = min(1.0, evidence / 12.0) if evidence else 0.2
    if prof.get("disambig_risk") == "high":
        conf *= 0.7  # D-057: risk lowers score confidence, not activity

    verdict, blockers = evaluate_eligibility(
        plan.get("intent_kind", "pre_phd"),
        prof.get("eligibility_facts", {}),
        prof.get("gate_confidences", {}),
    )
    return FitResult(
        person_id=prof.get("id", "?"),
        eligibility_verdict=verdict,
        blockers=blockers,
        components=components,
        score_total=round(total, 4),
        tier=_tier(total),
        confidence_of_score=round(conf, 4),
        reconciled=reconciled,
        evidence_count=evidence,
    )
