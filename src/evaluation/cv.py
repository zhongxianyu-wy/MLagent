from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from src.evaluation.metrics import accuracy, auc
from src.evaluation.threshold import ThresholdSelection, select_threshold
from src.models import EvaluationConfig


Trainer = Callable[
    [list[Sequence[float]], list[int], list[Sequence[float]]],
    list[float],
]


@dataclass(frozen=True)
class CrossValidationResult:
    validation_labels: list[int]
    validation_scores: list[float]
    metrics: dict[str, float]
    threshold: ThresholdSelection


def cross_validate(
    features: list[Sequence[float]],
    labels: list[int],
    config: EvaluationConfig,
    trainer: Trainer,
) -> CrossValidationResult:
    if len(features) != len(labels) or not labels:
        raise ValueError("features and labels must have the same non-zero length")

    folds = _stratified_folds(labels, config.k_folds)
    validation_labels: list[int] = []
    validation_scores: list[float] = []

    all_indices = list(range(len(labels)))
    for validation_indices in folds:
        validation_index_set = set(validation_indices)
        train_indices = [
            index for index in all_indices if index not in validation_index_set
        ]
        train_x = [features[index] for index in train_indices]
        train_y = [labels[index] for index in train_indices]
        validation_x = [features[index] for index in validation_indices]

        fold_scores = trainer(train_x, train_y, validation_x)
        if len(fold_scores) != len(validation_indices):
            raise ValueError("trainer must return one score per validation sample")

        validation_labels.extend(labels[index] for index in validation_indices)
        validation_scores.extend(float(score) for score in fold_scores)

    threshold = select_threshold(
        validation_labels,
        validation_scores,
        policy=config.threshold_policy,
        target_specificity=config.target_specificity,
    )
    predictions = [1 if score >= threshold.threshold else 0 for score in validation_scores]
    metrics = {
        "auc": auc(validation_labels, validation_scores),
        "accuracy": accuracy(validation_labels, predictions),
    }

    return CrossValidationResult(
        validation_labels=validation_labels,
        validation_scores=validation_scores,
        metrics=metrics,
        threshold=threshold,
    )


def _stratified_folds(labels: list[int], k_folds: int) -> list[list[int]]:
    if k_folds < 2:
        raise ValueError("k_folds must be at least 2")

    positive_indices = [index for index, label in enumerate(labels) if label == 1]
    negative_indices = [index for index, label in enumerate(labels) if label == 0]
    minority_count = min(len(positive_indices), len(negative_indices))
    if minority_count == 0:
        raise ValueError("k-fold evaluation requires positive and negative labels")
    if k_folds > minority_count:
        raise ValueError("k_folds cannot exceed minority class count")

    folds: list[list[int]] = [[] for _ in range(k_folds)]
    for class_indices in (positive_indices, negative_indices):
        for offset, index in enumerate(class_indices):
            folds[offset % k_folds].append(index)
    return folds
