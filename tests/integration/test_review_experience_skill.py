from pathlib import Path


def test_review_experience_skill_preserves_evidence_and_sop_boundaries():
    skill = Path(".claude/skills/review-experience/SKILL.md").read_text(
        encoding="utf-8"
    )
    normalized = " ".join(skill.lower().split())

    assert "evidence" in normalized
    assert "history" in normalized
    assert "approve" in normalized
    assert "reject" in normalized
    assert "conflict" in normalized
    assert "supersede" in normalized
    assert "never auto-approve" in normalized
    assert "must not create, approve, or modify an sop" in normalized
    assert "domain core" in normalized
    assert "do not edit team memory files directly" in normalized
