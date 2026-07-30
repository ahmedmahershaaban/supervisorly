# Using Supervisorly from the command line

Everything here runs **on your machine**. This is the same engine the web app runs; the CLI is
just the other surface over it.

---

## 0. One-time setup

```powershell
cd D:\AndroidStudioProjects\how_to_get_proffessor
.venv\Scripts\activate                 # or prefix every command with .venv\Scripts\python.exe
python -m supervisorly version          # sanity check
```

**Set your contact email.** Not optional for a live scan — OpenAlex's polite pool identifies
callers by email, and a scan without one is refused at preflight rather than sent anonymously.

```powershell
$env:SUPERVISORLY_CONTACT_EMAIL = "you@example.com"        # this session only
# permanent:
setx SUPERVISORLY_CONTACT_EMAIL "you@example.com"
```

---

## 1. Prove it works with no keys and no network

```powershell
python -m supervisorly scan --demo --out C:\Temp\sv\demo.html
```

Five synthetic professors on RFC-2606 `.example` hosts. Touches no real institution, needs no
credentials. If this opens a dashboard, the install is good.

---

## 2. Your first real scan

```powershell
python -m supervisorly scan `
  --country GB `
  --field "machine learning" `
  --intent phd `
  --shortlist 25 `
  --progress `
  --out C:\Temp\sv\gb-ml.html
```

| Flag | What it does |
|---|---|
| `--country` | ISO code (`GB`, `EG`, `CA`) or English name (`Canada`) |
| `--field` | free text; the subject map is generated from it, never looked up |
| `--intent` | `training`, `pre_master`, `pre_phd`, `mentor`, `master`, `phd`, `postdoc` |
| `--shortlist N` | how many discovered professors get deep-dived (default 40). Everyone else is still listed, marked unchecked — never dropped |
| `--max-institutions N` | cap the ROR enumeration while you are experimenting |
| `--progress` | one line per phase to stderr; otherwise silent |
| `--universities "Imperial College,UCL"` | with `--university-mode only` to restrict, `prioritise` to rank first |

Output is `gb-ml.html` + `gb-ml.json`, and a SQLite store next to them.

**Expect thin results on the first run.** That is the honest state of the data, not a bug:
measured on a real GB/ML scan, **88% of shortlisted professors had no page on record at all**
and 0% had a page they control. Steps 3 and 4 are what fix that.

---

## 3. Read pages properly — the local browser

```powershell
python -m supervisorly scan --country GB --field "machine learning" `
  --render-all --concurrency 8 --progress --out C:\Temp\sv\gb-ml.html
```

- `--render-all` — Chromium reads **every** page, not just the ones that came back as a login
  wall or JavaScript shell. Many academic pages are JS apps whose HTML holds no text.
- `--concurrency 8` — pages rendered in parallel. One host is always read strictly serially
  however high you set this, so you never hammer a single university.

Needs Playwright's Chromium. It is installed here already; if you ever wipe it:

```powershell
python -m playwright install chromium
```

Without it nothing breaks — every page falls back to the fetched text and the scan finishes.

---

## 4. Find the page that actually answers the question

Two optional keys. Both fail closed: without them the scan runs exactly as in step 3.

### 4a. Rung 7 — resolve a professor to their own page

This is the fix for the 88%. One generated query per shortlisted professor.

```powershell
$env:SUPERVISORLY_SEARCH_KEY = "<brave-or-tavily-key>"
$env:SUPERVISORLY_SEARCH_PROVIDER = "brave"      # or "tavily"
```

| Provider | Free tier | Sign-up |
|---|---|---|
| Brave Search API | 2,000 queries/month | api-dashboard.search.brave.com |
| Tavily | free tier | tavily.com |

### 4b. Let a model read the prose

The regexes only match shapes someone anticipated. *"I will be reviewing applications for the
2027 intake"* means recruiting and matches no cue word.

```powershell
$env:SUPERVISORLY_EXTRACT_KEY = "<any-openai-compatible-key>"
# optional, for a non-default provider:
$env:SUPERVISORLY_EXTRACT_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai"
$env:SUPERVISORLY_EXTRACT_MODEL    = "gemini-2.0-flash"
```

The model may only propose `(field, value, quote)`. Any quote not found verbatim in the stored
snapshot is dropped in code, twice. It cannot invent a professor or a deadline.

### 4c. Follow the link the recruiting sentence lives behind

```powershell
python -m supervisorly scan --country GB --field "machine learning" `
  --render-all --crawl --progress --out C:\Temp\sv\gb-ml.html
```

