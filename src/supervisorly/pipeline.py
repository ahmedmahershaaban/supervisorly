"""End-to-end scan orchestration (the deterministic path).

``run_offline`` ties the pieces together — fetch → deterministic signal extraction →
quote-verified claim → export → dashboard — with **no LLM and no network** (cassettes).
This is what the self-run exercises: a full run that, by construction, cannot hallucinate
(every value claim's quote is lifted verbatim from the page and re-verified against the
snapshot, D-010).

The signal tier here is a regex over normalised text — legitimately no-LLM (the design's
"signal tier"). Classifying a candidate sentence into recruiting *state* is the LLM
recruiting-analyst's Stage-2 job; the deterministic tier only surfaces the candidate.
"""

from __future__ import annotations

import re

from .export import dashboard as dash
from .export import json_export as jx
from .fetch.fetcher import Fetcher
from .fetch.normalize import main_text
from .fetch.snapshot import SnapshotStore
from .fetch.transport import Transport
from .model import claims, runs
from .model.db import open_db, utcnow

# a recruiting-related sentence (candidate signal — not a classification)
_RECRUIT = re.compile(
    r"[^.!?]*\b(recruit\w*|looking for|accepting|seeking|opening|join (?:my|the|our) "
    r"(?:lab|group|team)|hiring|taking (?:new )?students?)\b[^.!?]*[.!?]",
    re.IGNORECASE,
)

FIELD_DESCRIPTORS = [
    {"id": "recruiting_signal", "label": "Recruiting signal", "kind": "filter",
     "datatype": "string"},
]


def extract_recruiting_signal(html: str) -> str | None:
    """Return the first recruiting-related sentence in the page's main text, or None."""
    m = _RECRUIT.search(main_text(html))
    return m.group(0).strip() if m else None


def run_offline(plan: dict, targets: list[dict], transport: Transport, snap_root) -> dict:
    """Run a deterministic scan over ``targets`` (each {id, name, url}) using cassettes.

    Returns {run_id, export, html}. The run always finalises with a dashboard — it never
    blocks on the human rung (D-049)."""
    conn = open_db()
    snaps = SnapshotStore(snap_root)
    fetcher = Fetcher(transport, snaps)

    run_id = runs.create_run(conn)
    runs.set_run_status(conn, run_id, "deep_diving")

    for t in targets:
        pid = t["id"]
        task = runs.add_task(conn, run_id, "person", pid, stage="deep_dive")
        res = fetcher.fetch(t["url"])
        if res.ok:
            html = snaps.load(res.snapshot_hash)
            src_id = claims.record_web_source(
                conn, t["url"], snapshot_hash=res.snapshot_hash, http_status=200,
                source_tier="official_institutional", robots_allowed=True,
            )
            sig = extract_recruiting_signal(html)
            if sig:
                claims.record_claim(
                    conn, entity_kind="person", entity_id=pid, field="recruiting_signal",
                    value=sig, quote=sig, source_id=src_id, snapshot_hash=res.snapshot_hash,
                    snapshot_html=html, observed_at=utcnow(), extractor_agent="deterministic",
                    confidence="quoted_official",
                )
            else:
                claims.record_claim(
                    conn, entity_kind="person", entity_id=pid, field="recruiting_signal",
                    state="searched_absent", source_id=src_id, extractor_agent="deterministic",
                )
            runs.set_task_status(conn, task, "done")
        else:
            # a failed/blocked source is an honest 'blocked' state, not a dropped professor
            claims.record_claim(
                conn, entity_kind="person", entity_id=pid, field="recruiting_signal",
                state="blocked", extractor_agent="deterministic",
            )
            runs.set_task_status(conn, task, "blocked", last_error=res.error)

    runs.set_run_status(conn, run_id, "finalized")

    professors = [{"id": t["id"], "name": t.get("name")} for t in targets]
    claims_by_entity = {t["id"]: claims.claims_for(conn, "person", t["id"]) for t in targets}
    export = jx.build_export(
        run_summary={"run_id": run_id, "status": "finalized",
                     "counts": {"enumerated": len(targets)}},
        field_descriptors=FIELD_DESCRIPTORS,
        professors=professors,
        claims_by_entity=claims_by_entity,
        generated_at=utcnow(),
    )
    return {"run_id": run_id, "export": export, "html": dash.build_dashboard(export)}
