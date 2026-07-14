from pathlib import Path

from src.skill_bridge.candidate import SkillCandidateStore
from src.skill_bridge.darwin_adapter import DarwinSkillAdapter
from src.skill_bridge.generator import SkillCandidateGenerator


def test_notebook_distillation_writes_product_skill_candidate(tmp_path):
    store = SkillCandidateStore(str(tmp_path / "candidates.db"))
    generator = SkillCandidateGenerator(
        candidate_store=store,
        output_root=str(tmp_path / "drafts"),
        id_factory=lambda: "candidate-1",
        clock=lambda: 123,
    )

    candidate = generator.from_notebook("tests/fixtures/notebooks/skill_source.ipynb")
    validated = generator.validate_structure(candidate.candidate_id)
    iterated = DarwinSkillAdapter(store).iterate(candidate.candidate_id)
    text = Path(candidate.draft_path).read_text()

    assert validated.validation_status == "passed"
    assert iterated.darwin_iteration_status == "improved"
    assert iterated.review_status == "pending"
    assert "## Inputs" in text
    assert "## Procedure" in text
    assert "## Evaluation" in text
    assert "standardization" in text
    assert "low variance" in text
    assert "XGBoost" in text
