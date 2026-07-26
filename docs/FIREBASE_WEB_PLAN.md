# Supervisorly Web — full implementation plan (one dynamic page + Firebase)

> Status: **plan only — nothing here is implemented yet** (v2, hardened after an edge-case
> review). Everything is specified so that the ONLY remaining manual steps are inserting API
> keys / server config at the marked placeholders (`<LIKE_THIS>`). Binding constraints from
> `docs/DECISIONS.md` apply (D-005/009/010/035/037/038/046 + D-068/D-069 defined below).

## 0 — What the student sees (the product flow)

One dynamic page (Atlas design language), five steps, no CLI, no agent required:

1. **You** — contact email, intent (pre-PhD / pre-master / master / PhD / postdoc / mentor),
   country (name or ISO), optional universities + mode (all / prioritise / only).
2. **Field** — free text ("NLP", "mechanistic interpretability", "causal ML") → *Understand*:
   the backend expands the phrasing (acronyms/typos/synonyms) and returns the subject map as
   **meaning clusters** (domain → field → subfield → topics).
3. **Disambiguate** — the student checks the topics/meanings they want (tri-state checkbox
   tree — the existing Scan Studio component). This step IS the answer to "NLP means different
   things to different people": the tool presents senses, never guesses (D-066).
4. **Scan** — live progress (enumerated N → deep-diving k/40 → scoring → export), PARTIAL
   warnings inline. Runs server-side as an async job (§3).
5. **Dashboard** — the existing self-contained Atlas dashboard, opened in a new tab (never
   iframed — avoids CSP/sandbox conflicts with its inline JS).

## 1 — Architecture

