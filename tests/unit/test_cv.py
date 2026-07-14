import pytest

from src.evaluation.cv import cross_validate
from src.models import EvaluationConfig


def test_cross_validate_collects_out_of_fold_predictions_for_threshold():
    calls = []

    def trainer(train_x, train_y, validation_x):
        calls.append((train_x, train_y, validation_x))
        return [row[0] for row in validation_x]

    result = cross_validate(
        features=[[0.95], [0.85], [0.75], [0.15], [0.25], [0.35]],
        labels=[1, 1, 1, 0, 0, 0],
        config=EvaluationConfig(
            metric="auc",
            k_folds=3,
            target_specificity=None,
            threshold_policy="youden",
            use_test_if_available=True,
        ),
        trainer=trainer,
    )

    assert len(calls) == 3
    assert result.validation_scores == [0.95, 0.15, 0.85, 0.25, 0.75, 0.35]
    assert result.validation_labels == [1, 0, 1, 0, 1, 0]
    assert result.threshold.threshold == 0.75
    assert result.metrics["auc"] == 1.0


def test_cross_validate_rejects_k_larger_than_minority_class_count():
    with pytest.raises(ValueError, match="k_folds cannot exceed minority class count"):
        cross_validate(
            features=[[0.9], [0.8], [0.2]],
            labels=[1, 1, 0],
            config=EvaluationConfig(
                metric="auc",
                k_folds=2,
                target_specificity=None,
                threshold_policy="youden",
                use_test_if_available=True,
            ),
            trainer=lambda train_x, train_y, validation_x: [row[0] for row in validation_x],
        )
