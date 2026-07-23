"""University + professor ranking (D-031/D-057/D-059) — transparent, re-weightable, deterministic.

Reuses ``score_professor`` for the per-supervisor score, then **rolls professors up to their
institution** so a university is ranked by the strength + recruiting + activity of its supervisors.
Confidence is **lowered (never faked)** when the evidence is thin (few supervisors / sparse
signals). A fragmented (non-Western) profile is reconciled by the scorer before it counts (D-057);
intent-aware gates mean a ``pre_phd`` search is not gated on PhD-admission rules (D-059).
"""

from __future__ import annotations

from .scorer import score_professor

# Re-weightable institution weights (the *method* is the point, the numbers are a first cut).
UNIVERSITY_WEIGHTS = {"fit": 0.5, "recruiting": 0.3, "activity": 0.2}


def rank_professors(professors: list[dict], plan: dict, weights: dict | None = None):
    """Score and sort professors, best first. Each ``prof`` carries the scorer inputs
    (topic_ids/works/recruiting/eligibility_facts/…)."""
    scored = [score_professor(p, plan, weights) for p in professors]
    scored.sort(key=lambda f: (f.score_total, f.confidence_of_score), reverse=True)
    return scored


def rank_universities(professors: list[dict], plan: dict, *, weights: dict | None = None,
                      uni_weights: dict | None = None) -> list[dict]:
    """Aggregate scored professors into ranked universities (D-031).

    Each professor carries an ``institution`` name plus the scorer inputs. Returns institution
    rows (best first) with a transparent, re-weightable ``university_score`` and an honest
    ``confidence`` that reflects how much evidence backs it.
    """
    uw = uni_weights or UNIVERSITY_WEIGHTS
    by_inst: dict[str, list] = {}
    for p in professors:
        inst = p.get("institution") or "Unknown"
        fit = score_professor(p, plan, weights)
        by_inst.setdefault(inst, []).append((fit, float(p.get("recruiting", 0.0))))

    out = []
    for inst, members in by_inst.items():
        n = len(members)
        # Roll up from INDEPENDENT axes — research fit (topic_match), recruiting, activity — NOT
        # from score_total (which already blends recruiting+activity in), so uni_weights genuinely
        # re-weights each signal and zeroing one axis truly isolates it (audit finding).
        mean_fit = sum(f.components.get("topic_match", 0.0) for f, _ in members) / n
        recruiting_fraction = sum(1 for _, r in members if r >= 0.5) / n
        activity = sum(f.components.get("activity", 0.0) for f, _ in members) / n
        uni_score = (uw["fit"] * mean_fit + uw["recruiting"] * recruiting_fraction
                     + uw["activity"] * activity)
        # more supervisors + more per-professor evidence → higher confidence; sparse → lower
        breadth = min(1.0, n / 5.0)
        mean_conf = sum(f.confidence_of_score for f, _ in members) / n
        out.append({
            "institution": inst,
            "professor_count": n,
            "mean_fit": round(mean_fit, 4),
            "recruiting_fraction": round(recruiting_fraction, 4),
            "activity": round(activity, 4),
            "university_score": round(uni_score, 4),
            "confidence": round(breadth * mean_conf, 4),
            "members": [f.person_id for f, _ in members],
        })
    out.sort(key=lambda u: (u["university_score"], u["confidence"]), reverse=True)
    return out
