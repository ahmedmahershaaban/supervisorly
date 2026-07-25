"""Phase B3 (D-066) — `scan --plan` (Scan Studio plan JSON drives the scan; selected topic IDs
reach the ladder, flags override the plan, invalid plans fail loud) and `scan --targets`
(named professors resolved via OpenAlex author search, deep-dived directly; unresolved are
reported skips, never silently dropped). No live network — cassettes via the Transport seam;
fixtures are synthetic (D-035 safe)."""

import json

from supervisorly import cli
from supervisorly.discover import ladder, openalex, ror
from supervisorly.fetch import transport as transport_mod
from supervisorly.fetch.transport import CassetteTransport

EMAIL = "me@uni.edu"

_RECRUIT_PAGE = ("<html><body><main><p>I am recruiting a PhD student for 2027.</p>"
                 "</main></body></html>")
_ROBOTS = "User-agent: *\nAllow: /\n"


def _ladder_cassette():
    """The country-ladder cassette (same shape as test_cli_live): CA -> I1 -> Prof One."""
    tp = CassetteTransport()
    tp.record(ror.country_url("CA"), 200, json.dumps({"items": [   # ROR v2 shape
        {"id": "https://ror.org/00x",
         "names": [{"value": "Uni", "types": ["ror_display", "label"], "lang": "en"}],
         "locations": [{"geonames_details": {"country_code": "CA"}}],
         "links": [{"type": "website", "value": "https://uni.example/"}],
         "types": ["education"]}]}))
    tp.record(openalex.institutions_url("https://ror.org/00x", EMAIL), 200,
              json.dumps({"results": [{"id": "https://openalex.org/I1"}]}))
    tp.record(openalex.authors_url("I1", EMAIL), 200, json.dumps({"results": [
        {"id": "https://openalex.org/A1", "display_name": "Prof One", "works_count": 10,
         "topics": [], "last_known_institutions": [], "homepage_url": "https://uni.example/~a"}]}))
    tp.record("https://uni.example/robots.txt", 200, _ROBOTS)
    tp.record("https://uni.example/~a", 200, _RECRUIT_PAGE)
    return tp


def _author(n, name, inst, host):
    return {"id": f"https://openalex.org/A{n}", "display_name": name,
            "works_count": 30, "cited_by_count": 500,
            "topics": [{"id": "https://openalex.org/T10001"}],
            "last_known_institutions": [{"id": "https://openalex.org/I100",
                                         "display_name": inst}],
            "homepage_url": f"https://{host}/~ada"}


def _targets_cassette():
    """Author-search cassette: two 'Ada Maple' hits at different institutions + their pages."""
    tp = CassetteTransport()
    tp.record(openalex.author_search_url("Ada Maple", EMAIL), 200, json.dumps({"results": [
        _author(100, "Dr. Ada Maple", "Maple University", "maple.example"),
        _author(200, "Dr. Ada B. Maple", "Other Institute", "other.example"),
    ]}))
    tp.record(openalex.author_url("A100", EMAIL), 200,
              json.dumps(_author(100, "Dr. Ada Maple", "Maple University", "maple.example")))
    for host in ("maple.example", "other.example"):
        tp.record(f"https://{host}/robots.txt", 200, _ROBOTS)
        tp.record(f"https://{host}/~ada", 200, _RECRUIT_PAGE)
    return tp


def _plan(tmp_path, **over):
    plan = {"intent_kind": "phd", "country": "CA", "resolved_topic_ids": ["T10001", "T10002"],
            "field": "causal ml", "university_mode": "all", "universities": []}
    plan.update(over)
    p = tmp_path / "plan.json"
    p.write_text(json.dumps(plan), encoding="utf-8")
    return p


def _spec(tmp_path, entries):
    p = tmp_path / "profs.json"
    p.write_text(json.dumps(entries), encoding="utf-8")
    return p


# ── scan --plan ───────────────────────────────────────────────────────────────

