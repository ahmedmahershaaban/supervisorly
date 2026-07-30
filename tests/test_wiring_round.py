"""Round AK — modules that were built, tested, and reachable from no entry point.

An audit walked every public symbol in ``src/supervisorly`` and asked which ones no *other*
module ever names. Five came back: ``score/ranking``, ``score/programs``, ``export/delta``,
``discover/archive`` and ``ingest`` — plus the read half of ``model/conflicts``. Each had
tests, which is exactly why nobody noticed: a green suite says the code is correct, never
that anything calls it.

These tests pin the wiring, not the modules — each one fails if the connection is removed
even though the module underneath stays perfectly correct and perfectly tested.
"""

from __future__ import annotations

import argparse
import json

import pytest

from supervisorly import cli, demo, ingest, pipeline
from supervisorly.discover import ladder
from supervisorly.discover import ror as ror_mod
from supervisorly.model.db import open_db

MD = """# Supervisorly — human retrieval
target: person=eve  name=Prof. Eve Walled
retrieved_at: 2026-07-21

## field: recruiting_signal
value: Recruiting a PhD student in HCI for 2027.
quote: I am recruiting a PhD student in HCI for 2027.
source_url: https://x.com/evewalled/status/123
observed_at: 2026-07-21
confidence: unconfirmed
"""


def _ror(*insts):
    """A stand-in ROR client returning exactly ``insts`` for any country."""
    return type("R", (), {"institutions_in_country": lambda s, c, **k: list(insts)})()


UNI = {"name": "Uni", "types": ["education"]}
HOSPITAL = {"name": "Teaching Hospital", "types": ["healthcare"]}
INSTITUTE = {"name": "Max Planck", "types": ["facility"]}
CORP = {"name": "Corp", "types": ["company"]}


# ── 1. the institution pool is selectable, not a boolean ─────────────────────
def test_default_is_education_only():
    assert ladder.requested_types({}) == {"education"}


def test_several_types_can_be_asked_for_at_once():
    """Supervision is not only at universities: a Max Planck institute is `facility` and a
    teaching hospital is `healthcare`. Both are real supervisor pools in some countries."""
    got = ladder.select_institutions(
        {"country": "DE", "institution_types": ["education", "facility"]},
        _ror(UNI, HOSPITAL, INSTITUTE, CORP))
    assert [i["name"] for i in got] == ["Uni", "Max Planck"]


def test_all_keeps_every_type():
    assert ladder.requested_types({"institution_types": "all"}) is None
    got = ladder.select_institutions({"country": "DE", "institution_types": "all"},
                                     _ror(UNI, HOSPITAL, CORP))
    assert len(got) == 3


def test_the_old_boolean_still_means_all():
    """`--all-institution-types` shipped before the multi-select; a plan carrying it keeps
    working rather than silently narrowing to education."""
    assert ladder.requested_types({"all_institution_types": True}) is None


def test_a_dual_typed_organisation_is_found_by_either_pool():
    """A university hospital is typed both — asking for either must find it, so the filter is
    an intersection and never an equality."""
    both = {"name": "University Hospital", "types": ["education", "healthcare"]}
    assert [i["name"] for i in ladder.select_institutions(
        {"country": "SE", "institution_types": ["healthcare"]}, _ror(both))] == \
        ["University Hospital"]
    assert [i["name"] for i in ladder.select_institutions(
        {"country": "SE", "institution_types": ["education"]}, _ror(both))] == \
        ["University Hospital"]


def test_the_warning_is_a_census_of_what_was_left_unscanned():
    """A student who cannot see that 2 other pools exist cannot decide whether to scan them."""
    warnings: list[str] = []
    ladder.select_institutions({"country": "CA"}, _ror(UNI, HOSPITAL, INSTITUTE, CORP),
                               warnings=warnings)
    blob = " ".join(warnings)
    assert "kept 1 of 4 ROR institutions for CA" in blob
    assert "healthcare 1" in blob and "facility 1" in blob and "company 1" in blob


