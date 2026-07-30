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
# Windows — this session only, then permanently
$env:SUPERVISORLY_CONTACT_EMAIL = "you@example.com"
setx SUPERVISORLY_CONTACT_EMAIL "you@example.com"
```

```bash
# macOS / Linux — this session, then add the same line to ~/.zshrc or ~/.bashrc
export SUPERVISORLY_CONTACT_EMAIL="you@example.com"
```

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
| `--max-institutions N` | cap the ROR enumeration while you are experimenting |
| `--progress` | one line per phase to stderr; otherwise silent |
| `--universities "Imperial College,UCL"` | with `--university-mode only` to restrict, `prioritise` to rank first |

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

| Provider | Free tier | Sign-up |
|---|---|---|
| Brave Search API | 2,000 queries/month | api-dashboard.search.brave.com |
| Tavily | free tier | tavily.com |

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

---

## 6. Fill the gaps a machine must not fill

Professors whose page is behind a login or bot-wall are **not** scraped. The dashboard gives
each one a search link and a copy-ready prompt. You open the page yourself, then hand the text
back:

```bash
supervisorly ingest-page \
  --url "https://the-final-url-after-redirects" \
  --file ./page.txt \
  --db output/supervisorly.sqlite \
  --entity person:<id-from-the-dashboard> \
  --run <run-id>

supervisorly reexport
```

`reexport` rebuilds the dashboard from the store with no fetching at all.

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