def test_scan_plan_uses_the_selected_topic_ids(tmp_path, monkeypatch, capsys):
    # the plan's resolved_topic_ids reach the ladder AS-IS (D-066): resolve_topic_ids sees
    # them and the field-text OpenAlex topic lookup is never re-run.
    monkeypatch.setattr(transport_mod, "httpx_transport", lambda **kw: _ladder_cassette())
    seen = {}
    real = ladder.resolve_topic_ids

    def spy(plan, oa):
        seen["resolved_topic_ids"] = list(plan.get("resolved_topic_ids") or [])
        return real(plan, oa)

    topic_calls = []
    monkeypatch.setattr(ladder, "resolve_topic_ids", spy)
    monkeypatch.setattr(openalex.OpenAlexClient, "topic_ids",
                        lambda self, q: topic_calls.append(q) or [])
    out = tmp_path / "out" / "live.html"
    rc = cli.main(["scan", "--plan", str(_plan(tmp_path)), "--email", EMAIL, "--out", str(out)])
    assert rc == 0
    assert "scanned 1 professors (live)" in capsys.readouterr().out
    assert seen["resolved_topic_ids"] == ["T10001", "T10002"]
    assert topic_calls == []


def test_scan_plan_country_name_resolves(tmp_path, monkeypatch, capsys):
    # a plan may carry a country NAME — resolved to alpha-2 before the ladder runs (D-002)
    monkeypatch.setattr(transport_mod, "httpx_transport", lambda **kw: _ladder_cassette())
    out = tmp_path / "out" / "live.html"
    rc = cli.main(["scan", "--plan", str(_plan(tmp_path, country="Canada")),
                   "--email", EMAIL, "--out", str(out)])
    assert rc == 0
    assert "scanned 1 professors (live)" in capsys.readouterr().out


def test_scan_plan_explicit_flags_override_the_plan(tmp_path, monkeypatch, capsys):
    # plan says France, --country says Canada: the flag wins (the cassette only serves CA,
    # so a France run would enumerate 0 professors).
    monkeypatch.setattr(transport_mod, "httpx_transport", lambda **kw: _ladder_cassette())
    out = tmp_path / "out" / "live.html"
    rc = cli.main(["scan", "--plan", str(_plan(tmp_path, country="France")),
                   "--country", "Canada", "--email", EMAIL, "--out", str(out)])
    assert rc == 0
    assert "scanned 1 professors (live)" in capsys.readouterr().out


def test_scan_plan_invalid_files_fail_loud(tmp_path, capsys):
    missing = cli.main(["scan", "--plan", str(tmp_path / "nope.json"),
                        "--email", EMAIL, "--out", str(tmp_path / "d.html")])
    assert missing == 2 and "plan file not found" in capsys.readouterr().out

    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    rc = cli.main(["scan", "--plan", str(bad), "--email", EMAIL,
                   "--out", str(tmp_path / "d.html")])
    assert rc == 2 and "invalid plan JSON" in capsys.readouterr().out

    incomplete = tmp_path / "incomplete.json"
    incomplete.write_text(json.dumps({"country": "CA"}), encoding="utf-8")
    rc = cli.main(["scan", "--plan", str(incomplete), "--email", EMAIL,
                   "--out", str(tmp_path / "d.html")])
    printed = capsys.readouterr().out
    assert rc == 2 and "missing required key(s)" in printed
    assert "intent_kind" in printed and "resolved_topic_ids" in printed


# ── scan --targets ────────────────────────────────────────────────────────────

