"""The design atlas points at real code — enforced, not asserted in prose.

`docs/atlas.html` renders a "Where it lives" panel when you click a diagram node, and
`docs/design-atlas.md` carries the same mapping as a table. Both claim to be
machine-verified. This is the machine.

Without these tests the mapping rots silently: a rename leaves the atlas pointing at a
symbol that no longer exists, and the atlas becomes a confident liar — which is worse than
having no mapping at all. Here a rename fails the suite instead.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
ATLAS_HTML = ROOT / "docs" / "atlas.html"
ATLAS_MD = ROOT / "docs" / "design-atlas.md"


def _node_code() -> dict:
    """The NODE_CODE object literal out of atlas.html (it is strict JSON by construction)."""
    t = ATLAS_HTML.read_text(encoding="utf-8")
    i = t.index("var NODE_CODE = ")
    start = t.index("{", i)
    depth, j, in_str, esc = 0, start, False, False
    while j < len(t):                      # brace-match, string-aware
        c = t[j]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
        elif c == '"':
            in_str = True
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return json.loads(t[start:j + 1])
        j += 1
    raise AssertionError("NODE_CODE literal is unterminated")


def _defines(path: Path, sym: str) -> bool:
    t = path.read_text(encoding="utf-8", errors="replace")
    if path.suffix == ".sql":
        return re.search(
            rf"(?im)^\s*create\s+table\s+(if\s+not\s+exists\s+)?[\"'`]?{re.escape(sym)}\b", t
        ) is not None
    return any(re.search(p, t) for p in (
        rf"(?m)^\s*(async\s+)?def\s+{re.escape(sym)}\s*\(",
        rf"(?m)^\s*class\s+{re.escape(sym)}\b",
        rf"(?m)^{re.escape(sym)}\s*[:=]",
        rf"(?m)^\s{{4}}{re.escape(sym)}\s*[:=]",
    ))


CODE = _node_code()
REFS = [(node, r) for node, refs in CODE.items() for r in refs]


def test_the_atlas_maps_a_meaningful_number_of_nodes():
    """Guard against the map being silently emptied — an empty map would pass every
    per-reference test below while telling the reader nothing."""
    assert len(CODE) >= 50, f"only {len(CODE)} nodes mapped"
    assert len(REFS) >= 100, f"only {len(REFS)} code references"


@pytest.mark.parametrize("node,ref", REFS, ids=[f"{n}:{r['p']}" for n, r in REFS])
def test_every_atlas_code_reference_exists(node, ref):
    """Each (path, symbol) the atlas shows must resolve in this tree."""
    p = ROOT / ref["p"]
    assert p.exists(), f"node {node!r} points at a missing file: {ref['p']}"
    if "s" in ref:
        assert _defines(p, ref["s"]), \
            f"node {node!r}: {ref['p']} no longer defines {ref['s']!r}"


def test_every_mapped_node_is_a_real_drawer_entry():
    """NODE_CODE keys must match NODE_INFO keys, or the panel silently shows nothing."""
    t = ATLAS_HTML.read_text(encoding="utf-8")
    seg = t[t.index("var NODE_INFO"):t.index("var NODE_CODE")]
    info_keys = set(re.findall(r'^\s*"([^"]+)":\{', seg, re.M))
    orphans = sorted(set(CODE) - info_keys)
    assert not orphans, f"NODE_CODE keys with no NODE_INFO entry: {orphans}"


def test_the_markdown_twin_carries_the_same_mapping():
    """design-atlas.md and atlas.html must not drift apart — same source, same table."""
    md = ATLAS_MD.read_text(encoding="utf-8")
    assert "WHERE IT LIVES" in md, "the markdown atlas lost its code-map section"
    for node, ref in REFS:
        assert f"`{ref['p']}`" in md, f"{ref['p']} (node {node!r}) missing from design-atlas.md"


def test_unbuilt_nodes_are_declared_honestly():
    """Concepts the maps draw but the code does not implement must be labelled, not hidden."""
    t = ATLAS_HTML.read_text(encoding="utf-8")
    i = t.index("var NODE_UNBUILT = ")
    unbuilt = json.loads(t[t.index("{", i):t.index("};", i) + 1])
    assert unbuilt, "the not-built map is empty — if everything is built, delete the mechanism"
    for node, note in unbuilt.items():
        assert node not in CODE, f"{node!r} is marked unbuilt AND mapped to code"
        assert len(note) > 40, f"{node!r}'s not-built note is too terse to be useful"
    md = ATLAS_MD.read_text(encoding="utf-8")
    for node in unbuilt:
        assert node in md, f"{node!r} is unbuilt in atlas.html but absent from design-atlas.md"
