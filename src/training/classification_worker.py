from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.metrics import accuracy_score, f1_score, roc_auc_score
from sklearn.model_selection import StratifiedKFold

from src.domain.dataset_repository import DatasetRepository
from src.domain.run_repository import RunRepository


RESULT_FILENAME = "result.json"
ERROR_FILENAME = "error.json"


class WorkerContractError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ClassificationData:
    features: pd.DataFrame
    labels: np.ndarray
    sample_ids: np.ndarray
    partitions: np.ndarray
    task_type: str
    class_labels: tuple[str, ...]
    positive_class: str | None
    primary_metric: str
    split_strategy: str
    random_seed: int


def load_estimator(
    entrypoint_path: Path,
    context: dict[str, Any],
    code_root: Path | None = None,
) -> Any:
    path = entrypoint_path.expanduser()
    if path.is_symlink() or not path.is_file():
        raise WorkerContractError(
            "invalid_entrypoint",
            "Frozen estimator entrypoint is unavailable.",
        )
    module_name = f"mlagent_frozen_{hashlib.sha256(str(path).encode()).hexdigest()[:16]}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise WorkerContractError(
            "entrypoint_import_failed",
            "Frozen estimator entrypoint cannot be imported.",
        )
    module = importlib.util.module_from_spec(spec)
    import_root = str((code_root or path.parent).resolve())
    sys.path.insert(0, import_root)
    try:
        try:
            spec.loader.exec_module(module)
        except Exception as error:
            raise WorkerContractError(
                "entrypoint_import_failed",
                f"Frozen estimator entrypoint failed to import: {type(error).__name__}.",
            ) from error
        builder = getattr(module, "build_estimator", None)
        if not callable(builder):
            raise WorkerContractError(
                "missing_build_estimator",
                "Frozen entrypoint must define build_estimator(context).",
            )
        estimator = builder(dict(context))
    except WorkerContractError:
        raise
    except Exception as error:
        raise WorkerContractError(
            "estimator_build_failed",
            f"build_estimator failed: {type(error).__name__}.",
        ) from error
    finally:
        try:
            sys.path.remove(import_root)
        except ValueError:
            pass
    if not callable(getattr(estimator, "fit", None)) or not callable(
        getattr(estimator, "predict", None)
    ):
        raise WorkerContractError(
            "invalid_estimator",
            "build_estimator must return a sklearn-compatible estimator.",
        )
    try:
        clone(estimator)
    except Exception as error:
        raise WorkerContractError(
            "invalid_estimator",
            "Returned estimator cannot be cloned by sklearn.",
        ) from error
    return estimator


def classification_metrics(
    *,
    task_type: str,
    class_labels: tuple[str, ...],
    positive_class: str | None,
    observed: np.ndarray,
    predicted: np.ndarray,
    probabilities: np.ndarray,
) -> dict[str, float]:
    if probabilities.shape != (len(observed), len(class_labels)):
        raise WorkerContractError(
            "invalid_probability_output",
            "Estimator probabilities do not match samples and confirmed classes.",
        )
    if not np.isfinite(probabilities).all():
        raise WorkerContractError(
            "invalid_probability_output",
            "Estimator probabilities contain non-finite values.",
        )
    if task_type == "binary":
        if positive_class not in class_labels or len(class_labels) != 2:
            raise WorkerContractError(
                "invalid_dataset_semantics",
                "Binary task has invalid confirmed class semantics.",
            )
        positive_index = class_labels.index(positive_class)
        observed_binary = (observed == positive_class).astype(int)
        metrics = {
            "roc_auc": roc_auc_score(
                observed_binary,
                probabilities[:, positive_index],
            ),
            "accuracy": accuracy_score(observed, predicted),
            "f1": f1_score(observed, predicted, pos_label=positive_class),
        }
    elif task_type == "multiclass" and len(class_labels) >= 3:
        metrics = {
            "macro_f1": f1_score(observed, predicted, average="macro"),
            "accuracy": accuracy_score(observed, predicted),
            "roc_auc_ovr": roc_auc_score(
                observed,
                probabilities,
                labels=list(class_labels),
                multi_class="ovr",
                average="macro",
            ),
        }
    else:
        raise WorkerContractError(
            "invalid_dataset_semantics",
            "Worker supports only confirmed binary or multiclass tasks.",
        )
    normalized = {name: float(value) for name, value in metrics.items()}
    if any(
        not math.isfinite(value) or not 0 <= value <= 1
        for value in normalized.values()
    ):
        raise WorkerContractError(
            "invalid_metric_output",
            "Computed metric is non-finite or outside [0, 1].",
        )
    return normalized


