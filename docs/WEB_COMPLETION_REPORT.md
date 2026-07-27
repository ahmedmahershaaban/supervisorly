# Supervisorly — Goal 4 Completion Report (the hosted web product)

Branch `build/web`. Commit range `24de2bf..ace785d` (the web build begins after the last
Goal 3 commit on `build/browser`); the verification round is `bcc370d`, `3308b90`,
`ab8bac2`, `ace785d` plus the clean-verified commit that carries this report.

Plan of record: `docs/FIREBASE_WEB_PLAN.md` (§7 is the 8-step build order). There is no
`WEB_IMPLEMENTATION_GOAL.md`; the plan plays that role, and the completion contract is the
one in `docs/IMPLEMENTATION_GOAL.md` §5–§8.

**Status: steps 1–8 complete, and DEPLOYED — live at https://supervisorly.web.app,
verified end to end against real GCP (§4b). Suite green at 569.**

> This line previously read *"NOT DEPLOYED — see §6"*, and §6 called the untested cloud
> surface "the single biggest untested surface, and no test in this repo can close it."
> That prediction was exactly right: the first real deploy produced **seven** defects that
> 566 passing offline tests could not have caught. They are catalogued in §4b, which is the
> most useful section of this report.

---

## 1 — What was built (phase by phase)

| Step | What | Commit |
|---|---|---|
| 1 | **D-068** (the LLM may generate queries, never claims) + **D-069** (hosted product: honesty, privacy, user control) locked before code; `discover/expand.py`, fail-closed — no key means the student's own words, never an error and never a leaked key | `9688d72`, `e8d1b91` |
| 2 | `subject_map_multi` + ladder `max_institutions` (honest "capped at N of M", never a silent truncation) | `e8d1b91` |
| 3 | Rich progress events + a `should_stop` hook in `run_live`, persisted in SQLite; CLI `--progress`. Default CLI behaviour unchanged | `4b4068b` |
| 4 | `jobs.py` — lifecycle `queued → running → done\|failed\|cancelled`, §3.3 idempotency key, §3.2 stall watchdog, lock-guarded `JsonJobStore` — plus every scan endpoint and a local threaded worker, so the whole flow runs offline on cassettes | `125d6cc` |
| 5 | `export/webapp.py` — the 5-step Atlas wizard as one self-contained page (you → field → topics → scope → progress) | `7ef3b21` |
| 6 | `firebase/_core.py` (Firestore job store mirroring `jobs.py` one-for-one, per-IP throttles, expansion cache, Cloud Run bridge, signed URLs), `main.py` wrappers, `worker.py`. Every `google.cloud.*` import is lazy, so the module loads with no SDKs installed | `744c016` |
| 7 | Deploy artifacts: `firebase.json`, `.firebaserc`, `firestore.rules`, `storage.rules`, `lifecycle.json` (7-day TTL), `Dockerfile.worker`, and an 8-step `firebase/README.md` runbook incl. the `roles/run.invoker` IAM binding | `744c016` |
| 8 | This verification round | `bcc370d`…`ace785d` |

---

## 2 — Adversarial audit (plan §7 step 8; contract §5)

Audit surface named by the plan: **endpoint injection, job privacy, throttle bypass,
cancel races**. All four dimensions produced real defects — **8 confirmed (4 HIGH, 3
MEDIUM, 1 LOW)**, every one reproduced in code before fixing and every one closed with a
regression test.

### HIGH

- **F1 — the throttle key was caller-supplied.** `main._ip` took the *leftmost*
  `X-Forwarded-For` entry. GCP **appends** `<client>, <lb>` to the header it receives
  rather than replacing it, so that entry is whatever the caller sent: a fresh
  `X-Forwarded-For` per request gave every quota an unlimited budget. This defeats the
  §5.2 protection that exists *because OpenAlex's daily limit already 429'd this project
  once.* Now keyed on the entry the front end wrote (second from last), then the socket
  peer.
- **F2 — the job endpoints were unthrottled entirely.** `/api/scan/<id>/resume`
  re-invokes the Cloud Run Job and had no cap, so cancel→resume in a loop bought
  unlimited worker executions and walked straight around the 5/h scan limit. Buckets are
  now sized by real cost: resume 5/h (its own bucket, so it is never blocked by unrelated
  scan starts), cancel 60/h, result 120/h, status 3000/h — deliberately far above the
  page's 4 s poll (~900/h for one tab) so it cannot bite an honest user. A test ties the
  status cap to the page's real `POLL_MS` so the two cannot drift apart.
- **F3 — the Firestore rule handed out more than the endpoint it mirrored.**
  `allow get: if true` returned the **whole** job document — `email`, `email_ci`, the full
  `plan` — to anyone holding a job id, while `handle_scan_status` returns only
  status/progress. The page never touches Firestore (only `/api/**`, asserted by test), so
  the rule is now `if false` and the job id remains a token for our filtering endpoint.
