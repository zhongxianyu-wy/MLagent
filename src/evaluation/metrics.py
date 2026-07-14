from __future__ import annotations


def accuracy(y_true: list[int], y_pred: list[int]) -> float:
    if len(y_true) != len(y_pred) or not y_true:
        raise ValueError("y_true and y_pred must have the same non-zero length")
    correct = sum(1 for truth, pred in zip(y_true, y_pred) if truth == pred)
    return correct / len(y_true)


def auc(y_true: list[int], y_score: list[float]) -> float:
    if len(y_true) != len(y_score) or not y_true:
        raise ValueError("y_true and y_score must have the same non-zero length")

    positives = [score for truth, score in zip(y_true, y_score) if truth == 1]
    negatives = [score for truth, score in zip(y_true, y_score) if truth == 0]
    if not positives or not negatives:
        raise ValueError("auc requires at least one positive and one negative")

    wins = 0.0
    for pos in positives:
        for neg in negatives:
            if pos > neg:
                wins += 1.0
            elif pos == neg:
                wins += 0.5
    return wins / (len(positives) * len(negatives))


def sensitivity_at_specificity(
    y_true: list[int], y_score: list[float], threshold: float
) -> dict[str, float]:
    if len(y_true) != len(y_score) or not y_true:
        raise ValueError("y_true and y_score must have the same non-zero length")

    y_pred = [1 if score >= threshold else 0 for score in y_score]
    true_positive = sum(
        1 for truth, pred in zip(y_true, y_pred) if truth == 1 and pred == 1
    )
    false_negative = sum(
        1 for truth, pred in zip(y_true, y_pred) if truth == 1 and pred == 0
    )
    true_negative = sum(
        1 for truth, pred in zip(y_true, y_pred) if truth == 0 and pred == 0
    )
    false_positive = sum(
        1 for truth, pred in zip(y_true, y_pred) if truth == 0 and pred == 1
    )

    sensitivity = true_positive / (true_positive + false_negative)
    specificity = true_negative / (true_negative + false_positive)
    return {"sensitivity": sensitivity, "specificity": specificity}
