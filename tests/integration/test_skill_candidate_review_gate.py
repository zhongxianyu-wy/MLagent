from pathlib import Path

from src.skill_bridge.candidate import SkillCandidateStore
from src.skill_bridge.generator import SkillCandidateGenerator
from src.skill_bridge.registry import SkillPublisher


def test_unapproved_skill_candidate_is_not_published(tmp_path):
    store = SkillCandidateStore(str(tmp_path / "candidates.db"))
    generator = SkillCandidateGenerator(
        candidate_store=store,
        output_root=str(tmp_path / "drafts"),
        id_factory=lambda: "candidate-1",
        clock=lambda: 123,
    )
    candidate = generator.from_notebook("tests/fixtures/notebooks/skill_source.ipynb")
    publisher = SkillPublisher(candidate_store=store, skills_root=str(tmp_path / "skills"))

    try:
        publisher.publish(candidate.candidate_id, approved=False)
    except ValueError as exc:
        assert "human approval" in str(exc)
    else:
        raise AssertionError("unapproved candidate should not publish")
    assert not Path(tmp_path / "skills" / candidate.skill_name / "SKILL.md").exists()


def test_approved_skill_candidate_is_published(tmp_path):
    store = SkillCandidateStore(str(tmp_path / "candidates.db"))
    generator = SkillCandidateGenerator(
        candidate_store=store,
        output_root=str(tmp_path / "drafts"),
        id_factory=lambda: "candidate-1",
        clock=lambda: 123,
    )
    candidate = generator.from_notebook("tests/fixtures/notebooks/skill_source.ipynb")
    publisher = SkillPublisher(candidate_store=store, skills_root=str(tmp_path / "skills"))

    skill = publisher.publish(candidate.candidate_id, approved=True)

    assert skill.skill_id == candidate.skill_name
    assert Path(skill.path).exists()
    assert store.get(candidate.candidate_id).review_status == "approved"
