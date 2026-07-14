from __future__ import annotations


PREPROCESSING_STRATEGIES = ("standardize", "binarize")


def plan_preprocessing_strategy(round_num: int) -> str:
    return PREPROCESSING_STRATEGIES[(round_num - 1) % len(PREPROCESSING_STRATEGIES)]
