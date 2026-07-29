"""SPIKE-0 — of the professors a real scan shortlists, how many have an ORCID record with a
*current* employment (an employment-summary carrying no ``end-date``)?

**Threshold: >= 30%.** Below that, P0 is cosmetic and must be re-planned rather than built.

Throwaway measurement script, never product code (``docs/plan/01-spikes.md``). It parses the
ORCID XML inline and deliberately does not import a product parser — there is none yet, and
writing one here would quietly make the spike into the thing it is supposed to justify.

**Sampling rule, and why it is the whole point.** The cohort is the one a real scan surfaces:
country -> ROR -> OpenAlex authors *filtered by the plan's topics* -> the same shortlist gate
``run_live`` applies. Three estimates in this project's history were wrong because they
sampled the unfiltered author list, which returns the most prominent people — exactly the
ones with complete records — and flatters every number. Do not "fix" this script by widening
the sample.

Usage (needs SUPERVISORLY_CONTACT_EMAIL, per D-019/D-023):

    python tools/spikes/spike_orcid_employments.py --country EG --field cardiology
    python tools/spikes/spike_orcid_employments.py --country CA --field "machine learning" \
        --shortlist 40 --max-institutions 8

It hits real hosts, so §5 politeness applies: one request at a time, with an interval.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from supervisorly import pipeline, preflight                       # noqa: E402
from supervisorly.discover import ladder as _ladder                # noqa: E402
from supervisorly.discover import openalex as _openalex            # noqa: E402
from supervisorly.discover import orcid as orcid_mod               # noqa: E402
from supervisorly.discover import ror as _ror                      # noqa: E402
from supervisorly.fetch.transport import TransportError, httpx_transport   # noqa: E402

#: Confirmed live, 2026-07-29, against 0000-0002-1825-0097 and 0000-0001-5109-3700.
#: The SUMMARY element is in the employment namespace; every FIELD inside it — including
#: ``end-date``, the one this spike turns on — is in ``common``. Guessing that both shared
#: one namespace would have produced a script that reported 100% "current" for everybody.
NS_EMPLOYMENT = "{http://www.orcid.org/ns/employment}"
NS_COMMON = "{http://www.orcid.org/ns/common}"

#: Seconds between ORCID calls. A throwaway script is still a visitor (01-spikes.md §5).
ORCID_INTERVAL = 0.25

THRESHOLD = 0.30


def _text(el, tag):
    found = el.find(f"{NS_COMMON}{tag}")
    return (found.text or "").strip() if found is not None and found.text else None


def _date(el, tag):
    """An ORCID date is year/month/day sub-elements, any of which may be absent."""
    node = el.find(f"{NS_COMMON}{tag}")
    if node is None:
        return None
    parts = [_text(node, k) for k in ("year", "month", "day")]
    return "-".join(p for p in parts if p) or None


def employments(transport, orcid_id):
    """Every employment on a record as ``{org, role, department, start, end}``.

    Returns ``None`` on a lookup FAILURE (transport error, non-200, unparseable) — distinct
    from ``[]``, which means the record genuinely lists none. Collapsing the two is the exact
    mistake ``failed_lookups`` exists to prevent elsewhere in this codebase (D-037).
    """
    try:
        resp = transport.get(f"{orcid_mod.PUB_API}/{orcid_id}/employments")
    except TransportError:
        return None
    if resp.status != 200:
        return None
    try:
        root = ET.fromstring(resp.text)
    except ET.ParseError:
        return None
    out = []
    for s in root.iter(f"{NS_EMPLOYMENT}employment-summary"):
        org = s.find(f"{NS_COMMON}organization")
        out.append({
            "org": _text(org, "name") if org is not None else None,
            "role": _text(s, "role-title"),
            "department": _text(s, "department-name"),
            "start": _date(s, "start-date"),
            "end": _date(s, "end-date"),
        })
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--country", default="EG")
    ap.add_argument("--field", default="cardiology")
    ap.add_argument("--intent", default="phd")
    ap.add_argument("--shortlist", type=int, default=40)
    ap.add_argument("--max-institutions", type=int, default=None)
    args = ap.parse_args(argv)

    email = preflight.contact_email(os.environ)
    if not email:
        print(f"set {preflight.CONTACT_EMAIL_ENV} to an address you own — a spike is a "
              "visitor too (D-019/D-023)", file=sys.stderr)
        return 2

    transport = httpx_transport(user_agent=f"SupervisorlyBot/0.1 (mailto:{email})")
    plan = {"country": args.country, "field": args.field, "intent_kind": args.intent,
            "university_mode": "all"}

    print(f"# SPIKE-0 · {args.country} · {args.field!r} · shortlist {args.shortlist}")
    disc = _ladder.build_targets(
        plan,
        _ror.RorClient(transport, email=email),
        _openalex.OpenAlexClient(transport, email=email,
                                 key=preflight.openalex_key(os.environ)),
        max_institutions=args.max_institutions)
    print(f"# institutions {len(disc['institutions'])} · enumerated {len(disc['targets'])} "
          f"· topics {len(disc['plan'].get('resolved_topic_ids') or [])}")
    for w in disc.get("warnings") or []:
        print(f"# warning: {w}")

    # The SAME gate run_live applies — this is what makes the sample the real cohort.
    shortlisted = pipeline._apply_shortlist(
        list(disc["targets"]), set(), disc["plan"].get("resolved_topic_ids") or [],
        args.shortlist)
    if not shortlisted:
        print("\nRESULT: 0 shortlisted — nothing to measure. Widen the search or check the "
              "country code before reading anything into this.")
        return 1

    counts = {"current": 0, "past_only": 0, "record_lists_none": 0,
              "no_orcid": 0, "lookup_failed": 0}
    for i, t in enumerate(shortlisted, 1):
        name = (t.get("name") or t.get("id") or "?")[:44]
        oid = orcid_mod.normalize_id(t.get("orcid"))
        if not oid:
            counts["no_orcid"] += 1
            print(f"{i:3}. {name:<44} no ORCID on the OpenAlex record")
            continue
        if i > 1:
            time.sleep(ORCID_INTERVAL)
        rows = employments(transport, oid)
        if rows is None:
            counts["lookup_failed"] += 1
            print(f"{i:3}. {name:<44} {oid}  LOOKUP FAILED (not the same as 'none')")
            continue
        if not rows:
            counts["record_lists_none"] += 1
            print(f"{i:3}. {name:<44} {oid}  record lists no employment")
            continue
        current = [r for r in rows if not r["end"]]
        if current:
            counts["current"] += 1
            r = current[0]
            extra = f" +{len(current) - 1} more" if len(current) > 1 else ""
            print(f"{i:3}. {name:<44} {oid}  CURRENT: "
                  f"{r['role'] or '(no role)'} · {r['department'] or '(no dept)'} · "
                  f"{r['org'] or '(no org)'}{extra}")
        else:
            counts["past_only"] += 1
            newest = max((r["end"] or "") for r in rows)
            print(f"{i:3}. {name:<44} {oid}  past only (latest ended {newest})")

    n = len(shortlisted)
    share = counts["current"] / n
    print("\n" + "=" * 72)
    print(f"shortlisted                     {n}")
    for k in ("current", "past_only", "record_lists_none", "no_orcid", "lookup_failed"):
        print(f"{k:<32}{counts[k]}")
    print(f"\nSPIKE-0: {counts['current']}/{n} = {share:.0%} have a CURRENT ORCID employment")
    print(f"threshold {THRESHOLD:.0%} — {'PASS · build P0' if share >= THRESHOLD else 'MISS · stop and re-plan, do not build P0'}")
    # A lookup failure is not a "no". Say so, so a bad network hour cannot be read as a
    # verdict about ORCID coverage.
    if counts["lookup_failed"]:
        print(f"note: {counts['lookup_failed']} lookup(s) FAILED and are counted in the "
              "denominator but never as a yes — re-run before trusting a near-threshold number.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
