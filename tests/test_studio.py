"""Phase B4 (D-067) — the Scan Studio: a self-contained, offline, Atlas-language plan wizard
over a ``map-field`` subject map. Tests cover self-containment (no external requests),
injection-safety (hostile API strings), the tri-state checkbox tree + plan builder (structurally,
plus a node syntax check when node is on PATH), the honest truncation banner (D-037), the
``studio`` CLI (fail-loud map loading, D-005 --out guard), and the ``scan --plan`` wiring that
honours a Studio plan's own email + named-professor targets. No live network — cassettes only."""

import json
import shutil
import subprocess

import pytest

from supervisorly import cli
from supervisorly.discover import openalex
from supervisorly.export.studio import build_studio
from supervisorly.fetch import transport as transport_mod
from supervisorly.fetch.transport import CassetteTransport

EMAIL = "me@uni.edu"


def _map(**over):
    smap = {"query": "causal ml", "truncated": False, "groups": [
        {"domain": "Physical Sciences", "field": "Computer Science",
         "subfield": "Artificial Intelligence", "topics": [
             {"topic_id": "T10001", "name": "Causal Machine Learning", "works_count": 12400},
             {"topic_id": "T10002", "name": "Graph Neural Networks", "works_count": 960}]},
        {"domain": "Physical Sciences", "field": "Physics",
         "subfield": "Statistical Physics", "topics": [
             {"topic_id": "T10003", "name": "Causal Inference", "works_count": 1100000}]},
    ]}
    smap.update(over)
    return smap


# ── self-containment (D-033/D-048) ───────────────────────────────────────────

def test_studio_is_self_contained_no_external_resources():
    html = build_studio(_map())
    assert "<!doctype html>" in html.lower()
    for bad in ("<link", "<script src", "@import", "url(", "fetch(",
                "XMLHttpRequest", "<img", "<iframe"):
        assert bad not in html, f"external-request vector present: {bad}"
    low = html.lower()
    assert "googleapis" not in low and "cdn" not in low
    # the Blob download is the one allowed "write" — and no alert() popups anywhere
    assert "Blob(" in html and "alert(" not in html


def test_atlas_tokens_and_type_present():
    html = build_studio(_map())
    assert "#05070c" in html                                   # base void
    assert "#e8b24a" in html                                   # amber accent
    for kind in ("#43c9d6", "#79d06a", "#f0839a", "#b58cf0", "#7d828e"):  # tissue palette
        assert kind in html
    assert "'Space Grotesk'" in html and "'Space Mono'" in html  # named with fallbacks, never imported
    assert "eyebrow" in html and "letter-spacing:.24em" in html  # Atlas eyebrow convention
    assert "SCAN STUDIO" in html.upper()


# ── injection safety ──────────────────────────────────────────────────────────

def test_hostile_map_strings_cannot_break_the_data_block():
    hostile = _map(
        query='closing </script><img src=x onerror=alert(1)>',
        groups=[{"domain": 'dom</script>', "field": 'field\u2028break',
                 "subfield": 'javascript:alert(1)',
                 "topics": [{"topic_id": 'T1</script><script>alert(2)</script>',
                             "name": '<img onerror=alert(3)>', "works_count": 5}]}])
    html = build_studio(hostile)
    assert html.count("</script>") == 1          # only the one closing data-block tag
    assert " " not in html and " " not in html   # no raw JS line separators U+2028/U+2029
    assert "</script><img" not in html           # the hostile sequence never survives raw
    assert "\\u003c" in html                     # every '<' neutralised instead
    # the escaped header copy may carry the hostile words as inert TEXT, but no raw tag
    # ever survives — only the \u003c-escaped (data) and &lt;-escaped (markup) forms
    assert "<img" not in html


def test_query_interpolated_into_the_header_is_escaped():
    html = build_studio(_map(query='x"><script>alert(1)</script>'))
    assert 'x"><script>' not in html
    assert "x&quot;&gt;" in html                 # html-escaped in the hero paragraph


def test_defaults_are_embedded_safely():
    html = build_studio(_map(), defaults={"country": "Canada", "email": EMAIL,
                                          "universities": ["McGill"], "intent_kind": "phd"})
    assert '"defaults"' in html and "Canada" in html and "McGill" in html
    hostile = build_studio(_map(), defaults={"country": '</script>x'})
    assert hostile.count("</script>") == 1


# ── tree, tri-state, plan builder (structural + node syntax) ─────────────────

def test_reduced_motion_and_keyboard_support_present():
    html = build_studio(_map())
    assert "prefers-reduced-motion:reduce" in html
    assert ":focus-visible" in html                      # visible focus ring
    assert 'type="checkbox"' in html and 'type="radio"' in html   # real form controls
    assert 'e.key==="Escape"' in html                    # Escape closes transient UI


def test_tri_state_checkbox_logic_present():
    html = build_studio(_map())
    assert "indeterminate" in html
    assert "refreshTree" in html
    # checking a parent cascades to every descendant topic checkbox
    assert 'querySelectorAll("input.topic")' in html


def test_plan_builder_exists_with_the_full_plan_shape():
    html = build_studio(_map())
    assert "function buildPlan()" in html
    for key in ("intent_kind", "country", "field", "resolved_topic_ids",
                "university_mode", "universities", "targets", "email"):
        assert key in html, f"plan key missing: {key}"
    # the download + the exact next command
    assert "supervisorly_plan.json" in html
    assert "supervisorly scan --plan supervisorly_plan.json --out output/live.html" in html


