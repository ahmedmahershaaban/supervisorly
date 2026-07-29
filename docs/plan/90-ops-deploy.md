# OPS — Deploying, sizing, and what is deliberately out of scope

← [`README.md`](README.md) · [`00-invariants.md`](00-invariants.md)

---

# Deploying a phase (learned the hard way, twice)

**`firebase deploy` does not rebuild the worker.** The Functions tier and the Cloud Run Job are
separate images, and the scan pipeline lives in the **worker**. Deploying one and testing the
other has cost this project two full cycles.

For any change under `src/supervisorly/**`:

- [ ] **OPS-1** Commit, then `git tag -a web-vN -m "…"` and push the tag
- [ ] **OPS-2** Point `firebase/requirements.txt` at the new tag — the package installs **from
      the tag**, never from disk. A change on disk that is not in a pushed tag will not deploy
- [ ] **OPS-3** Deploy Functions: `firebase deploy --only functions --project supervisorly`
- [ ] **OPS-4** Deploy the worker: stage `requirements.txt`, `main.py`, `_core.py`, `worker.py`
      and **`Dockerfile.worker` renamed to plain `Dockerfile`** into a scratch dir, then
      `gcloud run jobs deploy supervisorly-scan-worker --source <dir> --region us-central1 --memory 4Gi --cpu 2 --task-timeout 21600 --set-env-vars "RESULTS_BUCKET=supervisorly-results" --set-secrets "SUPERVISORLY_CONTACT_EMAIL=SUPERVISORLY_CONTACT_EMAIL:latest"`

      **The rename is load-bearing.** Cloud Build only recognises a file literally called
      `Dockerfile`; staged under its own name it is ignored and the build silently falls back
      to **buildpacks**, which produce a web server. The container then starts gunicorn, logs
      `Failed to find attribute 'app' in 'main'` and `exit(4)`, every scan sits at *Queued*
      forever, and the deploy reports success. Done exactly this way on 2026-07-29.

      Pass the env and secrets explicitly: a `--source` deploy rewrites the container config,
      and `SUPERVISORLY_OPENALEX_KEY` is **not** one of them — that secret has never existed
      in this project and naming it leaves the job `Ready=False`.
- [ ] **OPS-5** **Verify both.** `python tools/verify_deploy.py` compares the live page against
      what this tree builds; for the worker, confirm the image **sha256 digest changed**. An
      unchanged digest means the scanner did not change, whatever the deploy said.

      **A changed digest is necessary, not sufficient** — a buildpack image is also a new
      digest. Confirm the container actually runs the worker:
      `gcloud run jobs executions list --job supervisorly-scan-worker --region us-central1 --limit 3`
      must show the next execution **succeeding**, and the log must contain the worker's own
      output rather than gunicorn's. OPS-6 is what proves it; do not skip it.
- [ ] **OPS-6** Run one real scan. Check `python tools/logs.py job <id>` and the new ledger rows
- [ ] **OPS-7** **Any new runtime data file** (`*.js`, `*.sql`, …) must be added to
      `pyproject.toml` `[tool.setuptools.package-data]`. A file present in the repo and absent
      from the wheel fails **only in production** — this is exactly how `page_extract.js` went
      missing and silently disabled the render rung for a whole deploy

## Reading production

| command | answers |
|---|---|
| `python tools/logs.py job <id>` | everything about one scan, both tiers |
| `python tools/logs.py client` | what BROWSERS reported (D-071); empty is the good case |
| `python tools/logs.py errors` | ERROR or worse, last 6 h |
| `python tools/verify_deploy.py` | does the live page match this tree |

**Filter on the payload, not the service.** Hosting rewrites `/api/**` to a single `api`
function, so per-endpoint services normally receive no traffic — filtering by
`service_name="clientlog"` returns nothing while the feature works perfectly.

## Throttles during testing

The §5.2 caps are 5 scans/hour per IP. Lifting them for a test pass means editing
`firebase/_core.py` and deploying — **commit the lift as its own commit and revert it the same
day.** Worked example: `a6fd713` and its revert `2e80d7d`.

---

# Sizing, for sequencing

| task | size | risk | note |
|---|---|---|---|
| CC-1 ledger | S | low | additive |
| CC-2 budgets | S | low | |
| CC-3 domain pool | **M** | **med** | async rewrite of the render path |
| CC-4 sessions | S | low | localStorage only |
| CC-5 PDF | S | low | `pypdf` + a size cap |
| FLAG | S | low | do it early; it de-risks everything after |
| P0 ORCID employments | S | low | mirrors shipped researcher-urls work |
| **P1 admissions** | **L** | **high** | new scope model + crawl + extraction |
| P4 triage | S | med | recall tuning is the risk |
| P5 model extraction | M | med | contract already written and tested |
| **P2 directory rung** | **L** | **high** | crawl traps + identity matching |
| P6 archive | S | low | isolated |
| P7 BYO key | S | low | CORS already verified |
| T-1 translation | S | low | display only |
| FE-1…6 | M | low | spread across the above |

**P1 and P2 carry most of the risk**, which is why both are gated by spikes.

---

# Deliberately NOT in this plan

Recorded so none of it is rediscovered as an oversight.

- **No cross-session caching** of page or institution data *(Ahmed, 2026-07-29)*. Pages change
  and a cache cannot be invalidated correctly — a stale deadline can cost a student a cycle
- **No installed coding agent** on the student's machine. The install and trust burden exceeds
  the product, and an autonomous browser agent on someone's machine is a serious safety surface
  for a supervisor search
- **No path or institution dictionaries** — `tests/test_no_seed_urls.py` enforces it
- **No translated quotes** — translation is display-only (T-1)
- **No Stage 4** (`recent_collaborators`) — still open as
  [BLOCKERS B-002](../BLOCKERS.md), and it needs a product decision before any code
- **No bulk fetching moved to the student's IP as the default path.** Client collection is
  permitted and lands at tier `agent_browser` (rank 2); the open web stays server-side

---

# Definition of done, per task

1. Code and tests written; the tests describe the **property**, not the implementation
2. `python -m pytest` green, with `TMPDIR` outside the repo
3. The seven invariants in [`00-invariants.md`](00-invariants.md) re-checked
4. A ledger row exists if the task touches a phase
5. One commit with a real message — what changed, what was run, what the result was
6. Only then mark `[R]`
