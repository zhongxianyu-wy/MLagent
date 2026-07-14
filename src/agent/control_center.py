from __future__ import annotations

from src.agent.run_control import evaluate_stop_condition
from src.models import RunControlPolicy


def instruction_to_validation_request(dataset_id: str, instruction: str) -> dict:
    return {
        "mode": "interactive_validation",
        "dataset_id": dataset_id,
        "direction": instruction,
        "max_rounds": 1,
        "pause_after_result": True,
    }


def apply_run_control(
    run_service,
    experiment_id: str,
    policy: RunControlPolicy,
    completed_iterations: int,
    elapsed_minutes: float,
    best_metric_value: float | None,
    rounds_since_improvement: int,
    user_stop_requested: bool,
) -> dict:
    decision = evaluate_stop_condition(
        policy=policy,
        completed_iterations=completed_iterations,
        elapsed_minutes=elapsed_minutes,
        best_metric_value=best_metric_value,
        rounds_since_improvement=rounds_since_improvement,
        user_stop_requested=user_stop_requested,
    )
    if decision.should_stop:
        return run_service.stop_run(experiment_id, reason=decision.reason)
    return run_service.get_status(experiment_id)
