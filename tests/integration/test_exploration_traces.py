import json

from src.agent.harness import ExplorationHarness
from src.frontend_api.run_service import RunService


def test_ten_round_exploration_records_complete_trace_fields():
    harness = ExplorationHarness(clock=lambda: 100)
    service = RunService(
        exploration_harness=harness,
        id_factory=lambda: "exp-1",
        clock=lambda: 100,
    )

    service.start_run(
        {
            "mode": "exploration",
            "dataset_id": "dataset-1",
            "max_rounds": 10,
            "guidance_metric_name": "auc",
        }
    )

    rounds = service.list_rounds("exp-1")
    assert len(rounds) == 10
    assert [round_.round_num for round_ in rounds] == list(range(1, 11))
    for round_ in rounds:
        assert round_.exploration_direction
        assert round_.preprocessing_strategy
        assert round_.feature_subset_strategy
        assert json.loads(round_.cv_metrics_json)["auc"] > 0
        assert round_.threshold_policy == "youden"
        assert round_.status == "completed"
        assert round_.llm_rationale_summary
    assert service.get_status("exp-1")["best_metric"] == 0.8