def evaluate(
    repository_path: Path,
    input_path: Path,
    output_path: Path,
) -> dict[str, Any]:
    repository = repository_path.expanduser().resolve()
    frozen_input = input_path.expanduser().resolve()
    output = output_path.expanduser().resolve()
    _require_within(frozen_input, repository, "invalid_input_path")
    _require_within(
        output,
        repository / ".mlagent-local" / "run-work",
        "invalid_output_path",
    )
    payload = _load_json(frozen_input, "invalid_frozen_input")
    data = _load_data(repository, frozen_input, payload)
    code_revision = RunRepository(repository).load_code_revision(
        payload["run_id"],
        payload["code_fingerprint"],
    )
    if (
        code_revision.asset_path != payload.get("code_revision_path")
        or code_revision.entrypoint_path != payload.get("entrypoint_path")
    ):
        raise WorkerContractError(
            "frozen_code_mismatch",
            "Frozen code revision does not match the Training Instance input.",
        )
    code_manifest = repository / code_revision.asset_path
    code_root = code_manifest.parent / "files"
    entrypoint = code_root / code_revision.entrypoint_path
    context = {
        "run_id": payload["run_id"],
        "instance_id": payload["instance_id"],
        "round_number": payload["round_number"],
        "random_seed": payload["random_seed"],
        "task_type": data.task_type,
        "class_labels": list(data.class_labels),
        "positive_class": data.positive_class,
        "configuration": payload["configuration"],
    }
    estimator = load_estimator(entrypoint, context, code_root=code_root)
    evaluation_ids, observed, predicted, probabilities, fitted = _evaluate_estimator(
        estimator,
        data,
        payload["configuration"],
    )
    metrics = classification_metrics(
        task_type=data.task_type,
        class_labels=data.class_labels,
        positive_class=data.positive_class,
        observed=observed,
        predicted=predicted,
        probabilities=probabilities,
    )
    if data.primary_metric not in metrics:
        raise WorkerContractError(
            "invalid_primary_metric",
            "Confirmed primary metric is not produced for this task.",
        )
    output.mkdir(parents=True, exist_ok=True)
    predictions_path = output / "predictions.csv"
    prediction_frame = pd.DataFrame(
        {
            "sample_id": evaluation_ids,
            "observed": observed,
            "predicted": predicted,
        }
    )
    for index, label in enumerate(data.class_labels):
        prediction_frame[
            f"probability_{index}_{_column_token(label)}"
        ] = probabilities[:, index]
    prediction_frame.to_csv(predictions_path, index=False, lineterminator="\n")
    _write_json(output / "metrics.json", metrics)
    model_path = output / "model.joblib"
    joblib.dump(fitted, model_path, compress=3)
    model_fingerprint = _sha256(model_path.read_bytes())
    result = {
        "state": "completed",
        "primary_metric_name": data.primary_metric,
        "primary_metric_value": metrics[data.primary_metric],
        "metrics": metrics,
        "predictions_path": predictions_path.name,
        "model_path": model_path.name,
        "model_fingerprint": model_fingerprint,
    }
    _write_json(output / RESULT_FILENAME, result)
    return result


