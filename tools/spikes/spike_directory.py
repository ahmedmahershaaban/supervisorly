"""SPIKE-2 — is a people/staff directory reachable within 3 hops by following an institution's
OWN links? **Threshold: >= 30%.**

Throwaway measurement script, never product code. Same discipline as `spike_admissions.py`:
it starts at the homepage ROR gave us and walks links that exist on pages it actually fetched.
It never tries `/staff` or `/people` — those work on the sites someone thought of and fail
silently everywhere else, which is the failure D-038 exists to prevent and the one this
project keeps rediscovering.

**Why this spike matters more than its own phase.** B-007 measured that **0%** of shortlisted
professors resolve to a page they control, so P4 (triage) and P5 (model extraction) have
nothing to work on. P2 — this phase — is what would create that supply. So this number is not
only P2's gate; it is the evidence for whether the deterministic path can produce professor
pages at all.

**Scope note.** SPIKE-2 as written also asks "can a named professor be located in it?". That
half needs a name from OpenAlex, and this run could not do it: OpenAlex's free daily budget
was exhausted (`429 "Insufficient budget… Resets at midnight UTC"`). What is measured here is
**reachability of the directory**, which is the necessary condition — if the directory is not
reachable, locating a person in it is moot. The second half is left explicitly unmeasured
rather than estimated.

Usage:  python tools/spikes/spike_directory.py --country EG --institutions 10
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

from supervisorly import preflight                                # noqa: E402
from supervisorly.discover import ladder as _ladder               # noqa: E402
from supervisorly.discover import ror as _ror                     # noqa: E402
from supervisorly.fetch.fetcher import Fetcher                    # noqa: E402
from supervisorly.fetch.normalize import main_text                # noqa: E402
from supervisorly.fetch.ratelimit import HostRateLimiter          # noqa: E402
from supervisorly.fetch.snapshot import SnapshotStore             # noqa: E402
from supervisorly.fetch.transport import httpx_transport          # noqa: E402

THRESHOLD = 0.30
MAX_DEPTH = 3

#: The measurement instrument, not a shipped dictionary — the product judges a FETCHED page
#: with a model (P2-2). A directory is a page that names an ACADEMIC ROLE and looks like a
#: LIST of people; either alone is far too loose ("professor" appears on every news page).
_ROLE = re.compile(r"\b(professor|lecturer|reader|faculty member|academic staff|"
                   r"teaching staff|research fellow|associate professor|assistant professor)\b",
                   re.I)
_LISTY = re.compile(r"\b(staff|people|faculty|members|directory|team|our academics|"
                    r"academic staff|department members)\b", re.I)
#: Link text worth walking FIRST. Ordering only — nothing is excluded by it (invariants §2).
_HINT = re.compile(r"(staff|people|faculty|academic|member|directory|team|department|"
                   r"school|about|research)", re.I)
#: A person's name next to a role is the strongest tell that this is a roster rather than
#: prose about staff. Deliberately crude — it only has to rank, not to be right.
_NAMEISH = re.compile(r"\b(?:Dr|Prof|Professor)\.?\s+[A-Z][a-z]+", re.I)


def _norm(u):
    return urldefrag(u)[0].rstrip("/")


def _same_site(a, b):
    ha, hb = urlsplit(a).netloc.lower(), urlsplit(b).netloc.lower()
    if not ha or not hb:
        return False
    pa = ha.split(".")
    root = ".".join(pa[-2:]) if len(pa) >= 2 else ha
    return hb == ha or hb.endswith("." + root)


def _links(html, base):
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


def _directory_score(text, html):
    """How strongly a FETCHED page reads as a roster of academics."""
    head = text[:8000]
    names = len(set(_NAMEISH.findall(head)))
    score = 0
    if _ROLE.search(head):
        score += 2
    if _LISTY.search(head):
        score += 1
    if names >= 3:                      # three or more titled people on one page
        score += 2
    return score, names


def crawl(fetcher, snaps, home, budget):
    start = _norm(home)
    seen, queue = {start}, deque([(start, 0)])
    fetched, best, blocked = 0, None, None
    while queue and fetched < budget:
        url, depth = queue.popleft()
        res = fetcher.fetch(url)
        fetched += 1
        if not res.ok:
            if blocked is None:
                blocked = res.error
            continue
        html = snaps.load(res.snapshot_hash)
        text = main_text(html)
        score, names = _directory_score(text, html)
        if score >= 4 and depth > 0:
            cand = {"url": url, "depth": depth, "names": names, "score": score}
            if best is None or cand["names"] > best["names"]:
                best = cand
            if best["names"] >= 8:
                break                   # unmistakably a roster; stop spending fetches
        if depth >= MAX_DEPTH:
            continue
        nxt = [(u, t) for (u, t) in _links(html, url) if u not in seen]
        nxt.sort(key=lambda ut: 0 if _HINT.search(ut[1] or "") or _HINT.search(ut[0]) else 1)
        for u, _t in nxt[:25]:
            seen.add(u)
            queue.append((u, depth + 1))
    return {"found": best is not None, "best": best, "fetched": fetched, "blocked": blocked}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--country", default="EG")
    ap.add_argument("--institutions", type=int, default=10)
    ap.add_argument("--budget", type=int, default=20)
    ap.add_argument("--rate", type=float, default=1.0)
    ap.add_argument("--all-types", action="store_true",
                    help="do not restrict to ROR 'education' types (see B-006)")
    args = ap.parse_args(argv)

    email = preflight.contact_email(os.environ)
    if not email:
        print(f"set {preflight.CONTACT_EMAIL_ENV}", file=sys.stderr)
        return 2

    transport = httpx_transport(user_agent=f"SupervisorlyBot/0.1 (mailto:{email})")
    insts = _ladder.select_institutions({"country": args.country, "university_mode": "all"},
                                        _ror.RorClient(transport, email=email))
    pool = [i for i in insts if i.get("homepage")]
    if not args.all_types:
        # B-006: ROR's first 100 per country are mostly not universities, and a company has no
        # staff directory to find. Restricting here measures P2's real question instead of
        # re-measuring B-006 — which is what SPIKE-1's first run accidentally did.
        pool = [i for i in pool
                if any("education" in str(t).lower() for t in (i.get("types") or []))]
    pool = pool[: args.institutions]
    print(f"# SPIKE-2 · {args.country} · {len(pool)} institutions · depth<={MAX_DEPTH} "
          f"· budget {args.budget}" + ("" if args.all_types else " · education types only"))
    if not pool:
        print("\nNOTHING MEASURED — no education-typed institution with a homepage. See B-006.")
        return 1

    snaps = SnapshotStore(Path(os.environ.get("TMPDIR", ".")) / "spike2-snaps")
    rows = []
    for n, inst in enumerate(pool, 1):
        fetcher = Fetcher(transport, snaps,
                          rate_limiter=HostRateLimiter(min_interval=args.rate))
        name = (inst.get("name") or "?")[:36]
        t0 = time.monotonic()
        try:
            r = crawl(fetcher, snaps, inst["homepage"], args.budget)
        except Exception as exc:                       # noqa: BLE001
            r = {"found": False, "best": None, "fetched": 0,
                 "blocked": f"{type(exc).__name__}: {exc}"}
        rows.append(r)
        b = r["best"]
        detail = (f"d{b['depth']} {b['names']} named people {b['url'][:60]}" if b
                  else (r["blocked"] or "not found")[:74])
        print(f"{n:3}. {name:<36} {'FOUND ' if r['found'] else '  --  '} "
              f"({r['fetched']:2} fetched, {time.monotonic() - t0:5.1f}s) {detail}")

    n = len(rows)
    found = [r for r in rows if r["found"]]
    blocked = [r for r in rows if not r["found"] and r["blocked"] and "robots" in r["blocked"]]
    share = len(found) / n
    print("\n" + "=" * 72)
    print(f"institutions crawled            {n}")
    print(f"directory found                 {len(found)}")
    print(f"  refused by robots.txt         {len(blocked)}")
    print(f"\nSPIKE-2: {len(found)}/{n} = {share:.0%} reachable within {MAX_DEPTH} hops")
    print(f"threshold {THRESHOLD:.0%} — "
          f"{'PASS · build P2' if share >= THRESHOLD else 'MISS · stop and re-plan'}")
    print("NOTE: this measures only whether the DIRECTORY is reachable. The second half of "
          "SPIKE-2 — locating a named professor in it — needs OpenAlex and was NOT measured.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
