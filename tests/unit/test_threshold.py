from src.evaluation.threshold import select_threshold


def test_select_threshold_maximizes_youden_index():
    result = select_threshold(
        y_true=[1, 1, 0, 0],
        y_score=[0.9, 0.7, 0.8, 0.2],
        policy="youden",
    )

    assert result.threshold == 0.7
    assert result.sensitivity == 1.0
    assert result.specificity == 0.5
    assert result.policy == "youden"


def test_select_threshold_for_target_specificity_prefers_highest_sensitivity():
    result = select_threshold(
        y_true=[1, 1, 0, 0],
        y_score=[0.9, 0.55, 0.6, 0.2],
        policy="target_specificity",
        target_specificity=1.0,
    )

    assert result.threshold == 0.9
    assert result.sensitivity == 0.5
    assert result.specificity == 1.0
    assert result.policy == "target_specificity"
