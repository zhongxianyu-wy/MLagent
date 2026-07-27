"""Contract tests for the six lifecycle Skills (Issue #15 T5, AC#1)."""
from __future__ import annotations

from pathlib import Path

REQUIRED_SKILLS = (
    "bootstrap-memory",
    "intake-data",
    "design-and-explore",
    "retrain-from-sop",
    "review-experience",
    "instance-to-sop",
)
REQUIRED_SECTIONS = ("## Boundary", "## Workflow")


def _skills_dir() -> Path:
    return Path(__file__).resolve().parents[2] / ".claude" / "skills"


def test_six_skills_exist_with_required_sections():
    for name in REQUIRED_SKILLS:
        skill = _skills_dir() / name / "SKILL.md"
        assert skill.exists(), f"missing skill SKILL.md: {name}"
        text = skill.read_text(encoding="utf-8")
        assert text.startswith("---\n"), f"{name}: missing YAML frontmatter"
        assert "name:" in text, f"{name}: frontmatter missing name"
        assert "description:" in text, f"{name}: frontmatter missing description"
        for section in REQUIRED_SECTIONS:
            assert section in text, f"{name}: missing section {section}"
