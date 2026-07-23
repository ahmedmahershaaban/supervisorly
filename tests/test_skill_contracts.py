"""The skill + agent definition files are the product surface (D-042). A missing
frontmatter field silently breaks the skill, so guard their structure."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / ".claude" / "skills" / "supervisorly" / "SKILL.md"
AGENTS_DIR = ROOT / ".claude" / "agents"
EXPECTED_AGENTS = {
    "recruiting-analyst", "eligibility-analyst", "profile-synthesist",
    "evidence-auditor", "adapter-author",
}


def _frontmatter(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---"), f"{path.name}: no YAML frontmatter"
    end = text.index("\n---", 3)
    block = text[3:end]
    fm: dict[str, str] = {}
    for line in block.splitlines():
        if ":" in line and not line.startswith((" ", "\t", "-")):
            key = line.split(":", 1)[0].strip()
            fm[key] = line.split(":", 1)[1].strip()
    return fm


def test_skill_has_name_and_description():
    fm = _frontmatter(SKILL)
    assert fm.get("name") == "supervisorly"
    assert "description" in fm


def test_all_five_agents_present_and_well_formed():
    files = {p.stem for p in AGENTS_DIR.glob("*.md")}
    assert EXPECTED_AGENTS <= files, f"missing agents: {EXPECTED_AGENTS - files}"
    for name in EXPECTED_AGENTS:
        fm = _frontmatter(AGENTS_DIR / f"{name}.md")
        assert fm.get("name") == name, f"{name}: frontmatter name mismatch"
        for key in ("description", "tools", "model"):
            assert key in fm, f"{name}: frontmatter missing {key}"


def test_skill_declares_the_no_llm_and_human_rung_rules():
    body = SKILL.read_text(encoding="utf-8")
    for token in ("generate", "human rung", "four states", "D-010", "D-035"):
        assert token in body, f"SKILL.md should reference {token!r}"
