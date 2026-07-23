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
  walled pages (X, Scholar, login-only directories) are handled by *you* in your own browser via
  a generated Claude-for-Chrome prompt.
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
open APIs, obeys `robots.txt`, and routes login-walled pages to you via a generated
Claude-for-Chrome prompt (paste the result back and the run resumes without re-fetching).

## Credentials (needed for live runs)

Two free credentials are required for a real scan; the tool **fails loud** (with the exact fix)
rather than running silently on the throttled anonymous tiers:

| Environment variable          | What it is                    | Get it |
|-------------------------------|-------------------------------|--------|
| `SUPERVISORLY_ROR_CLIENT_ID`  | ROR institution-registry client id | <https://ror.readme.io/> |
| `SUPERVISORLY_OPENALEX_KEY`   | OpenAlex key / polite-pool email — without it the daily credit ceiling is ~2 scans instead of ~20 | <https://openalex.org/> |

The offline test suite and `scan --demo` run without either.

## Opt-out

To exclude specific people, list their identifiers (homepage URL, ORCID, OpenAlex/ROR id, or
internal id — one per line) in an `optout.txt` and pass it to a scan; a match is dropped **before
any fetch** — never requested, scored, shown, or stored. The `optout.txt` shipped in the repo is
an empty template and must never contain real personal data.

## Ethics

Supervisorly processes public information about identifiable people. It obeys `robots.txt`,
honours an `optout.txt` at build time, never scrapes login-walled or `robots`-disallowed pages,
and never exports bare email lists or automated bulk outreach. Scan output stays local and is
never committed. See [`docs/ethics-and-compliance.md`](docs/ethics-and-compliance.md).

## Licence

MIT — see [`LICENSE`](LICENSE).
