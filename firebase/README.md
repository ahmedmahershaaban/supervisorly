# Deploying the Supervisorly web build to Firebase

Everything in this folder is ready except the marked `<PLACEHOLDERS>` — fill them in
the order below (plan §8). Prereqs: the Firebase CLI (`npm i -g firebase-tools`), the
gcloud CLI, and a billing-enabled Firebase/GCP project.

## 0. Placeholders

| Placeholder | Where | What |
|---|---|---|
| `<FIREBASE_PROJECT_ID>` | `.firebaserc`, deploy commands | your Firebase project id |
| `<FIREBASE_WEB_API_KEY>` etc. | `webapp.html` config block (public-safe by design) | Firebase console → project settings (only needed if you add App Check) |
| `<API_BASE_URL>` | `WEBAPP_API_BASE` env (or static `public/index.html`) | Functions base URL after first deploy — empty string = same-origin rewrites (default) |
| `<RESULTS_BUCKET>` | Functions/worker env `RESULTS_BUCKET` | private bucket for dashboards + job DBs |
| `<REGION>` | deploy commands | e.g. `us-central1` |
| `<RELEASE_TAG>` | `requirements.txt` | a git tag (e.g. `web-v1`) — branches float, tags don't |
| `<FIRESTORE_DATABASE>` | `.env`, step 4, step 5 | the Firestore database id — **check it**, a new project may give you a *named* database rather than `(default)` (step 4) |
| `<APP_CHECK_SITE_KEY>` | the page (optional, plan §5.2) | reCAPTCHA/App Check when public |
| `SUPERVISORLY_CONTACT_EMAIL` | Functions + worker secret | your email (OpenAlex polite pool) |
| `SUPERVISORLY_OPENALEX_KEY` | Functions + worker secret (optional) | premium key — raises the daily budget |
| `SUPERVISORLY_EXPAND_KEY` | Functions secret (optional, fail-closed) | API key for D-068 expansion — see "Query expansion" below |
| `SUPERVISORLY_EXPAND_BASE_URL` / `_MODEL` | `.env` | which provider/model does the expansion (server config, never a request param) |

## 1. Init + copy files

```bash
firebase login
firebase init          # choose: Hosting, Functions (Python), Firestore, Storage
```

This folder IS the functions source (`firebase.json` → `functions.source: "."`), so
once `firebase init` has created the project skeleton, copy/keep these files over the
generated ones: `main.py`, `_core.py`, `worker.py`, `requirements.txt`,
`firebase.json`, `.firebaserc`, `firestore.rules`, `storage.rules`,
`Dockerfile.worker`, `lifecycle.json`, `public/`.

## 2. Fill the placeholders

- **`<FIREBASE_PROJECT_ID>`** — edit `.firebaserc`, and use it in every command below.
- **`<RELEASE_TAG>`** — tag the repo and edit `requirements.txt`:

  ```bash
  git tag web-v1 && git push origin web-v1
  # requirements.txt:
  # supervisorly @ https://github.com/ahmedmahershaaban/supervisorly/archive/refs/tags/web-v1.tar.gz
  ```

  Use the **tarball** URL, not `git+https://…`. The `python:3.11-slim` worker base image
  ships no `git`, so a `git+` requirement fails the container build with
  `Cannot find command 'git'`. A tag tarball needs no git binary and is equally immutable.

- **Secrets** (both the Functions and the worker need the email/OpenAlex key):

  ```bash
  firebase functions:secrets:set SUPERVISORLY_CONTACT_EMAIL
  firebase functions:secrets:set SUPERVISORLY_OPENALEX_KEY   # optional
  firebase functions:secrets:set SUPERVISORLY_EXPAND_KEY     # optional (D-068; fail-closed without it)
  ```

- **Non-secret env** — create `.env` in this folder (git-ignored, loaded by the
  Functions at deploy):

  ```bash
  RESULTS_BUCKET=<RESULTS_BUCKET>
  SCAN_WORKER_JOB=projects/<FIREBASE_PROJECT_ID>/locations/<REGION>/jobs/supervisorly-scan-worker
  WEBAPP_API_BASE=            # empty = Hosting rewrites route /api/** (the default)
  FIRESTORE_DATABASE=         # empty = "(default)"; set it if step 4 shows a NAMED database
  ```

## 2b. Enable the APIs (do this before anything below)

Nothing else works until these are on, and the failures they cause name an API rather
than the step you were running, so turn them all on in one go:

```bash
gcloud services enable \
  run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com \
  cloudfunctions.googleapis.com firestore.googleapis.com storage.googleapis.com \
  secretmanager.googleapis.com eventarc.googleapis.com iam.googleapis.com \
  cloudresourcemanager.googleapis.com firebasestorage.googleapis.com \
  --project <FIREBASE_PROJECT_ID>
```

## 3. The results bucket (private, 7-day auto-delete)

```bash
gcloud storage buckets create gs://<RESULTS_BUCKET> --location <REGION> \
  --uniform-bucket-level-access --public-access-prevention
gcloud storage buckets update gs://<RESULTS_BUCKET> --lifecycle-file=lifecycle.json
```

`--public-access-prevention` **enforces** the block on public access. (An earlier version
of this file said `--no-public-access-prevention` with the comment "keep it PRIVATE" —
that flag does the exact opposite, *lifting* the protection. Scan results are personal
data, D-005/D-069(c), so the enforcing flag is the correct one.) Public-access prevention
does not affect signed URLs: those are authenticated by the signer's credentials, not
public reads.

`--uniform-bucket-level-access` turns off per-object ACLs so access is governed by IAM
alone — the worker writes with a service account, so nothing needs object ACLs.

`lifecycle.json` deletes every object after 7 days (D-069(c)). Verify with:

```bash
gcloud storage buckets describe gs://<RESULTS_BUCKET> \
  --format="value(location,uniform_bucket_level_access,public_access_prevention)"
# want: <REGION>  True  enforced
```

## 4. Firestore TTL on the job docs

Job docs carry an `updatedAt` timestamp refreshed on every write; the TTL policy
deletes a doc 7 days after its last update:

```bash
gcloud firestore databases list --project <FIREBASE_PROJECT_ID> --format=json   # get the id FIRST
gcloud firestore fields ttls update updatedAt --collection-group=scan_jobs --enable-ttl \
  --database=<FIRESTORE_DATABASE> --project <FIREBASE_PROJECT_ID>
```

**Check the database id before you run this.** Historically every project had exactly one
Firestore database, named `(default)`, and both gcloud and the Python client assume it. A
project created today can instead get a **named** database — this one's is `default`, with
no parentheses. Against such a project the command above fails with
`NOT_FOUND: … database '(default)' does not exist`, and, worse, the deployed code hits the
same wall at runtime unless `FIRESTORE_DATABASE` is set in `.env` (step 2) and in the
worker's env (step 5). `gcloud firestore databases list --format=json` prints the exact
`name`; the id is the part after `databases/`.

(or: Firebase console → Firestore → TTL policies → collection group `scan_jobs`,
field `updatedAt`. The command may live under `gcloud alpha firestore` on older CLIs.)

## 5. The scan-worker Cloud Run Job

Use `gcloud run jobs **deploy**`, not `create`: `create` only accepts a prebuilt
`--image`, and passing it `--source` fails with `unrecognized arguments: --source`.
`deploy` builds from source and creates-or-updates, so it is also the command to re-run
after any worker change.

It builds from a file named `Dockerfile` specifically, so stage a scratch dir first:

```bash
mkdir -p /tmp/scan-worker
cp Dockerfile.worker /tmp/scan-worker/Dockerfile
cp requirements.txt main.py _core.py worker.py /tmp/scan-worker/

gcloud run jobs deploy supervisorly-scan-worker --source /tmp/scan-worker \
  --region <REGION> --tasks 1 --max-retries 1 --task-timeout 6h \
  --set-env-vars RESULTS_BUCKET=<RESULTS_BUCKET>,FIRESTORE_DATABASE=<FIRESTORE_DATABASE> \
  --set-secrets SUPERVISORLY_CONTACT_EMAIL=SUPERVISORLY_CONTACT_EMAIL:latest,\
SUPERVISORLY_OPENALEX_KEY=SUPERVISORLY_OPENALEX_KEY:latest
```

(`FIRESTORE_DATABASE` must match step 4 — the worker writes progress to the same database
the Functions read. Drop it from `--set-env-vars` only if your project uses `(default)`.)

