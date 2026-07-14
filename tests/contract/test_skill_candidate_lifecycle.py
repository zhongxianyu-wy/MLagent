from src.skill_bridge.candidate import SkillCandidateStore
from src.skill_bridge.darwin_adapter import DarwinSkillAdapter
from src.skill_bridge.generator import SkillCandidateGenerator


def test_notebook_to_skill_candidate_lifecycle(tmp_path):
    store = SkillCandidateStore(str(tmp_path / "candidates.db"))
    generator = SkillCandidateGenerator(
        candidate_store=store,
        output_root=str(tmp_path / "drafts"),
        id_factory=lambda: "candidate-1",
        clock=lambda: 123,
    )

    candidate = generator.from_notebook("tests/fixtures/notebooks/skill_source.ipynb")
    validated = generator.validate_structure(candidate.candidate_id)
    optimized = DarwinSkillAdapter(store).iterate(candidate.candidate_id)

    assert candidate.source_type == "notebook"
    assert candidate.validation_status == "pending"
    assert validated.validation_status == "passed"
    assert optimized.darwin_iteration_status == "improved"
    assert optimized.review_status == "pending"
    assert store.get(candidate.candidate_id).review_status == "pending"


def test_best_run_to_skill_candidate_uses_trace_summary(tmp_path):
    store = SkillCandidateStore(str(tmp_path / "candidates.db"))
    generator = SkillCandidateGenerator(
        candidate_store=store,
        output_root=str(tmp_path / "drafts"),
        id_factory=lambda: "candidate-2",
        clock=lambda: 123,
    )

    candidate = generator.from_best_run(
        experiment_id="exp-1",
        trace_summary={
            "preprocessing": "standardize",
            "feature_subset": "low_variance",
            "model": "xgboost",
        },
    )

    assert candidate.source_type == "best_run"
    assert candidate.source_ref == "exp-1"
    assert candidate.skill_name == "exp-1-best-run"