def test_a_requested_type_the_country_has_none_of_is_reported():
    """The scan is narrower than the request and nothing else in the output would say so."""
    warnings: list[str] = []
    ladder.select_institutions({"country": "CA", "institution_types": ["education", "facility"]},
                               _ror(UNI, HOSPITAL), warnings=warnings)
    assert any("asked for facility" in w for w in warnings)


def test_no_requested_type_present_fails_open_rather_than_reporting_none():
    warnings: list[str] = []
    got = ladder.select_institutions({"country": "XX", "institution_types": ["facility"]},
                                     _ror(UNI, HOSPITAL), warnings=warnings)
    assert len(got) == 2
    assert any("scanning all types rather than reporting none" in w for w in warnings)


# ── 2. the CLI validates the pool names loudly ───────────────────────────────
def _args(**kw):
    base = {"institution_types": None, "all_institution_types": False}
    base.update(kw)
    return argparse.Namespace(**base)


def test_a_misspelled_type_fails_loud(capsys):
    """Silently ignoring it would run an education-only scan while the command line says
    otherwise, and nothing in the output would contradict that (D-002)."""
    assert cli._parse_institution_types(_args(institution_types="eductaion")) is cli._INVALID
    assert "unknown --institution-types" in capsys.readouterr().out


def test_conflicting_flags_fail_loud(capsys):
    assert cli._parse_institution_types(
        _args(institution_types="facility", all_institution_types=True)) is cli._INVALID
    assert "conflict" in capsys.readouterr().out


def test_a_valid_list_parses_to_the_plan_value():
    assert cli._parse_institution_types(
        _args(institution_types="education, facility")) == ["education", "facility"]
    assert cli._parse_institution_types(_args(institution_types="ALL")) == "all"
    assert cli._parse_institution_types(_args(all_institution_types=True)) == "all"
    assert cli._parse_institution_types(_args()) is None


def test_every_advertised_type_is_accepted():
    """The help text lists ROR's vocabulary; a value it names must not then be rejected."""
    for t in ror_mod.KNOWN_TYPES:
        assert cli._parse_institution_types(_args(institution_types=t)) == [t]


# ── 3. score/ranking.py — the university roll-up ─────────────────────────────
def test_the_export_carries_ranked_universities(tmp_path):
    """`rank_universities` answers what the professor list cannot: a student applies to a
    department, not to a row."""
    tp, targets, plan = demo.demo_fixture()
    r = pipeline.run_offline(plan, targets, tp, tmp_path / "s")
    unis = r["export"]["run"]["universities"]
    assert unis, "the roll-up must reach the export"
    scores = [u["university_score"] for u in unis]
    assert scores == sorted(scores, reverse=True)
    assert sum(len(u["members"]) for u in unis) == len(r["export"]["professors"])


def test_a_professor_with_no_affiliation_is_bucketed_not_dropped(tmp_path):
    """Honest emptiness applies to the roll-up too (D-022): 'Unknown' is a visible bucket."""
    tp, targets, plan = demo.demo_fixture()
    r = pipeline.run_offline(plan, targets, tp, tmp_path / "s")
    named = {m for u in r["export"]["run"]["universities"] for m in u["members"]}
    assert named == {p["id"] for p in r["export"]["professors"]}


def test_the_roll_up_scores_the_same_person_the_row_above_it_does(tmp_path):
    """Both read one `_scorer_input`, so a university can never be ranked on a different
    reading of the same professor than the list shows."""
    tp, targets, plan = demo.demo_fixture()
    r = pipeline.run_offline(plan, targets, tp, tmp_path / "s")
    solo = [u for u in r["export"]["run"]["universities"] if len(u["members"]) == 1]
    by_id = {p["id"]: p for p in r["export"]["professors"]}
    for u in solo:
        assert u["mean_fit"] * 100 == pytest.approx(
            by_id[u["members"][0]]["match"]["components"]["topic_match"], abs=1)


