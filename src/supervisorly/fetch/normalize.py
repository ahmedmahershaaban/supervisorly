"""Content normalisation, the cache hash, and quote verification.

Two distinct products from one page — do not conflate them:

* ``main_text(html)`` — the faithful main content with boilerplate (script/style/
  nav/footer/header/aside) removed and whitespace collapsed. This is what quotes are
  verified against, so it **keeps dates and numbers** (a recruiting quote may contain
  a deadline).

* ``content_hash(html)`` — ``main_text`` with *volatile tokens* (timestamps, view
  counters, dates) masked before hashing. This is the ExtractionCache key: two
  captures of the same page that differ only in a "last updated" line or a hit
  counter hash **identically**, so a monthly re-scan hits cache and issues ~0 LLM
  calls (cost §3b-i). A genuine content change still changes the hash.

Pure stdlib — no third-party HTML parser — so it is testable offline with no deps.
"""

from __future__ import annotations

import hashlib
import re
from html.parser import HTMLParser

# Unambiguous boilerplate — dropped from BOTH the text and the hash.
_SKIP_TAGS = {
    "script", "style", "noscript", "nav", "footer", "header",
    "aside", "form", "svg", "button", "template",
}

# Volatile *chrome* tokens masked for the HASH ONLY (kept in main_text).
# IMPORTANT: standalone content dates are deliberately NOT masked — a changed
# application deadline must change the hash and invalidate the cache (D-061).
# Only mask timestamps tied to a chrome keyword, copyright years, clock times, and
# view/visitor counters.
_VOLATILE = re.compile(
    r"""(
        \b(?:last\s+updated|updated|generated|accessed|retrieved)\s*:?\s*[^\n]{0,40}
      | ©\s*20\d{2}[^\n]{0,30}
      | \bcopyright\s+20\d{2}[^\n]{0,30}
      | \b\d{1,3}(?:,\d{3})+\s+(?:views?|visitors?|comments?|reads?)\b
      | \b\d{1,2}:\d{2}(?::\d{2})?\b             # clock times (page-render, not deadlines)
    )""",
    re.IGNORECASE | re.VERBOSE,
)

_WS = re.compile(r"\s+")


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip_depth = 0
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in _SKIP_TAGS:
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0:
            self._parts.append(data)

    @property
    def text(self) -> str:
        return _WS.sub(" ", " ".join(self._parts)).strip()


def main_text(html: str) -> str:
    """Faithful main content — boilerplate removed, whitespace collapsed. Keeps dates."""
    p = _TextExtractor()
    p.feed(html)
    p.close()
    return p.text


def content_hash(html: str) -> str:
    """Stable cache key: main_text with volatile tokens masked, then SHA-256 (cost §3b-i)."""
    masked = _VOLATILE.sub(" ", main_text(html))
    masked = _WS.sub(" ", masked).strip()
    return hashlib.sha256(masked.encode("utf-8")).hexdigest()


def _canon(s: str) -> str:
    return _WS.sub(" ", s).strip().lower()


def quote_in_snapshot(quote: str, html: str) -> bool:
    """True iff ``quote`` appears in the page's main text (whitespace/case-insensitive).

    The anti-hallucination primitive (D-010): a claim whose quote is not found here is
    rejected before it is ever stored. Proves *fidelity* (the model didn't invent text
    relative to the page), not *truth* — the page itself can still be wrong.
    """
    if not quote or not quote.strip():
        return False
    return _canon(quote) in _canon(main_text(html))
