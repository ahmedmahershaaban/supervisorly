"""The consumer half of the browser seam (D-064) — an agent-read page closes gaps.

``browser_rung.ingest_page`` only *stores* an agent-extracted page. This module is the
engine half that makes the SKILL recipe's "the deterministic engine takes it from there"
true: it runs the pipeline's own deterministic signal extractors over the stored snapshot,
records each result through the same quote-verified evidence path the deep-dive uses
(D-010 intact, human-assisted values protected), closes the entity's ``awaiting_human``
gap-fill tasks, and recomputes the run status (D-049). This is what lets a walled-social
gap close via ``ingest-page`` — until now only the classic MD-grammar rung could close one.

Everything here reuses ``pipeline``'s public wrappers — no extraction or precedence logic
is duplicated.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from .. import pipeline
from ..model import runs
from .browser_rung import ingest_page
from .snapshot import SnapshotStore

#: Run statuses a fill is allowed to recompute. A run still mid-flight (``deep_diving``…)
#: is never flipped to a terminal status by a gap-fill arriving out of band.
_FINALIZED_STATUSES = ("finalized", "finalized_with_open_gaps")


def fill_from_browser_page(
    conn: sqlite3.Connection,
    snap_root: str | Path,
    *,
    run_id: str,
    entity_kind: str,
    entity_id: str,
    final_url: str,
    text: str,
    title: str | None = None,
) -> dict:
    """Store an agent-read page and fill the entity's signal fields from it.

    Returns ``{"snapshot_hash", "source_id", "bytes", "fields", "tasks_closed",
    "run_status", "rejected"}`` where ``fields`` maps each of ``pipeline.BROWSER_FILL_FIELDS`` to
    ``value`` / ``searched_absent`` / ``kept_human`` (a human-assisted value was
    protected) / ``rejected`` (the D-010 quote gate refused it — see ``rejected``).

    Raises ``ValueError`` on an unknown run or a non-``person`` entity kind (the
    deep-dive machinery is person-based); the CLI turns these into exit 2.
    """
    if entity_kind != "person":
        raise ValueError(f"unsupported entity kind {entity_kind!r} — "
                         "deep-dive targets are 'person'")
    run = runs.get_run(conn, run_id)
    if run is None:
        raise ValueError(f"no such run: {run_id}")

    stored = ingest_page(conn, snap_root, final_url=final_url, text=text, title=title)
    html = SnapshotStore(snap_root).load(stored["snapshot_hash"])

    fields: dict[str, str] = {}
    rejected: dict[str, str] = {}
    for field, found in pipeline.run_signal_extractors(html).items():
        rec = pipeline.record_field_evidence(
            conn, entity_id, field, found,
            src_id=stored["source_id"], snapshot_hash=stored["snapshot_hash"], html=html)
        if found:
            if rec is not None and rec.ok:
                fields[field] = "value"
            else:
                fields[field] = "rejected"
                rejected[field] = rec.rejected if rec is not None else "record failed"
        else:
            # None back means a human-assisted value head was protected (D-043/D-046).
            fields[field] = "searched_absent" if rec is not None and rec.ok else "kept_human"

    tasks_closed = 0
    if not rejected:
        # The human-rung read this page was tasked with is done — its outcome (value or an
        # honest searched_absent) is recorded either way. A D-010 rejection instead means
        # something is off: fail loud, leave the gap open, change nothing else.
        for t in runs.tasks_for_run(conn, run_id):
            if (t["target_kind"] == entity_kind and t["target_ref"] == entity_id
                    and t["stage"] == "gap_fill"
                    and t["status"] in runs.INCOMPLETE_TASK_STATUSES):
                runs.set_task_status(
                    conn, t["task_id"], "done",
                    last_error=f"filled via ingest-page from {final_url} "
                               f"(agent_browser snapshot {stored['snapshot_hash'][:12]})")
                tasks_closed += 1

    run_status = run["status"]
    if run_status in _FINALIZED_STATUSES:
        new_status = pipeline.recompute_run_status(conn, run_id)
        if new_status != run_status:
            runs.set_run_status(conn, run_id, new_status)
            run_status = new_status

    return {
        "snapshot_hash": stored["snapshot_hash"],
        "source_id": stored["source_id"],
        "bytes": stored["bytes"],
        "fields": fields,
        "tasks_closed": tasks_closed,
        "run_status": run_status,
        "rejected": rejected,
    }
