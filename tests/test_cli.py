"""CLI smoke + regressions."""

import sqlite3

from supervisorly.cli import main


def test_version(capsys):
    assert main(["version"]) == 0
    assert "Supervisorly" in capsys.readouterr().out


def test_init_db_creates_nested_path(tmp_path):
    """Regression: init-db must create the parent directory (sqlite3 won't)."""
    db = tmp_path / "output" / "nested" / "run.sqlite"
    assert main(["init-db", "--db", str(db)]) == 0
    assert db.exists()
    conn = sqlite3.connect(db)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"run", "task", "claim"} <= tables
