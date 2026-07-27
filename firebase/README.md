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
| `SUPERVISORLY_EXPAND_KEY` | Functions secret (optional, fail-closed) | Kimi Code API key for D-068 expansion |

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

```bash
gcloud run jobs add-iam-policy-binding supervisorly-scan-worker --region <REGION> \
  --member "serviceAccount:<FIREBASE_PROJECT_ID>@appspot.gserviceaccount.com" \
  --role roles/run.invoker
```

(`<FIREBASE_PROJECT_ID>@appspot.gserviceaccount.com` is the App Engine default
service account, which 2nd-gen Functions use unless you configured a custom one —
substitute yours if so.)

## 7. First deploy

```bash
firebase deploy --only functions,firestore,storage
```

Note the Functions base URL it prints:
`https://<REGION>-<FIREBASE_PROJECT_ID>.cloudfunctions.net`.

## 8. Set `<API_BASE_URL>`, second deploy

The default needs nothing: Hosting rewrites send `/api/**` to the `api` function and
everything else to `webapp`, so `WEBAPP_API_BASE` stays empty. Only if you serve the
page statically (see `public/index.html`) or from another origin, set
`WEBAPP_API_BASE=<API_BASE_URL>` in `.env`. Then:

```bash
firebase deploy        # functions + hosting + rules
```

## Local emulation

```bash
firebase emulators:start --only functions,firestore
```

The wrappers talk to the emulated Firestore automatically; the Cloud Run Job bridge
(`invoke_worker`) and signed URLs still need real GCP credentials — for full local
parity use the repo's own dev server instead (`python -m supervisorly.webapi`).