- **F4 — a cancel race lost the user's cancel.** `FirestoreJobStore.set_status` was a
  full-document read-modify-write **outside any transaction**. A concurrent
  `request_cancel` was silently reverted — the student saw "cancelling", the flag went
  back to `False`, and the worker ran on — and concurrently appended progress events were
  dropped from the live log. Now transactional, restoring parity with `JsonJobStore`,
  which was always lock-guarded.

### MEDIUM / LOW

- **F5 (MED)** — CSRF: the named Functions wrappers ran their handler on **any** method;
  `_params` reads the query string on GET and `_job_id` falls back to `?id=`, so
  `GET /scan_cancel?id=<job id>` cancelled a scan from a third-party `<img>` tag. Every
  wrapper now enforces its method (405).
- **F6 (MED)** — the legacy `subject_map` alias called `handle_subject_map` directly: the
  one subject-map route with no throttle, leaving the 30/h cap a rename away from bypass.
- **F7 (MED)** — `webapi.route_request` matched `/api/map` on path alone, so
  `DELETE`/`PUT`/`PATCH` reached the handler.
- **F8 (LOW)** — `esc()` left `'` unescaped while the page mixes single- and
  double-quoted attribute markup: a latent XSS, closed before it became reachable.

### The reason two of these survived until now

Everything in `firebase/main.py` lives behind `if https_fn is not None:`, and the
Functions SDK is not installed in the suite — so **not one wrapper was reachable by any
test**. F5 and F6 both live in that gap. Wave 1 stubs the SDK the same way the google
clients are already stubbed, making the whole layer testable offline.

**Test-count progression:** 534 (`744c016`) → **556** (wave 1) → **565** (wave 2) →
**566** (wave 3). Audit closed with **zero open findings**.

---

## 3 — Test inventory

`python -m pytest` → **566 passed**, 0 failed, 0 skipped, ~66 s.

Added by this round (+32):

| File | Added | Covers |
|---|---|---|
| `tests/test_firebase_wrappers.py` | +20 | client-IP identity vs. spoofed XFF; method enforcement on all 7 wrappers (parametrised); the alias's throttled path; the `set_status`/`request_cancel` race and the progress-clobber twin; per-endpoint throttle buckets; the status cap vs. the page's poll rate; the Firestore rules; that the page never uses Firestore |
| `tests/test_webapp_clickthrough.py` | +10 | the whole-page click-through (below) |
| `tests/test_webapi.py` | +1 | `/api/map` method enforcement |
| `tests/test_webapp.py` | +1 | `esc()` and the single quote |

### The click-through (plan step 8)

Step 8 asks for a "headless-Chrome click-through of the whole page (the atlas.html harness
pattern)". Two facts had to be settled first, and both are stated plainly because they
change what the deliverable is:

1. **There is no real-Chrome harness in this repo.** B7's "system Chrome + mermaid-cli"
   check was a manual, uncommitted step; `docs/atlas.html` has no generator or validator.
2. The pattern step 8 names is therefore the **Node `vm` + mini-DOM harness** in
   `tests/test_studio.py`, which is what this extends — rather than adding a browser
   dependency the suite never had, which would `pytest.skip` wherever Chrome is absent and
   so prove nothing in CI.

What runs is the page's **own, unmodified JavaScript**, driven through the listeners it
wires itself: `DOMContentLoaded` → step 1 → *Understand* (one `/api/expand`, then one
`/api/map` per phrasing) → topic selection → scope → *Start scan* → poll → **Cancel** →
poll → **Resume** → poll → done → *Open dashboard*. The test asserts the exact request
sequence a student's browser makes, the honest-state text and button visibility at each
stage (§4: a terminal state is never a dead end), that a `partial_warning` surfaces as an
amber note, that a hostile API response never reaches the DOM as markup, and that an
`/api/expand` outage still maps the student's literal words instead of stalling (D-068
fail-closed). The mini-DOM **throws** on an unsupported selector, so a page change that
outgrows the harness fails loudly instead of quietly under-testing.

---

## 4 — Clean-room verification — **PASSED**

Per `IMPLEMENTATION_GOAL.md` §4 step 6:

- **Wiped:** `.pytest_cache`, `src/supervisorly.egg-info`, every `__pycache__`, all
  `*.sqlite`, `.cache/`, `snaps/`, `browser_staging/`, `scratchpad/`, and `output/` (which
  held a smoke run: dashboard HTML/JSON, a subject map, a page snapshot and the SQLite
  store).
- **D-005 gate before the run:** `git status --porcelain` **empty**; `git clean -ndx`
  **empty** apart from `.venv/`. No scan output, no snapshots, no personal data.
