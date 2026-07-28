"""`docs/USER_GUIDE.html` is generated from `docs/USER_GUIDE.md` — keep them in step.

A derived file that silently falls behind its source is worse than no derived file: the
Markdown renders on GitHub while the HTML is what gets shared, so a drifted HTML tells a
reader something the project no longer believes. These tests fail when someone edits the
Markdown and forgets `tools/build_user_guide.py`.

They also pin the two properties that make the HTML worth having at all: it is genuinely
self-contained (no external request, which is the same rule the product follows under
D-069), and the screenshots are actually embedded rather than referenced.
"""

from __future__ import annotations

import html as _html
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MD = ROOT / "docs" / "USER_GUIDE.md"
HTML = ROOT / "docs" / "USER_GUIDE.html"
SHOTS = ROOT / "docs" / "guide"


@pytest.fixture(scope="module")
def md() -> str:
    return MD.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def page() -> str:
    return HTML.read_text(encoding="utf-8")


def _plain(text: str) -> str:
    """Heading text with Markdown markers stripped, as the builder renders it."""
    t = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    t = re.sub(r"\*\*([^*]+)\*\*", r"\1", t)
    t = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"\1", t)
    return re.sub(r"\s+", " ", t.replace("`", "")).strip()


def test_both_artifacts_exist():
    assert MD.exists(), "the Markdown source is missing"
    assert HTML.exists(), "run tools/build_user_guide.py — the HTML has not been generated"


def test_every_markdown_section_survived_into_the_html(md, page):
    """The load-bearing check: a section added to the Markdown but never rebuilt into the
    HTML is exactly the drift this file exists to catch."""
    headings = [_plain(m.group(2)) for m in re.finditer(r"^(#{2,3})\s+(.*)$", md, re.M)]
    headings = [h for h in headings if h and h != "Contents"]
    assert len(headings) >= 15, f"only found {len(headings)} headings — parser broken?"

    # entities must be decoded first, or "Scope & Scan" never matches "Scope &amp; Scan"
    text = _html.unescape(re.sub(r"<[^>]+>", " ", page))
    text = re.sub(r"\s+", " ", text)
    missing = [h for h in headings if h not in text]
    assert not missing, (
        f"{len(missing)} section(s) in USER_GUIDE.md are absent from USER_GUIDE.html — "
        f"regenerate with tools/build_user_guide.py: {missing[:5]}")


def test_the_page_is_genuinely_self_contained(page):
    """No CDN, no font host, no tracker — the same promise the product itself makes."""
    external = [u for u in re.findall(r'(?:src|href)=["\']((?:https?:)?//[^"\']+)', page)
                if "supervisorly.web.app" not in u]
    assert not external, f"external resources would break offline use: {external[:4]}"
    assert "<script src=" not in page and "@import" not in page


def test_the_screenshots_are_embedded_not_linked(page):
    """A shared HTML file with linked images arrives broken."""
    embedded = page.count("data:image/webp")
    on_disk = len(list(SHOTS.glob("*.png")))
    assert embedded == on_disk, \
        f"{embedded} images embedded but {on_disk} screenshots exist in docs/guide/"
    assert 'src="guide/' not in page, "an image is referenced by path instead of embedded"


def test_no_unconverted_markdown_leaked_into_the_page(page):
    """Catches the converter silently failing on a construct — a literal '| --- |' or a
    raw heading in the output means a whole table or section rendered as prose."""
    body = page.split("<main>", 1)[-1].split("</main>", 1)[0]
    assert "<p>|" not in body, "a table rendered as a paragraph"
    assert not re.search(r"<p>#{1,6}\s", body), "a heading rendered as a paragraph"
    assert not re.search(r"<p>[^<]*\]\(http", body), "a link rendered as literal Markdown"


def test_the_navigation_resolves(page):
    """Every sidebar entry must point at a heading that exists on the page."""
    ids = set(re.findall(r'<h[23] id="([^"]+)"', page))
    links = re.findall(r'class="l[23]" href="#([^"]+)"', page)
    assert links, "the sidebar has no entries"
    dead = sorted(set(links) - ids)
    assert not dead, f"sidebar links with no matching section: {dead}"


def test_the_guide_states_what_is_not_built(md):
    """The guide's honesty section is load-bearing: a guide that lists only what works is
    marketing. If Stage 4 ever ships, this test should be updated deliberately."""
    assert "not* built" in md or "not built" in md.lower()
    assert "BLOCKERS.md" in md, "the open decisions should be linked from the guide"
