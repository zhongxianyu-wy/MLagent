from src.training.feature_selection import plan_feature_subset_strategy
from src.training.preprocessing import plan_preprocessing_strategy


def test_preprocessing_strategy_prioritizes_standardize_before_feature_selection():
    assert plan_preprocessing_strategy(round_num=1) == "standardize"
    assert plan_preprocessing_strategy(round_num=2) == "binarize"


def test_feature_subset_strategy_cycles_filter_methods():
    assert plan_feature_subset_strategy(round_num=1) == "low_variance"
    assert plan_feature_subset_strategy(round_num=2) == "correlation_filter"
