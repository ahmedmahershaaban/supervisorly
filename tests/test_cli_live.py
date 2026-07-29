"""Phase L8 — the `scan` CLI live path: fails loud without a contact email, needs country+field,
and (with a patched transport) runs the whole live pipeline to a dashboard offline."""

import json

from supervisorly import cli
from supervisorly.discover import openalex, ror
from supervisorly.fetch import transport as transport_mod
from supervisorly.fetch.transport import CassetteTransport

EMAIL = "me@uni.edu"


def _cassette():
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
    tp.record("https://uni.example/robots.txt", 200, "User-agent: *\nAllow: /\n")
    tp.record("https://uni.example/~a", 200,
              "<html><body><main><p>I am recruiting a PhD student for 2027.</p></main></body></html>")
    return tp


def test_scan_live_fails_loud_without_a_contact_email(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("SUPERVISORLY_CONTACT_EMAIL", raising=False)
    rc = cli.main(["scan", "--country", "CA", "--field", "causal ml",
                   "--out", str(tmp_path / "d.html")])
    assert rc == 2
    assert "SUPERVISORLY_CONTACT_EMAIL" in capsys.readouterr().out


def test_scan_live_needs_country_and_field(tmp_path, capsys):
    rc = cli.main(["scan", "--email", EMAIL, "--out", str(tmp_path / "d.html")])
    assert rc == 2
    assert "--country" in capsys.readouterr().out


def test_scan_live_runs_end_to_end_with_a_patched_transport(tmp_path, monkeypatch, capsys):
    # swap the live httpx transport for a cassette — the CLI wiring runs fully offline
    monkeypatch.setattr(transport_mod, "httpx_transport", lambda **kw: _cassette())
    out = tmp_path / "out" / "live.html"
    rc = cli.main(["scan", "--country", "CA", "--field", "causal ml", "--email", EMAIL,
                   "--out", str(out)])
    assert rc == 0
    assert out.exists() and out.with_suffix(".json").exists()
    printed = capsys.readouterr().out
    assert "scanned 1 professors (live)" in printed and printed.isascii()
    # This cassette deliberately records an UNFILTERED author query and no topics response,
    # i.e. the field did not resolve. That must now be said out loud: an unfiltered scan
    # returns the most prominent authors at the institution, not people in the field, and it
    # used to be indistinguishable from a filtered one (found via a live OpenAlex 429).
    assert "resolved to NO OpenAlex topics" in printed
    assert "causal ml" in printed
    # the sparse-coverage preflight is surfaced on the console (D-060): 1 institution < 5
    assert "WARNING: ROR lists only 1 institution(s)" in printed
    export = json.loads(out.with_suffix(".json").read_text(encoding="utf-8"))
    assert export["professors"][0]["fields"]["recruiting_signal"]["state"] == "value"


def test_scan_live_accepts_a_country_name(tmp_path, monkeypatch, capsys):
    # README/SKILL document `--country Canada`: the name resolves to ISO alpha-2 (CA) before the
    # plan is built — the cassette (keyed on the CA filter) only serves if it resolved (D-002).
    monkeypatch.setattr(transport_mod, "httpx_transport", lambda **kw: _cassette())
    out = tmp_path / "out" / "live.html"
    rc = cli.main(["scan", "--country", "Canada", "--field", "causal ml", "--email", EMAIL,
                   "--out", str(out)])
    assert rc == 0
    assert "scanned 1 professors (live)" in capsys.readouterr().out


def test_scan_live_rejects_an_unrecognized_country_loudly(tmp_path, capsys):
    # fail loud (exit 2) on an unrecognized country — never silently query ROR with a name
    rc = cli.main(["scan", "--country", "Narnia", "--field", "causal ml", "--email", EMAIL,
                   "--out", str(tmp_path / "d.html")])
    assert rc == 2
    assert "Narnia" in capsys.readouterr().out


def test_country_resolution_helper_codes_names_and_unknowns():
    # a multi-word name in the ISO table resolves (South Korea → KR); codes pass through;
    # unknowns return None so the CLI can fail loud
    from supervisorly.discover.countries import to_country_code
    assert to_country_code("South Korea") == "KR"
    assert to_country_code("Canada") == "CA"
    assert to_country_code("ca") == "CA"          # a 2-letter code passes through
    assert to_country_code("Narnia") is None


# ── live fix: --shortlist flag drives the D-056 gate ──────────────────────────

def _shortlist_cassette():
    """Two professors at one institution (works 10 and 5); only the works leader's page
    is recorded, so deep-diving the wrong one (or both) fails on the cassette seam."""
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
         "topics": [], "last_known_institutions": [], "homepage_url": "https://uni.example/~a"},
        {"id": "https://openalex.org/A2", "display_name": "Prof Two", "works_count": 5,
         "topics": [], "last_known_institutions": [], "homepage_url": "https://uni.example/~b"}]}))
    tp.record("https://uni.example/robots.txt", 200, "User-agent: *\nAllow: /\n")
    tp.record("https://uni.example/~a", 200,
              "<html><body><main><p>I am recruiting a PhD student for 2027.</p></main></body></html>")
    return tp


