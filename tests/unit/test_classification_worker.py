import math

import numpy as np
import pytest

from src.training.classification_worker import (
    WorkerContractError,
    classification_metrics,
    load_estimator,
)


def test_binary_metrics_use_the_confirmed_positive_class():
    metrics = classification_metrics(
        task_type="binary",
        class_labels=("case", "control"),
        positive_class="case",
        observed=np.array(["case", "control", "case", "control"]),
        predicted=np.array(["case", "control", "case", "case"]),
        probabilities=np.array(
            [
                [0.9, 0.1],
                [0.2, 0.8],
                [0.8, 0.2],
                [0.6, 0.4],
            ]
        ),
    )

    assert metrics["roc_auc"] == pytest.approx(1.0)
    assert metrics["accuracy"] == pytest.approx(0.75)
    assert metrics["f1"] == pytest.approx(0.8)


def test_multiclass_metrics_are_finite_and_bounded():
    metrics = classification_metrics(
        task_type="multiclass",
        class_labels=("a", "b", "c"),
        positive_class=None,
        observed=np.array(["a", "b", "c", "a", "b", "c"]),
        predicted=np.array(["a", "b", "c", "a", "c", "c"]),
        probabilities=np.array(
            [
                [0.8, 0.1, 0.1],
                [0.1, 0.8, 0.1],
                [0.1, 0.1, 0.8],
                [0.7, 0.2, 0.1],
                [0.1, 0.3, 0.6],
                [0.1, 0.2, 0.7],
            ]
        ),
    )

    assert set(metrics) == {"accuracy", "macro_f1", "roc_auc_ovr"}
    assert all(math.isfinite(value) and 0 <= value <= 1 for value in metrics.values())


@pytest.mark.parametrize(
    ("source", "error_code"),
    [
        ("VALUE = 1\n", "missing_build_estimator"),
        (
            "def build_estimator(context):\n    return object()\n",
            "invalid_estimator",
        ),
    ],
)
def test_entrypoint_must_return_a_sklearn_compatible_estimator(
    tmp_path,
    source,
    error_code,
):
    entrypoint = tmp_path / "entrypoint.py"
    entrypoint.write_text(source, encoding="utf-8")

    with pytest.raises(WorkerContractError) as caught:
        load_estimator(entrypoint, {"random_seed": 42})

    assert caught.value.code == error_code


def test_entrypoint_can_import_an_approved_sibling_during_build(tmp_path):
    (tmp_path / "helper.py").write_text(
        "from sklearn.linear_model import LogisticRegression\n"
        "def create(seed):\n"
        "    return LogisticRegression(random_state=seed)\n",
        encoding="utf-8",
    )
    entrypoint = tmp_path / "entrypoint.py"
    entrypoint.write_text(
        "def build_estimator(context):\n"
        "    from helper import create\n"
        "    return create(context['random_seed'])\n",
        encoding="utf-8",
    )

    estimator = load_estimator(
        entrypoint,
        {"random_seed": 17},
        code_root=tmp_path,
    )

    assert estimator.random_state == 17
