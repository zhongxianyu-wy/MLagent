from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


@dataclass(frozen=True)
class SklearnModelTrainer:
    model_type: str = "logistic_regression"
    random_seed: int = 0

    def predict_fold(
        self,
        train_x: list[Sequence[float]],
        train_y: list[int],
        validation_x: list[Sequence[float]],
    ) -> list[float]:
        if self.model_type != "logistic_regression":
            raise ValueError("only logistic_regression is currently supported")
        model = Pipeline(
            steps=[
                ("scaler", StandardScaler()),
                (
                    "classifier",
                    LogisticRegression(
                        random_state=self.random_seed,
                        solver="liblinear",
                    ),
                ),
            ]
        )
        model.fit(train_x, train_y)
        return [
            float(probability)
            for probability in model.predict_proba(validation_x)[:, 1]
        ]
