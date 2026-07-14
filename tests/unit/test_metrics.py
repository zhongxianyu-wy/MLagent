from src.evaluation.metrics import accuracy, auc, sensitivity_at_specificity


def test_accuracy_counts_correct_predictions():
    assert accuracy([1, 0, 1, 0], [1, 1, 1, 0]) == 0.75


def test_auc_ranks_positive_scores_above_negative_scores():
    assert auc([1, 1, 0, 0], [0.9, 0.8, 0.2, 0.1]) == 1.0
    assert auc([1, 0], [0.1, 0.9]) == 0.0


def test_sensitivity_at_specificity_uses_thresholded_scores():
    result = sensitivity_at_specificity(
        y_true=[1, 1, 0, 0],
        y_score=[0.9, 0.4, 0.3, 0.1],
        threshold=0.35,
    )

    assert result == {"sensitivity": 1.0, "specificity": 1.0}
