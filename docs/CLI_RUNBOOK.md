# Using Supervisorly from the command line

Everything here runs **on your machine**. This is the same engine the web app runs; the CLI is
just the other surface over it.

Nothing below depends on where you put the project — clone it anywhere.

---

## 0. Install

Needs [**Python 3.10+**](#prerequisites--installing-python-and-git) and [**git**](#prerequisites--installing-python-and-git) — see the appendix if you do not
have them. The repository is public.

```bash
git clone https://github.com/ahmedmahershaaban/supervisorly.git
cd supervisorly
```

Then a virtual environment, so the dependencies stay out of your system Python:

```powershell
# Windows — PowerShell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

```bash
# macOS / Linux
python3 -m venv .venv
source .venv/bin/activate
```

Install the package itself. `-e` means editable: `git pull` picks up new code with no reinstall.

```bash
pip install -e .
supervisorly version          # -> Supervisorly 0.1.0
```

That registers a `supervisorly` command on your PATH. Every example below uses it. If you would
rather not activate the venv, `python -m supervisorly …` does exactly the same thing.

<details>
<summary>Optional extras</summary>

```bash
pip install -e ".[dev]"           # pytest, for running the suite
pip install -e ".[browser]"       # playwright, for --render-all  (then see below)
```

Playwright is deliberately **not** a required dependency — a scan without it falls back to the
fetched text and still finishes.
</details>

### Staying current

```bash
git pull                # you are on main, which is where the CLI work lands
pip install -e .        # only needed if dependencies changed
```

### Set your contact email

Not optional for a live scan — OpenAlex's polite pool identifies callers by email, and a scan
without one is refused at preflight rather than sent anonymously.

```powershell
# Windows — you need BOTH lines. See the note below.
$env:SUPERVISORLY_CONTACT_EMAIL = "you@example.com"   # this terminal, right now
setx SUPERVISORLY_CONTACT_EMAIL "you@example.com"     # every terminal you open later
```

```bash
# macOS / Linux — this shell, then add the same line to ~/.zshrc or ~/.bashrc
export SUPERVISORLY_CONTACT_EMAIL="you@example.com"
```

> **Why both, on Windows.** `setx` prints `SUCCESS` and writes the *stored* environment, which
> only new terminals read. It does not change the terminal you are in — so running `setx` and
> then immediately scanning still fails the preflight check. Either open a new terminal after
> `setx`, or set `$env:…` as well.

Or skip the environment entirely and pass it per run:

```bash
supervisorly scan --email you@example.com --country GB --field "machine learning"
```

---

## 0b. Prefer a page to a command line?

```powershell
supervisorly serve
```

One command. It opens the 5-step wizard in your browser and runs scans from it — the **same
engine** as `scan`, on **your** machine, from **your** IP, using **your** Chromium. Step 4 has a
"Depth & engine" panel carrying every control this runbook describes as a flag:

| On the page | Same as |
|---|---|
| Universities to scan | `--max-institutions` |
| Professors to deep-dive | `--shortlist` |
| Which organisations count | `--institution-types` |
| Read every page with a real browser | `--render-all` |
| Follow links on the professor's site | `--crawl` |
| Pages open at once | `--concurrency` |
| Compare with an earlier search | `--compare-to` |
| Ignore robots.txt | `--ignore-robots` |

The page asks the server what it can actually do before offering any of it: if Chromium is not
installed, the browser checkbox is **disabled and says why**, rather than starting a scan that
renders nothing and reports success. Your search and model keys stay in your environment — the
page is told *whether* one is configured, never what it is.

`--ignore-robots` appears **only** on this local server. The hosted app at `supervisorly.web.app`
refuses it, because there the address being spent is not yours.

Nothing else changes: `--out`, the database, snapshots and `reexport` all work exactly as below.

---

## 1. Prove it works with no keys and no network

```bash
supervisorly scan --demo
```

Five synthetic professors on RFC-2606 `.example` hosts. Touches no real institution, needs no
credentials. If this opens a dashboard, the install is good.

---

## 2. Your first real scan

```bash
supervisorly scan \
  --country GB \
  --field "machine learning" \
  --intent phd \
  --shortlist 25 \
  --progress
```

| Flag | What it does |
|---|---|
| `--country` | ISO code (`GB`, `EG`, `CA`) or English name (`Canada`) |
| `--field` | free text; the subject map is generated from it, never looked up |
| `--intent` | `training`, `pre_master`, `pre_phd`, `mentor`, `master`, `phd`, `postdoc` |
| `--shortlist N` | how many discovered professors get deep-dived (default 40). Everyone else is still listed, marked unchecked — never dropped |
| `--max-institutions N` | how many institutions to enumerate (default 200). This drives how many pages are **fetched** from ROR, not a slice afterwards |
| `--institution-types education,facility` | which pools to scan — see below |
| `--compare-to output/last.json` | diff against a previous scan; the new export carries a `delta` block |
| `--archive` | where a page publishes no deadline, read its past years and project the next cycle |
| `--progress` | one line per phase to stderr; otherwise silent |
| `--universities "Imperial College,UCL"` | with `--university-mode only` to restrict, `prioritise` to rank first |

### Which institutions get scanned

By default: only the organisations ROR types as **`education`** — universities and colleges.
A hospital's or a company's author list cannot supply a PhD supervisor, and enumerating it
spends the institution budget.

But universities are not the only place supervision happens, and in some countries they are
not even where most of it happens. A Max Planck institute is typed `facility`. A teaching
hospital is `healthcare`. So the pool is a **selection**, not an on/off switch:

```bash
--institution-types education,facility,healthcare
--institution-types all
```

Valid values are ROR's own vocabulary: `education`, `facility` (research institutes and
national labs), `healthcare` (teaching hospitals), `government`, `nonprofit`, `company`,
`archive`, `funder`, `other`. A misspelling stops the scan rather than quietly running an
education-only one.

Whatever you pick, the run **tells you what it left out**, with counts:

```
Warning: kept 96 of 200 ROR institutions for CA - types: education 96.
Not scanned: healthcare 54, company 22, nonprofit 14, government 9, facility 5
```

An organisation can carry two types — a university hospital is both `education` and
`healthcare` — and asking for either pool finds it.

`--all-institution-types` still works; it is now a synonym for `--institution-types all`.

### What a scan tells you beyond the professor list

The JSON export carries three things the per-professor rows cannot:

* `run.universities` — the same scores rolled up to institutions, best first. You apply to a
  department, not to a row.
* `run.delta` — present only with `--compare-to`: new and removed professors, changed fields,
  recruiting signals worth re-reading, newly published deadlines.
* `profile.contested_fields` — fields where two sources disagreed and neither provenance nor
  recency could order them. Both claims are kept; the newer one leads.
* `profile.deadline_projection` — present only with `--archive`, and only for professors whose
  page published no deadline. **This is not a deadline.** It is a pattern read off the page's
  own archived copies, labelled `watch`, carrying the years it came from — and when it will not
  project (fewer than three archived cycles, or too few carrying a readable date) it says so
  instead of going quiet. Always confirm on the official page.

### About `--archive`

It costs the Internet Archive up to five extra page reads per professor, so it is off by
default and skipped entirely for anyone whose page already states a date. If the archive
rate-limits or is unreachable, the run continues and records the reason — a charity's throttle
never becomes our claim about an institution's admissions.

### Where the output lands

With no `--out`, everything goes to the project's own `output/` folder:

```
output/
  dashboard.html          the thing you open
  dashboard.json          the same data, machine-readable
  supervisorly.sqlite     the store — claims, snapshots, run state
  .cache/snaps/           content-hashed page snapshots
```

`/output/` is gitignored, as are `*.sqlite`, `**/.cache/` and `**/snaps/`, so a scan cannot
commit real academics' names and emails. **That guard is the only constraint** — within it,
name things however you like:

```bash
supervisorly scan --country GB --field "machine learning" \
  --out output/gb-ml.html          # -> output/gb-ml.json, output/.cache/snaps/
```

Keeping one file per scan is worth doing once you have more than one country in flight, since
the SQLite store sits next to the `--out` path and `--resume` reads it from there.

**Expect thin results on the first run.** That is the honest state of the data, not a bug:
measured on a real GB/ML scan, **88% of shortlisted professors had no page on record at all**
and 0% had a page they control. Steps 3 and 4 are what fix that.

---

## 3. Read pages properly — the local browser

```bash
supervisorly scan --country GB --field "machine learning" \
  --render-all --concurrency 8 --progress
```

- `--render-all` — Chromium reads **every** page, not just the ones that came back as a login
  wall or JavaScript shell. Many academic pages are JS apps whose HTML holds no text.
- `--concurrency 8` — pages rendered in parallel. One host is always read strictly serially
  however high you set this, so you never hammer a single university.

This needs Playwright, which is **two** steps — the Python package, then the browser it
drives. The second command downloads ~400 MB and presupposes the first:

```bash
pip install -e ".[browser]"            # the package
python -m playwright install chromium  # the browser itself
```

Skipping the first is the easy mistake, because the second reads like the whole job:

```
python -m playwright install chromium
-> No module named playwright
```

Without it nothing breaks — every page falls back to the fetched text and the scan finishes.

---

## 4. Find the page that actually answers the question

Two optional keys. Both fail closed: without them the scan runs exactly as in step 3.

### 4a. Rung 7 — resolve a professor to their own page

This is the fix for the 88%. One generated query per shortlisted professor.

```powershell
# Windows
$env:SUPERVISORLY_SEARCH_KEY = "<brave-or-tavily-key>"
$env:SUPERVISORLY_SEARCH_PROVIDER = "brave"      # or "tavily"
```

```bash
# macOS / Linux
export SUPERVISORLY_SEARCH_KEY="<brave-or-tavily-key>"
export SUPERVISORLY_SEARCH_PROVIDER=brave        # or tavily
```

| Provider | `_PROVIDER` | Free tier | Card needed? | Where |
|---|---|---|---|---|
| **Gemini** (grounded search) | `gemini` | yes | **no** | aistudio.google.com |
| **Google Programmable Search** | `google` | 100/day | **no** | developers.google.com/custom-search |
| Tavily | `tavily` | yes | check | tavily.com |
| Brave Search API | `brave` | 2,000/month | **yes** | api-dashboard.search.brave.com |

**Start with `gemini`** — no card, and the same key works for `SUPERVISORLY_EXTRACT_KEY`:

```powershell
$env:SUPERVISORLY_SEARCH_KEY = "<gemini-key>"
$env:SUPERVISORLY_SEARCH_PROVIDER = "gemini"
```

**Google Programmable Search needs a second value**, a search-engine id, and that engine must
be set to search the *entire web* or it will only answer from the sites it was scoped to:

```powershell
$env:SUPERVISORLY_SEARCH_KEY = "<google-api-key>"
$env:SUPERVISORLY_SEARCH_PROVIDER = "google"
$env:SUPERVISORLY_SEARCH_CX = "<search-engine-id>"
```

> **Gemini is not equivalent to a search index, and that is worth knowing before you rely on
> it.** Brave and Google return a *ranked list of results*. Gemini returns whichever sources
> the model chose to cite while answering — so it may return fewer, may differ between
> identical calls, and may cite a news article rather than a department page. It is the right
> tool for finding out whether this rung fixes your dashboard; it is not the one to
> standardise on if it does.
>
> Only the URLs it consulted are used — never its own sentences — so it cannot invent a page.
> Its citations are Google redirect links, which are resolved to the real page before anything
> is fetched, because fetching the proxy would consult Google's `robots.txt` instead of the
> university's.

### 4b. Let a model read the prose

The regexes only match shapes someone anticipated. *"I will be reviewing applications for the
2027 intake"* means recruiting and matches no cue word.

```powershell
# Windows
$env:SUPERVISORLY_EXTRACT_KEY = "<any-openai-compatible-key>"
# optional, for a non-default provider:
$env:SUPERVISORLY_EXTRACT_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai"
$env:SUPERVISORLY_EXTRACT_MODEL    = "gemini-2.0-flash"
```

```bash
# macOS / Linux
export SUPERVISORLY_EXTRACT_KEY="<any-openai-compatible-key>"
```

Keys live in your shell, never in the repo. `.env` is gitignored if you prefer a file.

The model may only propose `(field, value, quote)`. Any quote not found verbatim in the stored
snapshot is dropped in code, twice. It cannot invent a professor or a deadline.

### 4c. Follow the link the recruiting sentence lives behind

```bash
supervisorly scan --country GB --field "machine learning" \
  --render-all --crawl --progress
```

A professor's page is usually a staff card; *Vacancies* / *Join the group* is one click away.
`--crawl` follows those links only — depth 2, same host, 20 pages max, and it stops the moment
every field has an answer.

### The full stack

```bash
supervisorly scan \
  --country GB --field "machine learning" --intent phd \
  --render-all --concurrency 8 --crawl \
  --shortlist 25 --progress
```

---

## 5. Cheap re-scans

```bash
supervisorly scan --country GB --field "machine learning" --resume
```

Skips targets already deep-dived in the store next to `--out`. Use it after a cancelled run or
to pick up only what changed.

To be told *what* changed rather than re-reading the list, keep the previous export and point
at it:

```bash
cp output/dashboard.json output/last.json
supervisorly scan --country GB --field "machine learning" --compare-to output/last.json
```

The new export's `run.delta` names the new and removed professors, every field whose state,
value or confidence moved, and any deadline that went from watched to published.

---

## 6. Fill the gaps a machine must not fill

Professors whose page is behind a login or bot-wall are **not** scraped. The dashboard gives
each one a search link and a copy-ready prompt. You open the page yourself, then hand the
answer back — there are two ways in, and which one you use depends on what you have.

**You have the page's text.** Paste it to a file and let the normal extractors read it:

```bash
supervisorly ingest-page \
  --url "https://the-final-url-after-redirects" \
  --file ./page.txt \
  --db output/supervisorly.sqlite \
  --entity person:<id-from-the-dashboard> \
  --run <run-id>
```

**You have a model's reply to the dashboard's prompt.** That prompt asks for `## field:`
Markdown blocks; save the reply verbatim and pass it here:

```bash
supervisorly ingest-md --file ./reply.md --db output/supervisorly.sqlite
```

Either way, run:

```bash
supervisorly reexport
```

`reexport` rebuilds the dashboard from the store with no fetching at all.

Human-returned data is not privileged: every block goes through the same quote gate as a
fetched one and is stamped `human-assisted (Claude for Chrome)`, so a reader can always tell
how a value arrived. A quote that does not appear in what you pasted is rejected and the gap
stays open — as it should.

---

## 7. The other subcommands

```bash
supervisorly map-field --field "causal inference"
supervisorly studio    --map output/subject_map.json
```

`map-field` turns free text into a hierarchical OpenAlex subject map; `studio` renders it as a
self-contained plan wizard that emits a plan JSON you can feed back with `--plan`.

```bash
supervisorly init-db --db output/supervisorly.sqlite   # create/migrate a store
supervisorly pace --host x.com                             # exit 0 allow, 3 deny
```

---

## 8. `--ignore-robots`

Off by default. It prints a banner before the first request and names whose IP pays.

```bash
supervisorly scan ... --ignore-robots
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
| `SUPERVISORLY_SEARCH_CX` | `google` only | its search-engine id |
| `SUPERVISORLY_SEARCH_MODEL` | `gemini` only | override the grounded model |
| `SUPERVISORLY_EXTRACT_KEY` + `_BASE_URL` + `_MODEL` | no | reading prose |
| `SUPERVISORLY_EXPAND_KEY` + `_BASE_URL` + `_MODEL` | no | search-query expansion |
| `PHASES` | no | turn gated phases on/off |

---

## Two things to keep in mind

**Output goes to `output/`, and that is already the default** — so you can leave `--out` off
entirely. `/output/` is gitignored, as are `**/.cache/`, `**/snaps/` and `*.sqlite`, so a scan
cannot commit a dashboard full of real names.

If you do pass `--out`, keep it inside `output/` (or `results/` or `out/`, both also ignored).
A path anywhere else in the tree is **not** covered, and scan results are personal data.

**Running the test suite needs `TMPDIR` outside the repo**, or the D-005 guard correctly fires
on pytest's `tmp_path`:

```powershell
# Windows
$env:TMPDIR = "$env:LOCALAPPDATA\Temp\sv-pytest"
pytest -q
```

```bash
# macOS / Linux
export TMPDIR=/tmp/sv-pytest
pytest -q                    # 1,164 passed
```

---

## Appendix — prerequisites: installing Python and git

Only needed for the CLI. The web app needs none of this.

### Python 3.10+

```powershell
# Windows
winget install Python.Python.3.12
```

```bash
# macOS  (leave the system python alone; the command is python3)
brew install python@3.12

# Debian / Ubuntu   — python3-venv is a SEPARATE package and `python3 -m venv`
#                     fails without it, with an ensurepip error that never says so
sudo apt update && sudo apt install python3 python3-venv python3-pip

# Fedora / RHEL
sudo dnf install python3 python3-pip
```

Or the installers at <https://www.python.org/downloads/>.

> **Windows, the one box people miss.** The python.org installer leaves
> **"Add python.exe to PATH"** unticked, at the bottom of the first screen. Without it your
> terminal says `python: command not found` even though the install succeeded. If typing
> `python` opens the Microsoft Store, that is Windows' placeholder stub — *Settings → Apps →
> Advanced app settings → App execution aliases*, turn off both Python entries.

### git

```powershell
# Windows
winget install Git.Git
```

```bash
# macOS — ships git with Apple's command line tools
xcode-select --install

# Linux
sudo apt install git        # Debian / Ubuntu
sudo dnf install git        # Fedora / RHEL
```

Or <https://git-scm.com/downloads>.

### Check both

```bash
python --version     # or python3 --version -> 3.10 or higher
git --version
```

Two version numbers and you are ready for step 0.

**No git and would rather not install it?** Download the ZIP from the repository's green
*Code* button and unpack it anywhere. Everything works; you just update by downloading again
instead of `git pull`.

### What you do *not* need

| Not required | Why people assume otherwise |
|---|---|
| Node.js | Only the deploy-verification script uses it, never a scan |
| Docker | Only for building the hosted worker image |
| A Google Cloud account | Only to deploy the web app |
| Chromium / Playwright | Optional — `--render-all` only. A scan without it still finishes |
| Any API key | A scan needs only a contact email |
