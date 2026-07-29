"""T-1 — a translation is DISPLAY, and can never become evidence.

Ahmed asked for a marker showing a page was machine-translated, so a student knows the result
depends on that translation and should check the page before relying on it. The constraint
that shapes it: the quote must be verbatim in the stored snapshot. Translate the page, store
an English quote, and we have manufactured a sentence the page never contained — fabricating
evidence, with good intentions.

So the layering is: **snapshot** original always · **quote** original, verbatim, gate-verified
· **value** may be normalised English · **translation** display only, labelled, beside the
quote and never in place of it.

The load-bearing test is `test_a_translated_quote_can_never_satisfy_the_gate`. Everything else
here is presentation; that one is the D-010 boundary.
"""

from __future__ import annotations

from supervisorly.export import dashboard as dash
from supervisorly.export import json_export as jx
from supervisorly.model import claims
from supervisorly.model.db import open_db

# A real sentence in Arabic, and an English rendering of it. The snapshot holds only the first.
AR = "نبحث عن طلاب دكتوراه للانضمام إلى المختبر في خريف 2027."
EN = "We are looking for PhD students to join the lab in autumn 2027."
SNAP = f"<html><body><main><p>{AR}</p></main></body></html>"


def _conn():
    return open_db()


# ── the boundary ──────────────────────────────────────────────────────────────
def test_a_translated_quote_can_never_satisfy_the_gate():
    """The whole point of T-1. The snapshot is Arabic; an English sentence is not in it, and
    supplying it as `quote_translated` must not make it verifiable."""
    conn = _conn()
    src = claims.record_web_source(conn, "https://u.edu/p", snapshot_hash="h1")
    r = claims.record_claim(
        conn, entity_kind="person", entity_id="p1", field="recruiting_signal",
        value="open for PhD 2027",
        quote=EN,                       # English — NOT what the page says
        quote_translated=EN,
        translated_by="test-mt",
        source_id=src, snapshot_hash="h1", snapshot_html=SNAP)
    assert r.claim_id is None
    assert "quote not found in snapshot" in (r.rejected or "")


def test_the_source_language_quote_verifies_and_carries_its_translation():
    """The acceptance case: an Arabic page yields an Arabic quote that verifies, plus an
    English display translation."""
    conn = _conn()
    src = claims.record_web_source(conn, "https://u.edu/p", snapshot_hash="h1")
    r = claims.record_claim(
        conn, entity_kind="person", entity_id="p1", field="recruiting_signal",
        value="open for PhD 2027",
        quote=AR, quote_translated=EN, translated_by="test-mt",
        source_id=src, snapshot_hash="h1", snapshot_html=SNAP)
    assert r.claim_id, r.rejected
    stored = claims.claims_for(conn, "person", "p1")[0]
    assert stored["quote"] == AR, "the stored quote must stay in the source language"
    assert stored["quote_translated"] == EN
    assert stored["translated_by"] == "test-mt"


def test_a_claim_without_a_translation_stores_none():
    conn = _conn()
    src = claims.record_web_source(conn, "https://u.edu/p", snapshot_hash="h1")
    claims.record_claim(conn, entity_kind="person", entity_id="p2",
                        field="recruiting_signal", value="v", quote=AR,
                        source_id=src, snapshot_hash="h1", snapshot_html=SNAP)
    stored = claims.claims_for(conn, "person", "p2")[0]
    assert stored["quote_translated"] is None and stored["translated_by"] is None


# ── the export ────────────────────────────────────────────────────────────────
def _env(**over):
    claim = {"field": "recruiting_signal", "state": "value", "value": "v", "quote": AR,
             "source_url": "https://u.edu/p", "observed_at": "2026-07-29T00:00:00+00:00"}
    claim.update(over)
    return jx._envelope(claim)


def test_the_envelope_carries_the_translation_beside_the_quote():
    e = _env(quote_translated=EN, translated_by="test-mt")
    assert e["quote"] == AR, "the verbatim quote is never replaced"
    assert e["quote_translated"] == EN
    assert e["translated_by"] == "test-mt"


def test_the_keys_are_absent_when_there_is_no_translation():
    """Absent, not null: their presence is exactly what tells the UI to show the marker, so a
    key that is always there would make the marker meaningless."""
    e = _env()
    assert "quote_translated" not in e and "translated_by" not in e


def test_an_empty_translation_is_not_a_translation():
    assert "quote_translated" not in _env(quote_translated="")


# ── the dashboard ─────────────────────────────────────────────────────────────
def _export(field_env):
    return {"schema_version": "1", "generated_at": "2026-07-29T00:00:00+00:00",
            "run": {"run_id": "r", "status": "finalized", "coverage": "c", "ledger": [],
                    "intents": []},
            "fields": [{"id": "recruiting_signal", "label": "Recruiting signal",
                        "kind": "filter", "datatype": "string"}],
            "professors": [{"id": "p1", "name": "Dr Example",
                            "fields": {"recruiting_signal": field_env}}]}


def _data_block(html: str) -> str:
    """Just the inlined `const DATA = …` payload.

    Asserting on the whole document is what the first version of this test did, and it failed
    for the right reason: `transMark`'s own source contains the string "quote_translated", so
    the marker's *code* is present on every page. What must differ is the DATA that triggers
    it.
    """
    return html.split("const DATA = ", 1)[1].split("</script>", 1)[0]


def test_the_icon_appears_only_when_a_translation_exists():
    with_t = dash.build_dashboard(_export(_env(quote_translated=EN, translated_by="mt")))
    without = dash.build_dashboard(_export(_env()))
    assert "tmark" in with_t, "the marker's renderer must be on the page"
    assert "quote_translated" in _data_block(with_t)
    assert "quote_translated" not in _data_block(without)


def test_the_original_is_always_reachable_and_shown_first():
    """T-1.4. The translation is additional, never a replacement — if the Arabic disappeared
    from the page, the student could no longer check the claim against the source."""
    html = dash.build_dashboard(_export(_env(quote_translated=EN, translated_by="mt")))
    assert AR in html, "the source-language quote must still be on the page"
    assert EN in html


def test_the_hover_says_it_is_machine_translated_and_to_check_the_original():
    html = dash.build_dashboard(_export(_env(quote_translated=EN, translated_by="mt")))
    assert "Machine-translated" in html
    assert "check it before relying" in html


def test_the_marker_is_keyboard_reachable_and_labelled():
    """FE-6.1 applied to the one control T-1 adds: a title attribute alone is invisible to a
    keyboard or screen-reader user."""
    html = dash.build_dashboard(_export(_env(quote_translated=EN, translated_by="mt")))
    assert 'tabindex="0"' in html
    assert "aria-label=\"machine-translated" in html


def test_a_hostile_translation_cannot_break_out_of_the_page():
    """`quote_translated` is model-produced text rendered into HTML — same escaping as
    everything else."""
    html = dash.build_dashboard(
        _export(_env(quote_translated="</script><img src=x onerror=alert(1)>",
                     translated_by="mt")))
    assert "</script><img" not in html
