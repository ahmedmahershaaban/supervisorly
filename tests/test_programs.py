"""Edge case: two great professors in the same department roll up to one program — one
application, one fee (D-031). A professor with no program stays its own group (no invented
shared program)."""

from supervisorly.score.programs import group_by_program

CS_PHD = {"id": "prog_cs", "name": "PhD in Computer Science",
          "application_url": "https://uni/apply/cs", "fee": "$120"}
STATS_PHD = {"id": "prog_stats", "name": "PhD in Statistics"}


def test_same_program_rolls_up_to_one_application():
    groups = group_by_program([
        {"id": "a", "program": CS_PHD},
        {"id": "b", "program": CS_PHD},
    ])
    assert len(groups) == 1
    g = groups[0]
    assert g["members"] == ["a", "b"]
    assert g["one_application_covers"] == 2
    assert g["application_url"] == "https://uni/apply/cs"
    assert "apply and pay once" in g["note"]


def test_different_programs_stay_separate():
    groups = group_by_program([
        {"id": "a", "program": CS_PHD},
        {"id": "b", "program": STATS_PHD},
    ])
    assert len(groups) == 2
    assert {tuple(g["members"]) for g in groups} == {("a",), ("b",)}


def test_professor_without_a_program_is_its_own_group():
    groups = group_by_program([
        {"id": "a", "program": CS_PHD},
        {"id": "b"},                       # no program info — must not be merged into CS
        {"id": "c", "program": CS_PHD},
    ])
    # a + c share prog_cs; b is a solo group of its own
    by_members = sorted((tuple(g["members"]) for g in groups), key=len, reverse=True)
    assert ("a", "c") in by_members
    assert ("b",) in by_members
    assert len(groups) == 2


def test_order_is_preserved_for_ranking():
    groups = group_by_program([
        {"id": "top", "program": STATS_PHD},
        {"id": "mid", "program": CS_PHD},
    ])
    assert [g["members"][0] for g in groups] == ["top", "mid"]
