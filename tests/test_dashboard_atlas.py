"""Phase L7 — the dashboard is recreated in the "Supervisorly Atlas — Living" design language:
bioluminescent tokens, Space Grotesk/Mono, the cells-and-filaments diagram engine, and a
how-it-works specimen — all in ONE self-contained, offline, reduced-motion-aware file."""

from supervisorly.export import dashboard as db
from supervisorly.export import json_export as jx


def _html():
    export = jx.build_export(
        run_summary={"run_id": "r", "status": "finalized"},
        field_descriptors=[
            {"id": "recruiting", "label": "Recruiting", "kind": "filter", "datatype": "string"},
            {"id": "deadline", "label": "Deadline", "kind": "sort", "datatype": "date"},
        ],
        professors=[{"id": "p1", "name": "Prof One"}],
        claims_by_entity={"p1": [
            {"field": "recruiting", "state": "value", "value": "recruiting",
             "quote": "q", "source_url": "https://p1/"},
        ]},
        generated_at="2026-07-23T00:00:00+00:00",
    )
    return db.build_dashboard(export)


def test_atlas_tokens_and_type_present():
    html = _html()
    assert "#05070c" in html                       # base void
    for kind in ("#43c9d6", "#79d06a", "#f0839a", "#e8b24a", "#b58cf0"):  # tissue-type palette
        assert kind in html
    assert "Space Grotesk" in html and "Space Mono" in html
    assert "@keyframes omFlow" in html and "@keyframes omBreathe" in html


def test_fonts_are_self_contained_no_external_load():
    html = _html().lower()
    # named with fallbacks but NEVER imported from a CDN — the file must stay self-contained
    assert "googleapis" not in html and "@import" not in html
    assert "<link " not in html and "<script src=" not in html and "cdn" not in html


def test_diagram_engine_cells_and_filaments():
    html = _html()
    assert "drawDiagram" in html and "om-overlay" in html
    # curved bezier filaments with animated light-packets + deterministic bow sign + arrowheads
    assert "'M'+x0+' '+y0+' C'+c1x" in html          # cubic-bezier path
    assert 'stroke-dasharray="0.1 12"' in html and "om-flt" in html
    assert "hash(e[0]+e[1])%2" in html               # parallel edges bow opposite ways
    assert "<polygon" in html                        # arrowheads
    # highlight-connected + recompute on resize (the engine's core behaviours)
    assert "function hl(" in html
    assert 'addEventListener("resize"' in html


def test_how_it_works_view_and_reduced_motion():
    html = _html()
    assert 'id="vHow"' in html and "How it works" in html
    assert "SPEC" in html and '"discover"' in html   # the specimen's nodes/edges are present
    assert "prefers-reduced-motion" in html          # animation disabled for reduced motion
    assert "Xeno-Atlas" in html                      # the Atlas hero eyebrow


def test_professor_detail_is_a_cell_drawer():
    html = _html()
    assert "openDetail" in html and "closeDetail" in html
    assert "Cell detail" in html                      # the drawer's eyebrow label
    assert 'aside class="detail"' in html             # the right-sheet cell drawer markup
    assert "blockquote" in html                        # shows the verbatim quote (traceable, D-010)
