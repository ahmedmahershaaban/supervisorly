"""CC-5 — reading PDFs, and saying so honestly when we cannot.

The verified gap: the engine could not see PDFs at all, and admissions information is
frequently PDF-only. Such a page contributed nothing *and said nothing about why*, which is
the part that matters — "we looked, found nothing" and "the document is a scan of a printed
prospectus" are different answers, and only one of them tells a student to go look themselves.

The PDFs here are built by `pypdf` at test time rather than committed as fixtures. A binary
blob in the repo is one nobody can read in a diff, and — more to the point — D-035 forbids
importing document files as data. A PDF this test wrote itself is not somebody's page.
"""

from __future__ import annotations

import io

import pytest

from supervisorly.fetch import pdf
from supervisorly.fetch.fetcher import Fetcher
from supervisorly.fetch.normalize import main_text, quote_in_snapshot
from supervisorly.fetch.ratelimit import HostRateLimiter
from supervisorly.fetch.snapshot import SnapshotStore
from supervisorly.fetch.transport import MAX_RESPONSE_BYTES, CassetteTransport

pypdf = pytest.importorskip("pypdf")

ALLOW = "User-agent: *\nAllow: /\n"
SENTENCE = "Applications for the MSc close on 1 December 2026."


def _pdf_escape(s: str) -> str:
    """PDF string-literal escaping: backslash first, then the delimiters."""
    return s.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


def _pdf_with_text(*lines: str) -> bytes:
    """A real, single-page PDF carrying a text layer, assembled by hand.

    `pypdf` writes PDFs but cannot DRAW text (no `add_text`), and pulling in reportlab to
    generate two fixtures would add a dependency the product does not have. A minimal PDF is
    a few objects and a content stream, and building it here means the bytes under test are
    the same on every machine — with correct xref offsets, so the file is valid rather than
    merely tolerated by a lenient parser.
    """
    body = "BT /F1 12 Tf " + " ".join(
        f"1 0 0 1 52 {740 - i * 18} Tm ({_pdf_escape(line)}) Tj" for i, line in enumerate(lines)
    ) + " ET"
    stream = body.encode("latin-1")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref_at = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode() + b"0000000000 65535 f \n"
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += (f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_at}\n%%EOF\n").encode()
    return bytes(out)


def _pdf_without_text() -> bytes:
    """A page with NO text layer — what a scanned prospectus looks like to a parser."""
    from pypdf import PdfWriter

    w = PdfWriter()
    w.add_blank_page(width=612, height=792)
    buf = io.BytesIO()
    w.write(buf)
    return buf.getvalue()


# ── detection (CC-5.2) ────────────────────────────────────────────────────────
def test_a_declared_pdf_is_detected():
    assert pdf.looks_like_pdf("application/pdf", b"")


def test_a_content_type_with_parameters_still_matches():
    assert pdf.looks_like_pdf("application/pdf; charset=binary", b"")


def test_magic_bytes_win_when_the_header_is_wrong():
    """`application/octet-stream` for a PDF is routine. Trusting only the header silently
    skips real admissions pages, which is the whole failure this phase exists to fix."""
    assert pdf.looks_like_pdf("application/octet-stream", b"%PDF-1.7\n...")


def test_a_header_alone_is_enough_when_bytes_are_unavailable():
    assert pdf.looks_like_pdf("application/pdf", None)


def test_an_html_page_is_not_a_pdf():
    assert not pdf.looks_like_pdf("text/html", b"<html><body>hello</body></html>")
    assert not pdf.looks_like_pdf(None, None)


def test_a_pdf_mentioned_in_html_is_not_a_pdf():
    """The magic bytes must be at the START, not anywhere in the body — otherwise a page
    that merely links to "%PDF-" or discusses the format is misread as one."""
    assert not pdf.looks_like_pdf("text/html", b"<p>the file starts with %PDF-1.4</p>")


# ── extraction (CC-5.1, CC-5.3) ───────────────────────────────────────────────
def test_a_text_pdf_extracts_its_text():
    got = pdf.extract_pdf_text(_pdf_with_text(SENTENCE))
    assert got and "1 December 2026" in got


def test_a_pdf_with_no_text_layer_returns_none_not_empty_string():
    """CC-5.3. `None` and `""` are different answers: one is "there is nothing to read",
    the other is "we read it and it said nothing". Only the first is true of a scan."""
    assert pdf.extract_pdf_text(_pdf_without_text()) is None


def test_a_corrupt_pdf_returns_none_rather_than_raising():
    """A malformed file is a page we cannot use, not a reason to fail a whole scan."""
    assert pdf.extract_pdf_text(b"%PDF-1.4\nthis is not really a pdf") is None


def test_empty_and_missing_data_are_none():
    assert pdf.extract_pdf_text(b"") is None
    assert pdf.extract_pdf_text(None) is None


# ── the snapshot contract (CC-5.1) ────────────────────────────────────────────
def test_extracted_text_round_trips_through_the_quote_gate():
    """The whole point: a PDF snapshot must satisfy the D-010 gate exactly like HTML, using
    the SAME gate — no second, slightly-different comparison for PDFs."""
    snap = pdf.as_snapshot(pdf.extract_pdf_text(_pdf_with_text(SENTENCE)))
    assert quote_in_snapshot("1 December 2026", snap)


