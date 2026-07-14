from __future__ import annotations

from typing import Protocol

from src.models import TrackingRecord


class MLflowLikeClient(Protocol):
    def start_run(self, experiment_id: str) -> str:
        ...

    def log_param(self, run_id: str, key: str, value: object) -> None:
        ...

    def log_metric(self, run_id: str, key: str, value: float) -> None:
        ...

    def log_artifact(self, run_id: str, path: str) -> None:
        ...


class MLflowTracker:
    def __init__(self, client: MLflowLikeClient) -> None:
        self.client = client

    def log_round(
        self,
        tracking_id: str,
        round_id: str,
        experiment_id: str,
        params: dict[str, object],
        metrics: dict[str, float],
        artifact_paths: list[str],
        logged_at: int,
    ) -> TrackingRecord:
        run_id = self.client.start_run(experiment_id)
        for key, value in params.items():
            self.client.log_param(run_id, key, value)
        for key, value in metrics.items():
            self.client.log_metric(run_id, key, value)
        for path in artifact_paths:
            self.client.log_artifact(run_id, path)

        return TrackingRecord(
            tracking_id=tracking_id,
            round_id=round_id,
            experiment_id=experiment_id,
            mlflow_run_id=run_id,
            artifact_paths=artifact_paths,
            logged_at=logged_at,
            status="logged",
            error_msg=None,
        )
