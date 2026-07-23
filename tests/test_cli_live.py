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
    tp.record(ror.country_url("CA"), 200, json.dumps({"items": [
        {"id": "https://ror.org/00x", "name": "Uni", "country": {"country_code": "CA"},
         "links": ["https://uni.example/"], "types": ["Education"]}]}))
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
    export = json.loads(out.with_suffix(".json").read_text(encoding="utf-8"))
    assert export["professors"][0]["fields"]["recruiting_signal"]["state"] == "value"