def test_scan_targets_only_run_needs_no_country_or_field(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(transport_mod, "httpx_transport", lambda **kw: _targets_cassette())
    out = tmp_path / "out" / "live.html"
    rc = cli.main(["scan", "--targets", str(_spec(tmp_path, [{"name": "Ada Maple"}])),
                   "--email", EMAIL, "--out", str(out)])
    assert rc == 0
    printed = capsys.readouterr().out
    assert "scanned 1 professors (live)" in printed and printed.isascii()
    export = json.loads(out.with_suffix(".json").read_text(encoding="utf-8"))
    assert export["professors"][0]["name"] == "Dr. Ada Maple"
    assert export["professors"][0]["fields"]["recruiting_signal"]["state"] == "value"


def test_scan_targets_affiliation_prefers_the_matching_hit(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(transport_mod, "httpx_transport", lambda **kw: _targets_cassette())
    out = tmp_path / "out" / "live.html"
    spec = _spec(tmp_path, [{"name": "Ada Maple", "affiliation": "Other Institute"}])
    rc = cli.main(["scan", "--targets", str(spec), "--email", EMAIL, "--out", str(out)])
    assert rc == 0
    export = json.loads(out.with_suffix(".json").read_text(encoding="utf-8"))
    assert export["professors"][0]["name"] == "Dr. Ada B. Maple"   # the Other Institute hit


def test_scan_targets_unmatched_affiliation_marks_unverified(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(transport_mod, "httpx_transport", lambda **kw: _targets_cassette())
    out = tmp_path / "out" / "live.html"
    spec = _spec(tmp_path, [{"name": "Ada Maple", "affiliation": "Nowhere College"}])
    rc = cli.main(["scan", "--targets", str(spec), "--email", EMAIL, "--out", str(out)])
    assert rc == 0
    printed = capsys.readouterr().out
    # top hit taken, but the unconfirmed affiliation is surfaced (honest, never silent)
    assert "WARNING" in printed and "resolution=unverified" in printed
    assert "scanned 1 professors (live)" in printed


def test_scan_targets_unresolved_are_reported_skips_and_the_run_continues(
        tmp_path, monkeypatch, capsys):
    tp = _targets_cassette()
    tp.record(openalex.author_search_url("Nobody Here", EMAIL), 200,
              json.dumps({"results": []}))
    monkeypatch.setattr(transport_mod, "httpx_transport", lambda **kw: tp)
    out = tmp_path / "out" / "live.html"
    spec = _spec(tmp_path, [{"name": "Nobody Here"}, {"name": "Ada Maple"}])
    rc = cli.main(["scan", "--targets", str(spec), "--email", EMAIL, "--out", str(out)])
    assert rc == 0
    printed = capsys.readouterr().out
    assert "SKIPPED target Nobody Here" in printed      # reported, not silently dropped (D-022)
    assert "scanned 1 professors (live)" in printed     # the resolved one still deep-dived


def test_scan_targets_url_form_entries(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(transport_mod, "httpx_transport", lambda **kw: _targets_cassette())
    out = tmp_path / "out" / "live.html"
    spec = _spec(tmp_path, ["https://openalex.org/A100"])
    rc = cli.main(["scan", "--targets", str(spec), "--email", EMAIL, "--out", str(out)])
    assert rc == 0
    assert "scanned 1 professors (live)" in capsys.readouterr().out
    export = json.loads(out.with_suffix(".json").read_text(encoding="utf-8"))
    assert export["professors"][0]["name"] == "Dr. Ada Maple"


def test_scan_targets_plus_country_unions_both_sets(tmp_path, monkeypatch, capsys):
    # --targets + --country: the ladder's targets AND the named ones, one run (D-066)
    tp = _ladder_cassette()
    for resp in _targets_cassette()._c.values():      # merge both cassette sets into one
        tp.record(resp.url, resp.status, resp.text)
    monkeypatch.setattr(transport_mod, "httpx_transport", lambda **kw: tp)
    out = tmp_path / "out" / "live.html"
    spec = _spec(tmp_path, [{"name": "Ada Maple"}])
    rc = cli.main(["scan", "--targets", str(spec), "--country", "CA", "--field", "causal ml",
                   "--email", EMAIL, "--out", str(out)])
    assert rc == 0
    assert "scanned 2 professors (live)" in capsys.readouterr().out
