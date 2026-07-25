"""Supervisorly command line.

Every pipeline stage is independently runnable from here (architecture §7), so the
tool is debuggable and portable. Shipped commands: ``init-db``, ``version``,
``scan`` (demo + live), ``ingest-page`` (the browser seam, D-064) and ``pace``
(the social pacing gate, D-065).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import PRODUCT_NAME, __version__
from .model.db import open_db


def cmd_version(_args: argparse.Namespace) -> int:
    print(f"{PRODUCT_NAME} {__version__}")
    return 0


def cmd_init_db(args: argparse.Namespace) -> int:
    path = Path(args.db)
    # sqlite3 can't create the parent directory itself — do it here so a path
    # like output/run.sqlite works on a first run.
    if path.parent != Path("") and not path.parent.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
    open_db(path).close()
    print(f"initialised {path}")
    return 0


def cmd_ingest_page(args: argparse.Namespace) -> int:
    """Browser ingest seam (D-064): store agent-extracted page TEXT as a snapshot.

    The agent saves the in-page JS extractor's output to a staging file and calls
    this command; it handles only paths, byte counts, and the one-line result —
    raw HTML/DOM never enters the agent's context."""
    from urllib.parse import urlparse

    from .fetch.browser_rung import ingest_page

    url = (args.url or "").strip()
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        print(f"invalid --url {args.url!r}: pass the FINAL http(s) page url.")
        return 2
    file = Path(args.file)
    if not file.is_file():
        print(f"staging file not found: {file}")
        return 2
    text = file.read_text(encoding="utf-8")
    if not text.strip():
        print(f"staging file {file} is empty — nothing to ingest.")
        return 2

    db = Path(args.db)
    if db.parent != Path("") and not db.parent.exists():
        db.parent.mkdir(parents=True, exist_ok=True)   # same first-run rule as init-db
    snap_root = Path(args.snap_root) if args.snap_root else db.parent / ".cache" / "snaps"
    conn = open_db(db)
    try:
        res = ingest_page(conn, snap_root, final_url=url, text=text)
    finally:
        conn.close()
    # ASCII-only console output (cp1252 consoles can't encode arrows — see _write_result)
    print(f"ingested {res['bytes']} bytes -> snap {res['snapshot_hash'][:12]} "
          f"source {res['source_id']}")
    return 0


def cmd_pace(args: argparse.Namespace) -> int:
    """Social pacing gate (D-065): check/abort/reset before every browser page."""
    from .ethics import pacing

    if args.reset:
        pacing.reset(None if args.reset == "all" else args.reset, state_path=args.state)
        print(f"RESET host={args.reset}")
        return 0
    if not args.host:
        print("pace needs --host <host> (unless --reset is given).")
        return 2
    if args.abort is not None:
        pacing.abort(args.host, args.abort, state_path=args.state)
        print(f"ABORTED host={args.host} reason={args.abort or 'challenge'}")
        return 0
    res = pacing.check(args.host, state_path=args.state)
    verdict = "ALLOW" if res["allowed"] else "DENY"
    print(f"{verdict} host={args.host} wait={res['wait_seconds']}s reason={res['reason']}")
    return 0 if res["allowed"] else 3


def _warn_if_committable(out: Path) -> None:
    """D-005 guard: scan output holds personal data and must never be committed.

    When the resolved --out path sits inside a git work tree and neither it nor its
    sibling .json is covered by git-ignore rules, warn loudly BEFORE writing. Warn only —
    legitimate out-of-repo paths must keep working, and a missing git binary (or any git
    failure) is a clean no-op."""
    import subprocess

    target = out.resolve()
    cwd = target.parent
    while not cwd.is_dir() and cwd != cwd.parent:
        cwd = cwd.parent

    def _ignored(p: Path) -> bool | None:
        """True/False from git; None when git can't answer (absent, or not a work tree)."""
        try:
            r = subprocess.run(["git", "-C", str(cwd), "check-ignore", "-q", str(p)],
                               capture_output=True, timeout=10)
        except (OSError, subprocess.SubprocessError):
            return None
        return {0: True, 1: False}.get(r.returncode)   # 128 = not a work tree → no opinion

    ignored = [_ignored(target), _ignored(target.with_suffix(".json"))]
    if not all(i is False for i in ignored):
        return   # ignored, or git/repo unavailable → silent
    # ASCII-only: the default Windows console codec (cp1252) can't encode an em-dash and
    # would crash the command before the files are written (see _write_result).
    print(f"WARNING (D-005): {target} is inside a git work tree and is NOT git-ignored. "
          "Scan output contains personal data and must never be committed. "
          "Write under an ignored directory (e.g. output/) or add the path to .gitignore.",
          file=sys.stderr)


def _write_result(result: dict, out: Path, label: str) -> int:
    """Write the dashboard + sibling JSON and print an ASCII-safe status line."""
    import json
    _warn_if_committable(out)
    if out.parent != Path("") and not out.parent.exists():
        out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(result["html"], encoding="utf-8")
    out.with_suffix(".json").write_text(
        json.dumps(result["export"], ensure_ascii=False, indent=2), encoding="utf-8")
    n = len(result["export"]["professors"])
    # ASCII-only console output — the default Windows console codec (cp1252) can't encode a
    # Unicode arrow, which would crash the command after the files were already written.
    print(f"scanned {n} professors ({label}) -> {out} (+ {out.with_suffix('.json').name})")
    return 0


