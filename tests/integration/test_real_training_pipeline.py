import pandas as pd

from src.evaluation.cv import cross_validate
from src.models import EvaluationConfig
from src.training.modeling import SklearnModelTrainer


def test_sklearn_trainer_runs_real_kfold_predictions():
    features = pd.DataFrame(
        {
            "f1": [0, 0, 1, 1, 2, 2, 3, 3],
            "f2": [0, 1, 0, 1, 2, 3, 2, 3],
        }
    )
    labels = [0, 0, 0, 0, 1, 1, 1, 1]
    trainer = SklearnModelTrainer(model_type="logistic_regression", random_seed=11)

    result = cross_validate(
        features.values.tolist(),
        labels,
        EvaluationConfig(
            metric="auc",
            k_folds=2,
            target_specificity=None,
            threshold_policy="youden",
            use_test_if_available=True,
        ),
        trainer.predict_fold,
    )

    assert len(result.validation_scores) == len(labels)
    assert result.metrics["auc"] >= 0.75
    assert 0.0 <= result.threshold.threshold <= 1.0
