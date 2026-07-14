from src.tracking.mlflow_tracker import MLflowTracker


class FakeMLflowClient:
    def __init__(self):
        self.params = {}
        self.metrics = {}
        self.artifacts = []

    def start_run(self, experiment_id):
        return f"mlflow-{experiment_id}"

    def log_param(self, run_id, key, value):
        self.params[(run_id, key)] = value

    def log_metric(self, run_id, key, value):
        self.metrics[(run_id, key)] = value

    def log_artifact(self, run_id, path):
        self.artifacts.append((run_id, path))


def test_mlflow_tracker_logs_round_payload_and_returns_tracking_record():
    client = FakeMLflowClient()
    tracker = MLflowTracker(client=client)

    record = tracker.log_round(
        tracking_id="track-1",
        round_id="round-1",
        experiment_id="exp-1",
        params={"model": "xgboost"},
        metrics={"auc": 0.91},
        artifact_paths=["experiments/models/exp-1/model.pkl"],
        logged_at=123,
    )

    assert record.mlflow_run_id == "mlflow-exp-1"
    assert record.status == "logged"
    assert client.params[("mlflow-exp-1", "model")] == "xgboost"
    assert client.metrics[("mlflow-exp-1", "auc")] == 0.91
    assert client.artifacts == [
        ("mlflow-exp-1", "experiments/models/exp-1/model.pkl")
    ]