def cmd_scan(args: argparse.Namespace) -> int:
    out = Path(args.out)
    if out.parent != Path("") and not out.parent.exists():
        out.parent.mkdir(parents=True, exist_ok=True)   # for snapshots + the live DB
    snap_root = out.parent / ".cache" / "snaps"

    if args.demo:
        from .demo import demo_fixture
        from .pipeline import run_offline
        tp, targets, plan = demo_fixture()
        result = run_offline(plan, targets, tp, snap_root, optout_path=args.optout)
        return _write_result(result, out, "demo")

    # ── live scan ──
    import os

    from . import preflight
    email = args.email or os.environ.get(preflight.CONTACT_EMAIL_ENV)
    try:
        preflight.require_credentials({preflight.CONTACT_EMAIL_ENV: email or ""})
    except preflight.MissingCredentials as exc:
        print(str(exc))
        return 2
    if not args.country or not args.field:
        print("a live scan needs --country and --field (or use --demo for the offline demo). "
              "See --help.")
        return 2

    from .discover.countries import to_country_code
    # --country is documented as a country NAME ("Canada"); ROR's filter needs ISO alpha-2.
    # Resolve here, where the plan is built, and fail loud on anything unrecognized (D-002) —
    # never silently query ROR with a filter that matches 0 institutions.
    country_code = to_country_code(args.country)
    if not country_code:
        print(f"unrecognized --country {args.country!r}: pass an ISO 3166-1 alpha-2 code "
              "(e.g. CA) or an English country name (e.g. Canada).")
        return 2

    from .fetch.transport import httpx_transport
    from .pipeline import run_live
    plan = {"intent_kind": args.intent, "country": country_code, "field": args.field,
            "university_mode": args.university_mode,
            "universities": [u.strip() for u in args.universities.split(",")]
                            if args.universities else []}
    transport = httpx_transport(user_agent=f"SupervisorlyBot/0.1 (mailto:{email})")
    result = run_live(
        plan, transport, snap_root, email=email,
        openalex_key=(args.openalex_key or os.environ.get(preflight.OPENALEX_KEY_ENV)),
        db_path=out.parent / "supervisorly.sqlite", optout_path=args.optout, resume=args.resume,
    )
    # sparse-coverage preflight + discovery warnings (D-060) — ASCII-safe by construction
    # (preflight/ladder messages are ASCII-only, like the rest of this console output).
    for w in result["stats"].get("warnings", []):
        print(f"WARNING: {w}")
    return _write_result(result, out, "live")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="supervisorly", description=__doc__)
    p.add_argument("--version", action="version", version=f"{PRODUCT_NAME} {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("version", help="print the version").set_defaults(func=cmd_version)

    pi = sub.add_parser("init-db", help="create/migrate a scan database")
    pi.add_argument("--db", default="supervisorly.sqlite", help="database path")
    pi.set_defaults(func=cmd_init_db)

    ps = sub.add_parser("scan", help="run a scan and write a dashboard")
    ps.add_argument("--demo", action="store_true", help="run the offline synthetic demo (no keys)")
    ps.add_argument("--out", default="output/dashboard.html", help="dashboard output path")
    ps.add_argument("--optout", default=None,
                    help="path to an optout.txt suppression list (D-023)")
    # live-scan flags
    ps.add_argument("--country", help="country to scan: ISO alpha-2 code or English name "
                                      "(e.g. CA or Canada) (a live scan)")
    ps.add_argument("--field", help="research field / subfield (a live scan)")
    ps.add_argument("--intent", default="pre_phd",
                    choices=["training", "pre_master", "pre_phd", "mentor", "master", "phd",
                             "postdoc"],
                    help="what you're looking for (default: pre_phd)")
    ps.add_argument("--universities", default=None,
                    help="comma-separated universities to prioritise / restrict to")
    ps.add_argument("--university-mode", dest="university_mode", default="all",
                    choices=["all", "prioritise", "only"],
                    help="how to use --universities (default: all)")
    ps.add_argument("--email", default=None,
                    help="contact email for the OpenAlex polite pool "
                         "(or set SUPERVISORLY_CONTACT_EMAIL)")
    ps.add_argument("--openalex-key", dest="openalex_key", default=None,
                    help="optional OpenAlex premium key (higher limits)")
    ps.add_argument("--resume", action="store_true",
                    help="reuse prior state; skip already-completed targets (cheap re-scan)")
    ps.set_defaults(func=cmd_scan)

    pb = sub.add_parser("ingest-page",
                        help="store browser-extracted page TEXT as a snapshot (D-064)")
    pb.add_argument("--url", required=True, help="the FINAL page url (after redirects)")
    pb.add_argument("--file", required=True,
                    help="staging file holding the in-page extractor's text output")
    pb.add_argument("--db", default="supervisorly.sqlite", help="database path")
    pb.add_argument("--snap-root", dest="snap_root", default=None,
                    help="snapshot store root (default: <db-dir>/.cache/snaps)")
    pb.set_defaults(func=cmd_ingest_page)

    pp = sub.add_parser("pace", help="social pacing gate — run before every browser page "
                                     "(D-065); exit 0 = ALLOW, 3 = DENY")
    pp.add_argument("--host", help="page host being considered (e.g. x.com)")
    pp.add_argument("--abort", nargs="?", const="", default=None, metavar="REASON",
                    help="latch the host aborted (captcha/soft-block/login redirect)")
    pp.add_argument("--reset", nargs="?", const="all", default=None, metavar="HOST",
                    help="clear pacing state for HOST, or all hosts when omitted")
    pp.add_argument("--state", default=None,
                    help="pacing state path (default: ./pacing_state.json)")
    pp.set_defaults(func=cmd_pace)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
