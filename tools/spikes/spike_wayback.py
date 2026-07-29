"""SPIKE-6 — for admissions URLs, how many have **>= 3 archived cycles** in the Wayback
Machine? **Threshold: >= 25%.**

Three is not arbitrary: P6 projects a *next* deadline from past ones, and two points are not a
pattern. A projection from two cycles would be a straight line through noise presented as a
date a student might plan around.

**Where the URLs come from.** SPIKE-6 as written says "admissions URLs P1 found". P1 was not
built (SPIKE-1 = 0% on the real cohort), so this reads the URLs that **SPIKE-1 actually
discovered by crawling** — real pages, found by following institutions' own links, not
authored here. That is the same provenance rule (D-038): the archive is queried only for URLs
discovery produced, never one we invented.

Pass URLs on the command line, or a file with one per line.

    python tools/spikes/spike_wayback.py --urls-file admissions.txt
    python tools/spikes/spike_wayback.py https://www.asu.edu.eg/postgraduate
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from supervisorly.fetch.transport import TransportError, httpx_transport   # noqa: E402

THRESHOLD = 0.25
MIN_CYCLES = 3

#: The CDX API returns one row per capture. `collapse=timestamp:4` folds them to one per YEAR,
#: which is what "cycle" means for an admissions page — fifty captures in 2024 is one cycle,
#: not fifty, and counting raw captures would pass this gate on a single busy year.
CDX = ("https://web.archive.org/cdx/search/cdx?url={u}&output=json"
       "&fl=timestamp,statuscode&collapse=timestamp:4&limit=200")

#: SPIKE-1's real finds, 2026-07-29 — discovered by crawling, not authored. Used when no URLs
#: are passed, so the spike is runnable as-is; a wider run should pass its own list.
DEFAULT_URLS = [
    "https://www.asu.edu.eg/postgraduate",
    "https://www.must.edu.eg/academic_programs/graduate-studies",
    "https://www.aisegypt.com/admissions/application-help",
    "https://ohi.edu.eg/training-courses",
]


def cycles(transport, url: str):
    """(years_archived, ok_years) for one URL, or None if the lookup failed."""
    try:
        resp = transport.get(CDX.format(u=quote(url, safe="")))
    except TransportError:
        return None
    if resp.status != 200:
        return None
    try:
        rows = json.loads(resp.text)
    except ValueError:
        return None
    if not rows or len(rows) < 2:
        return [], []                      # a real answer: the archive has nothing
    body = rows[1:]                        # row 0 is the header
    years, ok = [], []
    for r in body:
        ts = str(r[0])[:4]
        status = str(r[1]) if len(r) > 1 else ""
        if ts not in years:
            years.append(ts)
        # A 200 capture is a page that was actually archived; a 301/404 capture is a record
        # that the URL existed, not a cycle whose deadline could ever be read from it.
        if status.startswith("2") and ts not in ok:
            ok.append(ts)
    return years, ok


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("urls", nargs="*")
    ap.add_argument("--urls-file")
    args = ap.parse_args(argv)

    urls = list(args.urls)
    if args.urls_file:
        urls += [ln.strip() for ln in Path(args.urls_file).read_text(
            encoding="utf-8").splitlines() if ln.strip() and not ln.startswith("#")]
    provenance = "passed in"
    if not urls:
        urls = list(DEFAULT_URLS)
        provenance = "SPIKE-1's crawl finds (2026-07-29)"

    print(f"# SPIKE-6 · {len(urls)} admissions URL(s) · source: {provenance} · "
          f">= {MIN_CYCLES} archived cycles counts")
    transport = httpx_transport(user_agent="SupervisorlyBot/0.1 (mailto:spike@localhost)")

    rows = []
    for i, u in enumerate(urls, 1):
        if i > 1:
            time.sleep(1.0)                # the archive is a charity; be polite
        got = cycles(transport, u)
        if got is None:
            rows.append({"url": u, "failed": True})
            print(f"{i:3}. LOOKUP FAILED  {u[:66]}")
            continue
        years, ok = got
        rows.append({"url": u, "years": years, "ok": ok, "failed": False})
        mark = "YES" if len(ok) >= MIN_CYCLES else " - "
        print(f"{i:3}. {mark} {len(ok):2} usable cycle(s) of {len(years):2} archived  "
              f"{','.join(sorted(ok)[-5:]):<25} {u[:44]}")

    live = [r for r in rows if not r["failed"]]
    failed = [r for r in rows if r["failed"]]
    if not live:
        print("\nNOTHING MEASURED — every archive lookup failed. Not a result; re-run.")
        return 1
    enough = [r for r in live if len(r["ok"]) >= MIN_CYCLES]
    share = len(enough) / len(live)

    print("\n" + "=" * 72)
    print(f"urls checked                    {len(live)}")
    print(f"  with >= {MIN_CYCLES} usable cycles       {len(enough)}")
    print(f"  archived but too few cycles   {len([r for r in live if r['ok'] and len(r['ok']) < MIN_CYCLES])}")
    print(f"  not archived at all           {len([r for r in live if not r['ok']])}")
    if failed:
        print(f"lookup failed (not a 'no')      {len(failed)}")
    print(f"\nSPIKE-6: {len(enough)}/{len(live)} = {share:.0%} have >= {MIN_CYCLES} cycles")
    print(f"threshold {THRESHOLD:.0%} — "
          f"{'PASS · build P6' if share >= THRESHOLD else 'MISS · stop and re-plan'}")
    if len(live) < 8:
        print(f"note: only {len(live)} URLs — thin. P1 was never built, so this is the small "
              "set SPIKE-1's crawl turned up rather than a real harvest. Treat as indicative.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
