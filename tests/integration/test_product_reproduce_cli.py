import json
from pathlib import Path

from src.agent.harness import StrictSkillReproductionAdapter
from src.frontend_api.dataset_service import DatasetService
from src.skill_bridge.registry import SkillRegistry


def test_strict_reproduction_loads_manifest_and_writes_summary(tmp_path):
    dataset_service = DatasetService(output_root=str(tmp_path / "standardized"))
    inspection = dataset_service.inspect_path("tests/fixtures/data_intake/clear")
    manifest = dataset_service.build_manifest(inspection.session_id)

    adapter = StrictSkillReproductionAdapter(
        registry=SkillRegistry(root="tests/fixtures/skills"),
        output_root=str(tmp_path / "outputs"),
    )

    result = adapter.reproduce(
        skill_id="ngs-xgboost-baseline",
        dataset={
            "manifest_path": str(
                Path(tmp_path, "standardized", manifest.dataset_id, "manifest.json")
            ),
            "experiment_id": "repro-1",
        },
    )

    summary_path = Path(tmp_path, "outputs", "repro-1", "run_summary.json")
    metrics_path = Path(tmp_path, "outputs", "repro-1", "metrics.json")
    assert summary_path.exists()
    assert metrics_path.exists()
    assert result["dataset_id"] == "clear"
    assert result["model_type"] == "xgboost"
    assert result["selected_features"] == ["f1", "f2"]
    assert "auc" in json.loads(metrics_path.read_text())["cv_metrics"]
    assert json.loads(summary_path.read_text())["status"] == "completed"


def test_strict_reproduction_manifest_fails_when_required_feature_is_missing(tmp_path):
    features = tmp_path / "features.csv"
    labels = tmp_path / "labels.csv"
    features.write_text("sample_id,f1\ns1,0.1\ns2,0.2\ns3,0.8\ns4,0.9\n")
    labels.write_text("sample_id,group\ns1,case\ns2,case\ns3,control\ns4,control\n")
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    features.rename(data_dir / "features.csv")
    labels.rename(data_dir / "labels.csv")
    dataset_service = DatasetService(output_root=str(tmp_path / "standardized"))
    inspection = dataset_service.inspect_path(str(data_dir))
    manifest = dataset_service.build_manifest(inspection.session_id)

    adapter = StrictSkillReproductionAdapter(
        registry=SkillRegistry(root="tests/fixtures/skills"),
        output_root=str(tmp_path / "outputs"),
    )

    try:
        adapter.reproduce(
            skill_id="ngs-xgboost-baseline",
            dataset={
                "manifest_path": str(
                    Path(tmp_path, "standardized", manifest.dataset_id, "manifest.json")
                ),
                "experiment_id": "repro-missing",
            },
        )
    except ValueError as exc:
        assert "missing required features: f2" in str(exc)
    else:
        raise AssertionError("strict reproduction should fail on missing feature")