def test_scan_shortlist_flag_bounds_the_deep_dive(tmp_path, monkeypatch, capsys):
    # the CLI field-text topic lookup has no cassette and honestly resolves to [] -> the
    # enumeration is unfiltered and the gate ranks by works_count (see _apply_shortlist).
    monkeypatch.setattr(transport_mod, "httpx_transport", lambda **kw: _shortlist_cassette())
    out = tmp_path / "out" / "live.html"
    rc = cli.main(["scan", "--country", "CA", "--field", "causal ml", "--email", EMAIL,
                   "--shortlist", "1", "--out", str(out)])
    assert rc == 0
    printed = capsys.readouterr().out
    assert "scanned 2 professors (live)" in printed      # both enumerated, nobody dropped
    export = json.loads(out.with_suffix(".json").read_text(encoding="utf-8"))
    states = {p["id"]: p["fields"]["recruiting_signal"]["state"]
              for p in export["professors"]}
    assert states == {"A1": "value", "A2": "never_attempted"}
    assert "Deep-dived the top 1 by topic fit" in export["run"]["coverage"]


def test_scan_shortlist_rejects_a_non_positive_cap(tmp_path, monkeypatch, capsys):
    # fail loud (D-002): --shortlist 0 would silently deep-dive NOBODY
    monkeypatch.setattr(transport_mod, "httpx_transport", lambda **kw: _shortlist_cassette())
    rc = cli.main(["scan", "--country", "CA", "--field", "causal ml", "--email", EMAIL,
                   "--shortlist", "0", "--out", str(tmp_path / "d.html")])
    assert rc == 2
    assert "--shortlist must be a positive integer" in capsys.readouterr().out


# ── §4.1: scan --progress prints one ASCII line per engine event ─────────────

def test_scan_progress_flag_prints_one_ascii_line_per_event(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(transport_mod, "httpx_transport", lambda **kw: _cassette())
    out = tmp_path / "out" / "live.html"
    rc = cli.main(["scan", "--country", "CA", "--field", "causal ml", "--email", EMAIL,
                   "--progress", "--out", str(out)])
    assert rc == 0
    captured = capsys.readouterr()
    lines = [l for l in captured.err.splitlines() if l.startswith("progress: ")]
    assert lines == [
        "progress: enumerated 1 targets across 1 institutions",
        "progress: deep-dive 0/1",
        # Two honest truncation markers (D-037), riding the same stream as a partial_warning:
        # the cassette lacks ROR's number_of_results, AND it records no topics response, so
        # the topic lookup FAILS. That second marker is the point — a failed topic lookup
        # used to be indistinguishable from "OpenAlex has no such topic", and both silently
        # produced an unfiltered scan of the wrong professors.
        "progress: PARTIAL - Coverage is PARTIAL - 2 source(s) had more results than "
        "were enumerated (institutions@CA, topics@causal ml).",
        "progress: deep-dive 1/1",
        "progress: scoring",
        "progress: exported",
    ]
    assert captured.err.isascii()
    assert "progress: " not in captured.out          # stderr only; stdout is result lines


def test_scan_default_is_silent_about_progress(tmp_path, monkeypatch, capsys):
    # no --progress flag → exactly today's behavior: no progress lines anywhere
    monkeypatch.setattr(transport_mod, "httpx_transport", lambda **kw: _cassette())
    out = tmp_path / "out" / "live.html"
    rc = cli.main(["scan", "--country", "CA", "--field", "causal ml", "--email", EMAIL,
                   "--out", str(out)])
    assert rc == 0
    captured = capsys.readouterr()
    assert "progress: " not in captured.out
    assert "progress: " not in captured.err
