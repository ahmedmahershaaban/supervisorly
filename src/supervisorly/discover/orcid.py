"""ORCID public API — resolve an ORCID iD to the professor's own web page.

**Why this module exists.** OpenAlex almost never carries ``homepage_url`` for the
institutions this tool searches (measured: 0 of 50 sampled Cairo University authors), so
``ladder._author_url`` falls back to the author's ORCID *profile page*. That page is a
JavaScript application: ``orcid.org/<id>`` returns ~65 KB whose entire visible text is CSS
font declarations, ``roster.detect_login_wall`` correctly flags it, and every field is
recorded ``blocked``. The measured result was a run with **331 professors and zero facts**
— every deep-dived target routed to the human rung (`BLOCKERS.md` B-003).

The same record is available as structured data from ORCID's public API, which is what this
module reads. It is an **API client, not a crawler**: like ``openalex.py`` and ``ror.py`` it
speaks to a documented public endpoint over the injected ``Transport``, and never touches the
robots-gated page fetcher ([D-072](../../../docs/DECISIONS.md#d-072)).

**What it does not do.** It returns URLs; it does not decide they may be fetched. Plenty of
researcher URLs point at ResearchGate, LinkedIn or X — 2 of the 6 found in the sample above.
Those are walled sources and D-039/D-043/D-044 route them to the human rung untouched. That
judgement belongs to the caller (``pipeline._WALLED_SOCIAL``), so this module stays a
transport-level reader with no policy in it.

**Honest expected yield.** Only about a quarter of ORCID records carry a researcher URL at
all (6 of 25 sampled), and some of those are walled. This turns "no page for anyone" into
"a real page for a minority" — a genuine improvement over zero, and deliberately not
described as more than that.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET

from ..fetch.transport import Transport, TransportError

PUB_API = "https://pub.orcid.org/v3.0"

#: The ORCID XML namespace carrying researcher URLs. Requests without an ``Accept`` header
#: (all this project's ``Transport`` can send) are served ``application/vnd.orcid+xml``, so
#: XML is the format we parse — there is no ``.json`` URL variant (verified: ``/record.json``,
#: ``/person.json`` and ``?format=json`` all 404 or return XML anyway).
NS_RESEARCHER_URL = "{http://www.orcid.org/ns/researcher-url}"

#: 0000-0002-1825-0097 — 16 digits in four groups, final character may be X (ISO 7064 check).
_ORCID_RE = re.compile(r"(\d{4}-\d{4}-\d{4}-\d{3}[\dX])", re.IGNORECASE)


def normalize_id(value: str | None) -> str | None:
    """Pull a bare ORCID iD out of whatever form it arrives in.

    Targets carry the iD as a full URI (``https://orcid.org/0000-…``) in one field and
    sometimes bare in another, so accept both rather than making callers remember which.
    Anything that is not an ORCID iD returns None — this is the guard that stops a stray
    value from being pasted into an API path.
    """
    if not value:
        return None
    m = _ORCID_RE.search(str(value))
    return m.group(1).upper() if m else None


def researcher_urls_url(orcid_id: str) -> str:
    """The public endpoint listing a record's researcher URLs.

    The dedicated endpoint, not ``/record``: it is ~3.5 KB against ~44 KB for the full
    record, and this is called once per shortlisted professor.
    """
    return f"{PUB_API}/{orcid_id}/researcher-urls"


def _clean(url: str | None) -> str | None:
    """Normalise one researcher URL, or None if it is not usable.

    Records are hand-typed, so a bare ``www.rheumatology4u.com`` with no scheme is common
    (1 of the 6 found in the sample). Default it to https rather than discarding a real
    homepage over a missing prefix.
    """
    u = (url or "").strip()
    if not u:
        return None
    if not re.match(r"^https?://", u, re.IGNORECASE):
        # Any OTHER scheme is refused, matched WITHOUT requiring "//" — `mailto:` has none,
        # so a `//`-based test lets it through and then prepends https, yielding the
        # nonsense `https://mailto:prof@uni.edu`, which passes a naive host check because it
        # contains a dot. A bare email address must never become a URL the fetcher visits.
        # Dots are excluded from the scheme class so a scheme-less `example.com:8080/x` is
        # still read as host:port rather than as a scheme.
        if re.match(r"^[a-z][a-z0-9+-]*:", u, re.IGNORECASE):
            return None
        u = "https://" + u
    return u if re.match(r"^https?://[^\s/]+\.[^\s/]", u, re.IGNORECASE) else None


class OrcidClient:
    """Thin ORCID public-API client over an injected ``Transport``.

    Mirrors ``OpenAlexClient``: no network of its own, so cassette-backed tests and the
    offline demo keep working with no credentials (D-011/D-063).
    """

    def __init__(self, transport: Transport) -> None:
        self._t = transport
        #: iDs whose lookup FAILED (transport error / non-200 / unparseable). Distinct from
        #: an iD with genuinely no URLs: absence is an answer, failure is not (D-037), and
        #: the caller must not read one as the other.
        self.failed_lookups: list[str] = []

    def researcher_urls(self, value: str | None) -> list[str]:
        """Every usable researcher URL on a record, in ORCID's own order.

        Returns ``[]`` for both "record lists none" and "lookup failed" — the two are
        distinguished by ``failed_lookups``, not by the return value, so a caller that
        does not care stays simple and one that does can still tell them apart.
        """
        oid = normalize_id(value)
        if not oid:
            return []
        try:
            resp = self._t.get(researcher_urls_url(oid))
        except TransportError:
            self.failed_lookups.append(oid)
            return []
        if resp.status != 200:
            self.failed_lookups.append(oid)
            return []
        try:
            root = ET.fromstring(resp.text)
        except ET.ParseError:
            self.failed_lookups.append(oid)
            return []
        out: list[str] = []
        for el in root.iter(f"{NS_RESEARCHER_URL}url"):
            cleaned = _clean(el.text)
            if cleaned and cleaned not in out:
                out.append(cleaned)
        return out
