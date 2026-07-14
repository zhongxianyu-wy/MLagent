import json
from pathlib import Path

from src.agent.harness import ExplorationHarness
from src.frontend_api.dataset_service import DatasetService
from src.frontend_api.run_service import RunService


def test_exploration_writes_real_rounds_and_best_config(tmp_path):
    dataset_service = DatasetService(output_root=str(tmp_path / "standardized"))
    inspection = dataset_service.inspect_path("tests/fixtures/data_intake/clear")
    manifest = dataset_service.build_manifest(inspection.session_id)
    manifest_path = Path(tmp_path, "standardized", manifest.dataset_id, "manifest.json")

    output_root = tmp_path / "outputs"
    harness = ExplorationHarness(output_root=str(output_root), clock=lambda: 100)
    service = RunService(
        exploration_harness=harness,
        id_factory=lambda: "exp-real",
        clock=lambda: 100,
    )

    run = service.start_run(
        {
            "mode": "exploration",
            "dataset_id": manifest.dataset_id,
            "manifest_path": str(manifest_path),
            "max_rounds": 2,
            "guidance_metric_name": "auc",
            "k_folds": 2,
        }
    )

    assert run.status == "completed"
    rounds_path = output_root / "exp-real" / "rounds.jsonl"
    best_path = output_root / "exp-real" / "best_config.json"
    assert rounds_path.exists()
    assert best_path.exists()
    rows = [json.loads(line) for line in rounds_path.read_text().splitlines()]
    assert len(rows) == 2
    assert rows[0]["cv_metrics"]["auc"] >= 0.5
    assert json.loads(best_path.read_text())["experiment_id"] == "exp-real"
