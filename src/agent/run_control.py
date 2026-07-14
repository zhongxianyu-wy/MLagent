from __future__ import annotations

from dataclasses import dataclass

from src.models import RunControlPolicy


@dataclass(frozen=True)
class StopDecision:
    should_stop: bool
    reason: str | None


def evaluate_stop_condition(
    policy: RunControlPolicy,
    completed_iterations: int,
    elapsed_minutes: float,
    best_metric_value: float | None,
    rounds_since_improvement: int,
    user_stop_requested: bool,
) -> StopDecision:
    if user_stop_requested and policy.user_stoppable:
        return StopDecision(True, "user_stop")

    if (
        policy.target_metric_value is not None
        and best_metric_value is not None
        and best_metric_value >= policy.target_metric_value
    ):
        return StopDecision(True, "target_metric_reached")

    if completed_iterations >= policy.max_iterations:
        return StopDecision(True, "max_iterations")

    if elapsed_minutes >= policy.max_runtime_minutes:
        return StopDecision(True, "max_runtime")

    if rounds_since_improvement >= policy.patience_rounds:
        return StopDecision(True, "patience")

    return StopDecision(False, None)
