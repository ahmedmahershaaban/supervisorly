"""Read the deployed backend's logs without remembering gcloud filter syntax.

    python tools/logs.py errors            # anything at ERROR or worse (default 6h)
    python tools/logs.py job <job_id>      # everything about one scan, both tiers
    python tools/logs.py tail              # recent activity across functions + worker
    python tools/logs.py runs              # Cloud Run job executions, one per scan
    python tools/logs.py where             # console URLs, for clicking rather than typing

    --hours N   how far back to look (default 6)
    --limit N   max entries (default 50)

Two tiers produce logs, and they answer different questions:

  * the **Functions** (`api`, `expand`, `map`, `scan_*`, `webapp`) — every HTTP request.
    A 500 from the page shows up here with a Python traceback.
  * the **Cloud Run worker** (`supervisorly-scan-worker`) — one execution per scan.

Note that the worker is deliberately quiet: scan progress is written to Firestore, because
that is what the page polls, so the container log shows little more than start and finish.
To see what a scan actually did, read its progress events (`GET /api/scan/<id>`) or open the
dashboard — not the container log.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys

PROJECT = "supervisorly"
REGION = "us-central1"
GCLOUD_FALLBACK = (r"C:\Users\ahmed\AppData\Local\Google\Cloud SDK"
                   r"\google-cloud-sdk\bin\gcloud.cmd")

CONSOLE = {
    "all logs": f"https://console.cloud.google.com/logs/query?project={PROJECT}",
    "functions": f"https://console.firebase.google.com/project/{PROJECT}/functions/logs",
    "worker runs": (f"https://console.cloud.google.com/run/jobs/details/{REGION}/"
                    f"supervisorly-scan-worker/executions?project={PROJECT}"),
    "firestore (job docs)": (f"https://console.firebase.google.com/project/{PROJECT}"
                             "/firestore/data/~2Fscan_jobs"),
    "results bucket": (f"https://console.cloud.google.com/storage/browser/"
                       f"{PROJECT}-results?project={PROJECT}"),
}


def gcloud() -> str:
    return shutil.which("gcloud") or GCLOUD_FALLBACK


def run(args: list[str]) -> str:
    r = subprocess.run([gcloud(), *args], capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        sys.stderr.write(r.stderr or "")
    return r.stdout or ""


def read(filt: str, hours: int, limit: int, fmt: str) -> str:
    return run(["logging", "read", filt, "--project", PROJECT,
                f"--freshness={hours}h", "--limit", str(limit), "--format", fmt])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mode", choices=["errors", "job", "tail", "runs", "where"])
    ap.add_argument("job_id", nargs="?")
    ap.add_argument("--hours", type=int, default=6)
    ap.add_argument("--limit", type=int, default=50)
    a = ap.parse_args()

    if a.mode == "where":
        for name, url in CONSOLE.items():
            print(f"  {name:22} {url}")
        return 0

    if a.mode == "runs":
        print(run(["run", "jobs", "executions", "list", "--job", "supervisorly-scan-worker",
                   "--region", REGION, "--project", PROJECT,
                   "--format", "table(name,status.conditions[0].type,creationTimestamp)"]))
        return 0

    if a.mode == "errors":
        out = read("severity>=ERROR", a.hours, a.limit,
                   "value(timestamp,resource.labels.service_name,"
                   "resource.labels.job_name,textPayload)").strip()
        print(out or f"  no errors in the last {a.hours}h")
        return 0

    if a.mode == "tail":
        out = read('resource.type="cloud_run_revision" OR resource.type="cloud_run_job"',
                   a.hours, a.limit,
                   "value(timestamp,resource.labels.service_name,"
                   "resource.labels.job_name,textPayload)").strip()
        print(out or f"  nothing logged in the last {a.hours}h")
        return 0

    # mode == "job"
    if not a.job_id:
        ap.error("job mode needs a job id: python tools/logs.py job <job_id>")
    print(f"— log lines mentioning {a.job_id} (last {a.hours}h) —")
    out = read(f'textPayload:"{a.job_id}"', a.hours, max(a.limit, 100),
               "value(timestamp,resource.labels.service_name,"
               "resource.labels.job_name,textPayload)").strip()
    print(out or "  nothing — the worker only logs start/finish; progress lives in Firestore")
    print("\n— its live state —")
    print(f"  curl -s https://{PROJECT}.web.app/api/scan/{a.job_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
