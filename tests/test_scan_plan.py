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
    tp.record(openalex.authors_url("I1", EMAIL, topic_ids=["T10001", "T10002"]),
              200, json.dumps({"results": [
        {"id": "https://openalex.org/A1", "display_name": "Prof One", "works_count": 10,
         "topics": [], "last_known_institutions": [], "homepage_url": "https://uni.example/~a"}]}))
    # the --targets + --country union run carries NO plan topics (the field-text topic lookup
    # has no cassette and honestly resolves to []) — its enumeration is unfiltered
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


# ── Wave B audit fixes: plan/targets validation + honesty carry-over (S1–S5) ──

def test_scan_plan_mangled_value_types_fail_loud(tmp_path, capsys):
    # S3 (D-002): plan values are type-checked — never silently list()-mangled into
    # char-lists or AttributeError tracebacks. Each message names the key + both types.
    cases = [
        ({"universities": "Uni"}, "'universities' must be a list of strings, got str"),
        ({"resolved_topic_ids": "T10001"},
         "'resolved_topic_ids' must be a list of strings, got str"),
        ({"country": ["CA"]}, "'country' must be a string, got list"),
        ({"universities": {"Uni": True}}, "'universities' must be a list of strings, got dict"),
    ]
    for over, expected in cases:
        rc = cli.main(["scan", "--plan", str(_plan(tmp_path, **over)), "--email", EMAIL,
                       "--out", str(tmp_path / "d.html")])
        printed = capsys.readouterr().out
        assert rc == 2, (over, printed)
        assert expected in printed, (over, printed)


def test_scan_plan_enum_typos_fail_loud(tmp_path, capsys):
    # S4 (D-002/D-045): an unrecognized university_mode would otherwise silently scan the
    # WHOLE country (scope inversion). Case is significant — "ONLY" is rejected, never
    # quietly normalised: a scope decision is never silently rewritten.
    cases = [
        ({"university_mode": "onyl"}, "'university_mode' must be one of all, prioritise, only"),
        ({"university_mode": "ONLY"}, "'university_mode' must be one of all, prioritise, only"),
        ({"intent_kind": "take over the world"}, "'intent_kind' must be one of"),
    ]
    for over, expected in cases:
        rc = cli.main(["scan", "--plan", str(_plan(tmp_path, **over)), "--email", EMAIL,
                       "--out", str(tmp_path / "d.html")])
        printed = capsys.readouterr().out
        assert rc == 2, (over, printed)
        assert expected in printed, (over, printed)


def test_scan_targets_malformed_entries_fail_loud(tmp_path, capsys):
    # S5 (D-002): non-string name/affiliation fails loud — a numeric name must NOT be
    # searched verbatim, a numeric affiliation must NOT crash with AttributeError.
    cases = [
        ([{"name": 42}], "'name' must be a non-empty string"),
        ([{"name": "Ada Maple", "affiliation": 123}], "'affiliation' must be a string"),
        ([{"name": ["Ada Maple"]}], "'name' must be a non-empty string"),
    ]
    for entries, expected in cases:
        spec = _spec(tmp_path, entries)
        rc = cli.main(["scan", "--targets", str(spec), "--email", EMAIL,
                       "--out", str(tmp_path / "d.html")])
        printed = capsys.readouterr().out
        assert rc == 2, (entries, printed)
        assert expected in printed, (entries, printed)


def test_scan_plan_carried_targets_are_validated_too(tmp_path, capsys):
    # S5: the same entry validation applies to a plan-carried "targets" list.
    rc = cli.main(["scan", "--plan", str(_plan(tmp_path, targets=[{"name": 42}])),
                   "--email", EMAIL, "--out", str(tmp_path / "d.html")])
    printed = capsys.readouterr().out
    assert rc == 2 and "'name' must be a non-empty string" in printed


