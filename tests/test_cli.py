"""CLI smoke + regressions."""

import shutil
import sqlite3
import subprocess

import pytest

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


# ── D-005 guard: committable --out paths warn loudly ───────────────────────────
def _git_repo(tmp_path):
    if shutil.which("git") is None:
        pytest.skip("git binary not available")
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True, capture_output=True)
    (repo / ".gitignore").write_text("/output/\n", encoding="utf-8")
    return repo


def test_scan_out_inside_repo_and_not_ignored_warns(tmp_path, capsys):
    """Regression (audit): .gitignore anchors only /output/, so `scan --out results/x.html`
    writes a committable dashboard full of personal data — the CLI must warn (D-005)."""
    repo = _git_repo(tmp_path)
    out = repo / "results" / "x.html"
    assert main(["scan", "--demo", "--out", str(out)]) == 0   # warns, never refuses
    assert out.exists()
    err = capsys.readouterr().err
    assert "D-005" in err and "git-ignored" in err


def test_scan_out_under_an_ignored_dir_is_silent(tmp_path, capsys):
    repo = _git_repo(tmp_path)
    out = repo / "output" / "x.html"
    assert main(["scan", "--demo", "--out", str(out)]) == 0
    assert "D-005" not in capsys.readouterr().err


def test_scan_out_outside_any_repo_is_silent(tmp_path, capsys):
    out = tmp_path / "elsewhere" / "x.html"   # tmp_path is not a git work tree
    assert main(["scan", "--demo", "--out", str(out)]) == 0
    assert "D-005" not in capsys.readouterr().err
