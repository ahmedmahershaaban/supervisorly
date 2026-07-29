"""SPIKE-1 — can an admissions / graduate page be found by following an institution's OWN
links, within 3 hops, and is it HTML rather than PDF?

**Threshold: >= 40% found.** Below that, P1 is not built (it is the plan's largest and
highest-risk phase, so the gate matters more here than anywhere else).

Throwaway measurement script, never product code (``docs/plan/01-spikes.md``).

**No guessed paths (D-038).** It starts at the homepage ROR gave us and walks links that
exist on pages it actually fetched. It never tries ``/admissions`` or ``/graduate`` — those
work on the sites someone thought of and fail silently everywhere else, which is exactly the
failure this project keeps rediscovering.

**About the detector, and how to read the number.** Deciding "is this an admissions page?"
is P1-2.2's job, and in the product a model reads the prose. A spike cannot wait for a phase
it is gating, so it scores page text against indicative terms. That instrument is
**conservative by construction**: it under-counts non-English pages and unusual phrasings and
never over-counts. So a result at or above the threshold is a genuine floor and safe to build
on, while a result below it is ambiguous — it could be the sites or it could be the ruler.
Say which in the write-up; do not report the bare number.

Usage (needs SUPERVISORLY_CONTACT_EMAIL):

    python tools/spikes/spike_admissions.py --country EG
    python tools/spikes/spike_admissions.py --country DE --institutions 10 --budget 25
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import time
from collections import deque
from pathlib import Path
from urllib.parse import urldefrag, urljoin, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from supervisorly import pipeline, preflight                      # noqa: E402
from supervisorly.discover import ladder as _ladder               # noqa: E402
from supervisorly.discover import ror as _ror                     # noqa: E402
from supervisorly.fetch import pdf as pdf_mod                     # noqa: E402
from supervisorly.fetch.fetcher import Fetcher                    # noqa: E402
from supervisorly.fetch.normalize import main_text                # noqa: E402
from supervisorly.fetch.ratelimit import HostRateLimiter          # noqa: E402
from supervisorly.fetch.snapshot import SnapshotStore             # noqa: E402
from supervisorly.fetch.transport import httpx_transport          # noqa: E402

THRESHOLD = 0.40
MAX_DEPTH = 3

#: The measurement instrument — NOT a shipped dictionary. It exists so this script can put a
#: number on reachability without waiting for the model phase it is gating. Two groups, both
#: required: a page about postgraduate STUDY, and something transactional (applying, entry,
#: deadlines). "Graduate" alone matches graduation ceremonies and alumni pages.
_LEVEL = re.compile(r"\b(postgraduate|graduate|master'?s|msc|ma |phd|doctoral|doctorate|"
                    r"research degree)\b", re.I)
_ACTION = re.compile(r"\b(admission|admissions|apply|application|applicant|entry requirement|"
                     r"how to apply|enrol|enroll|deadline|closing date|prospectus|"
                     r"fees and funding|tuition)\b", re.I)
#: Link text worth walking first. Ordering only — nothing is EXCLUDED by it, and a page is
#: judged on its own fetched text, never on the words in the link that led there.
_LINK_HINT = re.compile(r"(admiss|apply|applic|prospect|postgrad|graduate|study|student|"
                        r"future|entry|course|programme|program|degree|research)", re.I)

_DATEISH = re.compile(r"\b(20[2-3]\d)\b")


def _norm(url: str) -> str:
    return urldefrag(url)[0].rstrip("/")


def _same_site(a: str, b: str) -> bool:
    """Stay on the institution's own site, including its subdomains — a faculty often lives
    on one. Never wander to a third party."""
    ha, hb = urlsplit(a).netloc.lower(), urlsplit(b).netloc.lower()
    if not ha or not hb:
        return False
    pa = ha.split(".")
    pb = hb.split(".")
    root = ".".join(pa[-2:]) if len(pa) >= 2 else ha
    return hb == ha or hb.endswith("." + root) or ".".join(pb[-2:]) == root


def _links(html: str, base: str) -> list[tuple[str, str]]:
    """(absolute_url, link_text) for every on-site link. Extracted, never predicted."""
    out, seen = [], set()
    for m in re.finditer(r"<a\b[^>]*href=[\"']([^\"'#][^\"']*)[\"'][^>]*>(.*?)</a>",
                         html, re.I | re.S):
        href, text = m.group(1), re.sub(r"<[^>]+>", " ", m.group(2))
        if href.lower().startswith(("mailto:", "javascript:", "tel:")):
            continue
        u = _norm(urljoin(base, href))
        if not u.lower().startswith(("http://", "https://")) or u in seen:
            continue
        if not _same_site(base, u):
            continue
        seen.add(u)
        out.append((u, re.sub(r"\s+", " ", text).strip()[:80]))
    return out


def _score(text: str) -> int:
    """How strongly a FETCHED page reads as postgraduate admissions."""
    head = text[:6000]
    return (2 if _LEVEL.search(head) else 0) + (2 if _ACTION.search(head) else 0)


def _script(text: str) -> str:
    """Crude script label for the record — 'latin' or 'non-latin'."""
    sample = [c for c in text[:2000] if c.isalpha()]
    if not sample:
        return "none"
    non_latin = sum(1 for c in sample if ord(c) > 0x24F)
    return "non-latin" if non_latin > len(sample) * 0.3 else "latin"


def crawl(fetcher: Fetcher, snaps: SnapshotStore, home: str, budget: int) -> dict:
    """BFS from ``home``, at most ``budget`` fetches, depth <= 3. Returns what was found."""
    start = _norm(home)
    seen = {start}
    queue: deque[tuple[str, int]] = deque([(start, 0)])
    fetched = 0
    blocked_reason = None
    best = None

    while queue and fetched < budget:
        url, depth = queue.popleft()
        res = fetcher.fetch(url)
        fetched += 1
        if not res.ok:
            if blocked_reason is None:
                blocked_reason = res.error
            continue
        body = snaps.load(res.snapshot_hash)
        text = main_text(body)
        is_pdf = url.lower().endswith(".pdf") or body.startswith("<pre>")
        score = _score(text)
        if score >= 4 and depth > 0:      # the homepage itself is never "the admissions page"
            cand = {"url": url, "depth": depth, "kind": "pdf" if is_pdf else "html",
                    "script": _script(text), "chars": len(text),
                    "has_year": bool(_DATEISH.search(text)),
                    "has_date": pipeline.extract_deadline(body) is not None}
            # Prefer HTML over PDF, then the shallower find — the page a student would land on.
            if best is None or (best["kind"] == "pdf" and cand["kind"] == "html"):
                best = cand
            if best and best["kind"] == cand["kind"] and cand["depth"] < best["depth"]:
                best = cand
            if best["kind"] == "html" and best["depth"] <= 1:
                break                      # good enough; stop spending fetches
        if depth >= MAX_DEPTH or is_pdf:
            continue
        # Weak signals ORDER the queue; they never exclude from it (00-invariants §2).
        nxt = [(u, t) for (u, t) in _links(body, url) if u not in seen]
        nxt.sort(key=lambda ut: 0 if _LINK_HINT.search(ut[1] or "") or
                 _LINK_HINT.search(ut[0]) else 1)
        for u, _t in nxt[:25]:
            seen.add(u)
            queue.append((u, depth + 1))

    return {"found": best is not None, "best": best, "fetched": fetched,
            "blocked": blocked_reason}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--country", default="EG")
    ap.add_argument("--field", default=None,
                    help="run the REAL ladder and crawl the institutions a scan's shortlisted "
                         "professors actually work at (the sampling rule). Without it, the "
                         "cohort is ROR's raw order, which is hospitals and companies.")
    ap.add_argument("--max-institutions", type=int, default=25,
                    help="cap on the ladder's institution scan when --field is used")
    ap.add_argument("--universities-only", action="store_true",
                    help="crawl only ROR 'education' institutions. Answers the DIFFERENT "
                         "question of whether a university's admissions page is findable, "
                         "separately from whether a scan surfaces universities at all.")
    ap.add_argument("--institutions", type=int, default=10)
    ap.add_argument("--budget", type=int, default=25, help="fetches per institution")
    ap.add_argument("--rate", type=float, default=1.0, help="seconds between hits per host")
    args = ap.parse_args(argv)

    email = preflight.contact_email(os.environ)
    if not email:
        print(f"set {preflight.CONTACT_EMAIL_ENV} — a spike is a visitor too", file=sys.stderr)
        return 2

    transport = httpx_transport(user_agent=f"SupervisorlyBot/0.1 (mailto:{email})")
    ror_client = _ror.RorClient(transport, email=email)
    insts = _ladder.select_institutions({"country": args.country, "university_mode": "all"},
                                        ror_client)
    with_home = [i for i in insts if i.get("homepage")]
    if args.universities_only:
        edu = [i for i in with_home
               if any("education" in str(t).lower() for t in (i.get("types") or []))]
        print(f"# universities-only: {len(edu)} of {len(with_home)} ROR institutions are "
              "type 'education'")
        with_home = edu

    if args.field:
        # THE SAMPLING RULE (01-spikes.md), and it is not optional here.
        #
        # The first run of this spike took ROR's first ten rows for Egypt and got hospitals,
        # a pharmaceutical company, the WHO regional office and an international K-12 school
        # — one plausible university among ten, and a 10% score that says nothing about P1.
        # P1 does not crawl "the first ten institutions in the country". It crawls the
        # institutions where a scan actually FOUND professors. So do that: run the real
        # ladder, take the shortlist, and crawl the institutions those professors work at,
        # commonest first.
        from supervisorly.discover import openalex as _openalex   # noqa: PLC0415

        oa = _openalex.OpenAlexClient(transport, email=email,
                                      key=preflight.openalex_key(os.environ))
        disc = _ladder.build_targets(
            {"country": args.country, "field": args.field, "university_mode": "all"},
            ror_client, oa, max_institutions=args.max_institutions)
        topics = disc["plan"].get("resolved_topic_ids") or []
        if not topics:
            print(f"# WARNING: {args.field!r} resolved to ZERO OpenAlex topics, so the "
                  "enumeration is UNFILTERED and this cohort is the prominent-author list, "
                  "not a real scan's. Pick a field that resolves.", file=sys.stderr)
        shortlisted = pipeline._apply_shortlist(list(disc["targets"]), set(), topics, 40)
        counts: dict[str, int] = {}
        for t in shortlisted:
            for nm in (t.get("institution_names") or []):
                if nm:
                    counts[nm.strip().lower()] = counts.get(nm.strip().lower(), 0) + 1
        by_name = {(i.get("name") or "").strip().lower(): i for i in with_home}
        ranked = []
        for nm, c in sorted(counts.items(), key=lambda kv: -kv[1]):
            hit = by_name.get(nm) or next(
                (i for k, i in by_name.items() if nm and (nm in k or k in nm)), None)
            if hit is not None and hit not in ranked:
                ranked.append(hit)
        print(f"# cohort: institutions of {len(shortlisted)} shortlisted professors "
              f"({len(topics)} topics) — {len(ranked)} of {len(counts)} matched a ROR homepage")
        with_home = ranked

    with_home = with_home[: args.institutions]
    print(f"# SPIKE-1 · {args.country} · {len(with_home)} institutions · depth<={MAX_DEPTH} "
          f"· budget {args.budget}/institution")
    if not with_home:
        print("\nRESULT: no institution with a homepage to crawl — nothing measured.")
        return 1

    snaps = SnapshotStore(Path(os.environ.get("TMPDIR", ".")) / "spike1-snaps")
    rows = []
    for n, inst in enumerate(with_home, 1):
        fetcher = Fetcher(transport, snaps, rate_limiter=HostRateLimiter(min_interval=args.rate))
        name = (inst.get("name") or "?")[:38]
        t0 = time.monotonic()
        try:
            r = crawl(fetcher, snaps, inst["homepage"], args.budget)
        except Exception as exc:                       # noqa: BLE001 — one site, not the run
            r = {"found": False, "best": None, "fetched": 0, "blocked": f"{type(exc).__name__}: {exc}"}
        r["name"], r["home"] = name, inst["homepage"]
        rows.append(r)
        b = r["best"]
        detail = (f"{b['kind'].upper()} d{b['depth']} {b['script']} "
                  f"{'date' if b['has_date'] else ('year' if b['has_year'] else 'no-date')} "
                  f"{b['url'][:70]}" if b else (r["blocked"] or "not found")[:78])
        print(f"{n:3}. {name:<38} {'FOUND ' if r['found'] else '  --  '} "
              f"({r['fetched']:2} fetched, {time.monotonic() - t0:5.1f}s) {detail}")

    n = len(rows)
    found = [r for r in rows if r["found"]]
    html = [r for r in found if r["best"]["kind"] == "html"]
    with_date = [r for r in found if r["best"]["has_date"]]
    non_latin = [r for r in found if r["best"]["script"] == "non-latin"]
    share = (len(found) / n) if n else 0.0

    print("\n" + "=" * 72)
    print(f"institutions crawled            {n}")
    print(f"admissions page found           {len(found)}")
    print(f"  of those, HTML (not PDF)      {len(html)}")
    print(f"  of those, a parseable date    {len(with_date)}")
    print(f"  of those, non-latin script    {len(non_latin)}")
    print(f"not found                       {n - len(found)}")
    print(f"\nSPIKE-1: {len(found)}/{n} = {share:.0%} reachable within {MAX_DEPTH} hops")
    print(f"threshold {THRESHOLD:.0%} — "
          f"{'PASS · build P1' if share >= THRESHOLD else 'MISS · stop and re-plan'}")
    print("note: the detector is conservative (see the module docstring) — it under-counts "
          "and never over-counts, so a PASS is a floor and a MISS may be the ruler.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