- **Fresh install:** a brand-new virtualenv (Python 3.12.2) + `pip install -e ".[dev]"`
  per the README, nothing pre-warmed.
- **Result: 566 passed on the FIRST try**, ~66 s.
- **D-005 gate after the run:** `git status --porcelain` still **empty**; `git clean -ndx`
  lists only `.venv/`, `__pycache__/` and the editable-install `egg-info/` — all gitignored
  build artifacts. No database, snapshot or scan output survived into the tree.

**One deliberate deviation, recorded rather than hidden:** the contract says to delete the
editable install itself. The existing `.venv` was **kept** and the clean-room used a
*separate* fresh virtualenv outside the repo. Deleting the only working environment on a
machine whose package index might be unreachable is an unrecoverable risk for no extra
signal — a fresh venv installing the package from scratch proves the same thing (no hidden
dependency on dev state), because the suite ran entirely inside it.

---

## 4b — Production deploy (2026-07-27): seven defects no offline test could catch

Deployed to Firebase project `supervisorly` (number 1040155948868, `us-central1`, Blaze).
Every defect below survived a green 566-test suite, an eight-finding adversarial audit and
a clean-room pass. Each is fixed, and `firebase/README.md` now states the reason.

| # | Defect | What it would have cost |
|---|---|---|
| 1 | `firestore.Client()` implicitly targeted `(default)`; a project created today can get a **named** database instead | Every Firestore call 404s |
| 2 | Runbook said `--no-public-access-prevention`, commented *"keep it PRIVATE"* — the flag **lifts** the protection | A bucket of personal data left exposable (D-005/D-069c) |
| 3 | `gcloud run jobs create --source` — `create` takes only a prebuilt `--image` | Deploy stops dead |
| 4 | `supervisorly @ git+https://…` on `python:3.11-slim`, which ships no `git` | Container build fails |
| 5 | IAM step named `<project>@appspot.gserviceaccount.com`, which **does not exist** here (404 Unknown service account), and omitted three required roles | *Start scan* and *Open dashboard* both broken |
| 6 | `public/index.html` shadowed the `webapp` function — Hosting serves **static files before rewrites**, the opposite of what that file's own text claimed | Visitors got a 664-byte stub instead of the 54 KB app |
| 7 | v4 signing needs `service_account_email` + `access_token` to route through IAM signBlob; the `serviceAccountTokenCreator` grant alone is **not** sufficient | `/api/result/<id>` 500s: *"you need a private key to sign credentials"* |
| 8 | **`roles/run.invoker` was never sufficient.** The Functions launch the worker *with overrides* (that is how `JOB_ID` is injected), which needs `run.jobs.runWithOverrides` — a permission in `roles/run.developer`, not `run.invoker` | `POST /api/scan` 500s on any project where the default `roles/editor` has been removed |

Defects 2, 5, 6 and 7 all **deployed successfully**. A green deploy was never evidence the
thing worked — which is the transferable lesson here.

Defect 8 is sharper still, and was found only by applying least privilege. Every scan that
succeeded before it was fixed worked **only** because the Compute Engine default service
account ships with `roles/editor`, which silently covered the missing permission. So
`roles/editor` does not merely over-permit: **it masks missing grants**, and "it works" is
therefore no evidence that the documented permissions are correct. The documented IAM would
have failed on any project that had ever been hardened — at the moment a student pressed
*Start scan*, with nothing in the code to blame.

### Least privilege — applied and verified

`roles/editor` was removed from the runtime service account and replaced with
`cloudbuild.builds.builder`, `logging.logWriter`, `monitoring.metricWriter`,
`artifactregistry.writer` at project level, plus resource-scoped `datastore.user`,
`storage.objectAdmin` (results bucket), `secretmanager.secretAccessor` (the one secret),
and `run.invoker` + `run.developer` (the worker job). Verified afterwards by running a real
scan to completion — **not** by redeploying, since a deploy with no source change is
skipped entirely (`No changes detected`) and proves nothing.

### Verified live, not simulated

