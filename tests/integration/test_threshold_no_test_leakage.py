from src.evaluation.cv import cross_validate
from src.models import EvaluationConfig


def test_cross_validation_threshold_is_selected_before_test_scores_exist():
    def validation_trainer(train_x, train_y, validation_x):
        return [row[0] for row in validation_x]

    result = cross_validate(
        features=[[0.9], [0.8], [0.7], [0.6], [0.5], [0.4]],
        labels=[1, 1, 1, 0, 0, 0],
        config=EvaluationConfig(
            metric="auc",
            k_folds=3,
            target_specificity=None,
            threshold_policy="youden",
            use_test_if_available=True,
        ),
        trainer=validation_trainer,
    )

    test_scores_that_would_prefer_lower_threshold = [0.95, 0.45, 0.44, 0.43]

    assert result.validation_scores == [0.9, 0.6, 0.8, 0.5, 0.7, 0.4]
    assert result.threshold.threshold == 0.7
    assert result.threshold.threshold not in test_scores_that_would_prefer_lower_threshold
