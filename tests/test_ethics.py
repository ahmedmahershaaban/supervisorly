"""Ethics gates verified in code (D-005/009/024/035): no bare emails in exports, the
deterministic layer makes no LLM calls, and the methodology corpus is never read as data."""

from pathlib import Path

from supervisorly.export import json_export as jx

SRC = Path(__file__).resolve().parents[1] / "src" / "supervisorly"

# The deterministic layer (D-009): these packages/modules must contain zero model calls.
DETERMINISTIC = ["discover", "fetch", "model", "score", "export", "pipeline.py",
                 "ingest.py", "preflight.py", "demo.py"]
# Markers of an LLM/model dependency that must not appear in the deterministic layer.
LLM_MARKERS = ("import anthropic", "from anthropic", "import openai", "from openai",
               "OpenAI(", "Anthropic(", "messages.create", "chat.completions")
# The methodology-only corpus (D-035) must never be read/imported as data.
CORPUS_MARKERS = ("documents\\downloads", "documents/downloads")


def _py_files(*names):
    for n in names:
        p = SRC / n
        if p.is_dir():
            yield from p.rglob("*.py")
        elif p.exists():
            yield p


# ── no bare emails in exports (D-024) ─────────────────────────────────────────
def test_email_typed_field_is_dropped_at_build():
    export = jx.build_export(
        run_summary={"run_id": "r", "status": "finalized"},
        field_descriptors=[
            {"id": "recruiting", "label": "Recruiting", "kind": "filter", "datatype": "string"},
            {"id": "email", "label": "Email", "kind": "display", "datatype": "email"},
        ],
        professors=[{"id": "p1", "name": "P One"}],
        claims_by_entity={"p1": [
            {"field": "recruiting", "state": "value", "value": "recruiting",
             "quote": "q", "source_url": "https://p1/"},
            {"field": "email", "state": "value", "value": "p1@uni.edu",
             "quote": "q", "source_url": "https://p1/"},
        ]},
        generated_at="2026-07-23T00:00:00+00:00",
    )
    field_ids = {d["id"] for d in export["fields"]}
    assert "email" not in field_ids                       # dropped at build
    assert "email" not in export["professors"][0]["fields"]
    assert jx.validate_export(export) == []


def test_validate_rejects_a_leaked_email_field():
    bad = {"schema_version": "1", "generated_at": "t", "run": {},
           "fields": [{"id": "email", "label": "Email", "kind": "display", "datatype": "email"}],
           "professors": []}
    assert any("email" in e and "D-024" in e for e in jx.validate_export(bad))


def test_validate_rejects_a_bare_email_value_under_a_string_field():
    bad = {"schema_version": "1", "generated_at": "t", "run": {},
           "fields": [{"id": "contact", "label": "Contact", "kind": "display",
                       "datatype": "string"}],
           "professors": [{"id": "p", "fields": {"contact": {
               "state": "value", "value": "jane@uni.edu", "source_url": "https://p/"}}}]}
    assert any("email" in e.lower() for e in jx.validate_export(bad))


def test_incidental_email_inside_a_sentence_is_not_flagged():
    ok = {"schema_version": "1", "generated_at": "t", "run": {},
          "fields": [{"id": "recruiting", "label": "R", "kind": "filter",
                      "datatype": "string"}],
          "professors": [{"id": "p", "fields": {"recruiting": {
              "state": "value", "value": "Email me at jane@uni.edu to apply.",
              "source_url": "https://p/"}}}]}
    # a recruiting sentence that mentions an email is a legitimate quote, not a bare address
    assert jx.validate_export(ok) == []


# ── deterministic layer is LLM-free (D-009) ───────────────────────────────────
def test_deterministic_layer_has_no_llm_calls():
    offenders = []
    for f in _py_files(*DETERMINISTIC):
        text = f.read_text(encoding="utf-8")
        for marker in LLM_MARKERS:
            if marker in text:
                offenders.append(f"{f.name}: {marker}")
    assert offenders == [], offenders


# ── methodology corpus is never read as data (D-035) ──────────────────────────
def test_corpus_path_is_never_referenced_in_code():
    offenders = []
    for f in SRC.rglob("*.py"):
        low = f.read_text(encoding="utf-8").lower()
        for marker in CORPUS_MARKERS:
            if marker in low:
                offenders.append(f"{f.name}: {marker}")
    assert offenders == [], offenders


# ── no bulk-outreach path (D-024/053) ─────────────────────────────────────────
def test_no_bulk_outreach_helpers_exist():
    banned = ("smtplib", "send_email", "send_bulk", "mailto_all", "sendmail")
    offenders = []
    for f in SRC.rglob("*.py"):
        text = f.read_text(encoding="utf-8").lower()
        for b in banned:
            if b in text:
                offenders.append(f"{f.name}: {b}")
    assert offenders == [], offenders
