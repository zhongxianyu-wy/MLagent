from __future__ import annotations


FEATURE_SUBSET_STRATEGIES = (
    "low_variance",
    "correlation_filter",
    "statistical_test",
    "model_importance",
    "recursive_selection",
    "stability_selection",
)


def plan_feature_subset_strategy(round_num: int) -> str:
    return FEATURE_SUBSET_STRATEGIES[
        (round_num - 1) % len(FEATURE_SUBSET_STRATEGIES)
    ]
