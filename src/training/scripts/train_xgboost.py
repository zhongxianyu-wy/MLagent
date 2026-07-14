from __future__ import annotations


def train(train_x: list[list[float]], train_y: list[int], validation_x: list[list[float]]) -> list[float]:
    return [float(row[0]) for row in validation_x]