(`--tasks 1 --max-retries 1`: one execution = one scan; a retry reuses the same job
doc and the engine's checkpoints. The 6 h task-timeout is the §3.5 runtime cap.)

## 6. IAM — let the Functions invoke the worker job

The Functions runtime service account needs permission to run the job. The relevant
permission (`run.jobs.run`) is granted by **`roles/run.invoker`** — the invoker role
covers both services and jobs; there is no separate "jobs.run" role to bind:

**Do not assume the service account — read it.** This file used to say the runtime SA is
`<FIREBASE_PROJECT_ID>@appspot.gserviceaccount.com` (the App Engine default). On a project
created today that account may not exist at all: deploying to `supervisorly` logged
`404, Unknown service account` for exactly that address, and both the Functions and the
Cloud Run job in fact run as the **compute** default,
`<PROJECT_NUMBER>-compute@developer.gserviceaccount.com`. Binding the wrong one produces a
permission error only when a student first presses *Start scan*.

```bash
# 1. read the real runtime service account off what you deployed
gcloud run services describe api --region <REGION> --project <FIREBASE_PROJECT_ID> \
  --format="value(spec.template.spec.serviceAccountName)"
gcloud run jobs describe supervisorly-scan-worker --region <REGION> \
  --project <FIREBASE_PROJECT_ID> \
  --format="value(spec.template.spec.template.spec.serviceAccountName)"

# 2. bind BOTH roles on the job — see the warning below, run.invoker alone is NOT enough
gcloud run jobs add-iam-policy-binding supervisorly-scan-worker --region <REGION> \
  --member "serviceAccount:<THE_ACCOUNT_YOU_JUST_READ>" --role roles/run.invoker
gcloud run jobs add-iam-policy-binding supervisorly-scan-worker --region <REGION> \
  --member "serviceAccount:<THE_ACCOUNT_YOU_JUST_READ>" --role roles/run.developer
```

> **`roles/run.invoker` is NOT sufficient, despite what every "launch a Cloud Run job"
> tutorial says.** The Functions start the worker *with overrides* — that is how `JOB_ID`
> is injected per execution (`_core.invoke_worker`) — and overriding requires
> **`run.jobs.runWithOverrides`**, which `roles/run.invoker` does not grant. It is in
> `roles/run.developer`.
>
> This is easy to miss because the default Compute Engine service account ships with
> `roles/editor`, which covers it. Scans will appear to work perfectly until someone
> applies least privilege — and then `POST /api/scan` starts returning 500 with
> `Permission 'run.jobs.runWithOverrides' denied`, with nothing in the code changed. That
> is exactly how this was found here.

The runtime account needs three more grants the original runbook never mentioned, each of
which fails late and confusingly if missing:

```bash
SA=<THE_ACCOUNT_YOU_JUST_READ>
# Firestore read/write (job docs + progress)
gcloud projects add-iam-policy-binding <FIREBASE_PROJECT_ID> \
  --member "serviceAccount:$SA" --role roles/datastore.user
# write dashboards into the results bucket / read them back to sign
gcloud storage buckets add-iam-policy-binding gs://<RESULTS_BUCKET> \
  --member "serviceAccount:$SA" --role roles/storage.objectAdmin
# mint v4 signed URLs: with no private key on disk, signing goes through the IAM
# signBlob API, which needs the account to be able to sign AS ITSELF
gcloud iam service-accounts add-iam-policy-binding $SA \
  --member "serviceAccount:$SA" --role roles/iam.serviceAccountTokenCreator
```

Without the last one, `/api/result/<id>` fails with *"you need a private key to sign
credentials"* the first time anyone opens a finished dashboard.

### Least privilege (optional, but do it deliberately)

GCP gives the Compute Engine default service account **`roles/editor`** on the whole
project. That is far more than this app needs, and — as the `runWithOverrides` case above
shows — it also *masks* missing grants, so a project that looks healthy can be one
`roles/editor` removal away from breaking. If you drop it, grant these first or you will
break both builds and runtime:

```bash
SA=<THE_ACCOUNT_YOU_JUST_READ>
for R in roles/cloudbuild.builds.builder roles/logging.logWriter \
         roles/monitoring.metricWriter roles/artifactregistry.writer; do
  gcloud projects add-iam-policy-binding <FIREBASE_PROJECT_ID> \
    --member "serviceAccount:$SA" --role $R
done
gcloud projects remove-iam-policy-binding <FIREBASE_PROJECT_ID> \
  --member "serviceAccount:$SA" --role roles/editor
```

`cloudbuild.builds.builder` matters because Cloud Build uses this same account as its
build service account — strip `editor` without it and your next `firebase deploy` fails.
`logging.logWriter` matters because without it the worker's output silently disappears,
which is precisely the information you need when something goes wrong.

**Then re-verify by running an actual scan**, not just by redeploying: a deploy with no
source change is skipped entirely (`No changes detected`) and proves nothing.

## 7. First deploy

```bash
firebase deploy --only functions,firestore,storage
```

**On PowerShell, quote the list** — `--only "functions,firestore,storage"`. Unquoted,
PowerShell splits on the commas and passes three separate arguments, and the CLI answers
`Cannot understand what targets to deploy/serve`.

Run it from THIS folder (`firebase/`): that is where `firebase.json` and `.firebaserc`
live, and `firebase login:use` binds an account per-directory, so running it from the repo
root can also pick the wrong Google account.

Note the Functions base URL it prints:
`https://<REGION>-<FIREBASE_PROJECT_ID>.cloudfunctions.net`.

## 8. Set `<API_BASE_URL>`, second deploy

The default needs nothing: Hosting rewrites send `/api/**` to the `api` function and
everything else to `webapp`, so `WEBAPP_API_BASE` stays empty.

**`public/` must not contain an `index.html`.** Firebase Hosting serves matching static
files **first** and only falls through to `rewrites` when nothing matches — so an
`index.html` sitting in `public/` silently shadows the `webapp` function and your visitors
get that file instead of the app. This folder shipped exactly such a placeholder, whose own
text claimed it was "shadowed by the `/**` rewrite"; the precedence is the other way round,
and the deployed site served a 664-byte stub instead of the 54 KB page. `public/` now holds
only `.gitkeep`, which Hosting's `**/.*` ignore rule skips.

If you would rather serve the page as a static file (no cold start on first visit), that is
a deliberate alternative: generate it with
`build_webapp(api_base='')` into `public/index.html` AND drop the `**` rewrite from
`firebase.json`, so the two mechanisms cannot fight. Set
`WEBAPP_API_BASE=<API_BASE_URL>` only when serving from another origin. Then:

```bash
firebase deploy        # functions + hosting + rules
```

## Query expansion (D-068) — optional, and two traps

Expansion turns a student's phrasing into search variants, so typing `NLP` also searches
*natural language processing*. Without it the map is **empty for acronyms** — measured on
the live site: `NLP` → 0 topics, `natural language processing` → 11. It fails honestly
(the page says the map came back empty and offers to name professors directly), but an
acronym is a dead end. That is the hole D-068 exists to fill; a hardcoded acronym list
would violate [D-038](../docs/DECISIONS.md#d-038--queries-and-keywords-are-generated-per-search-never-looked-up).

It is genuinely optional: with no key the engine falls back to the student's literal words
and nothing breaks.

**Trap 1 — the key's project decides your billing tier.** A Gemini key created in *this*
project inherits its Cloud Billing (enabled for Cloud Run), so Gemini bills it as **paid
tier** and every call returns `429 "Your prepayment credits are depleted"` until you buy
credit. A key created in a **new project with no billing** gets the **free tier** — 1,500
requests/day, 15/min — which is far beyond this app's own 10/hour-per-IP throttle. Create
the key at `aistudio.google.com/apikey` and choose **"Create API key in new project"**.

**Trap 2 — pinned model versions get retired.** `gemini-2.5-flash-lite` returns
`404 "no longer available to new users"` for projects that had not used it before, so it
looks like a broken key rather than a retired model. Use the provider's **alias**
(`gemini-flash-lite-latest`) unless you need reproducibility more than you need it to keep
working.

```bash
# 1. the key (new, UNBILLED project) -> Secret Manager
firebase functions:secrets:set SUPERVISORLY_EXPAND_KEY

# 2. let the runtime read it
gcloud secrets add-iam-policy-binding SUPERVISORLY_EXPAND_KEY \
  --member "serviceAccount:<THE_RUNTIME_SA>" --role roles/secretmanager.secretAccessor

# 3. .env — provider + model are server config
#    SUPERVISORLY_EXPAND_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai
#    SUPERVISORLY_EXPAND_MODEL=gemini-flash-lite-latest
```

**Trap 3, the silent one — a 2nd-gen function only receives secrets it DECLARES.** Setting
the secret and the env var is not enough; without `@https_fn.on_request(secrets=[...])` the
key is simply absent at runtime and expansion fails closed exactly as if you had never set
it — no error, no log, just no expansion. `main.py` declares it on `expand` and on `api`
(which routes `/api/expand` behind the Hosting rewrite). Nothing else needs it: the scan
worker never expands.

Verify after deploying — `expanded` must be `true`:

```bash
curl -s "https://<your-site>/api/expand?field=NLP" | head -c 200
```

Any other provider works unchanged (the call is OpenAI-compatible): point
`SUPERVISORLY_EXPAND_BASE_URL`/`_MODEL` at DeepSeek, Groq, or anything else with a
`/chat/completions` endpoint and JSON mode.

## Local emulation

```bash
firebase emulators:start --only functions,firestore
```

The wrappers talk to the emulated Firestore automatically; the Cloud Run Job bridge
(`invoke_worker`) and signed URLs still need real GCP credentials — for full local
parity use the repo's own dev server instead (`python -m supervisorly.webapi`).
