-- Supervisorly schema — SQLite is the source of truth (D-026).
-- The DB is binary and never committed; the JSON export is the diffable view.
-- CHECK constraints encode the design's enums so an invalid state can't be
-- written silently. Everything is CREATE ... IF NOT EXISTS so migration is
-- idempotent.

PRAGMA foreign_keys = ON;

-- ── meta ────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS meta (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

-- ── SearchPlan (D-045) ────────────────────────────────────────────────────────
-- The interpreted intent that drives a search. Produced by the orchestrator
-- (Claude) inline; consumed by every deterministic tool. Nothing expensive runs
-- until confirmed_by_user = 1.
CREATE TABLE IF NOT EXISTS search_plan (
  plan_id                 TEXT PRIMARY KEY,
  applicant_id            TEXT,
  countries_json          TEXT NOT NULL DEFAULT '[]',
  field                   TEXT,
  subfield                TEXT,
  intent_kind             TEXT NOT NULL
    CHECK (intent_kind IN ('training','pre_master','pre_phd','mentor','master','phd','postdoc')),
  resolved_topic_terms_json      TEXT NOT NULL DEFAULT '[]',  -- generated (D-038)
  resolved_topic_ids_json        TEXT NOT NULL DEFAULT '[]',  -- OpenAlex topic IDs (D-058)
  resolved_venues_json           TEXT NOT NULL DEFAULT '[]',
  target_opportunity_kinds_json  TEXT NOT NULL DEFAULT '[]',
  target_source_types_json       TEXT NOT NULL DEFAULT '[]',
  excluded_source_types_json     TEXT NOT NULL DEFAULT '[]',
  hit_criteria            TEXT,
  languages_json          TEXT NOT NULL DEFAULT '[]',
  university_mode         TEXT NOT NULL DEFAULT 'all'
    CHECK (university_mode IN ('all','prioritise','only')),
  universities_json       TEXT NOT NULL DEFAULT '[]',
  confirmed_by_user       INTEGER NOT NULL DEFAULT 0 CHECK (confirmed_by_user IN (0,1)),
  created_at              TEXT NOT NULL
);

-- ── Run (D-029, D-049) ────────────────────────────────────────────────────────
-- One invocation of the pipeline. Resumability comes from SELECT on this, not an
-- agent's memory. finalized_with_open_gaps is the "student never returned the
-- Phase-3 Markdown" terminal state (D-049). 'cancelled' (schema v3) is the
-- cooperative-stop terminal state: the run halted between targets on request and
-- exported its partials honestly — completed-target claims persist, so a fresh
-- run with resume picks up the remainder (D-029).
CREATE TABLE IF NOT EXISTS run (
  run_id        TEXT PRIMARY KEY,
  plan_id       TEXT REFERENCES search_plan(plan_id),
  status        TEXT NOT NULL
    CHECK (status IN (
      'planning','enumerating','signalling','deep_diving','gap_filling',
      'awaiting_human_input','scoring','finalized','finalized_with_open_gaps',
      'failed','cancelled'
    )),
  budget_tokens INTEGER,
  budget_spent  INTEGER NOT NULL DEFAULT 0,
  counts_json   TEXT NOT NULL DEFAULT '{}',   -- {enumerated, shortlisted, deep_dived, gaps_open}
  started_at    TEXT NOT NULL,
  updated_at    TEXT NOT NULL,
  finalized_at  TEXT
);

-- ── Task ──────────────────────────────────────────────────────────────────────
-- The unit of resumable work: one (target × stage). A crashed run resumes by
-- re-querying incomplete tasks.
CREATE TABLE IF NOT EXISTS task (
  task_id     TEXT PRIMARY KEY,
  run_id      TEXT NOT NULL REFERENCES run(run_id),
  target_kind TEXT NOT NULL CHECK (target_kind IN ('institution','unit','person')),
  target_ref  TEXT NOT NULL,
  stage       TEXT NOT NULL
    CHECK (stage IN ('enumerate','signal','deep_dive','gap_fill','roster_enumerate')),
  phase       TEXT NOT NULL DEFAULT 'structured'
    CHECK (phase IN ('structured','browse','human')),
  status      TEXT NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending','running','done','blocked','awaiting_human','abandoned')),
  attempts    INTEGER NOT NULL DEFAULT 0,
  last_error  TEXT,
  updated_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_task_run_status ON task(run_id, status);

-- ── Checkpoint ────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS checkpoint (
  checkpoint_id TEXT PRIMARY KEY,
  run_id        TEXT NOT NULL REFERENCES run(run_id),
  stage         TEXT NOT NULL,
  cursor        TEXT,                 -- opaque resume position
  created_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_checkpoint_run ON checkpoint(run_id, created_at);

-- ── ExtractionCache (cost §3b-i) ──────────────────────────────────────────────
-- The dominant cost lever: if the (normalised) page and the prompt are unchanged,
-- the extraction is not re-run. The 4-tuple is the unique key.
-- Keyed per ENTITY as well as content: two different professors whose pages happen to have
-- identical normalised content must each be extracted (a content-only key would short-circuit
-- the second and leave it with no claims — dishonestly 'never_attempted').
CREATE TABLE IF NOT EXISTS extraction_cache (
  cache_id              TEXT PRIMARY KEY,
  entity_kind           TEXT NOT NULL DEFAULT 'person',
  entity_id             TEXT NOT NULL DEFAULT '',
  snapshot_content_hash TEXT NOT NULL,
  prompt_version        TEXT NOT NULL,
  model_id              TEXT NOT NULL,
  schema_version        TEXT NOT NULL,
  result_refs_json      TEXT NOT NULL DEFAULT '[]',  -- claim_ids this extraction produced
  created_at            TEXT NOT NULL,
  UNIQUE (entity_kind, entity_id, snapshot_content_hash, prompt_version, model_id, schema_version)
);

-- ── WebSource + Snapshot pointer ──────────────────────────────────────────────
-- Snapshots live on disk addressed by content hash; the DB holds the pointer.
-- 'agent_browser' (D-064) is the human-session browser tier: text extracted in-page
-- by the agent and ingested via `ingest-page`; robots was never consulted, so
-- robots_allowed stays NULL (honesty — same convention as 'human_assisted').
CREATE TABLE IF NOT EXISTS web_source (
  source_id     TEXT PRIMARY KEY,
  url           TEXT NOT NULL,
  canonical_url TEXT,
  fetched_at    TEXT,
  http_status   INTEGER,
  snapshot_hash TEXT,                 -- normalised-content hash (cost §3b-i)
  source_tier   TEXT
    CHECK (source_tier IS NULL OR source_tier IN
      ('official_api','official_institutional','cris','registry','open_social',
       'community_unverified','human_assisted','agent_browser')),
  robots_allowed INTEGER CHECK (robots_allowed IS NULL OR robots_allowed IN (0,1))
);
CREATE INDEX IF NOT EXISTS idx_web_source_hash ON web_source(snapshot_hash);

-- ── Claim (D-010, D-046, D-047) ───────────────────────────────────────────────
-- Every field is a Claim. A claim whose quote is not found in its snapshot is
-- rejected before it reaches here (enforced in code). `state` is the four-state
-- value envelope (D-046); `confidence` is the canonical enum (D-047).
CREATE TABLE IF NOT EXISTS claim (
  claim_id       TEXT PRIMARY KEY,
  entity_kind    TEXT NOT NULL,
  entity_id      TEXT NOT NULL,
  field          TEXT NOT NULL,
  state          TEXT NOT NULL DEFAULT 'value'
    CHECK (state IN ('value','searched_absent','never_attempted','blocked')),
  value          TEXT,                -- JSON-encoded; NULL when state != 'value'
  quote          TEXT,                -- verbatim supporting sentence
  source_id      TEXT REFERENCES web_source(source_id),
  snapshot_hash  TEXT,
  quote_offsets  TEXT,                -- [start,end] into normalised extracted text
  observed_at    TEXT,
  extractor_agent   TEXT,             -- 'deterministic' | agent name | 'human-assisted (Claude for Chrome)'
  extractor_model   TEXT,
  prompt_version    TEXT,
  schema_version    TEXT,
  confidence     TEXT
    CHECK (confidence IS NULL OR confidence IN
      ('quoted_official','derived','inferred','unconfirmed','action_needed')),
  superseded_by  TEXT REFERENCES claim(claim_id),
  created_at     TEXT NOT NULL,
  -- T-1 (schema v5). A DISPLAY translation travelling BESIDE the verbatim quote, never
  -- replacing it. `quote` stays in the SOURCE language because that is what the D-010 gate
  -- verifies against the snapshot; storing an English quote for an Arabic page would
  -- manufacture a sentence the page never contained — fabricating evidence with good
  -- intentions. `record_claim` never verifies against these columns, and a test pins it.
  -- Both nullable and added to an existing table by `_add_missing_columns` in db.py, which
  -- is idempotent (plain ALTER in this file would fail on the second migrate).
  quote_translated TEXT,
  translated_by    TEXT
);
CREATE INDEX IF NOT EXISTS idx_claim_entity ON claim(entity_kind, entity_id, field);

-- ── Conflict (D-010) ──────────────────────────────────────────────────────────
-- When two sources disagree, both claims are kept and the disagreement recorded.
CREATE TABLE IF NOT EXISTS conflict (
  conflict_id      TEXT PRIMARY KEY,
  entity_kind      TEXT NOT NULL,
  entity_id        TEXT NOT NULL,
  field            TEXT NOT NULL,
  claim_a          TEXT NOT NULL REFERENCES claim(claim_id),
  claim_b          TEXT NOT NULL REFERENCES claim(claim_id),
  resolution_state TEXT NOT NULL DEFAULT 'open'
    CHECK (resolution_state IN ('open','resolved_a','resolved_b','both_stand')),
  created_at       TEXT NOT NULL
);

-- ── Spine stubs (fleshed out in later phases) ─────────────────────────────────
-- Nothing is keyed on a display name (D-030): internal id first, external ids as
-- evidence, name_variants retained.
CREATE TABLE IF NOT EXISTS institution (
  institution_id TEXT PRIMARY KEY,
  ror_id         TEXT,
  openalex_id    TEXT,
  name           TEXT,
  country_code   TEXT,
  homepage       TEXT
);
CREATE TABLE IF NOT EXISTS unit (
  unit_id        TEXT PRIMARY KEY,
  institution_id TEXT REFERENCES institution(institution_id),
  name           TEXT,
  kind           TEXT,               -- department|faculty|school|institute|chair
  directory_url  TEXT,
  coverage_note  TEXT                -- e.g. LOGIN_WALL (D-052)
);
CREATE TABLE IF NOT EXISTS person (
  person_id       TEXT PRIMARY KEY,
  unit_id         TEXT REFERENCES unit(unit_id),
  orcid           TEXT,
  openalex_id     TEXT,
  dblp_id         TEXT,
  display_name    TEXT,
  name_variants_json TEXT NOT NULL DEFAULT '[]',
  homepage        TEXT,
  disambig_risk   TEXT               -- null|low|high (D-030/D-057)
);

-- ── PhaseLedger (CC-1, D-037) ─────────────────────────────────────────────────
-- What each phase attempted, what it reached, and what it skipped and WHY. Purely
-- additive (a new table, no CHECK widening), so `migrate` needs no rebuild path.
--
-- The point is coverage honesty: "the dashboard looks thin" must be an answerable
-- question. A phase that reached nothing still writes a row — absence of a row means
-- the phase never ran at all, which is itself a different and visible answer. Rows
-- are append-only in insertion order; `rowid` is the ordering, so a phase that runs
-- twice (resume) shows both attempts rather than overwriting the first.
CREATE TABLE IF NOT EXISTS phase_ledger (
  ledger_id  TEXT PRIMARY KEY,
  run_id     TEXT NOT NULL REFERENCES run(run_id),
  phase      TEXT NOT NULL,          -- 'p0', 'p1', 'discovery', … free text by design
  attempted  INTEGER NOT NULL DEFAULT 0,
  reached    INTEGER NOT NULL DEFAULT 0,
  skipped    INTEGER NOT NULL DEFAULT 0,
  reason     TEXT,                   -- why the skipped ones were skipped; NULL only if skipped=0
  seconds    REAL NOT NULL DEFAULT 0,
  tokens     INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL
);
-- run_id only: an index entry already carries the rowid as its payload, and SQLite
-- refuses `rowid` as an indexed column outright — so this IS the (run_id, rowid)
-- ordering the reader wants.
CREATE INDEX IF NOT EXISTS idx_phase_ledger_run ON phase_ledger(run_id);