def _load_data(
    repository: Path,
    input_path: Path,
    payload: dict[str, Any],
) -> ClassificationData:
    try:
        dataset_id = payload["dataset_id"]
        dataset_version = payload["dataset_version"]
        snapshot = DatasetRepository(repository).load(dataset_id, dataset_version)
    except (KeyError, TypeError) as error:
        raise WorkerContractError(
            "invalid_frozen_input",
            "Training Instance is missing its Dataset Version binding.",
        ) from error
    if (
        snapshot.asset_path != payload.get("dataset_asset_path")
        or snapshot.content_fingerprint
        != payload.get("dataset_content_fingerprint")
        or snapshot.version_fingerprint
        != payload.get("dataset_version_fingerprint")
        or snapshot.primary_metric != payload.get("primary_metric_name")
        or snapshot.random_seed != payload.get("random_seed")
    ):
        raise WorkerContractError(
            "dataset_binding_mismatch",
            "Dataset Version does not match the frozen Training Instance input.",
        )
    dataset_root = repository / snapshot.asset_path
    dataset_manifest = _load_json(dataset_root, "invalid_dataset_version")
    if dataset_manifest.get("split_fingerprint") != payload.get(
        "split_fingerprint"
    ):
        raise WorkerContractError(
            "dataset_binding_mismatch",
            "Frozen split does not belong to the confirmed Dataset Version.",
        )
    dataset_root = dataset_root.parent
    features = pd.read_csv(dataset_root / snapshot.files["features"])
    labels = pd.read_csv(dataset_root / snapshot.files["labels"])
    split_path = input_path.parent / "split.csv"
    split_bytes = split_path.read_bytes()
    if _sha256(split_bytes) != payload.get("split_fingerprint"):
        raise WorkerContractError(
            "split_fingerprint_mismatch",
            "Frozen Training Instance split has changed.",
        )
    split = pd.read_csv(split_path)
    sample_column = snapshot.sample_id_col
    label_column = snapshot.label_col
    if (
        sample_column not in features
        or sample_column not in labels
        or sample_column not in split
        or label_column not in labels
    ):
        raise WorkerContractError(
            "invalid_dataset_files",
            "Dataset files do not contain the confirmed identifier and label columns.",
        )
    for frame in (features, labels, split):
        frame[sample_column] = frame[sample_column].astype("string").str.strip()
        if frame[sample_column].isna().any() or frame[sample_column].duplicated().any():
            raise WorkerContractError(
                "invalid_dataset_files",
                "Dataset files contain missing or duplicate sample IDs.",
            )
    feature_ids = features[sample_column].tolist()
    if set(feature_ids) != set(labels[sample_column]) or set(feature_ids) != set(
        split[sample_column]
    ):
        raise WorkerContractError(
            "dataset_alignment_failed",
            "Features, labels, and split do not contain the same samples.",
        )
    labels = labels.set_index(sample_column).loc[feature_ids]
    split = split.set_index(sample_column).loc[feature_ids]
    feature_columns = [column for column in features if column != sample_column]
    try:
        numeric_features = features[feature_columns].apply(
            pd.to_numeric,
            errors="raise",
        )
    except (TypeError, ValueError) as error:
        raise WorkerContractError(
            "non_numeric_features",
            "Frozen worker currently requires numeric feature columns.",
        ) from error
    if numeric_features.isna().any().any():
        raise WorkerContractError(
            "missing_features",
            "Frozen worker does not accept missing feature values.",
        )
    observed = labels[label_column].astype("string").str.strip().to_numpy(dtype=str)
    class_labels = tuple(str(value) for value in snapshot.class_labels)
    if set(observed) != set(class_labels):
        raise WorkerContractError(
            "invalid_dataset_semantics",
            "Observed labels do not match the confirmed classes.",
        )
    partitions = split["partition"].astype("string").str.strip().to_numpy(dtype=str)
    if set(partitions) - {"train", "test"}:
        raise WorkerContractError(
            "invalid_split",
            "Frozen split contains an unsupported partition.",
        )
    return ClassificationData(
        features=numeric_features,
        labels=observed,
        sample_ids=np.asarray(feature_ids, dtype=str),
        partitions=partitions,
        task_type=snapshot.task_type,
        class_labels=class_labels,
        positive_class=snapshot.positive_class,
        primary_metric=snapshot.primary_metric,
        split_strategy=snapshot.split_strategy,
        random_seed=snapshot.random_seed,
    )


def _evaluate_estimator(
    estimator: Any,
    data: ClassificationData,
    configuration: dict[str, Any],
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, Any]:
    if data.split_strategy == "train_only":
        requested_folds = configuration.get("cv_folds", 5)
        if type(requested_folds) is not int or requested_folds < 2:
            raise WorkerContractError(
                "invalid_cv_folds",
                "cv_folds must be an integer of at least 2.",
            )
        class_counts = pd.Series(data.labels).value_counts()
        fold_count = min(requested_folds, int(class_counts.min()))
        if fold_count < 2:
            raise WorkerContractError(
                "insufficient_class_samples",
                "Each class requires at least two samples for train-only evaluation.",
            )
        predicted = np.empty(len(data.labels), dtype=object)
        probabilities = np.zeros((len(data.labels), len(data.class_labels)))
        splitter = StratifiedKFold(
            n_splits=fold_count,
            shuffle=True,
            random_state=data.random_seed,
        )
        for train_indices, validation_indices in splitter.split(
            data.features,
            data.labels,
        ):
            fold_model = clone(estimator)
            fold_model.fit(
                data.features.iloc[train_indices],
                data.labels[train_indices],
            )
            predicted[validation_indices] = np.asarray(
                fold_model.predict(data.features.iloc[validation_indices]),
                dtype=str,
            )
            probabilities[validation_indices] = _probability_matrix(
                fold_model,
                data.features.iloc[validation_indices],
                data.class_labels,
            )
        fitted = clone(estimator).fit(data.features, data.labels)
        return (
            data.sample_ids,
            data.labels,
            predicted.astype(str),
            probabilities,
            fitted,
        )
    if data.split_strategy == "stratified_random":
        train_mask = data.partitions == "train"
        test_mask = data.partitions == "test"
        if not train_mask.any() or not test_mask.any():
            raise WorkerContractError(
                "invalid_split",
                "Held-out evaluation requires non-empty train and test partitions.",
            )
        fitted = clone(estimator).fit(
            data.features.loc[train_mask],
            data.labels[train_mask],
        )
        test_features = data.features.loc[test_mask]
        predicted = np.asarray(fitted.predict(test_features), dtype=str)
        probabilities = _probability_matrix(
            fitted,
            test_features,
            data.class_labels,
        )
        return (
            data.sample_ids[test_mask],
            data.labels[test_mask],
            predicted,
            probabilities,
            fitted,
        )
    raise WorkerContractError(
        "invalid_split",
        "Worker supports train_only or stratified_random splits.",
    )


