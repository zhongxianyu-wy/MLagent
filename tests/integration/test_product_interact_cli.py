from pathlib import Path

from src.agent.harness import ExplorationHarness
from src.frontend_api.dataset_service import DatasetService
from src.frontend_api.run_service import RunService


def test_interactive_validation_runs_one_real_round_then_pauses(tmp_path):
    dataset_service = DatasetService(output_root=str(tmp_path / "standardized"))
    inspection = dataset_service.inspect_path("tests/fixtures/data_intake/clear")
    manifest = dataset_service.build_manifest(inspection.session_id)
    manifest_path = Path(tmp_path, "standardized", manifest.dataset_id, "manifest.json")
    service = RunService(
        exploration_harness=ExplorationHarness(output_root=str(tmp_path / "outputs")),
        id_factory=lambda: "interact-1",
        clock=lambda: 100,
    )

    run = service.start_run(
        {
            "mode": "interactive_validation",
            "dataset_id": manifest.dataset_id,
            "manifest_path": str(manifest_path),
            "max_rounds": 3,
            "guidance_metric_name": "auc",
            "k_folds": 2,
            "direction": "验证 f1+f2 的标准化逻辑回归",
        }
    )

    rounds = service.list_rounds("interact-1")
    assert run.status == "paused"
    assert run.stop_reason == "awaiting_user_instruction"
    assert len(rounds) == 1
    assert rounds[0].exploration_direction == "验证 f1+f2 的标准化逻辑回归"
