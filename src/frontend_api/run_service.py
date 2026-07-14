from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from dataclasses import replace

from src.models import ExperimentRoundTrace, ExperimentRun


class RunService:
    def __init__(
        self,
        exploration_harness=None,
        id_factory: Callable[[], str] | None = None,
        clock: Callable[[], int] | None = None,
    ) -> None:
        self.exploration_harness = exploration_harness
        self.id_factory = id_factory or (lambda: str(uuid.uuid4()))
        self.clock = clock or (lambda: int(time.time()))
        self._runs: dict[str, ExperimentRun] = {}
        self._rounds: dict[str, list[ExperimentRoundTrace]] = {}

    def start_run(self, request: dict) -> ExperimentRun:
        experiment_id = request.get("experiment_id") or self.id_factory()
        run = ExperimentRun(
            experiment_id=experiment_id,
            mode=request["mode"],
            dataset_id=request.get("dataset_id") or request.get("dataset_ref"),
            status="running",
            run_control_policy_id=None,
            started_at=self.clock(),
            ended_at=None,
            stop_reason=None,
        )
        self._runs[experiment_id] = run
        self._rounds.setdefault(experiment_id, [])

        if request["mode"] in {"exploration", "interactive_validation"} and self.exploration_harness is not None:
            harness_request = dict(request)
            harness_request["experiment_id"] = experiment_id
            if request["mode"] == "interactive_validation":
                harness_request["max_rounds"] = 1
            for trace in self.exploration_harness.start(harness_request):
                self.add_round_trace(trace)
            if request["mode"] == "interactive_validation":
                run = replace(
                    run,
                    status="paused",
                    ended_at=self.clock(),
                    stop_reason="awaiting_user_instruction",
                )
                self._runs[experiment_id] = run
            elif request.get("manifest_path"):
                run = replace(
                    run,
                    status="completed",
                    ended_at=self.clock(),
                    stop_reason="completed",
                )
                self._runs[experiment_id] = run

        return run

    def get_status(self, experiment_id: str) -> dict:
        run = self._runs[experiment_id]
        rounds = self._rounds.get(experiment_id, [])
        best_metric = None
        completed = [round_ for round_ in rounds if round_.guidance_metric_value is not None]
        if completed:
            best_metric = max(round_.guidance_metric_value for round_ in completed)
        return {
            "experiment_id": experiment_id,
            "status": run.status,
            "current_round": len(rounds),
            "stop_reason": run.stop_reason,
            "best_metric": best_metric,
        }

    def list_rounds(self, experiment_id: str) -> list[ExperimentRoundTrace]:
        return list(self._rounds.get(experiment_id, []))

    def stop_run(self, experiment_id: str, reason: str) -> dict:
        run = self._runs[experiment_id]
        stopped = replace(
            run,
            status="stopped",
            ended_at=self.clock(),
            stop_reason=reason,
        )
        self._runs[experiment_id] = stopped
        return self.get_status(experiment_id)

    def add_round_trace(self, trace: ExperimentRoundTrace) -> None:
        self._rounds.setdefault(trace.experiment_id, []).append(trace)
