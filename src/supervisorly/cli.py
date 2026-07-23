"""Supervisorly command line.

Every pipeline stage is independently runnable from here (architecture §7), so the
tool is debuggable and portable. Phase A ships ``init-db`` and ``version``; later
phases add ``scan``, ``resume``, ``export`` and friends.
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


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="supervisorly", description=__doc__)
    p.add_argument("--version", action="version", version=f"{PRODUCT_NAME} {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("version", help="print the version").set_defaults(func=cmd_version)

    pi = sub.add_parser("init-db", help="create/migrate a scan database")
    pi.add_argument("--db", default="supervisorly.sqlite", help="database path")
    pi.set_defaults(func=cmd_init_db)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
