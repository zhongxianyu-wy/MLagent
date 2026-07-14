from src.memory.episodic import EpisodicMemory
from src.models import ExperimentRoundTrace
from src.tracking.mlflow_tracker import MLflowTracker
from src.tracking.round_logger import RoundLogger


class FakeMLflowClient:
    def start_run(self, experiment_id):
        return f"mlflow-{experiment_id}"

    def log_param(self, run_id, key, value):
        pass

    def log_metric(self, run_id, key, value):
        pass

    def log_artifact(self, run_id, path):
        pass


def test_completed_round_logs_sqlite_trace_and_tracking_record(tmp_path):
    memory = EpisodicMemory(str(tmp_path / "experiments.db"))
    tracker = MLflowTracker(client=FakeMLflowClient())
    logger = RoundLogger(memory=memory, tracker=tracker)
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
        model_type="xgboost",
        params_json='{"max_depth": 2}',
        cv_metrics_json='{"auc": 0.9}',
        threshold_policy="youden",
        selected_threshold=0.5,
        test_metrics_json=None,
        guidance_metric_name="auc",
        guidance_metric_value=0.9,
        status="completed",
        stop_reason=None,
        error_msg=None,
        llm_rationale_summary="baseline round",
        created_at=123,
    )

    record = logger.log_completed_round(
        trace=trace,
        tracking_id="tracking-1",
        artifact_paths=["experiments/models/exp-1/model.pkl"],
    )

    assert memory.list_round_traces("exp-1") == [trace]
    assert record.round_id == "round-1"
    assert record.experiment_id == "exp-1"
    assert record.mlflow_run_id == "mlflow-exp-1"
    assert record.status == "logged"
