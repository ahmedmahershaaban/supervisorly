# Supervisorly Web — full implementation plan (one dynamic page + Firebase)

> Status: **plan only — nothing here is implemented yet** (v3: progress UX, scale controls,
> safe-exit/resume, consolidated safety model). Everything is specified so that the ONLY
> remaining manual steps are inserting API keys / server config at the marked placeholders
> (`<LIKE_THIS>`). Binding constraints from `docs/DECISIONS.md` apply (D-005/009/010/035/037/
> 038/046 + D-068/D-069 defined below).

## 0 — What the student sees (the product flow)

One dynamic page (Atlas design language), five steps, no CLI, no agent required:

1. **You** — contact email, intent (pre-PhD / pre-master / master / PhD / postdoc / mentor),
   country (name or ISO), optional universities + mode (all / prioritise / only).
2. **Field** — free text ("NLP", "mechanistic interpretability", "causal ML") → *Understand*:
   the backend expands the phrasing and returns the subject map as **meaning clusters**
   (domain → field → subfield → topics).
3. **Disambiguate** — the student checks the topics/meanings they want (tri-state checkbox
   tree). The tool presents senses, never guesses (D-066).
4. **Scope & scan** — the student picks HOW BIG the search is (§4.3: institutions and
   professors, with a time estimate), starts the job, and watches a **progress bar with
   plain-language status** (§4.1). They can **pause/cancel safely and resume** (§4.2) —
   nothing is ever a dead end.
5. **Dashboard** — the existing self-contained Atlas dashboard, opened in a new tab (never
   iframed — avoids CSP/sandbox conflicts with its inline JS).

## 1 — Architecture

```
Student's browser ── one dynamic page (Firebase Hosting, Atlas design)
   │  GET/POST /api/expand        optional LLM query expansion (D-068; graceful fallback)
   │  GET/POST /api/map          subject map          [ALREADY BUILT: webapi.subject_map]
   │  POST     /api/scan         start a scan job → {job_id}      (idempotent, §3.3)
   │  GET      /api/scan/<id>    job status + rich progress (polled every 3–5 s)
   │  POST     /api/scan/<id>/cancel   safe stop → partial export kept
   │  POST     /api/scan/<id>/resume   continue from the last checkpoint
   │  GET      /api/result/<id>  → 302 to a signed dashboard URL (re-issued on expiry)
   ▼
Firebase Functions 2nd gen (Python) — thin wrappers; all logic in the supervisorly package
   │   job state  ──▶ Firestore (collection "scan_jobs", TTL on docs)
   │   long scans ──▶ Cloud Run Job "supervisorly-scan-worker" (hours allowed)
   ▼
OpenAlex · ROR · (optional) browser-tier sources
```

**Why a worker for scans:** Functions cap at 60 min (2nd gen); a country scan runs longer.
The Function only validates + starts jobs + serves status; the Cloud Run Job executes.

## 2 — Decisions to append (before any code)

- **D-068 — the LLM may generate queries, never claims.** Expansion is optional, fail-closed,
  output strictly validated (≤8 strings, ≤120 chars each, deduped; anything else discarded),
  the key lives server-side only and is never logged or returned, and every downstream fact
  still passes the D-010 quote gate. A wrong expansion yields zero topics, never a fake fact.
- **D-069 — the hosted web product's honesty, privacy, and control model.** (a) Public
  endpoints are read-only and rate-limited — the shared OpenAlex budget is a resource we
  protect, not spend for strangers (§5.2). (b) Job ids are unguessable UUIDv4 and are the
  access token: status readable only by id, never listable. (c) Results are personal data
  (D-005): private bucket, 15-min signed URLs re-issued on request, 7-day auto-delete for
  results AND job docs. (d) The hosted page MAY call the API (a new artifact class vs
  D-048/D-067) but ships no other external resource and no tracking; no personal data is
  ever stored client-side. (e) **The user can always stop safely and continue** — cancel is
  graceful, partial results are kept and exportable, and every terminal state is resumable.

## 3 — The async scan job (the critical design)

### 3.1 Lifecycle
`queued → running → done | failed | cancelled`, plus `cancelling` while the worker drains.
The worker writes results to the bucket FIRST, then flips status — `/api/result` can never
404 on a completed job. On exception: `failed` with an honest, stack-free message; the
partial SQLite DB is kept in the bucket so a resume continues instead of starting over.

