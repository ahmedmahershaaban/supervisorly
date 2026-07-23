"""Phase E DoD: the three review fixes are real — intent-aware gates (D-059),
topic-ID overlap incl. interdisciplinary (D-058), and works reconciliation so a
fragmented non-Western profile is not wrongly dropped (D-057)."""

from supervisorly.score import scorer as sc


def test_topic_match_is_id_overlap_and_interdisciplinary_safe():
    plan_ids = ["T_nlp", "T_causal"]
    # a professor tagged with the two sub-areas separately still fully matches
    assert sc.topic_match(["T_nlp", "T_causal", "T_ml"], plan_ids) == 1.0
    assert sc.topic_match(["T_nlp"], plan_ids) == 0.5
    assert sc.topic_match(["T_vision"], plan_ids) == 0.0


def test_pre_phd_not_gated_on_phd_admission_rules():
    """The pre-PhD trace: an RA/pre-PhD seeker must NOT be blocked by direct-entry or
    language rules that don't apply to them (D-059)."""
    facts = {"degree_route": False, "language_band": False,  # would block a PhD applicant
             "availability": True, "remote_ok": True}
    conf = {k: "quoted_official" for k in facts}

    pre = sc.evaluate_eligibility("pre_phd", facts, conf)
    assert pre == ("eligible", [])            # not gated on degree/language

    phd = sc.evaluate_eligibility("phd", facts, conf)
    assert phd[0] == "blocked"
    assert set(phd[1]) >= {"degree_route", "language_band"}


def test_unreliable_gate_fact_does_not_block():
    """A failing gate fact with low confidence sorts/warns, never blocks (D-023/D-047)."""
    facts = {"degree_route": False, "language_band": True, "enrolment": True, "funding": True}
    conf = {"degree_route": "inferred", "language_band": "quoted_official",
            "enrolment": "quoted_official", "funding": "quoted_official"}
    verdict, blockers = sc.evaluate_eligibility("phd", facts, conf)
    assert verdict == "eligible" and blockers == []   # inferred fail does not gate


def test_fragmented_profile_is_reconciled_not_dropped():
    """A non-Western name split across OpenAlex profiles: reconcile the works first, so
    the professor scores on the union and is not wrongly dropped from the shortlist,
    while disambiguation risk lowers score *confidence* not activity (D-057)."""
    plan = {"intent_kind": "phd", "resolved_topic_ids": ["T_nlp", "T_causal"]}
    fragmented = {
        "id": "p1", "disambig_risk": "high",
        "candidate_profiles": [
            {"topic_ids": ["T_nlp"], "works_count": 20, "recent_works": 5},
            {"topic_ids": ["T_causal"], "works_count": 13, "recent_works": 3},
            {"topic_ids": ["T_ml"], "works_count": 10, "recent_works": 2},
        ],
        "recruiting": 0.5, "funding": 0.5, "evidence_count": 8,
        "eligibility_facts": {}, "gate_confidences": {},
    }
    r = sc.score_professor(fragmented, plan)
    assert r.reconciled is True
    # union topics fully cover the plan -> topic_match 1.0 (would be 0.5 unreconciled)
    assert r.components["topic_match"] == 1.0
    # summed works (43) -> full activity, not the 20 of a single fragment
    assert r.components["activity"] == 1.0
    # risk lowered the confidence, not the score
    clean = dict(fragmented, disambig_risk=None,
                 topic_ids=["T_nlp", "T_causal", "T_ml"], works_count=43,
                 candidate_profiles=None)
    rc = sc.score_professor(clean, plan)
    assert r.score_total == rc.score_total          # same score
    assert r.confidence_of_score < rc.confidence_of_score  # lower confidence


def test_score_is_reweightable():
    plan = {"intent_kind": "phd", "resolved_topic_ids": ["T_nlp"]}
    prof = {"id": "p", "topic_ids": ["T_nlp"], "works_count": 40, "recruiting": 0.0,
            "funding": 0.0, "evidence_count": 12}
    topic_heavy = sc.score_professor(prof, plan, weights={"topic_match": 1.0}).score_total
    recruit_heavy = sc.score_professor(prof, plan, weights={"recruiting": 1.0}).score_total
    assert topic_heavy == 1.0 and recruit_heavy == 0.0   # weights drive the ranking
