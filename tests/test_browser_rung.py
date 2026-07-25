"""B1: the browser ingest seam (D-064). Agent-extracted page TEXT becomes a normal
content-addressed snapshot under tier ``agent_browser``; the D-010 quote gate runs on
it unchanged. No network — synthetic extracted text only."""

import sqlite3
from pathlib import Path

import pytest

from supervisorly.cli import main
from supervisorly.fetch.browser_rung import ingest_page
from supervisorly.fetch.normalize import quote_in_snapshot
from supervisorly.fetch.snapshot import SnapshotStore
from supervisorly.model.claims import record_claim
from supervisorly.model.db import connect, open_db

PAGE_TEXT = (
    "Professor Jane Doe — I am recruiting PhD students for Fall 2027. "
    "Research interests: differentiable rendering, neural fields. "
    "Applicants should have strong math skills & curiosity."
)
FINAL_URL = "https://u.edu/people/jane"


def test_ingest_stores_snapshot_retrievable_by_the_existing_reader(tmp_path):
    conn = open_db(tmp_path / "run.sqlite")
    res = ingest_page(conn, tmp_path / "snaps", final_url=FINAL_URL, text=PAGE_TEXT)
    assert set(res) == {"snapshot_hash", "source_id", "bytes", "final_url"}
    assert res["bytes"] == len(PAGE_TEXT.encode("utf-8"))
    # the existing snapshot store reads it back, and the text survives main_text
    stored = SnapshotStore(tmp_path / "snaps").load(res["snapshot_hash"])
    assert quote_in_snapshot("I am recruiting PhD students for Fall 2027", stored)


def test_source_is_agent_browser_tier_under_the_final_url_with_robots_unset(tmp_path):
    conn = open_db(tmp_path / "run.sqlite")
    res = ingest_page(conn, tmp_path / "snaps", final_url=FINAL_URL, text=PAGE_TEXT)
    row = conn.execute(
        "SELECT url, source_tier, robots_allowed, snapshot_hash FROM web_source "
        "WHERE source_id=?", (res["source_id"],)).fetchone()
    assert row["url"] == FINAL_URL
    assert row["source_tier"] == "agent_browser"
    assert row["robots_allowed"] is None      # robots never consulted — honesty
    assert row["snapshot_hash"] == res["snapshot_hash"]


def test_claim_with_a_quote_from_the_text_passes_the_d010_gate(tmp_path):
    conn = open_db(tmp_path / "run.sqlite")
    res = ingest_page(conn, tmp_path / "snaps", final_url=FINAL_URL, text=PAGE_TEXT)
    stored = SnapshotStore(tmp_path / "snaps").load(res["snapshot_hash"])
    rec = record_claim(
        conn, entity_kind="person", entity_id="p1", field="recruiting_signal",
        value="recruiting", quote="I am recruiting PhD students for Fall 2027",
        source_id=res["source_id"], snapshot_hash=res["snapshot_hash"],
        snapshot_html=stored)
    assert rec.ok, rec.rejected


def test_claim_with_a_quote_not_in_the_text_is_rejected(tmp_path):
    conn = open_db(tmp_path / "run.sqlite")
    res = ingest_page(conn, tmp_path / "snaps", final_url=FINAL_URL, text=PAGE_TEXT)
    stored = SnapshotStore(tmp_path / "snaps").load(res["snapshot_hash"])
    rec = record_claim(
        conn, entity_kind="person", entity_id="p1", field="recruiting_signal",
        value="recruiting", quote="fully funded positions available for everyone",
        source_id=res["source_id"], snapshot_hash=res["snapshot_hash"],
        snapshot_html=stored)
    assert not rec.ok and "D-010" in rec.rejected


def test_html_metacharacters_in_text_survive_the_round_trip(tmp_path):
    """Regression guard for the snapshot shell: a '<tag>'-looking fragment in the
    extracted text must not be misparsed as markup on read-back."""
    text = "Use x < 5 and the <b>bold</b> idea carefully."
    conn = open_db(tmp_path / "run.sqlite")
    res = ingest_page(conn, tmp_path / "snaps", final_url=FINAL_URL, text=text)
    stored = SnapshotStore(tmp_path / "snaps").load(res["snapshot_hash"])
    assert quote_in_snapshot("x < 5 and the <b>bold</b> idea", stored)


