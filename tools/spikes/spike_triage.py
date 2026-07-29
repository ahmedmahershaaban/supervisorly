"""SPIKE-4 — does deterministic triage keep the pages that actually contain recruiting
language? **Recall must be >= 90%.**

Triage is the token gate: a page with no recruiting cue, no date near an application word and
no supervision term cannot produce a recruiting claim, so sending it to a model spends tokens
to learn nothing. The risk is entirely one-sided. A false *positive* costs a few tokens. A
false *negative* is invisible — the page never reaches the model, never produces a claim, and
never appears anywhere for anyone to notice. So recall is the number that gates P4, and
precision is reported only as the saving it buys.

**What "known to contain recruiting language" means here, and why it is not circular.**
The obvious labelling — "pages where the existing regex finds something" — would measure the
regex against itself and return 100%. Instead each page is labelled by **the model triage
exists to feed**, asked independently whether the text states anything about recruiting,
admitting or supervising. That is not a convenience: it is the definition. Triage's whole job
is to avoid sending pages the model would find nothing in, so "did triage keep a page the
model found something in?" is exactly the question worth answering.

The pages are real, fetched live from the cohort a real scan produces, robots-gated and
rate-limited like any other visit. Nothing is read from the corpus (D-035).

Usage (needs SUPERVISORLY_CONTACT_EMAIL; the judge needs SUPERVISORLY_EXPAND_KEY, which is
read from firebase/.env if not in the environment and is NEVER printed):

    python tools/spikes/spike_triage.py --country EG --field "cardiovascular disease"
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from supervisorly import pipeline, preflight                      # noqa: E402
from supervisorly.discover import ladder as _ladder               # noqa: E402
from supervisorly.discover import openalex as _openalex           # noqa: E402
from supervisorly.discover import ror as _ror                     # noqa: E402
from supervisorly.fetch import walls                              # noqa: E402
from supervisorly.fetch.fetcher import Fetcher                    # noqa: E402
from supervisorly.fetch.normalize import main_text                # noqa: E402
from supervisorly.fetch.ratelimit import HostRateLimiter          # noqa: E402
from supervisorly.fetch.snapshot import SnapshotStore             # noqa: E402
from supervisorly.fetch.transport import httpx_transport          # noqa: E402

RECALL_THRESHOLD = 0.90

# ── the prototype triage under test ───────────────────────────────────────────
# Built from pipeline.py's shipped regexes, as P4-1.2 directs: they are excellent at "worth a
# closer look" even where they are too blunt to be the extractor. P4-1 promotes this rule to
# `extract/triage.py` — it lives here first so the number that gates the phase is measured
# against the thing that would actually ship.

_APPLY_NEAR_DATE = re.compile(
    r"\b(appl\w*|admission\w*|deadline|closing|enrol\w*|submission\w*)\b", re.IGNORECASE)
_SUPERVISION = re.compile(
    r"\b(supervis\w*|phd|doctoral|postdoc\w*|master'?s|msc|graduate student\w*|"
    r"research assistant\w*|studentship\w*|scholarship\w*)\b", re.IGNORECASE)
_CONTACT = re.compile(r"[^@\s]+@[^@\s]+\.[a-z]{2,}", re.IGNORECASE)


def _is_mostly_latin(text: str) -> bool:
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return False
    latin = sum(1 for c in letters if "LATIN" in unicodedata.name(c, ""))
    return latin >= len(letters) * 0.7


def triage(text: str) -> str:
    """``candidate`` | ``empty`` | ``uncertain`` — tuned for recall, never precision."""
    if not text or not text.strip():
        return "empty"                      # genuinely nothing to read
    if not _is_mostly_latin(text):
        # THE RULE THAT MATTERS. The cue lists are English; a page that is not mostly Latin
        # script has not been assessed at all, so it escalates. Calling it `empty` is how an
        # Arabic-language institution returns nothing and reads as "that country has no
        # professors" — precisely the failure D-038 exists to prevent.
        return "uncertain"
    if pipeline._RECRUIT.search(text) or _SUPERVISION.search(text):
        return "candidate"
    for sentence in pipeline._sentences(text):
        if _APPLY_NEAR_DATE.search(sentence) and pipeline._dates_in(sentence):
            return "candidate"              # a date next to an application word
    if pipeline._STUDENTS.search(text) or _CONTACT.search(text):
        return "candidate"
    return "empty"


KEPT = ("candidate", "uncertain")           # both reach the model; only `empty` is dropped


# ── the independent judge ─────────────────────────────────────────────────────
def _expand_key() -> str | None:
    """The judge's API key, from the environment or firebase/.env. Never printed, never logged."""
    key = (os.environ.get("SUPERVISORLY_EXPAND_KEY") or "").strip()
    if key:
        return key
    env_file = ROOT / "firebase" / ".env"
    if env_file.is_file():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("SUPERVISORLY_EXPAND_KEY="):
                return line.split("=", 1)[1].strip() or None
    return None


