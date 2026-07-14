from src.frontend_api.skill_service import SkillService
from src.skill_bridge.candidate import SkillCandidateStore
from src.skill_bridge.generator import SkillCandidateGenerator
from src.skill_bridge.registry import SkillPublisher


def test_skill_service_creates_and_approves_candidate(tmp_path):
    store = SkillCandidateStore(str(tmp_path / "candidates.db"))
    generator = SkillCandidateGenerator(
        candidate_store=store,
        output_root=str(tmp_path / "drafts"),
        id_factory=lambda: "candidate-1",
        clock=lambda: 123,
    )
    service = SkillService(
        registry=None,
        candidate_generator=generator,
        publisher=SkillPublisher(store, skills_root=str(tmp_path / "skills")),
    )

    candidate = service.create_candidate_from_notebook(
        "tests/fixtures/notebooks/skill_source.ipynb"
    )
    skill = service.approve_candidate(candidate.candidate_id)

    assert candidate.candidate_id == "candidate-1"
    assert skill.created_from_candidate_id == "candidate-1"