### 3.2 Stuck-job watchdog
The worker updates `heartbeat_at` on every progress event. `/api/scan/<id>` treats a job as
stalled (`failed — "worker stalled; safe to resume"`) when the heartbeat is older than
10 min. No job can sit at `running` forever.

### 3.3 Idempotent start (double-click / refresh safe)
The job key is `sha256(email + canonical_plan_json)`. `POST /api/scan` creates the doc in a
Firestore transaction: a non-terminal job with that key returns the EXISTING `job_id`; a
completed/failed/cancelled key starts fresh. Cloud Run Job retries reuse the same job doc.

### 3.4 Safe exit + resume (user- and system-initiated)
- **User cancel:** `POST /api/scan/<id>/cancel` sets `cancel_requested: true`. The worker
  checks the flag between targets (the engine gets a `should_stop()` callback — see §6.4):
  it stops at the next checkpoint, **exports the partial results honestly** (the four-state
  model means whatever is gathered is already a coherent, honest dashboard), writes them to
  the bucket, and marks `cancelled` with a resume hint. A queued-not-started job just flips
  to `cancelled`.
- **Resume:** `POST /api/scan/<id>/resume` (only from `failed`/`cancelled`) re-invokes the
  worker with the SAME job doc; the engine's existing Run/Task/Checkpoint state machine
  (`--resume`) skips completed targets and reuses the warm cache — a resumed job costs a
  fraction of the original. Fresh start remains one click away (new idempotent key via a
  `force_new: true` flag).
- **System stops** (watchdog stall, 6 h runtime cap, worker crash) land in the same
  resumable `failed` state — never a dead end.

### 3.5 Cost guards (server-side caps, all returning honest 4xx)
- One active job per email (429 with retry guidance).
- Plan JSON ≤ 64 KB; field ≤ 200 chars; topics ≤ 25; universities ≤ 50; named targets ≤ 100.
- Scope caps: `max_institutions` 1–300, `shortlist` 1–200 (defaults §4.3) — wide enough for
  serious research, bounded enough to protect budget and runtime.
- Worker runtime cap: 6 h per attempt → resumable `failed ("time cap — resume or narrow the
  scope")`.

### 3.6 Worker environment
SQLite + snapshots live on the worker's ephemeral disk during the run and are copied to the
bucket at the end (DB for resume, dashboard for serving). A mid-run crash restarts discovery
on retry (v1, documented) — it costs time, never correctness.

## 4 — Progress model (the UX centerpiece)

### 4.1 Rich progress events (engine → job doc → page)
The engine emits structured events (§6.4); the worker appends them to the job doc; the page
renders a **determinate progress bar + plain-language line + elapsed timer**:

| Phase event | Page text (plain language) |
|---|---|
| `("expanding",)` | "Understanding your field…" |
| `("map_ready", n)` | "Found N topic areas for you to pick from." |
| `("discovering", country)` | "Finding universities and researchers in {country}…" |
| `("enumerated", n, inst)` | "Found **n researchers across inst institutions** — picking the best matches." |
| `("deep_dive_start", k)` | "Reading the pages of the top k matches…" |
| `("deep_dive_progress", i, k)` | "Reading professor pages — i of k…" |
| `("gap_fill", m)` | "m pages need the slower path — filling what we can…" |
| `("scoring",)` | "Ranking researchers and universities…" |
| `("exported",)` | "Building your dashboard…" |
| `("partial_warning", msg)` | inline amber note under the bar (honest, D-037) |

Bar math: discovery 0–30%, deep-dive 30–90% (i/k), scoring/export 90–100%. Indeterminate
pulse only before the first count arrives. Every event carries `ts` so the page can show
elapsed time and "still working" honesty instead of faked percentages.

### 4.2 Longer-than-expected (the honest slow state)
Per-phase soft expectations (discovery ~2–5 min, deep-dive ~1–2 min per 10 professors). When
a phase exceeds 1.5× its soft expectation, the page shows a calm notice: **"This is taking
longer than usual — the source sites are slow today. You can keep waiting, or pause and
resume later, or cancel and keep what we have."** All three actions are first-class (§3.4).
Never a spinner with no explanation; never a fake "almost done".

### 4.3 Scale controls (student-chosen, within §3.5 caps)
Two sliders/selects on step 4, with a live cost preview:
- **Universities to scan** (`max_institutions`, default 25, cap 300): "top N institutions in
  the country, ranked by relevance" — the ladder enumerates in relevance order and stops at
  N (new engine param, §6.3). Smaller = faster and cheaper; 0/unset = all (with the estimate
  shown before they confirm).