| Check | Result |
|---|---|
| `GET /` | 200, 54,312 bytes — byte-size identical to a local `build_webapp()`, **zero external URLs** (D-069.4 holds in production) |
| `GET /api/map?field=…` | 200, 13 groups / 25 topics from live OpenAlex |
| `GET /api/scan/<unknown>` | 404, the honest "never listable" message (D-069b) |
| `POST /api/scan` | 202, Cloud Run worker launched (`run.invoker` correct) |
| Job lifecycle | `queued → running → done`, phase `exported` |
| **Cancel** | 202 → `cancelling` → `cancelled` |
| **Resume** | 202 → `queued` → `done` — §3.4 safe-exit/resume proven |
| `GET /api/result/<id>` | 302 → `GOOG4-RSA-SHA256`, 900 s, signed by the runtime SA |
| The signed URL | 200, 21,890-byte dashboard, `searched_absent` / `never_attempted` rendering |
| **Same object, unsigned** | **403** — the bucket is genuinely private; the signature does the work |
| **§3.2 stuck-job watchdog** | ✅ a job stranded by defect 8 was flipped to `failed` — *"worker stalled; safe to resume"* — after the 600 s stall window |
| **Resume after failure** | ✅ that same failed job resumed → `queued` → `done` → signed URL |
| **§3.3 idempotent start** | ✅ a repeat of the same plan+email returned the EXISTING job (`"existing": true`) rather than a duplicate |
| **§3.5 one active job per email** | ✅ a second concurrent scan was refused with an honest 429 naming the active job |

One false alarm, recorded because being wrong loudly matters: a cancelled *queued* job
appeared stuck in `cancelling`, and I called it a dead-end bug. Reading the Firestore
document directly showed `cancelled`, written ~130 s in — the Cloud Run container simply
had to cold-start before it could observe the flag, and my poll window was 100 s. Not a
defect; an impatient test.

## 5 — Definition of Done

| DoD item (contract §6) | Status |
|---|---|
| All tests pass | ✅ 566 passed, 0 failed, 0 skipped |
| Adversarial self-audit returns no open findings | ✅ 8 found, 8 fixed, each with a regression test |
| Every new endpoint/edge case has a passing test | ✅ incl. cancel races, throttle buckets, method enforcement, injection |
| Clean-room passes green on the first try | ✅ §4 |
| `git status` shows no scan output / personal data | ✅ before **and** after the run |
| Docs updated — `README.md` | ✅ new "The hosted web app" section (local run + deploy pointer) |
| Docs updated — `BUILD_LOG.md` | ✅ backfilled W0–W6 (never written at the time) + W8 |
| Docs updated — `DECISIONS.md` | ✅ D-070 |
| Completion report with honest limitations | ✅ this file |
| **Deployed and verified against real GCP** | ✅ §4b — live, full lifecycle exercised |

---

## 6 — Known limitations (honest)

1. ~~Nothing has ever been deployed.~~ **Resolved 2026-07-27** — deployed and exercised end
   to end (§4b). The prediction that this was "the single biggest untested surface" was
   correct: it yielded seven defects, four of which deployed green.
   **What remains untested even now:** the 6-hour task timeout, the 7-day
   Firestore/bucket TTLs (they need seven days to prove), throttle behaviour under genuine
   concurrent load, and any scan large enough to hit the OpenAlex daily budget. The scans
   run were deliberately tiny (2 institutions, shortlist 3).
   The **§3.2 watchdog is no longer on this list** — defect 8 stranded a real job in
   `queued`, and the watchdog flipped it to `failed` with "safe to resume" on schedule,
   after which it resumed to `done`. A better test than anything that could have been
   staged deliberately.
2. **F1's fix encodes an assumption about the hosting front end** — that GCP appends
   `<client>, <lb>` to `X-Forwarded-For`. It is correct for Cloud Functions/Run behind
   Google's front end and is the documented behaviour, but it is *hosting-specific*: put
   another proxy in front and the "second from last" entry must be re-derived.
3. **No real browser has ever rendered the page.** The click-through drives the real JS in
   a mini-DOM, which catches logic, wiring, escaping and request-sequence bugs — but it
   cannot catch CSS/layout problems, real focus behaviour, or a genuine browser API
   difference.
4. **App Check is not enabled** (§5.2 lists it as optional). Until it is, the throttles are
   the only abuse control, and they are per-IP.
5. **`subject_map_multi` is unwired** (D-070, BLOCKERS B-001). The merge lives in the page.
   The accepted cost: one *Understand* click can spend up to 8 of the 30/h map allowance.
6. **Running the web app locally takes two commands**, because the dev server serves the
   API only and the page is a generated artifact. Fine for development, but it is a rough
   edge, and the README now says so rather than implying a single command exists.
7. **Per-round test counts for W1–W6 are gone.** The build log was not kept during that
   work; the backfill omits them rather than inventing them.

---

## 7 — How to run it

```bash
python -m venv .venv
.venv\Scripts\activate                      # Windows;  source .venv/bin/activate elsewhere
python -m pip install -e ".[dev]"
python -m pytest                             # 566 passed

# the web app, locally (no cloud account):
python -m supervisorly.webapi --port 8765
python -c "from supervisorly.export.webapp import build_webapp; \
  print(build_webapp(api_base='http://localhost:8765'))" > output/webapp.html
# then open output/webapp.html
```

To deploy: `firebase/README.md`, steps 0–8. Fill the placeholders in step 2 with your own
project values first — nothing in this repo points at a live project.
