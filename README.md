# Supervisorly

Find a research supervisor — for a **PhD, master's, or postdoc, in any country** — with
evidence you can check. Supervisorly is a **Claude-Code skill + agents + tools**: you tell it a
country, a field, and what you need, and it builds a filterable dashboard of professors where
every fact links back to its source.

> **Status: in development.** The design is complete (`docs/`) and implementation is underway on
> the `build/v1` branch, one tracked round at a time. This README grows with the build.

## What makes it different

- **Any country, any field** — nothing is hardcoded; the search strategy is generated per query.
- **Evidence, not vibes** — every displayed fact is a *claim* with a verbatim quote, a source
  URL, and a confidence level. "We looked and found nothing" is shown honestly, never guessed.
- **Respectful by design** — it reads public sources and open APIs and never defeats a login;
  walled pages (X, LinkedIn, Scholar) are read through *your own* logged-in browser session by the
  agent (one-time login, strict pacing), and anything it still can't read goes to you via a
  generated Claude-for-Chrome prompt.
- **Runs in Claude Code** — no server, no account. Point Claude at this repo.

See [`docs/HANDOVER.md`](docs/HANDOVER.md) for the map, and the interactive design atlas.

## Install (development)

Use a virtual environment — it keeps dependencies isolated and avoids writing scripts into a
global Python directory.

```bash
python -m venv .venv
# Windows:  .venv\Scripts\activate         # macOS/Linux:  source .venv/bin/activate
python -m pip install -e ".[dev]"          # add --no-deps to install the package only
```

Run the CLI as a module (works everywhere, no console-script needed):

```bash
python -m supervisorly version
python -m supervisorly init-db --db output/run.sqlite
```

Run the tests:

```bash
python -m pytest
```

## Run a scan

There are two ways to run, sharing one deterministic pipeline behind a transport seam.

**Offline demo (no network, no credentials)** — a fully synthetic fixture (invented names,
`example` domains) covering three directory shapes across three countries, a non-English page,
and a robots-blocked one. Use it to see the output end to end:

```bash
python -m supervisorly scan --demo --out output/dashboard.html
# writes output/dashboard.html (open it in any browser) + output/dashboard.json
```

The dashboard is a single self-contained file: a filterable table, a **Deadlines** view that
shows projected dates as *watch dates* (never firm), and a click-through detail panel where
every fact carries its verbatim quote and source link. A professor is never dropped for missing
data — the four states (`value` / `searched_absent` / `never_attempted` / `blocked`) render
distinctly.

**Live scan (real sources)** — needs the credentials below. It fetches only public pages and
open APIs, obeys `robots.txt`, reads advertised walled profiles through your own logged-in
browser (the browser tier below), and routes whatever remains to you via a generated
Claude-for-Chrome prompt (paste the result back and the run resumes without re-fetching).

## Credentials (needed for live runs)

