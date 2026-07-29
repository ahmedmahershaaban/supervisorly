"""Byte-comparison helper for exports.

Two tests need to assert "this change altered *nothing*" about an export — the progress
callback (it must be a pure observer) and the phase flags (all off must behave as before).
Both need the same list of fields that legitimately differ between two identical runs, and
keeping that list in one place is the point: when the export grows a new volatile field, a
single edit keeps both tests honest instead of one of them silently starting to compare
timestamps and failing for the wrong reason.
"""

from __future__ import annotations

import copy
import json

#: Placeholder written over every volatile value, so a diff points at real content.
STAMP = "<volatile>"


def stable(export: dict) -> dict:
    """A copy of ``export`` with wall-clock and uuid values neutralised.

    Volatile by nature, and *legitimately* so:

    - ``run.run_id`` — a fresh uuid per run
    - ``generated_at`` / ``observed_at`` — wall clock
    - the CC-1 ledger's ``seconds`` and ``created_at`` — the ledger measures elapsed time,
      so two identical runs differ here by construction. The COUNTS and the REASONS are the
      substance and are deliberately left alone: a phase that skipped a different number of
      targets is a real difference and must still fail the comparison.
    """
    e = copy.deepcopy(export)
    e["generated_at"] = STAMP
    run = e.get("run")
    if isinstance(run, dict):
        run["run_id"] = STAMP
        for row in run.get("ledger") or []:
            row["seconds"] = STAMP
            row["created_at"] = STAMP
    for p in e.get("professors") or []:
        for env in (p.get("fields") or {}).values():
            if env.get("observed_at"):
                env["observed_at"] = STAMP
    return e


def stable_bytes(export: dict) -> bytes:
    """``stable`` serialised deterministically — what an equality assertion compares."""
    return json.dumps(stable(export), sort_keys=True).encode()
