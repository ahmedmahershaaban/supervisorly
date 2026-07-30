"""Read a scan's JSON export and say plainly how it did.

`--progress` reports phases, not outcomes: a run that rendered nothing and a run that rendered
everything print the same lines. So after a scan the honest question — *did any of this
actually find anything?* — had no cheap answer short of scrolling the dashboard.

Usage:  python tools/inspect_scan.py output/dashboard.json
"""

from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

STATES = ("value", "searched_absent", "blocked", "never_attempted")
BAR = "-" * 66


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__.strip())
        return 2
    path = Path(argv[1])
    if not path.exists():
        print(f"no such file: {path}")
        return 2
    data = json.loads(path.read_text(encoding="utf-8"))

    profs = data.get("professors", [])
    run = data.get("run", {}) or {}
    print(BAR)
    print(f"{path.name}  ·  {len(profs)} professors  ·  generated {data.get('generated_at','?')}")
    if run:
        keep = {k: v for k, v in run.items()
                if k in ("status", "gaps", "shortlisted", "unchecked", "discovered",
                         "institutions", "rendered", "render_fallback", "render_batched",
                         "crawl_pages", "crawl_claims", "search_resolved", "orcid_resolved",
                         "model_claims", "model_rejected", "extractions", "cache_hits")}
        for k, v in keep.items():
            print(f"  {k:<18} {v}")
    print(BAR)

    # ---- per-field state counts -------------------------------------------------
    per_field: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    sources: collections.Counter = collections.Counter()
    extractors: collections.Counter = collections.Counter()
    deep_dived = 0
    for p in profs:
        fields = p.get("fields", {}) or {}
        if any((c or {}).get("state") != "never_attempted" for c in fields.values()):
            deep_dived += 1
        for name, cell in fields.items():
            cell = cell or {}
            per_field[name][cell.get("state", "?")] += 1
            if cell.get("state") == "value":
                if cell.get("source_url"):
                    sources[cell["source_url"].split("/")[2]] += 1
                extractors[cell.get("extractor") or "?"] += 1

    print(f"{'field':<20}" + "".join(f"{s:>17}" for s in STATES))
    for name, c in per_field.items():
        row = f"{name:<20}"
        for s in STATES:
            n = c.get(s, 0)
            row += f"{n:>17}" if n else f"{'.':>17}"
        print(row)
    print(BAR)

    values = sum(c.get("value", 0) for c in per_field.values())
    absent = sum(c.get("searched_absent", 0) for c in per_field.values())
    blocked = sum(c.get("blocked", 0) for c in per_field.values())
    read = values + absent + blocked
    print(f"deep-dived professors : {deep_dived} of {len(profs)}")
    print(f"cells with a real value: {values}"
          + (f"   ({100*values/read:.0f}% of the {read} cells actually attempted)" if read else ""))
    if extractors:
        print("found by              :", dict(extractors))
    if sources:
        print("top source hosts      :", dict(sources.most_common(6)))
    print(BAR)

    # ---- the verdict, in words --------------------------------------------------
    if not deep_dived:
        print("VERDICT  nothing was deep-dived. Check --shortlist and the target list.")
    elif values == 0:
        print("VERDICT  every attempted cell came back empty.")
        print("         The pages were reached but say nothing, or there were no pages to")
        print("         reach. This is the supply problem: a search key (rung 7) is the")
        print("         thing that changes it. --render-all alone cannot.")
    elif values < deep_dived:
        print("VERDICT  a few real values. Reading works; supply is thin.")
        print("         A search key would widen it; --shortlist raises the count.")
    else:
        print("VERDICT  real evidence is coming through. Raise --shortlist and re-run.")
    print(BAR)

    # ---- show the actual finds, so the number is checkable ----------------------
    shown = 0
    for p in profs:
        for name, cell in (p.get("fields") or {}).items():
            cell = cell or {}
            if cell.get("state") != "value" or shown >= 8:
                continue
            shown += 1
            q = (cell.get("quote") or "").replace("\n", " ")[:96]
            print(f"\n  {p.get('name','?')}  ·  {name}")
            print(f"    value : {str(cell.get('value'))[:90]}")
            print(f"    quote : {q}")
            print(f"    source: {cell.get('source_url')}")
    if not shown:
        print("\n  (no value cells to show)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
