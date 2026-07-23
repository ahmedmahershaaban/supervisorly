# Build log

One short entry per milestone: what was built, what was run, what passed, what changed.
Newest at the bottom. Branch: `build/v1`.

---

## round 0 — design baseline (commit `9f07e31`)

The completed `docs/` design set, integrity-checked. No code. Starting point for implementation.

## round A — scaffold + schema (Phase A)

**Built:**
- `pyproject.toml` — package `supervisorly`, src layout, `[dev]` = pytest, module + console entry.
- `src/supervisorly/` — `__init__` (PRODUCT_NAME, version), `__main__` (`python -m supervisorly`),
  `cli.py` (`version`, `init-db`).
- `src/supervisorly/model/` — `schema.sql` (SQLite source of truth, D-026): the pipeline-state
  entities (Run/Task/Checkpoint/ExtractionCache/SearchPlan), the provenance spine
  (Claim/WebSource/Conflict) with the four-state envelope (D-046) and confidence enum (D-047), and
  spine stubs (Institution/Unit/Person). CHECK constraints encode the design's enums.
  `db.py` (connect + idempotent migrate), `runs.py` (Run/Task/Checkpoint state machine, D-029/D-049).
- `tests/` — `test_state_machine.py`, `test_cli.py`.
- `README.md`, this log; `.gitignore` extended to never commit `*.sqlite` (D-005).

**Ran:** `python -m pytest` → **9 passed** in a clean `.venv`. CLI `version` and `init-db` (incl.
nested-path) smoke-tested.

**Fixed (self-test caught it):** `init-db` failed with "unable to open database file" when the
parent directory didn't exist — sqlite3 won't create it. Now creates parents; regression test added.

**Environment note:** on this Windows machine, `pip install -e .` into the **global** Python 3.12
fails writing the `supervisorly.exe` console script into `C:\Python312\Scripts` (a permissions/path
quirk). Resolved by using a project **`.venv`** — the venv's Scripts dir is writable, install is
clean, and `python -m supervisorly` works regardless. The venv is the documented install path
(README) and what the clean-room verification (§4 step 6) will use.

**DoD (Phase A):** met — DB migrates idempotently; Run/Task state machine round-trips through
`awaiting_human_input` and `finalized_with_open_gaps`; resume via `incomplete_tasks`; the
ExtractionCache 4-tuple is unique.

## round B1 — Phase-3 Markdown grammar (commit `0f524d7`)

**Built:** `extract/md_grammar.py` — the single source of truth for the human-return format
(D-051): `parse`, `emit` (lossless), `to_claim_dicts` (extractor=human-assisted, D-043). A value
must cite a `source_url` (D-010); `searched_absent` records honest nulls (D-046). Contract doc.
**Ran:** pytest → **16 passed**. **DoD:** met — fixture round-trips losslessly; malformed input
fails loud.

## round B2 — JSON export contract (commit pending)

**Built:** `export/json_export.py` — `build_export` (claims → four-state envelopes + generic
field descriptors) and `validate_export` (D-046). Judgement/PII fields (`exportable: false`)
never serialise (D-024); every `value` cites a source (D-010); a professor with no claims is
still exported, all fields `never_attempted` (D-037). Contract doc.
**Ran:** pytest → **22 passed**. **DoD (Phase B contracts):** met — MD round-trips into claims;
the JSON validates against a worked example and rejects leaks.

## round C1 — fetch primitives: normalisation, cache hash, quote verification, robots (commit pending)

**Built:** `fetch/normalize.py` — `main_text` (faithful content, keeps dates, for quote
verification), `content_hash` (volatile tokens masked → stable cache key, cost §3b-i),
`quote_in_snapshot` (the anti-hallucination primitive, D-010). `fetch/robots.py` — `is_allowed`,
fail-closed (D-019/D-039), honest User-Agent. Pure stdlib (no HTML-parser dep) — testable offline.
**Ran:** pytest → **29 passed**, incl. the edge-case-matrix rows: *content hash stable across
volatile chrome* and *quote-in-snapshot rejects a fabricated quote*.

**Remaining phases:** C2 (transport/cassettes + fetcher 3-phase + snapshot store + HTTP cache),
D (LLM agents + wiring quote-verification into extraction), E (scoring: intent gates, topic-ID
match, works reconciliation), F (dashboard), G (human-rung wiring + roster-enumeration), H (eval
set), I (self-run), J (refine), then clean-room verify. SKILL.md + agent definition files still to write.
