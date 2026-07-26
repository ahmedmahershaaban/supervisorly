# Supervisorly Web — full implementation plan (one dynamic page + Firebase)

> Status: **plan only — nothing here is implemented yet.** Everything is specified so that the
> ONLY remaining manual steps are inserting API keys / server config at the marked placeholders
> (`<LIKE_THIS>`). Binding constraints from `docs/DECISIONS.md` apply (D-005/009/010/035/037/
> 038/046 + the new D-068 defined in §2).

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
4. **Scan** — live progress bar (enumerated N → deep-diving k/40 → scoring → export), PARTIAL
   warnings surfaced inline. Runs server-side as an async job (see §3 — never a silent 2-hour
   terminal again).
5. **Dashboard** — the existing self-contained Atlas dashboard, served as the result.

## 1 — Architecture

```
Student's browser ── one dynamic page (Firebase Hosting, Atlas design)
   │  GET/POST /api/expand      optional LLM query expansion (D-068; graceful fallback)
   │  GET/POST /api/map         subject map          [ALREADY BUILT: webapi.subject_map]
   │  POST     /api/scan        start a scan job → {job_id}
   │  GET      /api/scan/<id>   job status + progress (polled every 3–5 s)
   │  GET      /api/result/<id> dashboard.html (+ .json)
   ▼
Firebase Functions (Python) — thin wrappers; all logic in the supervisorly package
   │   writes/reads job state ──▶ Firestore (collection "scan_jobs")
   │   long scans             ──▶ Cloud Run Job "supervisorly-scan-worker" (no timeout)
   ▼
OpenAlex · ROR · (optional) browser-tier sources
```

**Why a worker for scans:** Firebase Functions cap at 60 s default (configurable to 60 min on
2nd gen). A country scan takes minutes to hours. Scans therefore run as **Cloud Run Jobs**
(hours allowed); the Function only starts jobs and reports status. A "lite" alternative —
host only expand+map+plan and run the scan locally — is Phase 6 (optional fallback).

## 2 — New/changed engine pieces (repo work, fully specified)

| # | Piece | File | Spec |
|---|-------|------|------|
| 1 | **D-068 decision** | `docs/DECISIONS.md` | "The LLM may generate *queries*, never *claims*": expansion is optional, fail-closed, validated output (a short list of strings), and every downstream fact still passes the D-010 quote gate. Appended after D-067. |
| 2 | **Query expansion module** | `src/supervisorly/discover/expand.py` | `expand_query(field, *, base_url, api_key, model, timeout) -> list[str]`. OpenAI-compatible chat call (JSON-mode prompt: "return up to 6 English query variants: canonical, acronym-expanded, synonyms, broader/narrower"). Output validated: list of ≤8 strings, each ≤120 chars, else discarded. **Fail-closed**: no key / error / timeout → `[]` (caller proceeds with the raw query + a note). Default `base_url=https://api.kimi.com/coding/v1`, `model=kimi-for-coding`; key from `SUPERVISORLY_EXPAND_KEY` or param. |
| 3 | **Multi-query subject map** | `discover/subjects.py` | `subject_map_multi(queries, ...)`: runs existing `subject_map` per variant, merges by topic id, ranks by best per-variant score, marks each topic with the variants that found it (`found_by`). Preserves meaning clusters (grouping unchanged — ambiguity surfaces as separate clusters, not merged soup). |
| 4 | **Progress events** | `pipeline.py` | `run_live(..., progress: callable | None = None)` — called at phase transitions: `("enumerated", n)`, `("deep_dive_start", k)`, `("deep_dive_progress", i, k)`, `("scoring",)`, `("exported", path)`. Default `None` = today's behavior (CLI unchanged; CLI also gains a `--progress` flag printing one line per event, ASCII-safe). |
| 5 | **Job runner** | `src/supervisorly/jobs.py` | `run_scan_job(plan, hooks) -> result`: wraps `run_live`, maps progress events onto a `hooks.on_event(dict)` callback, catches exceptions into a terminal `"failed"` state with an honest message. Storage-agnostic: Firestore hook impl lives in `firebase/`, local JSON-file hook in `webapi.py`. |
| 6 | **Endpoints** | `src/supervisorly/webapi.py` | Add `handle_expand(params)` (uses expand.py; returns `{"variants": [...], "expanded": bool, "note"}`), `handle_scan_start(params)` → validates plan, creates job, returns `{"job_id"}`, `handle_scan_status(job_id)` → `{"status", "progress": [...], "coverage_so_far"}`, `handle_scan_result(job_id)` → dashboard HTML. Local dev server routes them (worker runs in a background thread locally). |
| 7 | **Firebase wrappers** | `firebase/main.py` | Add `expand`, `scan_start`, `scan_status`, `scan_result` functions alongside `subject_map`. `firebase/worker.py` = the Cloud Run Job entrypoint (reads job doc → runs `run_scan_job` → writes progress + result). `firebase/requirements.txt` unchanged (package from git). |
| 8 | **The dynamic page** | `src/supervisorly/export/webapp.py` (new, generates `webapp.html`) | Extends the Studio's Atlas shell into the 5-step wizard: step navigation, fetch calls with try/catch + honest error states, meaning-cluster tree (reuses Studio's tri-state logic), progress view (polled, with phase labels + PARTIAL notes), result view (iframe/link to the dashboard). Works against localhost for dev and the hosted base URL in prod (`<API_BASE_URL>` injected at build/deploy time). |

