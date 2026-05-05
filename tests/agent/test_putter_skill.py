"""Regression coverage for the bundled putter skill."""

from pathlib import Path
from unittest.mock import patch

from agent.skill_commands import scan_skill_commands
from tools.skills_tool import _parse_frontmatter


REPO_ROOT = Path(__file__).resolve().parents[2]
PUTTER_SKILL = REPO_ROOT / "skills" / "autonomous-ai-agents" / "putter" / "SKILL.md"


def test_putter_skill_frontmatter_exposes_expected_slug():
    content = PUTTER_SKILL.read_text(encoding="utf-8")
    frontmatter, body = _parse_frontmatter(content)

    assert frontmatter["name"] == "putter"
    assert "low-risk" in frontmatter["description"]
    hermes_metadata = frontmatter["metadata"]["hermes"]
    assert "# Putter Compact Invocation" in hermes_metadata["compact_invocation"]
    assert "# Scheduled Putter Compact Invocation" in hermes_metadata["cron_invocation"]
    assert "## Good Putter Tasks" in body
    assert "## Bad Putter Tasks" in body
    assert "Putter is allowed to improve Putter" in body
    assert "Preserve evidence first" in body
    assert "When this skill is invoked from a scheduled cron job" in body
    assert "inspect at most three candidate sources" in body
    assert "exactly `[SILENT]`" in body
    assert "do not continue or resume a prior autonomous search" in body
    assert "do not create, update, pause, resume, run, or remove cron jobs" in body


def test_putter_skill_registers_as_slash_command(tmp_path):
    skill_dir = tmp_path / "autonomous-ai-agents" / "putter"
    skill_dir.mkdir(parents=True)
    skill_dir.joinpath("SKILL.md").write_text(
        PUTTER_SKILL.read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    with patch("tools.skills_tool.SKILLS_DIR", tmp_path):
        commands = scan_skill_commands()

    assert "/putter" in commands
    assert commands["/putter"]["name"] == "putter"