def test_a_quote_that_is_not_in_the_pdf_is_still_rejected():
    snap = pdf.as_snapshot(pdf.extract_pdf_text(_pdf_with_text(SENTENCE)))
    assert not quote_in_snapshot("1 December 2027", snap)


def test_pdf_prose_containing_html_characters_survives_the_parser():
    """`main_text` runs an HTML parser. Unescaped PDF prose containing `<` or `&` would be
    silently eaten, and a quote taken from that page would then fail against its own
    snapshot — the gate would throw away a true claim."""
    text = "Fees & funding: see <Annex B> for the 2026 rates."
    snap = pdf.as_snapshot(text)
    assert quote_in_snapshot("Fees & funding", snap)
    assert quote_in_snapshot("<Annex B>", snap)
    assert "Annex B" in main_text(snap)


# ── through the real fetcher ──────────────────────────────────────────────────
def _fetcher(tmp_path, transport):
    return Fetcher(transport, SnapshotStore(tmp_path / "snaps"),
                   sleep=lambda _s: None, rate_limiter=HostRateLimiter(min_interval=0.0))


def test_the_fetcher_snapshots_a_pdf_as_readable_text(tmp_path):
    tp = CassetteTransport()
    tp.record("https://u.edu/robots.txt", 200, ALLOW)
    tp.record("https://u.edu/admissions.pdf", 200, "", {"Content-Type": "application/pdf"},
              content=_pdf_with_text(SENTENCE))
    r = _fetcher(tmp_path, tp).fetch("https://u.edu/admissions.pdf")
    assert r.ok, r.error
    stored = SnapshotStore(tmp_path / "snaps").load(r.snapshot_hash)
    assert quote_in_snapshot("1 December 2026", stored)


def test_a_scanned_pdf_blocks_WITH_A_REASON(tmp_path):
    """CC-5.3 / the goal's hard rule: never silently."""
    tp = CassetteTransport()
    tp.record("https://u.edu/robots.txt", 200, ALLOW)
    tp.record("https://u.edu/scan.pdf", 200, "", {"Content-Type": "application/pdf"},
              content=_pdf_without_text())
    r = _fetcher(tmp_path, tp).fetch("https://u.edu/scan.pdf")
    assert not r.ok
    assert r.snapshot_hash is None, "nothing readable was stored"
    assert r.error == pdf.SCANNED_REASON
    assert r.status == 200, "the fetch itself succeeded — the document is the problem"


def test_an_oversize_response_is_refused_with_a_reason(tmp_path):
    """CC-5.4. The refusal is a state carrying a reason, not an exception and not silence."""
    tp = CassetteTransport()
    tp.record("https://u.edu/robots.txt", 200, ALLOW)
    tp.record("https://u.edu/huge.pdf", 200, "", {"Content-Type": "application/pdf"},
              oversize=True)
    r = _fetcher(tmp_path, tp).fetch("https://u.edu/huge.pdf")
    assert not r.ok and r.snapshot_hash is None
    assert "not downloaded" in r.error and "MB" in r.error


def test_an_html_page_takes_exactly_the_path_it_always_did(tmp_path):
    """The PDF branch must be invisible to every page that is not a PDF."""
    tp = CassetteTransport()
    tp.record("https://u.edu/robots.txt", 200, ALLOW)
    tp.record("https://u.edu/p", 200, "<html><body><p>Recruiting PhD students.</p></body></html>",
              {"Content-Type": "text/html"})
    r = _fetcher(tmp_path, tp).fetch("https://u.edu/p")
    assert r.ok
    stored = SnapshotStore(tmp_path / "snaps").load(r.snapshot_hash)
    assert stored.startswith("<html>"), "an HTML body must be stored verbatim, unwrapped"


def test_a_pdf_served_as_octet_stream_is_still_read(tmp_path):
    """The case the magic-byte sniff exists for, end to end."""
    tp = CassetteTransport()
    tp.record("https://u.edu/robots.txt", 200, ALLOW)
    tp.record("https://u.edu/x", 200, "", {"Content-Type": "application/octet-stream"},
              content=_pdf_with_text(SENTENCE))
    r = _fetcher(tmp_path, tp).fetch("https://u.edu/x")
    assert r.ok, r.error
    assert quote_in_snapshot("1 December 2026",
                             SnapshotStore(tmp_path / "snaps").load(r.snapshot_hash))


# ── the size cap is a real number, not a comment ─────────────────────────────
def test_the_cap_is_generous_enough_for_a_real_prospectus():
    """A cap that refuses ordinary admissions PDFs would be a silent coverage hole. 25 MB is
    far above any real prospectus and far below the 200 MB case CC-5.4 names."""
    assert 10 * 1024 * 1024 <= MAX_RESPONSE_BYTES < 200 * 1024 * 1024


def test_content_type_helper_ignores_header_case_and_parameters():
    from supervisorly.fetch.transport import Response

    r = Response("u", 200, "", {"CONTENT-TYPE": "Application/PDF; charset=binary"})
    assert r.content_type() == "application/pdf"
