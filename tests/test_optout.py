"""Ethics gate: the opt-out suppression list is enforced at build (D-023/032/053).

This is the *failing test* the goal requires: if enforcement were removed, the suppressed
professor would reappear in the export and this test would fail."""

from supervisorly import demo, pipeline
from supervisorly.ethics import optout


def test_load_optout_ignores_comments_and_blanks(tmp_path):
    f = tmp_path / "optout.txt"
    f.write_text("# a comment\n\nhttps://Example.edu/~Jdoe/\n0000-0002-1825-0097\n",
                 encoding="utf-8")
    s = optout.load_optout(f)
    assert s == {"https://example.edu/~jdoe", "0000-0002-1825-0097"}  # normalised


def test_missing_optout_file_is_empty_not_an_error(tmp_path):
    assert optout.load_optout(tmp_path / "nope.txt") == set()
    assert optout.load_optout(None) == set()


def test_opted_out_professor_is_dropped_before_fetch(tmp_path):
    tp, targets, plan = demo.demo_fixture()
    # suppress Ada by her page URL
    f = tmp_path / "optout.txt"
    f.write_text("https://ca-uni.example/people/ada\n", encoding="utf-8")

    result = pipeline.run_offline(plan, targets, tp, tmp_path / "snaps", optout_path=f)
    ids = {p["id"] for p in result["export"]["professors"]}
    assert "ada" not in ids                     # suppressed — never shown
    assert "ben" in ids and "cara" in ids       # everyone else still present
    assert result["stats"]["opted_out"] == 1


def test_without_optout_ada_is_present(tmp_path):
    # the counterfactual that makes the test above meaningful
    tp, targets, plan = demo.demo_fixture()
    result = pipeline.run_offline(plan, targets, tp, tmp_path / "snaps")
    assert "ada" in {p["id"] for p in result["export"]["professors"]}


def test_reexport_resume_path_also_honours_optout(tmp_path):
    """Audit finding 1: someone whose claims were already stored, then opts out, must not
    survive into a re-exported dashboard/JSON — opt-out is enforced on the resume path too."""
    tp, targets, plan = demo.demo_fixture()
    db = tmp_path / "run.sqlite"
    # first scan stores Ada's claims (no opt-out yet)
    r1 = pipeline.run_offline(plan, targets, tp, tmp_path / "snaps", db_path=db)
    assert "ada" in {p["id"] for p in r1["export"]["professors"]}

    # Ada later opts out; the resume/re-export must drop her
    f = tmp_path / "optout.txt"
    f.write_text("https://ca-uni.example/people/ada\n", encoding="utf-8")
    r2 = pipeline.reexport(db, targets, optout_path=f)
    ids = {p["id"] for p in r2["export"]["professors"]}
    assert "ada" not in ids
    assert "ben" in ids
    assert r2["stats"]["opted_out"] == 1
    # and her name must not linger anywhere in the serialised output
    import json
    assert "Ada Placeholder" not in json.dumps(r2["export"])
