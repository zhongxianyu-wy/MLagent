from src.agent.harness import StrictSkillReproductionAdapter
from src.skill_bridge.registry import SkillRegistry


def test_strict_reproduction_fails_when_required_feature_is_missing():
    adapter = StrictSkillReproductionAdapter(
        registry=SkillRegistry(root="tests/fixtures/skills")
    )

    try:
        adapter.reproduce(
            skill_id="ngs-xgboost-baseline",
            dataset={"dataset_id": "dataset-1", "features": ["f1"]},
        )
    except ValueError as exc:
        assert "missing required features: f2" in str(exc)
    else:
        raise AssertionError("strict reproduction should fail on missing feature")