- **Professors to deep-dive** (`shortlist`, default 40, cap 200 — the D-056 gate): "we read
  the pages of the best N matches thoroughly; the rest stay listed, unchecked."
Preview text updates live: "≈ 25 institutions + 40 professors ≈ **15–30 minutes**."
The caps protect the budget; the defaults protect their afternoon; the choice is theirs.

## 5 — Endpoints + safety model (all: CORS preflight, JSON, stack-free errors)

| Endpoint | Behavior |
|---|---|
| `GET/POST /api/expand` | variants; **cached by normalized field** (Firestore, 30-day TTL); model/base_url from server config ONLY (never client-overridable, D-068) |
| `GET/POST /api/map` | already built; + per-variant `found_by` once multi-query lands |
| `POST /api/scan` | CLI's `_load_plan` validation + §3.5 caps; idempotent (§3.3) → `{job_id}` |
| `GET /api/scan/<id>` | `{status, phase, counts, elapsed, heartbeat_age, warnings[]}` — counts only until `done` (no premature coverage claims) |
| `POST /api/scan/<id>/cancel` | §3.4 → `{status: "cancelling"}` (idempotent) |
| `POST /api/scan/<id>/resume` | §3.4 → `{status: "queued"}`; `force_new: true` starts over with a fresh key |
| `GET /api/result/<id>` | 302 → fresh 15-min signed URL (safe to re-poll after expiry) |

### 5.1 Cold starts (honest note)
Cold starts take 10–30 s. The page shows "warming up…" with a 45 s client timeout + one
retry. Optional `min-instances=1` on the two hot endpoints is a documented toggle, off by
default.

### 5.2 Budget protection (we hit OpenAlex's daily 429 ourselves — this matters)
- Per-client-IP throttle: `/api/map` ≤ 30/h, `/api/expand` ≤ 10/h, `/api/scan` ≤ 5/h
  (Firestore counters, fixed-window; 429 with a plain message).
- Optional **Firebase App Check** (`<APP_CHECK_SITE_KEY>` placeholder) once public; off in
  development.
- When OpenAlex itself 429s: `503 {"error": "source budget exhausted — resets midnight UTC
  (OpenAlex free tier)"}` mapped from the engine's truncation marker, never a fake empty.

### 5.3 The safety matrix (what protects whom — consolidated)

| Threat | Mechanism |
|---|---|
| Budget abuse by strangers | per-IP throttles, App Check, one active job/email, caps (§3.5) |
| Runaway scan | shortlist gate (D-056), `max_institutions`, 6 h cap, cancel |
| Stuck forever | heartbeat watchdog (§3.2), every terminal state resumable |
| Duplicate work | idempotent job key (§3.3), warm-cache resume |
| Lost work on exit/crash | checkpoint state machine, partial export on cancel, DB in bucket |
| Fabricated facts | D-010 quote gate everywhere; LLM only ever writes queries (D-068) |
| Personal-data leak (D-005) | private bucket, signed URLs, 7-day TTL on results + job docs, no client-side storage of plan/email, job id unguessable |
| Silent failure | honest 4xx/5xx with plain messages; PARTIAL markers; §4.2 slow-state |
| Expansion misuse | validated output, server-only model, per-field cache, key never returned |

## 6 — Engine/repo work items (fully specified)

| # | Piece | File | Spec |
|---|-------|------|------|
| 1 | D-068 + D-069 | `docs/DECISIONS.md` | as §2 |
| 2 | Query expansion | `src/supervisorly/discover/expand.py` | OpenAI-compatible JSON-mode call; validated output (§2); fail-closed `[]`; defaults `base_url=https://api.kimi.com/coding/v1`, `model=kimi-for-coding`; key from `SUPERVISORLY_EXPAND_KEY` |
| 3 | Multi-query map + institution cap | `discover/subjects.py`, `discover/ladder.py` | `subject_map_multi(queries, …)` (merge, rank, `found_by`, clusters preserved); ladder gains `max_institutions` (relevance-ordered enumeration stops at N; honest warning when capped, D-037) |
| 4 | Progress + cancellation | `pipeline.py` | `run_live(..., progress=None, should_stop=None)`: the §4.1 event stream (counts + phase + ts), and between targets it consults `should_stop()` → on True it stops cleanly, exports partials, and reports `cancelled`; CLI gains `--progress` and keeps Ctrl+C safety |
| 5 | Job runner | `src/supervisorly/jobs.py` | storage-agnostic `run_scan_job(plan, hooks)`; maps engine events → job doc; cancel-flag wiring; result-first-then-status; exceptions → resumable `failed` |
| 6 | Endpoints | `src/supervisorly/webapi.py` | §5 table + local dev server with threaded worker + JSON job store (local parity: heartbeat, idempotent key, cancel/resume, TTL) |
| 7 | Firebase | `firebase/main.py`, `firebase/worker.py` | wrappers + worker entrypoint; requirements add `google-cloud-firestore`, `google-cloud-run`, `google-cloud-storage`; pin `supervisorly @ git+…@<RELEASE_TAG>` |
| 8 | The page | `src/supervisorly/export/webapp.py` → `webapp.html` | §0/§4/§5 wizard incl. progress bar + phase text, scale sliders + cost preview, cancel/resume buttons, slow-state notice |