# ── 4. export/delta.py — what changed since last time ────────────────────────
def test_no_previous_export_means_no_delta_block(tmp_path):
    """A first run reporting every professor as 'new' is noise, not news."""
    tp, targets, plan = demo.demo_fixture()
    r = pipeline.run_offline(plan, targets, tp, tmp_path / "s")
    assert "delta" not in r["export"]["run"]


def test_a_previous_export_produces_a_delta(tmp_path):
    tp, targets, plan = demo.demo_fixture()
    first = pipeline.run_offline(plan, targets, tp, tmp_path / "s1")["export"]
    trimmed = dict(first, professors=first["professors"][1:])
    tp2, targets2, plan2 = demo.demo_fixture()
    second = pipeline.run_offline(plan2, targets2, tp2, tmp_path / "s2",
                                  previous_export=trimmed)["export"]
    assert second["run"]["delta"]["new_professors"] == [
        first["professors"][0].get("name") or first["professors"][0]["id"]]


def test_compare_to_a_missing_file_fails_loud(tmp_path, capsys):
    """Running anyway would produce an export with no delta, and the student would read
    'nothing changed' into a comparison that never happened."""
    rc = cli.main(["scan", "--demo", "--out", str(tmp_path / "d.html"),
                   "--compare-to", str(tmp_path / "nope.json")])
    assert rc == 2 and "--compare-to file not found" in capsys.readouterr().out


def test_compare_to_a_non_export_fails_loud(tmp_path, capsys):
    junk = tmp_path / "junk.json"
    junk.write_text('{"hello": 1}', encoding="utf-8")
    rc = cli.main(["scan", "--demo", "--out", str(tmp_path / "d.html"),
                   "--compare-to", str(junk)])
    assert rc == 2 and "not a Supervisorly export" in capsys.readouterr().out


# ── 5. model/conflicts.py — the read half ────────────────────────────────────
def test_an_open_conflict_is_visible_on_the_professor(tmp_path):
    """`detect_for_claim` has been writing conflict rows all along and nothing read them
    back, so a field two sources disagreed about displayed exactly like an agreed one."""
    from supervisorly.model import conflicts

    tp, targets, plan = demo.demo_fixture()
    db = tmp_path / "run.sqlite"
    r = pipeline.run_offline(plan, targets, tp, tmp_path / "s", db_path=db)
    conn = open_db(db)
    # a real pair of claim ids — the conflict table has a foreign key to them, which is what
    # makes a conflict row traceable to the two sources it is about
    row = conn.execute(
        "SELECT entity_id, field, claim_id FROM claim WHERE entity_kind='person' "
        "AND state='value' LIMIT 1").fetchone()
    pid, field = row["entity_id"], row["field"]
    conflicts.record_conflict(conn, entity_kind="person", entity_id=pid, field=field,
                              claim_a=row["claim_id"], claim_b=row["claim_id"],
                              resolution_state="open")
    conn.commit()
    conn.close()

    again = pipeline.reexport(db, [{"id": p["id"]} for p in r["export"]["professors"]])
    prof = next(p for p in again["export"]["professors"] if p["id"] == pid)
    assert prof["profile"]["contested_fields"] == [field]
    assert "CONTESTED" in again["export"]["run"]["coverage"]


# ── 6. ingest.py — the human rung's return path ──────────────────────────────
def _scanned(tmp_path):
    tp, targets, plan = demo.demo_fixture()
    db = tmp_path / "run.sqlite"
    pipeline.run_offline(plan, targets, tp, tmp_path / "s", db_path=db)
    return db


def test_ingest_md_command_records_the_claims(tmp_path, capsys):
    """The dashboard hands out a prompt asking for this exact Markdown; until now no command
    accepted it back. A blocked field that offers a prompt and takes no answer is a dead end."""
    db = _scanned(tmp_path)
    md = tmp_path / "eve.md"
    md.write_text(MD, encoding="utf-8")
    rc = cli.main(["ingest-md", "--file", str(md), "--db", str(db)])
    out = capsys.readouterr().out
    assert rc == 0, out
    assert "ingested 1 claim(s) for person eve" in out
    conn = open_db(db)
    live = [dict(r) for r in conn.execute(
        "SELECT state, extractor_agent FROM claim WHERE entity_id='eve' "
        "AND field='recruiting_signal' AND superseded_by IS NULL")]
    conn.close()
    assert live and live[0]["state"] == "value"
    assert live[0]["extractor_agent"] == ingest.HUMAN_EXTRACTOR


