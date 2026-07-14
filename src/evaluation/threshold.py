from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ThresholdSelection:
    threshold: float
    sensitivity: float
    specificity: float
    policy: str


def select_threshold(
    y_true: list[int],
    y_score: list[float],
    policy: str,
    target_specificity: float | None = None,
) -> ThresholdSelection:
    if len(y_true) != len(y_score) or not y_true:
        raise ValueError("y_true and y_score must have the same non-zero length")
    if policy not in {"youden", "target_specificity"}:
        raise ValueError("policy must be 'youden' or 'target_specificity'")
    if policy == "target_specificity" and target_specificity is None:
        raise ValueError("target_specificity is required for target_specificity policy")

    candidates = []
    for threshold in sorted(set(y_score), reverse=True):
        sensitivity, specificity = _classification_rates(y_true, y_score, threshold)
        candidates.append(
            ThresholdSelection(
                threshold=threshold,
                sensitivity=sensitivity,
                specificity=specificity,
                policy=policy,
            )
        )

    if policy == "youden":
        return max(
            candidates,
            key=lambda item: (
                item.sensitivity + item.specificity - 1.0,
                item.sensitivity,
                item.specificity,
            ),
        )

    eligible = [
        item for item in candidates if item.specificity >= float(target_specificity)
    ]
    if not eligible:
        raise ValueError("no threshold reaches target_specificity")
    return max(eligible, key=lambda item: (item.sensitivity, item.specificity))


def _classification_rates(
    y_true: list[int], y_score: list[float], threshold: float
) -> tuple[float, float]:
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

    if true_positive + false_negative == 0 or true_negative + false_positive == 0:
        raise ValueError("threshold selection requires positive and negative labels")
    sensitivity = true_positive / (true_positive + false_negative)
    specificity = true_negative / (true_negative + false_positive)
    return sensitivity, specificity