def test_embedded_js_parses_under_node_when_available(tmp_path):
    node = shutil.which("node")
    if node is None:
        pytest.skip("node not on PATH")
    html = build_studio(_map())
    js = html.split("<script>", 1)[1].rsplit("</script>", 1)[0]
    f = tmp_path / "studio.js"
    f.write_text(js, encoding="utf-8")
    r = subprocess.run([node, "--check", str(f)], capture_output=True)
    assert r.returncode == 0, r.stderr.decode("utf-8", "replace")


# ── honesty: truncation banner (D-037) ────────────────────────────────────────

def test_truncation_banner_rendered_only_when_partial():
    partial = build_studio(_map(truncated=True))
    assert "PARTIAL MAP" in partial and "more topics than shown" in partial
    complete = build_studio(_map(truncated=False))
    assert "PARTIAL MAP" not in complete


def test_empty_map_is_an_honest_empty_tree_not_a_crash():
    html = build_studio({"query": "nothing", "groups": [], "truncated": False})
    assert "subject map is empty" in html
    assert build_studio({}).count("</script>") == 1      # even a malformed map degrades honestly


# ── CLI: studio ───────────────────────────────────────────────────────────────

def _write_map(tmp_path, smap=None):
    p = tmp_path / "subject_map.json"
    p.write_text(json.dumps(smap if smap is not None else _map()), encoding="utf-8")
    return p


def test_studio_cli_missing_map_fails_loud(tmp_path, capsys):
    rc = cli.main(["studio", "--map", str(tmp_path / "nope.json"),
                   "--out", str(tmp_path / "s.html")])
    assert rc == 2
    assert "subject map not found" in capsys.readouterr().out


def test_studio_cli_invalid_json_and_wrong_shape_fail_loud(tmp_path, capsys):
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    rc = cli.main(["studio", "--map", str(bad), "--out", str(tmp_path / "s.html")])
    assert rc == 2 and "invalid subject-map JSON" in capsys.readouterr().out

    wrong = tmp_path / "wrong.json"
    wrong.write_text(json.dumps({"topics": []}), encoding="utf-8")
    rc = cli.main(["studio", "--map", str(wrong), "--out", str(tmp_path / "s.html")])
    assert rc == 2 and "not a subject map" in capsys.readouterr().out


def test_studio_cli_writes_the_html_and_an_ascii_line(tmp_path, capsys):
    out = tmp_path / "out" / "studio.html"
    rc = cli.main(["studio", "--map", str(_write_map(tmp_path)), "--out", str(out)])
    assert rc == 0
    printed = capsys.readouterr().out
    assert "studio wrote 3 topics in 2 groups" in printed and printed.isascii()
    html = out.read_text(encoding="utf-8")
    assert "<!doctype html>" in html.lower() and "SCAN STUDIO" in html.upper()


def test_studio_out_inside_repo_and_not_ignored_warns(tmp_path, capsys):
    """The D-005 guard applies to `studio --out` exactly like `scan --out` (mirrors test_cli)."""
    if shutil.which("git") is None:
        pytest.skip("git binary not available")
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True, capture_output=True)
    (repo / ".gitignore").write_text("/output/\n", encoding="utf-8")
    out = repo / "results" / "studio.html"
    rc = cli.main(["studio", "--map", str(_write_map(tmp_path)), "--out", str(out)])
    assert rc == 0 and out.exists()                      # warns, never refuses
    err = capsys.readouterr().err
    assert "D-005" in err and "git-ignored" in err


# ── scan --plan honours a Studio plan's email + targets ──────────────────────

def _targets_cassette():
    tp = CassetteTransport()
    tp.record(openalex.author_search_url("Ada Maple", EMAIL), 200, json.dumps({"results": [
        {"id": "https://openalex.org/A100", "display_name": "Dr. Ada Maple", "works_count": 30,
         "cited_by_count": 500, "topics": [],
         "last_known_institutions": [{"id": "https://openalex.org/I100",
                                      "display_name": "Maple University"}],
         "homepage_url": "https://maple.example/~ada"}]}))
    tp.record("https://maple.example/robots.txt", 200, "User-agent: *\nAllow: /\n")
    tp.record("https://maple.example/~ada", 200,
              "<html><body><main><p>I am recruiting a PhD student for 2027.</p></main></body></html>")
    return tp


def _studio_plan(tmp_path, **over):
    plan = {"intent_kind": "phd", "country": "", "field": "", "resolved_topic_ids": [],
            "university_mode": "all", "universities": [], "email": EMAIL,
            "targets": [{"name": "Ada Maple", "affiliation": "Maple University"}]}
    plan.update(over)
    p = tmp_path / "supervisorly_plan.json"
    p.write_text(json.dumps(plan), encoding="utf-8")
    return p


def test_scan_plan_uses_the_plans_email_and_targets(tmp_path, monkeypatch, capsys):
    # a Studio-exported plan is self-sufficient: no --email, no --targets, no country needed
    monkeypatch.setattr(transport_mod, "httpx_transport", lambda **kw: _targets_cassette())
    out = tmp_path / "out" / "live.html"
    rc = cli.main(["scan", "--plan", str(_studio_plan(tmp_path)), "--out", str(out)])
    assert rc == 0
    printed = capsys.readouterr().out
    assert "scanned 1 professors (live)" in printed and printed.isascii()
    export = json.loads(out.with_suffix(".json").read_text(encoding="utf-8"))
    assert export["professors"][0]["name"] == "Dr. Ada Maple"


def test_scan_plan_invalid_targets_entry_fails_loud(tmp_path, capsys):
    rc = cli.main(["scan", "--plan", str(_studio_plan(tmp_path, targets={"name": "x"})),
                   "--out", str(tmp_path / "d.html")])
    assert rc == 2
    assert "invalid 'targets'" in capsys.readouterr().out