The open data services this tool uses are **free and keyless**: [ROR](https://ror.org)'s API is
open and needs no account, and [OpenAlex](https://openalex.org) is free. The only thing a live
scan genuinely needs is a **contact email** — OpenAlex's "polite pool" marker (`?mailto=…`) that
earns faster, more reliable service, and the address we identify ourselves with in the HTTP
User-Agent. The tool **fails loud** (with the exact fix) if it's missing, rather than hammering
public APIs anonymously.

| Environment variable          | Required? | What it is | Where |
|-------------------------------|-----------|------------|-------|
| `SUPERVISORLY_CONTACT_EMAIL`  | **yes** (live) | **Your own email** — used for the OpenAlex polite pool and our User-Agent. Any address you own. | — |
| `SUPERVISORLY_OPENALEX_KEY`   | optional  | A **paid** OpenAlex premium key for higher limits / the full snapshot. Not needed for a scan. | <https://openalex.org/pricing> |

There is **no ROR key** — its API is open. The offline test suite and `scan --demo` need nothing.

## Opt-out

To exclude specific people, list their identifiers (homepage URL, ORCID, OpenAlex/ROR id, or
internal id — one per line) in an `optout.txt` and pass it to a scan; a match is dropped **before
any fetch** — never requested, scored, shown, or stored. The `optout.txt` shipped in the repo is
an empty template and must never contain real personal data.

## A live scan

```bash
supervisorly scan --country Canada --field "causal ML" --intent pre_phd \
  --email you@example.com --out output/live.html
# optional: --universities "University of Toronto,McGill" --university-mode only
#           --openalex-key <premium>   --optout optout.txt   --resume
```

`--university-mode` is `all` (default), `prioritise`, or `only`. The scan discovers institutions
(ROR) and professors (OpenAlex), deep-dives each professor's public pages into quote-verified
claims (recruiting, deadline, students, collaborations, social), scores + ranks them, and writes a
self-contained dashboard.

## Planning a scan: subject map, Scan Studio, named professors

Before a scan you can map your free-text field to a hierarchical, API-derived OpenAlex **subject
map**, pick the topics you want (a numbered list in conversation, or the self-contained **Scan
Studio** wizard), and run from the exported plan — or skip discovery and name professors directly:

```bash
python -m supervisorly map-field --field "causal ML"        # → output/subject_map.json
python -m supervisorly studio --map output/subject_map.json # → output/studio.html (offline wizard)
python -m supervisorly scan --plan supervisorly_plan.json --out output/live.html
python -m supervisorly scan --targets profs.json --email you@example.com --out output/live.html
```

`--plan` takes a Scan Studio plan JSON (explicit flags override its values); `--targets` takes a
JSON list of `{"name": ..., "affiliation": ...}` objects or OpenAlex author URLs — anyone who
doesn't resolve is reported as an honest skip, never silently dropped.

## The browser tier (live page fetches)

When an agent runs Supervisorly, Chrome (driven via `chrome-devtools-mcp`) is the **primary** page
fetch for live scans: the agent navigates, extracts the main text in-page, and hands it to the
deterministic engine through the `ingest-page` seam — raw HTML never enters the agent's context,
and APIs (ROR/OpenAlex) stay on plain HTTP. The browser runs on a persistent profile: on the
**first** run you log into the walled sites (X, LinkedIn) **once, yourself**, in the opened Chrome
window; after that the agent can read advertised profiles on its own, under a strict anti-ban
pacing policy (`pace` gates every page — jittered intervals, per-session caps, abort-on-challenge).
The setup is host-portable: register the server once at user level, e.g. for Claude Code
`claude mcp add chrome-devtools --scope user npx chrome-devtools-mcp@latest`.

```bash
python -m supervisorly pace --host x.com            # gate before a browser page: exit 0 = go, 3 = wait/deny
python -m supervisorly ingest-page --url <finalUrl> --file browser_staging/page.txt \
    --db supervisorly.sqlite                        # store agent-extracted text as a snapshot
```

## Scheduled re-scans

Supervisorly is built for repeat runs: `--resume` reuses the warm cache, so an unchanged page is
never re-extracted, and you get a *"what changed since last time"* delta (new professors, newly-open
recruiting, newly-published deadlines). Schedule it to keep your shortlist fresh:

```bash
# macOS / Linux (crontab -e) — every Monday 08:00
0 8 * * 1  cd /path/to/supervisorly && .venv/bin/supervisorly scan --country Canada \
  --field "causal ML" --email you@example.com --out output/live.html --resume
```

On **Windows**, use Task Scheduler → *Create Task* → a weekly trigger running the same command via
`.venv\Scripts\supervisorly.exe`. Output stays local and is never committed.

## Ethics

Supervisorly processes public information about identifiable people. It obeys `robots.txt`,
honours an `optout.txt` at build time, never scrapes login-walled or `robots`-disallowed pages,
and never exports bare email lists or automated bulk outreach. Scan output stays local and is
never committed. See [`docs/ethics-and-compliance.md`](docs/ethics-and-compliance.md).

## Licence

MIT — see [`LICENSE`](LICENSE).
