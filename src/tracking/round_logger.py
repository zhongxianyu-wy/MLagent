from __future__ import annotations

import json

from src.memory.episodic import EpisodicMemory
from src.models import ExperimentRoundTrace, TrackingRecord
from src.tracking.mlflow_tracker import MLflowTracker


class RoundLogger:
    def __init__(self, memory: EpisodicMemory, tracker: MLflowTracker) -> None:
        self.memory = memory
        self.tracker = tracker

    def log_completed_round(
        self,
        trace: ExperimentRoundTrace,
        tracking_id: str,
        artifact_paths: list[str],
    ) -> TrackingRecord:
        self.memory.add_round_trace(trace)
        return self.tracker.log_round(
            tracking_id=tracking_id,
            round_id=trace.round_id,
            experiment_id=trace.experiment_id,
            params=json.loads(trace.params_json),
            metrics=json.loads(trace.cv_metrics_json),
            artifact_paths=artifact_paths,
            logged_at=trace.created_at,
        )