A professor's page is usually a staff card; *Vacancies* / *Join the group* is one click away.
`--crawl` follows those links only — depth 2, same host, 20 pages max, and it stops the moment
every field has an answer.

### The full stack

```powershell
python -m supervisorly scan `
  --country GB --field "machine learning" --intent phd `
  --render-all --concurrency 8 --crawl `
  --shortlist 25 --progress `
  --out C:\Temp\sv\gb-ml.html
```

---

## 5. Cheap re-scans

```powershell
python -m supervisorly scan --country GB --field "machine learning" --resume `
  --out C:\Temp\sv\gb-ml.html
```

Skips targets already deep-dived in the store next to `--out`. Use it after a cancelled run or
to pick up only what changed.

---

## 6. Fill the gaps a machine must not fill

Professors whose page is behind a login or bot-wall are **not** scraped. The dashboard gives
each one a search link and a copy-ready prompt. You open the page yourself, then hand the text
back:

```powershell
python -m supervisorly ingest-page `
  --url "https://the-final-url-after-redirects" `
  --file C:\Temp\page.txt `
  --db C:\Temp\sv\supervisorly.sqlite `
  --entity person:<id-from-the-dashboard> `
  --run <run-id>

python -m supervisorly reexport --db C:\Temp\sv\supervisorly.sqlite --out C:\Temp\sv\gb-ml.html
```

`reexport` rebuilds the dashboard from the store with no fetching at all.

---

## 7. The other subcommands

```powershell
python -m supervisorly map-field --field "causal inference" --out C:\Temp\sv\map.json
python -m supervisorly studio    --map C:\Temp\sv\map.json  --out C:\Temp\sv\studio.html
```

`map-field` turns free text into a hierarchical OpenAlex subject map; `studio` renders it as a
self-contained plan wizard that emits a plan JSON you can feed back with `--plan`.

```powershell
python -m supervisorly init-db --db C:\Temp\sv\supervisorly.sqlite   # create/migrate a store
python -m supervisorly pace --host x.com                             # exit 0 allow, 3 deny
```

---

## 8. `--ignore-robots`

Off by default. It prints a banner before the first request and names whose IP pays.

```powershell
python -m supervisorly scan ... --ignore-robots
```

robots.txt is still read and the **real verdict is stored per source**, so an export never
claims consent that was not given, and the run carries a `robots_override` note.

Worth knowing before you reach for it: measured, robots refusals hit 5 of 10 Egyptian
institutions and 0 of 4 UK ones, and **nothing** against the 88% — that number is professors
with no page on record, and no robots setting creates a URL that is not there.

---

## Environment variables, all together

| Variable | Required? | For |
|---|---|---|
| `SUPERVISORLY_CONTACT_EMAIL` | **yes**, live scans | OpenAlex polite pool |
| `SUPERVISORLY_OPENALEX_KEY` | no | paid OpenAlex, higher limits |
| `SUPERVISORLY_SEARCH_KEY` + `_PROVIDER` | no | rung 7 page resolution |
| `SUPERVISORLY_EXTRACT_KEY` + `_BASE_URL` + `_MODEL` | no | reading prose |
| `SUPERVISORLY_EXPAND_KEY` + `_BASE_URL` + `_MODEL` | no | search-query expansion |
| `PHASES` | no | turn gated phases on/off |

---

## Two things to keep in mind

**Write output outside the repo.** Scan results are personal data and must never be committed.
`C:\Temp\sv\` or anywhere outside the working tree.

**Running the test suite needs `TMPDIR` outside the repo**, or the D-005 guard correctly fires
on pytest's `tmp_path`:

```powershell
$env:TMPDIR = "C:\Temp\sv-pytest"
python -m pytest -q          # 1164 passed
```