```
Student's browser ── one dynamic page (Firebase Hosting, Atlas design)
   │  GET/POST /api/expand      optional LLM query expansion (D-068; graceful fallback)
   │  GET/POST /api/map         subject map          [ALREADY BUILT: webapi.subject_map]
   │  POST     /api/scan        start a scan job → {job_id}      (idempotent, §3.3)
   │  GET      /api/scan/<id>   job status + progress (polled every 3–5 s)
   │  GET      /api/result/<id> → 302 to a signed dashboard URL (re-issued on expiry)
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
- **D-069 — the hosted web product's honesty and privacy model.** (a) Public endpoints are
  read-only and rate-limited — the shared OpenAlex budget is a resource we protect, not spend
  for strangers (§4.2). (b) Job ids are unguessable UUIDv4 and are the access token: status
  readable only by id, never listable. (c) Results are personal data (D-005): private bucket,
  15-min signed URLs re-issued on request, 7-day auto-delete for results AND job docs. (d) The
  hosted page is a new artifact class — unlike the dashboard/Studio (D-048/D-067) it MAY call
  the API; it still ships no other external resource and no tracking.

## 3 — The async scan job (the critical design)

### 3.1 Lifecycle
`queued → running → done | failed`. The worker writes results to the bucket FIRST, then flips
status to `done` — `/api/result` can never 404 on a completed job. On exception the worker
writes `failed` with an honest, stack-free message; the partial SQLite DB is kept in the
bucket so a retry can `--resume` instead of starting over.

### 3.2 Stuck-job watchdog
The worker updates a `heartbeat_at` timestamp every progress event. `/api/scan/<id>` treats a
job as `failed ("worker stalled — no heartbeat for 10 min; safe to retry")` when the heartbeat
is older than 10 min. No job can sit at `running` forever.

### 3.3 Idempotent start (double-click / refresh safe)
The job key is `sha256(email + canonical_plan_json)`. `POST /api/scan` creates the doc in a
Firestore transaction: if a non-terminal job with that key exists, it returns the EXISTING
`job_id` (never a duplicate run); a completed/failed key starts fresh. Cloud Run Job retries
reuse the same job doc (attempt counter, not a new job).

### 3.4 Cost guards (server-side caps, all returning honest 4xx)
- One active job per email (429 with retry guidance).
- `max_results ≤ 100`, topics ≤ 25, universities ≤ 50, named targets ≤ 100,
  `--shortlist ≤ 100` (default 40 — the D-056 gate already caps the expensive phase).
- Plan JSON ≤ 64 KB; field ≤ 200 chars.
- Worker runtime cap: 6 h per attempt, then `failed ("time cap — narrow the scope")`.

### 3.5 Worker environment
The engine's SQLite + snapshots live on the worker's ephemeral disk during the run and are
copied to the bucket at the end (DB for `--resume`, dashboard for serving). A mid-run crash
restarts discovery on retry (v1, documented) — extraction cache does not survive, which costs
time but never correctness.

## 4 — Endpoints (all: CORS preflight, JSON, stack-free errors)

| Endpoint | Behavior |
|---|---|
| `GET/POST /api/expand` | `{"variants": [...], "expanded": bool, "note"}`; **cached by normalized field string** (Firestore, 30-day TTL) so repeat expansions cost nothing; request params are an allowlist — the model/base_url come from server config ONLY (never client-overridable, D-068) |
| `GET/POST /api/map` | already built (`webapi.subject_map`); + per-variant `found_by` once multi-query lands |
| `POST /api/scan` | validates via the CLI's `_load_plan` rules + §3.4 caps; idempotent start (§3.3) → `{job_id}` |
| `GET /api/scan/<id>` | `{status, progress: [...], heartbeat age, message}` — counts only until `done` (no premature coverage claims) |
| `GET /api/result/<id>` | 302 → fresh 15-min signed URL (safe to re-poll after expiry) |

### 4.1 Cold starts (honest note)
The Function installs `supervisorly` from git at deploy time, but cold starts still take
10–30 s. The page shows an explicit "warming up…" state with a 45 s client timeout + one
retry. Optional `min-instances=1` on the two hot endpoints (small steady cost) is a
documented toggle, not a default.

### 4.2 Budget protection (we hit OpenAlex's daily 429 ourselves — this matters)
- Per-client-IP throttle: `/api/map` ≤ 30/h, `/api/expand` ≤ 10/h (Firestore counters,
  fixed-window; 429 with a plain message).
- Optional **Firebase App Check** (`<APP_CHECK_SITE_KEY>` placeholder) as the stronger
  anti-abuse layer — recommended once public, off during development.
- When OpenAlex itself 429s, endpoints return `503 {"error": "source budget exhausted —
  resets midnight UTC (OpenAlex free tier)"}` mapped from the engine's truncation marker,
  never a fake empty map.

## 5 — The dynamic page (webapp)

Extends the Studio's Atlas shell into the 5-step wizard. Edge cases it MUST render honestly
(each has a test):

- **Cold start / slow backend** — spinner + "warming up" copy, 45 s timeout, one retry, then
  an actionable error (not a dead button).
- **OpenAlex 429** (midnight-UTC reset message), **backend 500** (generic, no internals),
  **offline** (`navigator.onLine` + fetch failure → "check your connection", state preserved
  in memory so nothing typed is lost).
- **Expansion unavailable** (no `SUPERVISORLY_EXPAND_KEY`) — the *Understand* step silently
  uses the deterministic path; a small note says smart expansion is off, never an error.
- **Ambiguous query** — meaning clusters render as separate, labeled groups; nothing is
  pre-checked except nothing (the user disambiguates, always — D-066).
- **Back/forward between steps** — in-memory state only; **no personal data in localStorage
  or cookies** (email/plan never persisted client-side, D-005/D-069).
- **Double-click on Start** — button disables immediately; idempotent backend (§3.3) is the
  backstop.
- **Polling resilience** — poll stops on terminal status; a stalled poll (>2 min of errors)
  shows "lost contact with the job — your job id is …, come back to this URL" (the job id IS
  the recovery token; the page offers to re-query by id).
- Keyboard + focus order across steps, `prefers-reduced-motion`, Escape closes transient UI —
  same bar as Studio/dashboard.

## 6 — Engine/repo work items (fully specified)

| # | Piece | File | Spec |
|---|-------|------|------|
| 1 | D-068 + D-069 | `docs/DECISIONS.md` | as §2 |
| 2 | Query expansion | `src/supervisorly/discover/expand.py` | OpenAI-compatible JSON-mode call; validated output (§2); fail-closed `[]`; defaults `base_url=https://api.kimi.com/coding/v1`, `model=kimi-for-coding`; key from `SUPERVISORLY_EXPAND_KEY` |
| 3 | Multi-query map | `discover/subjects.py` | `subject_map_multi(queries, …)`: merge by topic id, rank by best per-variant score, tag `found_by` (capped list), meaning clusters preserved, per-variant + total caps (§3.4) |
| 4 | Progress events | `pipeline.py` | `run_live(..., progress=None)`: `("enumerated",n)` → `("deep_dive_start",k)` → `("deep_dive_progress",i,k)` → `("scoring",)` → `("exported",)`; CLI gains `--progress` (one ASCII line per event); default behavior unchanged |
| 5 | Job runner | `src/supervisorly/jobs.py` | storage-agnostic `run_scan_job(plan, hooks)`; exceptions → terminal honest `failed`; events → `hooks.on_event(dict)`; result-first-then-status ordering (§3.1) |
| 6 | Endpoints | `src/supervisorly/webapi.py` | `handle_expand`, `handle_scan_start`, `handle_scan_status`, `handle_scan_result` + local dev server with a threaded worker + JSON job store (local parity for Firestore semantics: heartbeat, idempotent key, TTL) |
| 7 | Firebase | `firebase/main.py`, `firebase/worker.py` | wrappers + Cloud Run Job entrypoint; `requirements.txt` adds `google-cloud-firestore`, `google-cloud-run`, `google-cloud-storage` and pins `supervisorly @ git+…@<RELEASE_TAG>` (never a floating branch — see §8) |
| 8 | The page | `src/supervisorly/export/webapp.py` → `webapp.html` | §5; `<API_BASE_URL>` injected at deploy |

## 7 — Implementation steps in order (each leaves the suite green)

1. D-068 + D-069 + `expand.py` + tests (fail-closed, validation, timeout, no key leakage).
2. `subject_map_multi` + tests (merge/rank/`found_by`, caps, clusters preserved).
3. Progress events + CLI `--progress` + tests (event order; CLI unchanged by default).
4. `jobs.py` + the four endpoints + local worker + tests (start→status→result round-trip on
   cassettes; idempotent start; watchdog stale-heartbeat flip; result-before-status).
5. `webapp.py` + tests (every §5 state, injection-safe, Atlas self-containment except the API
   base URL, reduced-motion, keyboard).
6. Firebase wrappers + worker + requirements; run locally with
   `firebase emulators:start --only functions,firestore`.
7. Deploy files: `firebase.json` (hosting + functions + `/api/**` rewrites), `.firebaserc`,
   Firestore rules (write: functions only; read: by document id only, no list), Storage rules
   (private), bucket + Firestore TTL (7 days), Cloud Run Job definition (§3),
   IAM: the Functions service account needs `run.jobs.run` on the worker job.
8. Verification round: full suite; headless-Chrome click-through of the page against the
   local server (the atlas.html harness pattern); adversarial audit of the new surface
   (endpoint injection, job-state privacy, expansion output handling, throttle bypass);
   clean-room.

## 8 — Placeholders (the ONLY things you fill in later)

| Placeholder | Where | What |
|---|---|---|
| `<FIREBASE_PROJECT_ID>` | `.firebaserc`, deploy commands | your Firebase project id |
| `<FIREBASE_WEB_API_KEY>` etc. | `webapp.html` config block (public-safe by design) | Firebase console → project settings |
| `<API_BASE_URL>` | `webapp.html` deploy step | Functions base URL after first deploy |
| `<RESULTS_BUCKET>` | `firebase/main.py`, worker, storage rules | private bucket for dashboards + job DBs |
| `<REGION>` | deploy commands | e.g. `us-central1` |
| `<RELEASE_TAG>` | `firebase/requirements.txt` | a git tag (e.g. `web-v1`) so deploys are reproducible — branches float, tags don't |
| `<APP_CHECK_SITE_KEY>` | `webapp.html` (optional, §4.2) | reCAPTCHA/App Check when public |
| `SUPERVISORLY_CONTACT_EMAIL` | Functions secret | your email (OpenAlex polite pool) |
| `SUPERVISORLY_OPENALEX_KEY` | Functions secret (optional) | premium key — raises the daily budget that 429'd us |
| `SUPERVISORLY_EXPAND_KEY` | Functions secret (optional, fail-closed) | Kimi Code API key for D-068 expansion |

## 9 — Optional "lite" fallback (no worker, no Firestore, no Cloud Run)

Host only `/api/expand` + `/api/map` + the page; step 4 exports `supervisorly_plan.json` and
the student runs the scan locally (current CLI flow). Steps 1–5 apply unchanged; 7–8 shrink
to hosting + two functions + App Check. Zero recurring job cost; the live-progress view
arrives later when the worker lands.

## 10 — Explicitly out of scope (unchanged)

- The agent flow (SKILL.md) — untouched, still the power-user path.
- The browser tier (Chrome MCP) — stays agent-side; the hosted page does not drive browsers.
- The deterministic engine's contracts (D-009/010/046) — expansion touches queries, never facts.
