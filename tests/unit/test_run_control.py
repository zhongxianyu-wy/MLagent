from src.agent.run_control import evaluate_stop_condition
from src.models import RunControlPolicy


def test_evaluate_stop_condition_stops_when_target_metric_is_reached():
    decision = evaluate_stop_condition(
        policy=RunControlPolicy(
            target_metric_name="auc",
            target_metric_value=0.9,
            max_iterations=20,
            max_runtime_minutes=120,
            patience_rounds=5,
            min_delta=0.01,
            user_stoppable=True,
        ),
        completed_iterations=3,
        elapsed_minutes=10,
        best_metric_value=0.91,
        rounds_since_improvement=0,
        user_stop_requested=False,
    )

    assert decision.should_stop is True
    assert decision.reason == "target_metric_reached"


def test_evaluate_stop_condition_stops_on_max_iterations_before_patience():
    decision = evaluate_stop_condition(
        policy=RunControlPolicy(
            target_metric_name="auc",
            target_metric_value=None,
            max_iterations=5,
            max_runtime_minutes=120,
            patience_rounds=2,
            min_delta=0.01,
            user_stoppable=True,
        ),
        completed_iterations=5,
        elapsed_minutes=10,
        best_metric_value=0.7,
        rounds_since_improvement=2,
        user_stop_requested=False,
    )

    assert decision.should_stop is True
    assert decision.reason == "max_iterations"


def test_evaluate_stop_condition_continues_when_no_limit_is_met():
    decision = evaluate_stop_condition(
        policy=RunControlPolicy(
            target_metric_name="auc",
            target_metric_value=0.9,
            max_iterations=5,
            max_runtime_minutes=120,
            patience_rounds=3,
            min_delta=0.01,
            user_stoppable=True,
        ),
        completed_iterations=2,
        elapsed_minutes=10,
        best_metric_value=0.7,
        rounds_since_improvement=1,
        user_stop_requested=False,
    )

    assert decision.should_stop is False
    assert decision.reason is None
