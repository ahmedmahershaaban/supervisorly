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