_JUDGE_PROMPT = (
    "You are labelling a web page for a research dataset. Read the page text and answer "
    "ONLY with compact JSON: {\"recruiting\": true|false, \"quote\": \"<verbatim sentence "
    "from the text, or empty string>\"}.\n\n"
    "Set recruiting=true if the text contains ANY explicit statement about recruiting, "
    "admitting, hiring or supervising students, PhD candidates, postdocs or research "
    "assistants — including openings, studentships, application instructions or deadlines "
    "for them, or a statement that the person supervises or takes students.\n"
    "Set recruiting=false if the page is only a biography, publication list, course page, "
    "news item or contact page with none of that.\n"
    "The quote MUST be copied verbatim from the text, in its original language.\n\n"
    "PAGE TEXT:\n"
)


def judge(client, base_url: str, model: str, key: str, text: str) -> dict | None:
    """The model's independent label for one page, or None if the call failed."""
    try:
        r = client.post(
            f"{base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={"model": model, "temperature": 0,
                  "messages": [{"role": "user", "content": _JUDGE_PROMPT + text[:12000]}]},
            timeout=60.0)
        if r.status_code != 200:
            return None
        content = r.json()["choices"][0]["message"]["content"]
        m = re.search(r"\{.*\}", content, re.S)
        return json.loads(m.group(0)) if m else None
    except Exception:                        # noqa: BLE001 — a failed label is not a label
        return None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--country", default="EG")
    ap.add_argument("--field", default="cardiovascular disease")
    ap.add_argument("--pages", type=int, default=40, help="pages to fetch and label")
    ap.add_argument("--max-institutions", type=int, default=25)
    args = ap.parse_args(argv)

    email = preflight.contact_email(os.environ)
    if not email:
        print(f"set {preflight.CONTACT_EMAIL_ENV}", file=sys.stderr)
        return 2
    key = _expand_key()
    if not key:
        print("no SUPERVISORLY_EXPAND_KEY — the independent judge cannot run, and labelling "
              "with the same regexes under test would measure them against themselves",
              file=sys.stderr)
        return 2

    import httpx
    base_url = (os.environ.get("SUPERVISORLY_EXPAND_BASE_URL")
                or "https://generativelanguage.googleapis.com/v1beta/openai")
    model = os.environ.get("SUPERVISORLY_EXPAND_MODEL") or "gemini-flash-lite-latest"

    transport = httpx_transport(user_agent=f"SupervisorlyBot/0.1 (mailto:{email})")
    oa = _openalex.OpenAlexClient(transport, email=email,
                                  key=preflight.openalex_key(os.environ))
    disc = _ladder.build_targets(
        {"country": args.country, "field": args.field, "university_mode": "all"},
        _ror.RorClient(transport, email=email), oa, max_institutions=args.max_institutions)
    topics = disc["plan"].get("resolved_topic_ids") or []
    shortlisted = pipeline._apply_shortlist(list(disc["targets"]), set(), topics, 200)

    print(f"# SPIKE-4 · {args.country} · {args.field!r} · {len(topics)} topics · "
          f"judge={model}")
    # Resolve each target to the page a real deep-dive would actually read, using the
    # pipeline's OWN resolver. Filtering to `url_kind == "homepage"` returned ZERO of 200 on
    # the first run: OpenAlex almost never carries `homepage_url` (0 of 50 sampled, per
    # discover/orcid.py), so nearly every target's only lead is an ORCID iD that has to be
    # resolved to a researcher URL first. Measuring triage on a cohort that excludes that
    # path would be measuring a page set the product never sees.
    from supervisorly.discover import orcid as orcid_mod          # noqa: PLC0415

    orcid_client = orcid_mod.OrcidClient(transport)
    stats: dict = {}
    fetchable = []
    for t in shortlisted:
        if len(fetchable) >= args.pages * 2:      # resolve a surplus; many will fail to fetch
            break
        try:
            url = pipeline._page_url_for(t, orcid_client, stats)
        except Exception:                          # noqa: BLE001 — one target, not the run
            url = None
        if url and not walls.is_walled(url):
            fetchable.append({**t, "url": url})
    print(f"# {len(shortlisted)} shortlisted; {len(fetchable)} resolved to a fetchable page")
    if not fetchable:
        print("\nRESULT: no fetchable professor page in this cohort — nothing to measure. "
              "(See B-006: the institution enumeration may be the reason.)")
        return 1

    snaps = SnapshotStore(Path(os.environ.get("TMPDIR", ".")) / "spike4-snaps")
    fetcher = Fetcher(transport, snaps, rate_limiter=HostRateLimiter(min_interval=1.0))
    client = httpx.Client()

    # Same rung the pipeline builds for a live run (D-073); inert without Playwright.
    from supervisorly.fetch import render as render_mod            # noqa: PLC0415

    renderer = render_mod.ChromiumRenderer(fetcher.robots_allows)
    if not renderer.available():
        print("# WARNING: no Chromium — JS-app pages cannot be read, and this cohort is "
              "mostly JS apps. The number below will understate what production sees.")
        renderer = None
    rendered_n = [0]
    rows = []
    dropped: dict[str, int] = {}

    def _drop(reason: str) -> None:
        dropped[reason] = dropped.get(reason, 0) + 1

    for t in fetchable:
        if len(rows) >= args.pages:
            break
        res = fetcher.fetch(t["url"])
        text = ""
        if res.ok:
            text = main_text(snaps.load(res.snapshot_hash))
        elif res.error and "robots" in res.error:
            _drop("disallowed by robots.txt")
            continue
        if len(text) < 200 and renderer is not None:
            # THE RENDER RUNG, which production uses and the first version of this spike did
            # not. Without it 15 of 17 pages scored "under 200 chars" and the spike reported
            # a blocker that was really its own measurement gap — the deployed worker reaches
            # 10 of 40 targets on the same cohort. A spike that skips a rung the product has
            # measures a product nobody ships.
            page = renderer.render(t["url"])
            if page is not None and page.text:
                text = page.text
                rendered_n[0] += 1
        if len(text) < 200:
            _drop("no readable text even after rendering"
                  if renderer is not None else "under 200 chars (no renderer)")
            continue
        label = judge(client, base_url, model, key, text)
        if label is None:
            _drop("judge call failed")
            continue
        got = triage(text)
        rows.append({"url": t["url"], "name": t.get("name"), "truth": bool(label.get("recruiting")),
                     "triage": got, "kept": got in KEPT, "latin": _is_mostly_latin(text),
                     "chars": len(text), "quote": (label.get("quote") or "")[:70]})
        mark = "OK " if (bool(label.get("recruiting")) == (got in KEPT)) else "!! "
        if label.get("recruiting") and got not in KEPT:
            mark = "MISS"                    # the failure that matters
        print(f"{len(rows):3}. {mark} truth={'Y' if label.get('recruiting') else 'n'} "
              f"triage={got:<10} {(t.get('name') or '')[:26]:<26} {t['url'][:46]}")

    n = len(rows)
    if not n:
        print("\nRESULT: no page could be both fetched and labelled — nothing measured.")
        return 1
    pos = [r for r in rows if r["truth"]]
    neg = [r for r in rows if not r["truth"]]
    kept_pos = [r for r in pos if r["kept"]]
    dropped_neg = [r for r in neg if not r["kept"]]

    print("\n" + "=" * 72)
    print(f"pages fetched and labelled       {n}")
    print(f"  the judge called recruiting    {len(pos)}")
    print(f"  the judge called irrelevant    {len(neg)}")
    print(f"non-latin pages (auto-escalated) {len([r for r in rows if not r['latin']])}")
    print(f"needed the browser to be readable {rendered_n[0]}")
    if dropped:
        print(f"\ncandidates dropped before labelling ({sum(dropped.values())} of "
              f"{len(fetchable)} resolved):")
        for reason, c in sorted(dropped.items(), key=lambda kv: -kv[1]):
            print(f"  {c:4}  {reason}")

    if not pos:
        # NOT the same as recall 0%. Recall is undefined with an empty positive set, and
        # printing "0% - MISS" here would kill a phase that was never tested. This is the
        # SPIKE-1 lesson applied to a different spike: say whether the PHASE failed or the
        # INPUT did.
        print("\nRECALL   NOT MEASURED — the judge found recruiting language on 0 of "
              f"{n} pages, so there is no positive set to have recall against.")
        print("verdict  INCONCLUSIVE · do not read this as a MISS, and do not build P4 on it.")
        print("         Re-run on a cohort whose professors have readable pages; if that is "
              "not reachable, B-006 and B-003 are the blockers to resolve first.")
        return 3

    recall = len(kept_pos) / len(pos)
    print(f"\nRECALL   {len(kept_pos)}/{len(pos)} = {recall:.0%}   "
          f"(of pages with recruiting language, the share triage KEEPS)")
    if neg:
        print(f"savings  {len(dropped_neg)}/{len(neg)} = {len(dropped_neg) / len(neg):.0%}   "
              f"(of irrelevant pages, the share triage DROPS before the model)")
    for r in pos:
        if not r["kept"]:
            print(f"  MISSED: {r['url']}\n          judge quoted: {r['quote']!r}")
    print(f"\nthreshold recall {RECALL_THRESHOLD:.0%} — "
          f"{'PASS · build P4' if recall >= RECALL_THRESHOLD else 'MISS · stop and re-plan'}")
    if len(pos) < 20:
        print(f"note: only {len(pos)} positive pages — thin. Treat this as provisional and "
              "re-run on a wider cohort before relying on the number.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