def test_ingest_md_reads_a_powershell_utf16_paste(tmp_path, capsys):
    """`>` and Out-File on Windows write UTF-16 with a BOM — the single most common way this
    file arrives. Decoding it is the difference between the rung working and looking broken."""
    db = _scanned(tmp_path)
    md = tmp_path / "eve16.md"
    md.write_bytes(MD.encode("utf-16"))
    assert cli.main(["ingest-md", "--file", str(md), "--db", str(db)]) == 0
    assert "ingested 1 claim(s)" in capsys.readouterr().out


def test_ingest_md_points_at_the_grammar_when_the_paste_is_malformed(tmp_path, capsys):
    db = _scanned(tmp_path)
    md = tmp_path / "bad.md"
    md.write_text("I asked Claude and it said she is recruiting.", encoding="utf-8")
    rc = cli.main(["ingest-md", "--file", str(md), "--db", str(db)])
    out = capsys.readouterr().out
    assert rc == 2
    assert "could not parse" in out and "## field:" in out


def test_ingest_md_without_a_scan_says_so(tmp_path, capsys):
    md = tmp_path / "eve.md"
    md.write_text(MD, encoding="utf-8")
    rc = cli.main(["ingest-md", "--file", str(md), "--db", str(tmp_path / "none.sqlite")])
    assert rc == 2 and "database not found" in capsys.readouterr().out


def test_the_prompt_the_dashboard_hands_out_has_a_receiving_command():
    """The point of the whole fix: `chrome_prompt` emits its contract through `md_grammar`,
    and `ingest-md` parses that same grammar. If these ever drift, the rung is a dead end
    again — so the parser is pointed at the emitter's own worked example."""
    from supervisorly.extract import md_grammar as mg

    doc = mg.MDDocument(target_kind="person", target_ref="p1", target_name="Prof",
                        retrieved_at="2026-07-21",
                        entries=[mg.MDEntry(field="recruiting_signal", value="v", quote="q",
                                            source_url="https://example.edu/x",
                                            observed_at="2026-07-21")])
    reparsed = mg.parse(mg.emit(doc))
    assert reparsed.target_ref == "p1"
    assert [e.field for e in reparsed.entries] == ["recruiting_signal"]


# ── 7. the audit's own guard ─────────────────────────────────────────────────
def test_the_wired_modules_are_actually_imported_by_the_pipeline():
    """A regression here means someone deleted the call and left the module — which is the
    state this whole round existed to end."""
    src = (pipeline.__file__)
    text = open(src, encoding="utf-8").read()
    for name in ("ranking_mod.rank_universities", "delta_mod.compute_delta",
                 "conflicts_mod.open_conflicts"):
        assert name in text, f"{name} is no longer called from the pipeline"


def test_ingest_md_is_a_registered_command():
    parser = cli.build_parser()
    ns = parser.parse_args(["ingest-md", "--file", "x.md"])
    assert ns.func is cli.cmd_ingest_md


def test_json_export_is_not_widened_by_the_new_blocks(tmp_path):
    """`universities` and `delta` are run-level arithmetic; neither may enter the quote-gated
    per-professor `fields` surface (D-010)."""
    from supervisorly.export import json_export as jx

    tp, targets, plan = demo.demo_fixture()
    r = pipeline.run_offline(plan, targets, tp, tmp_path / "s")
    assert jx.validate_export(r["export"]) == []
    for p in r["export"]["professors"]:
        assert "universities" not in p["fields"] and "delta" not in p["fields"]
    json.dumps(r["export"])          # the whole thing must still serialise
