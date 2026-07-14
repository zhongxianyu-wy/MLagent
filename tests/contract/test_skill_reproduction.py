from src.agent.harness import StrictSkillReproductionAdapter
from src.frontend_api.skill_service import SkillService
from src.skill_bridge.registry import SkillRegistry


def test_skill_registry_lists_fixture_approved_skill():
    registry = SkillRegistry(root="tests/fixtures/skills")

    skills = registry.list_skills()

    assert len(skills) == 1
    assert skills[0].skill_id == "ngs-xgboost-baseline"
    assert skills[0].name == "ngs-xgboost-baseline"
    assert skills[0].version == "1.0.0"


def test_skill_service_reproduces_skill_with_declared_workflow_only():
    registry = SkillRegistry(root="tests/fixtures/skills")
    service = SkillService(
        registry=registry,
        reproduction_adapter=StrictSkillReproductionAdapter(registry=registry),
    )

    result = service.reproduce(
        skill_id="ngs-xgboost-baseline",
        dataset={
            "dataset_id": "dataset-1",
            "features": ["f1", "f2", "f3"],
        },
    )

    assert result["skill_id"] == "ngs-xgboost-baseline"
    assert result["preprocessing_strategy"] == "standardize"
    assert result["feature_subset_strategy"] == "all_features"
    assert result["model_type"] == "xgboost"
    assert result["selected_features"] == ["f1", "f2"]