## 3 — The async scan job (the critical design)

- `POST /api/scan` → validates the plan (same `_load_plan` rules as the CLI), creates
  `scan_jobs/<uuid>` in Firestore `{status: "queued", plan, created_at}` and **invokes the
  Cloud Run Job** (REST call with the job id) → returns `{job_id}` immediately.
- The worker (`firebase/worker.py`) updates the doc: `{status: "running", progress: [...]}`,
  then `{status: "done", result_path}` or `{status: "failed", error}`.
- Results land in **Cloud Storage** (`<RESULTS_BUCKET>/<job_id>/dashboard.html` + `.json`);
  `/api/result/<id>` redirects to a signed URL (15-min expiry).
- `GET /api/scan/<id>` reads the doc — the page polls it every 3–5 s.
- **D-005/ethics:** results contain personal data → bucket is private, signed URLs only,
  lifecycle rule deletes results after **7 days**, job docs hold no page content (status only).
- **Cost guard:** one active job per email address (429 with an honest message otherwise);
  shortlist defaults to 40 (the D-056 gate already caps the expensive phase).

## 4 — Placeholders (the ONLY things you fill in later)

| Placeholder | Where | What |
|---|---|---|
| `<FIREBASE_PROJECT_ID>` | `firebase.json`, `.firebaserc`, deploy commands | your Firebase project id |
| `<FIREBASE_WEB_API_KEY>` etc. | `webapp.html` config block (page is public-safe — Firebase web keys identify, not authorize) | from Firebase console → project settings |
| `<API_BASE_URL>` | `webapp.html` deploy step | the Functions base URL after first deploy |
| `<RESULTS_BUCKET>` | `firebase/main.py`, worker, storage rules | Cloud Storage bucket for dashboards |
| `<REGION>` | deploy commands | e.g. `us-central1` |
| `SUPERVISORLY_CONTACT_EMAIL` | Functions secret (`firebase functions:secrets:set`) | your email (OpenAlex polite pool) |
| `SUPERVISORLY_OPENALEX_KEY` | Functions secret (optional) | premium key if you buy one (raises the daily budget that hit 429 today) |
| `SUPERVISORLY_EXPAND_KEY` | Functions secret (optional — expansion is fail-closed) | Kimi Code API key for the LLM expansion endpoint (D-068) |

No other secrets exist: ROR is keyless, OpenAlex works with just the email, and the page
itself holds no credentials beyond the public Firebase web config.

## 5 — Implementation steps in order (each leaves the suite green)

1. **D-068 + `expand.py` + tests** (fail-closed paths, output validation, timeout).
2. **`subject_map_multi` + tests** (merge/rank/found_by, meaning clusters preserved).
3. **Progress events in `run_live` + CLI `--progress` + tests** (event order, CLI unchanged by default).
4. **`jobs.py` + webapi endpoints + local threaded worker + tests** (start → status → result round-trip on cassettes).
5. **`webapp.py` wizard page + tests** (Atlas self-containment except API calls, injection-safe, reduced-motion, keyboard; graceful degradation when expand is unavailable).
6. **Firebase wrappers + worker + requirements**; local Functions emulator run (`firebase emulators:start --only functions`).
7. **Deploy files**: `firebase.json` (hosting + functions + `/api/**` rewrites), `.firebaserc`, Firestore rules (job docs: functions-only write, read by job id), Storage rules (private), bucket lifecycle rule (7-day delete).
8. **Verification round**: full suite, headless-Chrome click-through of the page against the local server (the harness pattern already used for atlas.html), adversarial audit of the new surface (injection, job-state privacy, expansion output handling), clean-room.

## 6 — Optional "lite" fallback (no worker, no Firestore)

Host only `/api/expand` + `/api/map` + the page; step 4 exports `supervisorly_plan.json` and
the student runs the scan locally (current CLI flow). All Phases 1–5 apply; 7–8 shrink to
hosting + two functions. Choose this if you want zero Cloud Run/Firestore cost on day one.

## 7 — Explicitly out of scope (unchanged)

- The agent flow (SKILL.md) — untouched, still the power-user path.
- The browser tier (Chrome MCP) — stays agent-side; the hosted page does not drive browsers.
- The deterministic engine's contracts (D-009/010/046) — expansion touches queries, never facts.