## 7 — Implementation steps in order (each leaves the suite green)

1. D-068 + D-069 + `expand.py` + tests (fail-closed, validation, timeout, no key leakage).
2. `subject_map_multi` + ladder `max_institutions` + tests (merge/rank/`found_by`, cap honesty).
3. Progress events + `should_stop` + CLI `--progress` + tests (event order, partial export on
   stop, CLI unchanged by default).
4. `jobs.py` + all endpoints + local worker + tests (start→status→cancel→resume→result
   round-trip on cassettes; idempotent start; watchdog flip; result-before-status).
5. `webapp.py` + tests (every §4/§5 state incl. progress phases, slow-state, cancel/resume
   buttons, slider cost preview; injection-safe; reduced-motion; keyboard).
6. Firebase wrappers + worker + requirements; local run with
   `firebase emulators:start --only functions,firestore`.
7. Deploy files: `firebase.json` (hosting + functions + `/api/**` rewrites), `.firebaserc`,
   Firestore rules (write: functions only; read: by id only, no list), Storage rules
   (private), bucket + Firestore TTL (7 days), Cloud Run Job definition, IAM
   (`run.jobs.run` for the Functions service account).
8. Verification round: full suite; headless-Chrome click-through of the whole page (the
   atlas.html harness pattern) including a cancel+resume pass; adversarial audit of the new
   surface (endpoint injection, job privacy, throttle bypass, cancel races); clean-room.

## 8 — Placeholders (the ONLY things you fill in later)

| Placeholder | Where | What |
|---|---|---|
| `<FIREBASE_PROJECT_ID>` | `.firebaserc`, deploy commands | your Firebase project id |
| `<FIREBASE_WEB_API_KEY>` etc. | `webapp.html` config block (public-safe by design) | Firebase console → project settings |
| `<API_BASE_URL>` | `webapp.html` deploy step | Functions base URL after first deploy |
| `<RESULTS_BUCKET>` | `firebase/main.py`, worker, storage rules | private bucket for dashboards + job DBs |
| `<REGION>` | deploy commands | e.g. `us-central1` |
| `<RELEASE_TAG>` | `firebase/requirements.txt` | a git tag (e.g. `web-v1`) — branches float, tags don't |
| `<APP_CHECK_SITE_KEY>` | `webapp.html` (optional, §5.2) | reCAPTCHA/App Check when public |
| `SUPERVISORLY_CONTACT_EMAIL` | Functions secret | your email (OpenAlex polite pool) |
| `SUPERVISORLY_OPENALEX_KEY` | Functions secret (optional) | premium key — raises the daily budget that 429'd us |
| `SUPERVISORLY_EXPAND_KEY` | Functions secret (optional, fail-closed) | Kimi Code API key for D-068 expansion |

## 9 — Optional "lite" fallback (no worker, no Firestore, no Cloud Run)

Host only `/api/expand` + `/api/map` + the page; step 4 exports `supervisorly_plan.json` and
the student runs the scan locally (current CLI flow, which still gets `--progress` and
Ctrl+C-safe resume from step 3). Steps 1–5 apply unchanged; 7–8 shrink to hosting + two
functions + App Check. Zero recurring job cost; the live progress + cancel/resume view
arrives when the worker lands.

## 10 — Explicitly out of scope (unchanged)

- The agent flow (SKILL.md) — untouched, still the power-user path.
- The browser tier (Chrome MCP) — stays agent-side; the hosted page does not drive browsers.
- The deterministic engine's contracts (D-009/010/046) — expansion touches queries, never facts.
