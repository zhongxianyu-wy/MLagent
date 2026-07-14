from src.agent.control_center import instruction_to_validation_request
from src.agent.harness import ExplorationHarness
from src.frontend_api.run_service import RunService


def test_interactive_validation_pauses_after_one_result():
    service = RunService(
        exploration_harness=ExplorationHarness(clock=lambda: 100),
        id_factory=lambda: "exp-1",
        clock=lambda: 100,
    )

    run = service.start_run(
        instruction_to_validation_request(
            dataset_id="dataset-1",
            instruction="测试标准化后低方差过滤",
        )
    )

    status = service.get_status(run.experiment_id)
    rounds = service.list_rounds(run.experiment_id)

    assert len(rounds) == 1
    assert rounds[0].exploration_direction == "测试标准化后低方差过滤"
    assert status["status"] == "paused"
    assert status["stop_reason"] == "awaiting_user_instruction"
