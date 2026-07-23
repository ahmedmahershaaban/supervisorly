"""Phase H — genericity eval + edge cases (D-063, D-034 mitigations, edge-case matrix).

Runs the synthetic demo (3 directory shapes / 3 countries + a non-English page + a
robots-blocked one) and asserts the pipeline stays generic, honest, and hallucination-free
across all of them. Also covers the zero-result edge case."""

from supervisorly import demo, pipeline
from supervisorly.cli import main
from supervisorly.export import json_export as jx
from supervisorly.fetch.normalize import quote_in_snapshot
from supervisorly.fetch.snapshot import SnapshotStore


def _run_demo(tmp_path):
    tp, targets, plan = demo.demo_fixture()
    result = pipeline.run_offline(plan, targets, tp, tmp_path / "snaps")
    return result, SnapshotStore(tmp_path / "snaps"), targets


def test_demo_scan_valid_across_shapes_and_countries(tmp_path):
    result, _, targets = _run_demo(tmp_path)
    assert jx.validate_export(result["export"]) == []
    ids = {p["id"] for p in result["export"]["professors"]}
    assert ids == {t["id"] for t in targets}   # every professor, every shape, present


def test_demo_states_are_honest_per_shape(tmp_path):
    result, _, _ = _run_demo(tmp_path)
    st = {p["id"]: p["fields"]["recruiting_signal"]["state"]
          for p in result["export"]["professors"]}
    assert st["ada"] == "value"           # CA: <main><p> markup
    assert st["ben"] == "value"           # UK: <section><ul><li> markup — still found
    assert st["cara"] == "value"          # AU: nested <div class=bio> markup — still found
    # DE: German recruiting text — the English-first deterministic tier can't read it, so it
    # honestly records searched_absent rather than guessing (the LLM analyst handles language).
    assert st["dana"] == "searched_absent"
    assert st["eve"] == "blocked"         # robots-disallowed → blocked, not dropped


def test_demo_deadlines_firm_vs_projected(tmp_path):
    """Edge (projected deadline, D-061): a published date is firm (quoted_official); a
    date wrapped in projection language ("usually due by") is a *watch* date (inferred),
    never presented as firm. Both are parsed deterministically to ISO — never guessed."""
    result, _, _ = _run_demo(tmp_path)
    dl = {p["id"]: p["fields"]["deadline"] for p in result["export"]["professors"]}
    assert dl["ada"]["state"] == "value"
    assert dl["ada"]["value"] == "2026-12-01"
    assert dl["ada"]["confidence"] == "quoted_official"        # firm
    assert dl["ben"]["state"] == "value"
    assert dl["ben"]["value"] == "2026-09-15"
    assert dl["ben"]["confidence"] == "inferred"               # projected → watch
    assert dl["cara"]["state"] == "searched_absent"           # no deadline sentence
    assert dl["eve"]["state"] == "blocked"                    # blocked page → blocked field


def test_demo_has_zero_hallucinations(tmp_path):
    result, snaps, _ = _run_demo(tmp_path)
    for p in result["export"]["professors"]:
        env = p["fields"]["recruiting_signal"]
        if env["state"] == "value":
            assert quote_in_snapshot(env["quote"], snaps.load(env["snapshot_hash"]))


def test_zero_result_run_is_valid_and_empty(tmp_path):
    """No targets → a valid, empty export and a dashboard that says so, not a crash."""
    tp, _, plan = demo.demo_fixture()
    result = pipeline.run_offline(plan, [], tp, tmp_path / "snaps")
    assert jx.validate_export(result["export"]) == []
    assert result["export"]["professors"] == []
    assert "no professors" in result["html"].lower()


def test_cli_scan_demo_writes_dashboard(tmp_path):
    out = tmp_path / "out" / "dashboard.html"
    rc = main(["scan", "--demo", "--out", str(out)])
    assert rc == 0
    assert out.exists() and out.with_suffix(".json").exists()
    html = out.read_text(encoding="utf-8")
    assert "<!doctype html>" in html.lower() and "Ada Placeholder" in html
