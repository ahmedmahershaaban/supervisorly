"""How many deep-dived professors resolve to a page that could *contain* recruiting language?

Not one of the numbered spikes — it was written because SPIKE-4 could not be measured and the
reason needed a number rather than an impression. SPIKE-4 asks what share of recruiting pages
triage keeps; on two real cohorts the judge found recruiting language on **zero** pages, and
the cause turned out to be upstream of triage entirely: the pages a deep-dive actually reads
are overwhelmingly ORCID profiles, which never contain a sentence like "I am recruiting PhD
students" because ORCID has no field for one.

So this counts the supply. For the targets a real scan shortlists, it resolves each to the URL
``pipeline._page_url_for`` would deep-dive and tallies what KIND of page that is. No fetching
— the question is what the pipeline aims at, not what comes back.

Usage:  python tools/spikes/spike_page_supply.py --country GB --field "machine learning"
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from supervisorly import pipeline, preflight                      # noqa: E402
from supervisorly.discover import ladder as _ladder               # noqa: E402
from supervisorly.discover import openalex as _openalex           # noqa: E402
from supervisorly.discover import orcid as orcid_mod              # noqa: E402
from supervisorly.discover import ror as _ror                     # noqa: E402
from supervisorly.fetch import walls                              # noqa: E402
from supervisorly.fetch.transport import httpx_transport          # noqa: E402

#: Hosts that are registries or profile aggregators. A page here identifies a person and
#: lists their output; it is not a page they wrote and cannot carry their own words about
#: taking students. This is page-classification structure (an enum of source kinds), the same
#: class D-038 explicitly allows — not a dictionary of search terms.
_REGISTRY_HOSTS = ("orcid.org", "publons.com", "researcherid.com", "scopus.com",
                   "semanticscholar.org", "openalex.org", "wikidata.org", "viaf.org")


def kind_of(url: str | None) -> str:
    if not url:
        return "no page at all"
    host = (urlsplit(url).netloc or "").lower().removeprefix("www.")
    if any(host == h or host.endswith("." + h) for h in _REGISTRY_HOSTS):
        return "registry profile (cannot state recruiting)"
    if walls.is_walled(url):
        return "walled — human rung only"
    if host in ("github.com", "gitlab.com"):
        return "code host"
    return "a page the person controls"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--country", default="GB")
    ap.add_argument("--field", default="machine learning")
    ap.add_argument("--targets", type=int, default=120)
    ap.add_argument("--max-institutions", type=int, default=40)
    args = ap.parse_args(argv)

    email = preflight.contact_email(os.environ)
    if not email:
        print(f"set {preflight.CONTACT_EMAIL_ENV}", file=sys.stderr)
        return 2

    transport = httpx_transport(user_agent=f"SupervisorlyBot/0.1 (mailto:{email})")
    oa = _openalex.OpenAlexClient(transport, email=email,
                                  key=preflight.openalex_key(os.environ))
    disc = _ladder.build_targets(
        {"country": args.country, "field": args.field, "university_mode": "all"},
        _ror.RorClient(transport, email=email), oa,
        max_institutions=args.max_institutions)
    topics = disc["plan"].get("resolved_topic_ids") or []
    shortlisted = pipeline._apply_shortlist(list(disc["targets"]), set(), topics,
                                            args.targets)

    print(f"# page supply · {args.country} · {args.field!r} · {len(topics)} topics · "
          f"{len(shortlisted)} shortlisted")
    client = orcid_mod.OrcidClient(transport)
    counts: dict[str, int] = {}
    examples: dict[str, str] = {}
    for i, t in enumerate(shortlisted, 1):
        if i > 1:
            time.sleep(0.2)                    # a throwaway script is still a visitor
        try:
            url = pipeline._page_url_for(t, client, {})
        except Exception:                      # noqa: BLE001
            url = None
        k = kind_of(url)
        counts[k] = counts.get(k, 0) + 1
        examples.setdefault(k, url or "-")

    n = len(shortlisted)
    if not n:
        print("\nNOTHING MEASURED — the ladder shortlisted no professors. Check the "
              f"`{len(topics)} topics` line above: zero topics means the field did not "
              "resolve and the enumeration was unfiltered or empty. Re-run before reading "
              "anything into this.")
        return 1
    print("\n" + "=" * 72)
    for k, c in sorted(counts.items(), key=lambda kv: -kv[1]):
        print(f"{c:4}  {c / n:5.0%}  {k}")
        print(f"            e.g. {examples[k][:66]}")
    own = counts.get("a page the person controls", 0)
    print(f"\nPAGES THAT COULD CARRY RECRUITING LANGUAGE: {own}/{n} = {own / n:.0%}")
    print("Everything else is a registry profile, a walled host, or nothing at all — none of")
    print("which can contain the professor's own statement about taking students.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
