"""PDF text extraction (CC-5).

**The gap this closes.** The engine could not see PDFs *at all*, and admissions information —
deadlines, entry requirements, funding conditions — is frequently PDF-only. Such a page
contributed nothing and, worse, said nothing about why. A student reading "we looked, found
nothing" had no way to know the page was a scan of a printed prospectus.

**Code extracts, a model only reads.** The text comes out of ``pypdf``, never out of a model
asked to "read this PDF". A model that transcribes is a model that can silently improve the
wording, and the quote gate would then be verifying the model against itself.

**The snapshot is the contract.** Extracted text is wrapped in an escaped ``<pre>`` envelope
and stored exactly like HTML, so ``normalize.main_text`` and ``normalize.quote_in_snapshot``
work on it unchanged. That envelope is load-bearing rather than cosmetic: ``main_text`` runs
an HTML parser, so raw PDF prose containing ``<`` or ``&`` would be silently mangled — and a
quote that fails to match its own snapshot is a claim the gate throws away (D-010).
"""

from __future__ import annotations

import html as _html
import io

#: Every PDF begins with this, per the specification. The sniff exists because a
#: content-type header is a claim by the server, and servers get it wrong constantly —
#: `application/octet-stream` for a PDF is routine, as is `text/html` for a redirect page
#: that is actually a PDF. Trusting the header alone silently skips real admissions pages.
PDF_MAGIC = b"%PDF-"

#: Content types that assert a PDF. Some servers use the pre-registration x- form.
PDF_CONTENT_TYPES = frozenset({"application/pdf", "application/x-pdf"})

#: Why a PDF we could reach still yielded nothing. A real, reportable state — never silence.
SCANNED_REASON = "scanned PDF — no text layer"


def looks_like_pdf(content_type: str | None, data: bytes | None) -> bool:
    """True if this response is a PDF, by **content-type or magic bytes** (CC-5.2).

    Either signal alone is enough, deliberately. The header is what the server *claims*; the
    magic bytes are what the body *is*. Requiring both would drop every PDF served as
    ``application/octet-stream``; requiring only the header would drop those and also trust a
    header on a body that is not a PDF at all.
    """
    if (content_type or "").split(";", 1)[0].strip().lower() in PDF_CONTENT_TYPES:
        return True
    return bool(data) and data[:len(PDF_MAGIC)] == PDF_MAGIC


def extract_pdf_text(data: bytes | None) -> str | None:
    """The PDF's text layer, or ``None`` if it has none.

    ``None`` means "there is nothing to read" — a scanned page, an image-only prospectus, or
    a file we could not parse. The caller turns that into a `blocked` state carrying
    ``SCANNED_REASON``; it must never become an empty string, which would read as "we looked
    and the document said nothing".

    Never raises. A malformed PDF is a page we cannot use, not a reason to fail a scan —
    the same rule every other reader in ``fetch/`` follows.
    """
    if not data:
        return None
    try:
        from pypdf import PdfReader              # noqa: PLC0415 — lazy: offline use needs none
    except ImportError:
        # Fail closed and INERT, exactly like the render rung without Playwright (D-068):
        # without the dependency a PDF is simply unreadable, which is where we started.
        return None
    try:
        reader = PdfReader(io.BytesIO(data))
        parts = []
        for page in reader.pages:
            try:
                parts.append(page.extract_text() or "")
            except Exception:                    # noqa: BLE001 — one bad page, not a bad file
                continue
    except Exception:                            # noqa: BLE001 — encrypted, truncated, corrupt
        return None
    text = "\n".join(p for p in parts if p.strip())
    return text if text.strip() else None


def as_snapshot(text: str) -> str:
    """Wrap extracted text so it stores and reads back exactly like an HTML snapshot.

    Escaped, so PDF prose containing ``<`` or ``&`` survives ``main_text``'s HTML parser
    intact — otherwise a quote could fail to match the very snapshot it was taken from.
    """
    return f"<pre>{_html.escape(text)}</pre>"
