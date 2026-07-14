from src.frontend_api.run_service import RunService
from src.models import ExperimentRoundTrace, RunControlPolicy


class FakeExplorationHarness:
    def __init__(self):
        self.requests = []

    def start(self, request):
        self.requests.append(request)
        return []


def test_run_service_starts_exploration_and_reports_status():
    harness = FakeExplorationHarness()
    service = RunService(
        exploration_harness=harness,
        id_factory=lambda: "exp-1",
        clock=lambda: 123,
    )

    run = service.start_run(
        {
            "mode": "exploration",
            "dataset_id": "dataset-1",
            "run_control_policy": RunControlPolicy(
                target_metric_name="auc",
                target_metric_value=None,
                max_iterations=10,
                max_runtime_minutes=60,
                patience_rounds=3,
                min_delta=0.01,
                user_stoppable=True,
            ),
        }
    )

    assert run.experiment_id == "exp-1"
    assert run.status == "running"
    assert service.get_status("exp-1") == {
        "experiment_id": "exp-1",
        "status": "running",
        "current_round": 0,
        "stop_reason": None,
        "best_metric": None,
    }
    assert harness.requests[0]["experiment_id"] == "exp-1"


def test_run_service_lists_rounds_and_stops_run():
    service = RunService(id_factory=lambda: "exp-1", clock=lambda: 123)
    service.start_run({"mode": "exploration", "dataset_id": "dataset-1"})
    trace = ExperimentRoundTrace(
        round_id="round-1",
        experiment_id="exp-1",
        round_num=1,
        mode="exploration",
        exploration_direction="baseline",
        hypothesis=None,
        preprocessing_strategy="standardize",
        feature_subset_strategy="all_features",
        selected_features_json='["f1"]',
        model_type="sklearn",
        params_json="{}",
        cv_metrics_json='{"auc": 0.8}',
        threshold_policy="youden",
        selected_threshold=0.5,
        test_metrics_json=None,
        guidance_metric_name="auc",
        guidance_metric_value=0.8,
        status="completed",
        stop_reason=None,
        error_msg=None,
        llm_rationale_summary="baseline",
        created_at=124,
    )
    service.add_round_trace(trace)

    stopped = service.stop_run("exp-1", reason="user_stop")

    assert service.list_rounds("exp-1") == [trace]
    assert stopped["status"] == "stopped"
    assert stopped["stop_reason"] == "user_stop"