def _probability_matrix(
    estimator: Any,
    features: pd.DataFrame,
    class_labels: tuple[str, ...],
) -> np.ndarray:
    estimator_classes = tuple(str(value) for value in estimator.classes_)
    if set(estimator_classes) != set(class_labels):
        raise WorkerContractError(
            "invalid_probability_output",
            "Fitted estimator classes do not match confirmed classes.",
        )
    if callable(getattr(estimator, "predict_proba", None)):
        raw = np.asarray(estimator.predict_proba(features), dtype=float)
    elif callable(getattr(estimator, "decision_function", None)):
        decision = np.asarray(estimator.decision_function(features), dtype=float)
        if decision.ndim == 1 and len(estimator_classes) == 2:
            positive = 1.0 / (1.0 + np.exp(-np.clip(decision, -700, 700)))
            raw = np.column_stack([1.0 - positive, positive])
        elif decision.ndim == 2:
            shifted = decision - decision.max(axis=1, keepdims=True)
            exponentiated = np.exp(shifted)
            raw = exponentiated / exponentiated.sum(axis=1, keepdims=True)
        else:
            raise WorkerContractError(
                "invalid_probability_output",
                "Estimator decision output has an unsupported shape.",
            )
    else:
        raise WorkerContractError(
            "missing_probability_output",
            "Estimator must provide predict_proba or decision_function.",
        )
    if raw.shape != (len(features), len(estimator_classes)):
        raise WorkerContractError(
            "invalid_probability_output",
            "Estimator probability output has an unexpected shape.",
        )
    aligned = np.zeros((len(features), len(class_labels)))
    for source_index, label in enumerate(estimator_classes):
        aligned[:, class_labels.index(label)] = raw[:, source_index]
    if not np.isfinite(aligned).all():
        raise WorkerContractError(
            "invalid_probability_output",
            "Estimator probabilities contain non-finite values.",
        )
    return aligned


def _load_json(path: Path, code: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise WorkerContractError(code, f"JSON input cannot be read: {path.name}.") from error
    if not isinstance(payload, dict):
        raise WorkerContractError(code, f"JSON input must be an object: {path.name}.")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )


def _require_within(path: Path, root: Path, code: str) -> None:
    try:
        path.relative_to(root.resolve())
    except ValueError as error:
        raise WorkerContractError(code, "Worker path is outside its allowed root.") from error


def _column_token(value: str) -> str:
    token = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("_")
    return token[:48] or "class"


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _is_local_output(repository: Path, output: Path) -> bool:
    try:
        output.expanduser().resolve(strict=False).relative_to(
            repository.expanduser().resolve()
            / ".mlagent-local"
            / "run-work"
        )
    except ValueError:
        return False
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", required=True, type=Path)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    arguments = parser.parse_args(argv)
    try:
        evaluate(arguments.repository, arguments.input, arguments.output)
    except WorkerContractError as error:
        if _is_local_output(arguments.repository, arguments.output):
            arguments.output.mkdir(parents=True, exist_ok=True)
            _write_json(
                arguments.output / ERROR_FILENAME,
                {"error_code": error.code, "error_summary": str(error)[:2000]},
            )
        print(f"{error.code}: {error}", file=sys.stderr)
        return 1
    except Exception as error:
        summary = f"Unhandled worker error: {type(error).__name__}."
        if _is_local_output(arguments.repository, arguments.output):
            arguments.output.mkdir(parents=True, exist_ok=True)
            _write_json(
                arguments.output / ERROR_FILENAME,
                {"error_code": "worker_failed", "error_summary": summary},
            )
        print(summary, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
