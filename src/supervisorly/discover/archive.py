"""P6 — historical admissions cycles from the Wayback Machine.

**What this is for.** An admissions page publishes one deadline at a time. Its *archive*
shows the same page across several years, and the pattern in those dates says roughly when
the next cycle is likely to open — useful to a student planning a year ahead, and worthless
if presented as a fact.

**The line this module holds.** An archived page describes **the past**. It may inform a
projection; it may never be presented as the current deadline. So:

- **Fewer than 3 cycles → no projection at all.** Two points are not a pattern; a line through
  two dates is noise with a slope, and rendering it as a date somebody might plan around is
  the failure this rule exists to prevent.
- A projection is ``watch``, never ``firm`` — reusing the dashboard's existing distinction
  rather than inventing a label (D-061).
- **The live page always wins for "current".** This module never returns a `deadline`; it
  returns a *projection* the caller attaches beside one.
- Snapshots that exist but carry no date are ``searched_absent`` for the pattern — honest, not
  a failure.

**Never load-bearing.** The archive being slow, down, rate-limiting or empty returns a result
with a reason and never raises. Historical enrichment must not be able to fail a scan.

**No authored URLs** (D-038 / invariants §2). ``cycles_for`` takes a URL that discovery
produced — P1's admissions finds. It never constructs a candidate URL, and it never follows a
URL's successors: if a page moved between cycles, CDX is asked about the URL we were given and
nothing else, because guessing a successor is guessing which institution's deadline this is.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from urllib.parse import quote

from ..fetch.transport import Transport, TransportError

#: Below this, no projection. The number is the whole point of the rule — see the docstring.
MIN_CYCLES = 3

#: One row per capture; ``collapse=timestamp:4`` folds them to one per YEAR. A busy page can
#: be captured fifty times in a year, and counting captures would turn one cycle into fifty —
#: which is exactly how a "pattern" gets manufactured from a single year of activity.
_CDX = ("https://web.archive.org/cdx/search/cdx?url={u}&output=json"
        "&fl=timestamp,statuscode&collapse=timestamp:4&limit={limit}")

_YEAR = re.compile(r"^(\d{4})")


@dataclass
class CycleHistory:
    """What the archive knows about one URL. Always returned — never an exception."""

    url: str
    #: Years with a 2xx capture, ascending. A 3xx/4xx capture proves the URL existed, not that
    #: a page was archived whose deadline could be read — so it is not a cycle.
    years: list[str] = field(default_factory=list)
    #: Why there is no usable history, when there is none. ``None`` when the lookup worked.
    reason: str | None = None

    @property
    def enough(self) -> bool:
        return len(self.years) >= MIN_CYCLES

    @property
    def searched(self) -> bool:
        """True if the archive answered at all — distinguishes 'nothing archived' (an answer)
        from 'we could not ask' (a failure). The four-state honesty rule, applied here."""
        return self.reason is None


def cdx_url(url: str, limit: int = 200) -> str:
    """The CDX query for ``url``. Exposed so a test names the same endpoint the client uses."""
    return _CDX.format(u=quote(url, safe=""), limit=limit)


#: How the archive addresses a capture of a URL in a given year. This is NOT an authored
#: candidate URL: it is the archive's own addressing scheme applied to a URL discovery already
#: produced, and the ``id_`` suffix asks for the page as captured rather than the replay
#: chrome the archive normally wraps around it. Guessing a *different* page would be guessing
#: whose deadline it is; asking for last year's copy of THIS page is not.
_REPLAY = "https://web.archive.org/web/{ts}id_/{u}"


def replay_url(url: str, year: str) -> str:
    """The archived copy of ``url`` nearest mid-``year``. Mid-year, not January, because a
    timestamp the archive has no capture near resolves to the closest one in either
    direction — and from June that is a capture within the same admissions cycle."""
    return _REPLAY.format(ts=f"{int(year):04d}0601000000", u=url)


def cycles_for(transport: Transport, url: str, *, limit: int = 200) -> CycleHistory:
    """Which years this URL has an archived, readable capture in.

    Returns a ``CycleHistory`` in every case, including failure — the caller decides what to
    do with an empty one, and no branch here can take down a scan.
    """
    if not url or not url.lower().startswith(("http://", "https://")):
        return CycleHistory(url=url, reason="not a fetchable url")
    try:
        resp = transport.get(cdx_url(url, limit))
    except TransportError as exc:
        return CycleHistory(url=url, reason=f"archive unreachable: {exc}")
    if resp.status == 429:
        # The archive is a charity and rate-limits. Skipping is correct; pretending the page
        # has no history would turn their throttle into our claim about an institution.
        return CycleHistory(url=url, reason="archive rate-limited this lookup")
    if resp.status != 200:
        return CycleHistory(url=url, reason=f"archive returned http {resp.status}")
    try:
        rows = json.loads(resp.text)
    except ValueError:
        return CycleHistory(url=url, reason="archive returned unparseable json")
    if not isinstance(rows, list) or len(rows) < 2:
        return CycleHistory(url=url)            # asked, and the archive has nothing: an ANSWER
    years: list[str] = []
    for r in rows[1:]:                          # row 0 is the CDX header
        if not isinstance(r, (list, tuple)) or not r:
            continue
        m = _YEAR.match(str(r[0]))
        status = str(r[1]) if len(r) > 1 else ""
        if m and status.startswith("2") and m.group(1) not in years:
            years.append(m.group(1))
    return CycleHistory(url=url, years=sorted(years))


@dataclass
class Projection:
    """A projected next occurrence, or an honest refusal to project."""

    projected: str | None            #: ISO date, or None
    confidence: str                  #: always "watch" when projected — never "firm"
    reason: str                      #: why this is or is not a projection
    from_years: list[str] = field(default_factory=list)


def project_next(history: CycleHistory, observed: list[str]) -> Projection:
    """Project the next cycle from dates observed on archived captures.

    ``observed`` is the ISO dates the caller extracted from the archived pages — this module
    does not parse pages, because the pipeline already has one date extractor and a second
    would be a second set of bugs.

    Refuses far more often than it projects, on purpose. The failure being avoided is a
    student treating an invented date as a deadline, and every refusal below is cheaper than
    that.
    """
    if not history.searched:
        return Projection(None, "watch", f"not projected — {history.reason}",
                          list(history.years))
    if len(history.years) < MIN_CYCLES:
        return Projection(
            None, "watch",
            f"not projected — {len(history.years)} archived cycle(s), fewer than the "
            f"{MIN_CYCLES} needed; two points are not a pattern",
            list(history.years))

    months = []
    for iso in observed:
        m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", str(iso or ""))
        if m:
            months.append((int(m.group(1)), int(m.group(2)), int(m.group(3))))
    if len(months) < MIN_CYCLES:
        # Captures exist but too few carried a readable date. `searched_absent` for the
        # pattern — an honest answer, not a failure, and NOT a reason to guess from fewer.
        return Projection(
            None, "watch",
            f"not projected — only {len(months)} of {len(history.years)} archived cycle(s) "
            "carried a readable date",
            list(history.years))

    # The projection itself is deliberately dull: the modal month/day, one year on from the
    # most recent observation. A regression through three noisy points would look cleverer and
    # mean less, and the output is labelled `watch` either way.
    months.sort()
    latest_year = months[-1][0]
    common = max({(m, d) for _y, m, d in months},
                 key=lambda md: sum(1 for _y, m, d in months if (m, d) == md))
    return Projection(
        f"{latest_year + 1:04d}-{common[0]:02d}-{common[1]:02d}",
        "watch",
        f"projected from {len(months)} archived cycle(s) — this is a pattern, not a "
        "published date; always confirm on the official page",
        list(history.years))
