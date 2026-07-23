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

## Credentials (needed for live runs)

Two free credentials are required for a real scan and the setup fails loud without them:

- a **ROR client ID** (institution registry) — required as of 2026-07;
- a **free OpenAlex API key** — without it the daily credit ceiling is ~2 scans instead of ~20.

The offline test suite and the `--offline --demo` mode run without either.

## Ethics

Supervisorly processes public information about identifiable people. It obeys `robots.txt`,
honours an `optout.txt` at build time, never scrapes login-walled or `robots`-disallowed pages,
and never exports bare email lists or automated bulk outreach. Scan output stays local and is
never committed. See [`docs/ethics-and-compliance.md`](docs/ethics-and-compliance.md).

## Licence

MIT — see [`LICENSE`](LICENSE).
