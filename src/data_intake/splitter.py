from __future__ import annotations


def deterministic_split_indices(n_samples: int, test_ratio: float, seed: int) -> tuple[list[int], list[int]]:
    # Placeholder deterministic split primitive; full stratified splitting arrives
    # when random_split intake is exercised by a failing test.
    test_count = int(n_samples * test_ratio)
    indices = list(range(n_samples))
    offset = seed % n_samples if n_samples else 0
    rotated = indices[offset:] + indices[:offset]
    test = sorted(rotated[:test_count])
    train = sorted(index for index in indices if index not in test)
    return train, test
