"""Phase L4 — university + professor ranking: deterministic, re-weightable, reconciles fragmented
profiles (D-057), and does not gate a pre_phd search on PhD-admission rules (D-059)."""

from supervisorly.score import ranking

PLAN = {"intent_kind": "pre_phd", "resolved_topic_ids": ["T1", "T2"]}


def _prof(pid, inst, topics, works, recruiting):
    return {"id": pid, "institution": inst, "topic_ids": topics, "works_count": works,
            "recruiting": recruiting, "funding": 0.0, "evidence_count": 8}


PROFS = [
    _prof("a", "Maple University", ["T1", "T2"], 40, 1.0),    # strong fit + recruiting
    _prof("b", "Maple University", ["T1"], 20, 0.0),          # ok fit, not recruiting
    _prof("c", "Northern Institute", ["T3"], 5, 0.0),         # weak fit
]


def test_rank_professors_orders_best_first():
    ranked = ranking.rank_professors(PROFS, PLAN)
    assert [f.person_id for f in ranked][0] == "a"           # best fit + recruiting on top
    assert ranked[-1].person_id == "c"                       # weakest last


def test_rank_universities_aggregates_and_orders():
    unis = ranking.rank_universities(PROFS, PLAN)
    names = [u["institution"] for u in unis]
    assert names[0] == "Maple University"                    # two strong supervisors
    maple = unis[0]
    assert maple["professor_count"] == 2
    assert maple["recruiting_fraction"] == 0.5               # 1 of 2 recruiting
    assert set(maple["members"]) == {"a", "b"}


def test_ranking_is_reweightable():
    # weighting recruiting heavily vs fit changes the transparent university score
    fit_heavy = ranking.rank_universities(PROFS, PLAN,
                                          uni_weights={"fit": 1.0, "recruiting": 0.0, "activity": 0.0})
    rec_heavy = ranking.rank_universities(PROFS, PLAN,
                                          uni_weights={"fit": 0.0, "recruiting": 1.0, "activity": 0.0})
    maple_fit = next(u for u in fit_heavy if u["institution"] == "Maple University")
    maple_rec = next(u for u in rec_heavy if u["institution"] == "Maple University")
    assert maple_fit["university_score"] != maple_rec["university_score"]


def test_sparse_university_has_lower_confidence():
    unis = ranking.rank_universities(PROFS, PLAN)
    maple = next(u for u in unis if u["institution"] == "Maple University")
    northern = next(u for u in unis if u["institution"] == "Northern Institute")
    # Maple has 2 supervisors, Northern 1 → Northern's confidence is not inflated
    assert northern["confidence"] <= maple["confidence"]


def test_fragmented_profile_is_reconciled_not_dropped():
    frag = {"id": "f", "institution": "Split U", "disambig_risk": "high",
            "candidate_profiles": [{"topic_ids": ["T1"], "works_count": 15},
                                   {"topic_ids": ["T2"], "works_count": 12}],
            "recruiting": 1.0, "evidence_count": 6}
    ranked = ranking.rank_professors([frag], PLAN)
    assert len(ranked) == 1 and ranked[0].reconciled is True   # merged, present, not dropped


def test_pre_phd_is_not_gated_on_phd_admission_rules():
    # a pre_phd professor with a failing degree_route fact must NOT be gated (D-059)
    p = {"id": "x", "institution": "U", "topic_ids": ["T1"], "works_count": 10,
         "recruiting": 1.0, "evidence_count": 5,
         "eligibility_facts": {"degree_route": False},
         "gate_confidences": {"degree_route": "quoted_official"}}
    fit = ranking.rank_professors([p], PLAN)[0]
    assert fit.eligibility_verdict != "blocked"               # pre_phd ignores degree_route