def test_two_pages_with_the_same_text_dedupe_to_one_snapshot(tmp_path):
    conn = open_db(tmp_path / "run.sqlite")
    a = ingest_page(conn, tmp_path / "snaps", final_url="https://a.edu/p", text=PAGE_TEXT)
    b = ingest_page(conn, tmp_path / "snaps", final_url="https://b.edu/q", text=PAGE_TEXT)
    assert a["snapshot_hash"] == b["snapshot_hash"]   # content-addressed
    assert a["source_id"] != b["source_id"]           # provenance stays per-page


def test_blank_text_or_url_is_a_value_error(tmp_path):
    conn = open_db(tmp_path / "run.sqlite")
    with pytest.raises(ValueError):
        ingest_page(conn, tmp_path / "snaps", final_url=FINAL_URL, text="   \n ")
    with pytest.raises(ValueError):
        ingest_page(conn, tmp_path / "snaps", final_url=" ", text=PAGE_TEXT)


# ── the 60 KiB cap is JS-side; Python accepts staged text as-is ───────────────
def test_js_cap_constant_is_pinned():
    """The cap lives in page_extract.js (enforced in-page, D-064). Pin the constant
    and the truncation marker so a silent JS-side change fails here."""
    js = (Path(__file__).resolve().parents[1] / "src" / "supervisorly" / "extract"
          / "page_extract.js").read_text(encoding="utf-8")
    assert "MAX_TEXT_BYTES: 61440" in js          # 60 * 1024
    assert '"\\n[truncated]"' in js
    assert "scrollBy" in js                        # D-065 scroll mode still present


def test_oversized_text_is_stored_as_is(tmp_path):
    """Capping is the JS extractor's job; the Python seam stores what it is given."""
    big = "word " * 20000                          # ~100 KB of text
    conn = open_db(tmp_path / "run.sqlite")
    res = ingest_page(conn, tmp_path / "snaps", final_url=FINAL_URL, text=big)
    assert res["bytes"] == len(big.encode("utf-8"))


# ── schema migration: a v1 DB (pre-'agent_browser' CHECK) keeps working ───────
V1_WEB_SOURCE_DDL = """
CREATE TABLE web_source (
  source_id     TEXT PRIMARY KEY,
  url           TEXT NOT NULL,
  canonical_url TEXT,
  fetched_at    TEXT,
  http_status   INTEGER,
  snapshot_hash TEXT,
  source_tier   TEXT
    CHECK (source_tier IS NULL OR source_tier IN
      ('official_api','official_institutional','cris','registry','open_social',
       'community_unverified','human_assisted')),
  robots_allowed INTEGER CHECK (robots_allowed IS NULL OR robots_allowed IN (0,1))
);
CREATE INDEX idx_web_source_hash ON web_source(snapshot_hash);
"""


