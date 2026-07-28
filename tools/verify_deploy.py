"""Does the LIVE site actually serve the code in this working tree?

Run this after every deploy. It exists because "the deploy exited 0" has now been wrong
twice for the same reason, and both times the failure was silent:

    firebase/*.py deploys from local disk.
    src/supervisorly/** does NOT — the Functions pip-install it from the tag pinned in
    firebase/requirements.txt.

So editing the engine, committing, and deploying leaves the live site running the OLD
package while every other signal says success. Nothing errors; the page is simply stale.
The fix is to cut a new tag and repoint requirements.txt — but the thing that *catches*
the mistake is comparing what the site serves against what this tree builds.

    python tools/verify_deploy.py                       # compares the page byte for byte
    python tools/verify_deploy.py --expect "some text"  # also assert a specific string

Exit code 0 = the live page matches this tree. Non-zero = you have a stale deploy.
"""
from __future__ import annotations

import argparse
import hashlib
import sys
import urllib.request

SITE = "https://supervisorly.web.app"


def fetch(url: str, timeout: float = 60.0) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "supervisorly-verify/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--site", default=SITE)
    ap.add_argument("--expect", action="append", default=[],
                    help="a string that MUST be present in the served page")
    ap.add_argument("--absent", action="append", default=[],
                    help="a string that must NOT be present (e.g. a line you just removed)")
    args = ap.parse_args()

    from supervisorly.export.webapp import build_webapp

    local = build_webapp(api_base="")          # what a deploy with WEBAPP_API_BASE="" serves
    try:
        live = fetch(args.site + "/")
    except Exception as exc:                    # noqa: BLE001 — report, don't traceback
        print(f"FAIL  could not fetch {args.site}: {type(exc).__name__}: {exc}")
        return 2

    lh = hashlib.sha256(live.encode()).hexdigest()[:16]
    bh = hashlib.sha256(local.encode()).hexdigest()[:16]
    print(f"  live  : {len(live):>7,} bytes  sha256:{lh}")
    print(f"  local : {len(local):>7,} bytes  sha256:{bh}")

    problems = []
    if lh != bh:
        problems.append(
            "the live page differs from this tree's build — almost always a STALE TAG:\n"
            "        cut a new tag, point firebase/requirements.txt at it, redeploy")
    for s in args.expect:
        if s not in live:
            problems.append(f"expected string missing from the live page: {s!r}")
    for s in args.absent:
        if s in live:
            problems.append(f"string that should be gone is still live: {s!r}")

    if problems:
        print("\nFAIL")
        for p in problems:
            print("  - " + p)
        return 1

    print("\nOK  the live site serves exactly what this tree builds")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