def test_scan_targets_lookup_failure_marks_partial_and_persists(
        tmp_path, monkeypatch, capsys):
    # S1 (D-037): an HTTP 500 on one of two --targets lookups must surface as PARTIAL
    # coverage + the author-search@ marker in the export AND the persisted run counts (so a
    # human-rung reexport still discloses it), and the console must say "lookup FAILED" —
    # a transient failure is never worded as "no match".
    from supervisorly import pipeline
    from supervisorly.model import runs
    from supervisorly.model.db import open_db

    tp = _targets_cassette()
    tp.record(openalex.author_search_url("Ghost Prof", EMAIL), 500, "server error")
    monkeypatch.setattr(transport_mod, "httpx_transport", lambda **kw: tp)
    out = tmp_path / "out" / "live.html"
    spec = _spec(tmp_path, [{"name": "Ghost Prof"}, {"name": "Ada Maple"}])
    rc = cli.main(["scan", "--targets", str(spec), "--email", EMAIL, "--out", str(out)])
    assert rc == 0                                    # the resolved target still deep-dives
    printed = capsys.readouterr().out
    assert "SKIPPED target Ghost Prof: OpenAlex lookup FAILED" in printed
    assert "scanned 1 professors (live)" in printed
    export = json.loads(out.with_suffix(".json").read_text(encoding="utf-8"))
    assert "PARTIAL" in export["run"]["coverage"]
    assert "author-search@Ghost Prof" in export["run"]["coverage"]
    # persisted on the run (update_counts/get_counts pattern) so a reexport keeps it (D-037)
    db = out.parent / "supervisorly.sqlite"
    conn = open_db(db)
    row = conn.execute(
        "SELECT run_id FROM run ORDER BY started_at DESC, rowid DESC LIMIT 1").fetchone()
    persisted = runs.get_counts(conn, row["run_id"])
    conn.close()
    assert "author-search@Ghost Prof" in persisted["truncated"]
    r2 = pipeline.reexport(
        str(db), [{"id": p["id"], "name": p.get("name")} for p in export["professors"]])
    assert "PARTIAL" in r2["export"]["run"]["coverage"]
    assert "author-search@Ghost Prof" in r2["export"]["run"]["coverage"]


def test_scan_targets_genuine_absence_stays_unmarked(tmp_path, monkeypatch, capsys):
    # S1 (other half): a 200 with empty results is a genuine "no such author" — an honest
    # skip, NOT a truncation marker and NOT PARTIAL coverage.
    tp = _targets_cassette()
    tp.record(openalex.author_search_url("Nobody Here", EMAIL), 200,
              json.dumps({"results": []}))
    monkeypatch.setattr(transport_mod, "httpx_transport", lambda **kw: tp)
    out = tmp_path / "out" / "live.html"
    spec = _spec(tmp_path, [{"name": "Nobody Here"}, {"name": "Ada Maple"}])
    rc = cli.main(["scan", "--targets", str(spec), "--email", EMAIL, "--out", str(out)])
    assert rc == 0
    printed = capsys.readouterr().out
    assert "SKIPPED target Nobody Here: no OpenAlex author match" in printed
    export = json.loads(out.with_suffix(".json").read_text(encoding="utf-8"))
    assert "PARTIAL" not in export["run"]["coverage"]


def test_scan_targets_resolution_travels_to_export_and_dashboard(
        tmp_path, monkeypatch, capsys):
    # S2 (D-010): the identity honesty label survives into the durable artifacts —
    # unverified (affiliation given, no hit matched), unchecked (no affiliation given),
    # verified (affiliation matched). validate_export stays clean either way.
    from supervisorly.export import json_export as jx

    cases = [
        ([{"name": "Ada Maple", "affiliation": "Nowhere College"}], "unverified"),
        ([{"name": "Ada Maple"}], "unchecked"),
        ([{"name": "Ada Maple", "affiliation": "Other Institute"}], "verified"),
    ]
    for entries, expected in cases:
        monkeypatch.setattr(transport_mod, "httpx_transport", lambda **kw: _targets_cassette())
        out = tmp_path / f"out_{expected}" / "live.html"
        rc = cli.main(["scan", "--targets", str(_spec(tmp_path, entries)), "--email", EMAIL,
                       "--out", str(out)])
        assert rc == 0
        export = json.loads(out.with_suffix(".json").read_text(encoding="utf-8"))
        assert jx.validate_export(export) == []
        assert export["professors"][0]["identity_resolution"] == expected
        # the dashboard is a VIEW over this JSON (D-046): the label must be in its inlined
        # data, and the badge renderer must be present (badges render client-side).
        html = out.read_text(encoding="utf-8")
        assert f'"identity_resolution": "{expected}"' in html
        assert "function idBadge(" in html


# ── scan --max-institutions (§4.3 scale control) ──────────────────────────────

def test_scan_max_institutions_reaches_the_ladder(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(transport_mod, "httpx_transport", lambda **kw: _ladder_cassette())
    seen = {}
    real = ladder.build_targets

    def spy(plan, ror, oa, **kw):
        seen.update(kw)
        return real(plan, ror, oa, **kw)

    monkeypatch.setattr(ladder, "build_targets", spy)
    out = tmp_path / "out" / "live.html"
    rc = cli.main(["scan", "--plan", str(_plan(tmp_path)), "--email", EMAIL,
                   "--max-institutions", "1", "--out", str(out)])
    assert rc == 0
    assert "scanned 1 professors (live)" in capsys.readouterr().out
    assert seen["max_institutions"] == 1


def test_scan_max_institutions_fails_loud_on_a_non_positive_cap(tmp_path, capsys):
    rc = cli.main(["scan", "--plan", str(_plan(tmp_path)), "--email", EMAIL,
                   "--max-institutions", "0", "--out", str(tmp_path / "d.html")])
    assert rc == 2
    assert "--max-institutions must be a positive integer, got 0." in capsys.readouterr().out