def test_v1_db_is_rebuilt_so_agent_browser_inserts_and_data_survives(tmp_path):
    db = tmp_path / "old.sqlite"
    conn = connect(db)
    conn.executescript(V1_WEB_SOURCE_DDL)
    conn.execute("INSERT INTO web_source(source_id, url, source_tier) "
                 "VALUES('src_keep', 'https://u.edu/old', 'human_assisted')")
    conn.commit()
    conn.close()

    conn = open_db(db)    # migrate: stale CHECK → table rebuild
    res = ingest_page(conn, tmp_path / "snaps", final_url=FINAL_URL, text=PAGE_TEXT)
    assert res["source_id"]
    rows = {r["source_id"]: r["source_tier"] for r in
            conn.execute("SELECT source_id, source_tier FROM web_source")}
    assert rows["src_keep"] == "human_assisted"           # prior data preserved
    assert rows[res["source_id"]] == "agent_browser"
    # the rebuild must not lose the snapshot-hash index (renamed away with the old table)
    idx = {r["name"] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index'")}
    assert "idx_web_source_hash" in idx
    conn.close()
    open_db(db).close()   # and a second migrate is a clean no-op


# ── F1: claim-bearing v1 DBs migrate atomically, and a crashed rebuild recovers ─
def _v1_db_with_claim(db_path):
    """A v1 (pre-'agent_browser') DB with a web_source row AND a claim referencing
    it — the shape that crashed the pre-fix rebuild (FK constraint failed)."""
    from supervisorly.model import db as db_module

    conn = connect(db_path)
    conn.executescript(db_module._load_schema())   # every other table, incl. claim
    conn.execute("DROP TABLE web_source")          # ... then swap in the v1 table
    conn.executescript(V1_WEB_SOURCE_DDL)
    conn.execute("INSERT INTO web_source(source_id, url, source_tier) "
                 "VALUES('src_a', 'https://u.edu/a', 'official_institutional')")
    conn.execute("INSERT INTO claim(claim_id, entity_kind, entity_id, field, state, "
                 "value, quote, source_id, created_at) VALUES('c1', 'person', 'p1', "
                 "'recruiting_signal', 'value', '\"recruiting\"', 'I am recruiting', "
                 "'src_a', '2026-01-01T00:00:00+00:00')")
    conn.commit()
    conn.close()


def test_v1_db_with_claims_migrates_and_provenance_survives(tmp_path):
    from supervisorly.model.claims import claims_for

    db = tmp_path / "old.sqlite"
    _v1_db_with_claim(db_path=db)

    conn = open_db(db)        # must not raise; both rows must survive
    rows = {r["source_id"]: r["url"] for r in
            conn.execute("SELECT source_id, url FROM web_source")}
    assert rows == {"src_a": "https://u.edu/a"}
    # the claim's provenance still resolves through claims_for (D-010)
    claim = claims_for(conn, "person", "p1")[0]
    assert claim["source_url"] == "https://u.edu/a"
    # nothing stranded in a temp table
    tables = {r["name"] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    assert "web_source_old" not in tables
    # FK enforcement is ON after migrate (open_db/connect set it; the rebuild must
    # restore it after its foreign_keys=OFF phase)
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO claim(claim_id, entity_kind, entity_id, field, "
                     "source_id, created_at) VALUES('c2', 'person', 'p1', 'f', "
                     "'no_such_source', '2026-01-01T00:00:00+00:00')")
    conn.close()

    conn = open_db(db)        # double migration is a no-op — rows still intact
    assert conn.execute("SELECT COUNT(*) FROM web_source").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM claim").fetchone()[0] == 1
    conn.close()


def test_leftover_web_source_old_from_a_crashed_rebuild_is_recovered(tmp_path):
    """The half-applied state a pre-fix crash left behind: an empty v2 web_source,
    the original rows stranded in web_source_old, and claim's stored FK clause
    rewritten to the temp name (the old code renamed with FK enforcement ON).
    migrate must complete the rebuild — rows merged back, temp table dropped, the
    dangling FK clause repaired — instead of skipping it as already-migrated."""
    from supervisorly.model import db as db_module
    from supervisorly.model.claims import claims_for

    db = tmp_path / "crashed.sqlite"
    _v1_db_with_claim(db_path=db)
    conn = connect(db)                          # FK ON, like the pre-fix code path
    conn.execute("DROP INDEX IF EXISTS idx_web_source_hash")
    conn.execute("ALTER TABLE web_source RENAME TO web_source_old")
    conn.executescript(db_module._load_schema())   # empty v2 web_source recreated
    conn.commit()                               # ... then the old code crashed here
    assert "web_source_old" in conn.execute(
        "SELECT sql FROM sqlite_master WHERE name='claim'").fetchone()["sql"]
    conn.close()

    conn = open_db(db)        # recovery, not a skip
    rows = {r["source_id"]: r["url"] for r in
            conn.execute("SELECT source_id, url FROM web_source")}
    assert rows == {"src_a": "https://u.edu/a"}
    assert claims_for(conn, "person", "p1")[0]["source_url"] == "https://u.edu/a"
    tables = {r["name"] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    assert "web_source_old" not in tables
    # claim's FK clause points back at web_source — new claims insert cleanly
    conn.execute("INSERT INTO claim(claim_id, entity_kind, entity_id, field, "
                 "source_id, created_at) VALUES('c2', 'person', 'p1', 'f2', "
                 "'src_a', '2026-01-02T00:00:00+00:00')")
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    conn.close()


# ── CLI: ingest-page ──────────────────────────────────────────────────────────
def _staging(tmp_path, text=PAGE_TEXT):
    f = tmp_path / "browser_staging" / "page.txt"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(text, encoding="utf-8")
    return f


def test_cli_ingest_page_happy_path(tmp_path, capsys):
    f = _staging(tmp_path)
    db = tmp_path / "out" / "run.sqlite"       # nested: parent dirs must be created
    rc = main(["ingest-page", "--url", FINAL_URL, "--file", str(f), "--db", str(db)])
    assert rc == 0
    out = capsys.readouterr().out
    assert out.startswith("ingested ") and " snap " in out and " source " in out
    out.encode("ascii")                        # console contract: ASCII-safe
    conn = sqlite3.connect(db)
    tier = conn.execute("SELECT source_tier FROM web_source").fetchone()[0]
    assert tier == "agent_browser"
    assert (tmp_path / "out" / ".cache" / "snaps").is_dir()   # default snap root


def test_cli_ingest_page_missing_file_exits_2(tmp_path, capsys):
    rc = main(["ingest-page", "--url", FINAL_URL,
               "--file", str(tmp_path / "nope.txt"), "--db", str(tmp_path / "r.sqlite")])
    assert rc == 2
    assert "not found" in capsys.readouterr().out


def test_cli_ingest_page_empty_text_exits_2(tmp_path, capsys):
    f = _staging(tmp_path, text="  \n\t ")
    rc = main(["ingest-page", "--url", FINAL_URL, "--file", str(f),
               "--db", str(tmp_path / "r.sqlite")])
    assert rc == 2
    assert "empty" in capsys.readouterr().out


def test_cli_ingest_page_invalid_url_exits_2(tmp_path, capsys):
    f = _staging(tmp_path)
    rc = main(["ingest-page", "--url", "notaurl", "--file", str(f),
               "--db", str(tmp_path / "r.sqlite")])
    assert rc == 2
    assert "invalid --url" in capsys.readouterr().out


# ── F2: non-UTF-8 staging files — a loud exit 2, never a traceback ────────────
def test_cli_ingest_page_cp1252_exits_2_with_an_actionable_message(tmp_path, capsys):
    f = tmp_path / "page.txt"
    f.write_bytes("Café naïve — recruits".encode("cp1252"))
    rc = main(["ingest-page", "--url", FINAL_URL, "--file", str(f),
               "--db", str(tmp_path / "r.sqlite")])
    assert rc == 2
    out = capsys.readouterr()
    assert "not UTF-8" in out.out and "UTF-8" in out.out
    assert out.err == ""                        # no traceback
    out.out.encode("ascii")                     # console contract: ASCII-safe


def test_cli_ingest_page_utf16_with_bom_is_decoded(tmp_path, capsys):
    """UTF-16 with a BOM is the PowerShell 5.1 `>` / Out-File default on Windows —
    accept it rather than punish the platform's default."""
    f = tmp_path / "page.txt"
    f.write_text(PAGE_TEXT, encoding="utf-16")           # BOM + LE
    db = tmp_path / "r.sqlite"
    rc = main(["ingest-page", "--url", FINAL_URL, "--file", str(f), "--db", str(db)])
    assert rc == 0
    out = capsys.readouterr().out
    assert out.startswith("ingested ")
    out.encode("ascii")
    conn = sqlite3.connect(db)
    snap = conn.execute("SELECT snapshot_hash FROM web_source").fetchone()[0]
    conn.close()
    stored = SnapshotStore(db.parent / ".cache" / "snaps").load(snap)
    assert quote_in_snapshot("I am recruiting PhD students for Fall 2027", stored)


# ── F3: a BOM is framing, not content ──────────────────────────────────────────
def test_cli_ingest_page_bom_only_file_is_empty(tmp_path, capsys):
    f = tmp_path / "page.txt"
    f.write_bytes(b"\xef\xbb\xbf")                       # UTF-8 BOM, nothing else
    rc = main(["ingest-page", "--url", FINAL_URL, "--file", str(f),
               "--db", str(tmp_path / "r.sqlite")])
    assert rc == 2
    assert "empty" in capsys.readouterr().out


def test_cli_ingest_page_bom_plus_text_ingests_normally(tmp_path, capsys):
    f = tmp_path / "page.txt"
    f.write_bytes(b"\xef\xbb\xbf" + PAGE_TEXT.encode("utf-8"))
    db = tmp_path / "r.sqlite"
    rc = main(["ingest-page", "--url", FINAL_URL, "--file", str(f), "--db", str(db)])
    assert rc == 0
    conn = sqlite3.connect(db)
    snap = conn.execute("SELECT snapshot_hash FROM web_source").fetchone()[0]
    conn.close()
    stored = SnapshotStore(db.parent / ".cache" / "snaps").load(snap)
    assert quote_in_snapshot("I am recruiting PhD students for Fall 2027", stored)


def test_ingest_page_strips_a_leading_bom_before_the_empty_check(tmp_path):
    conn = open_db(tmp_path / "run.sqlite")
    with pytest.raises(ValueError):
        ingest_page(conn, tmp_path / "snaps", final_url=FINAL_URL, text="\ufeff")
    res = ingest_page(conn, tmp_path / "snaps", final_url=FINAL_URL,
                      text="\ufeff" + PAGE_TEXT)
    assert res["bytes"] == len(PAGE_TEXT.encode("utf-8"))   # BOM not stored/counted
