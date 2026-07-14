from src.training.scripts.train_sklearn import train as train_sklearn
from src.training.scripts.train_xgboost import train as train_xgboost


def test_sklearn_training_script_returns_score_per_validation_sample():
    scores = train_sklearn(
        train_x=[[0.9], [0.1]],
        train_y=[1, 0],
        validation_x=[[0.8], [0.2]],
    )

    assert scores == [0.8, 0.2]


def test_xgboost_training_script_returns_score_per_validation_sample():
    scores = train_xgboost(
        train_x=[[0.9], [0.1]],
        train_y=[1, 0],
        validation_x=[[0.7], [0.3]],
    )

    assert scores == [0.7, 0.3]
