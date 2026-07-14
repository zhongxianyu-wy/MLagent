from __future__ import annotations

import csv
import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
from sklearn.model_selection import train_test_split

from src.domain.models import (
    ConfirmDatasetCommand,
    DatasetInspection,
    DatasetPreview,
    InspectDatasetCommand,
    WorkspaceError,
)


SAMPLE_ID_NAMES = ("sample_id", "sample", "id")
LABEL_NAMES = ("label", "group", "status", "class", "target")
TASK_METRICS = {
    "binary": {"roc_auc", "accuracy", "f1"},
    "multiclass": {"macro_f1", "accuracy", "roc_auc_ovr"},
}


@dataclass(frozen=True)
class NormalizedDataset:
    feature_bytes: bytes
    label_bytes: bytes
    split_bytes: bytes
    content_fingerprint: str
    split_fingerprint: str
    version_fingerprint: str
    source_files: tuple[dict[str, str], ...]
    sample_id_col: str
    label_col: str
    task_type: str
    class_labels: tuple[str, ...]
    positive_class: str | None
    primary_metric: str
    target_metric: float
    split_strategy: str
    test_ratio: float | None
    random_seed: int
    sample_count: int
    feature_count: int
    dtypes: dict[str, str]
    missing_rates: dict[str, float]
    class_distribution: dict[str, int]
    preview: DatasetPreview
    warnings: tuple[str, ...]


class DatasetInspector:
    def inspect(self, command: InspectDatasetCommand) -> DatasetInspection:
        started = time.perf_counter()
        feature_path = self._validate_csv_path(command.feature_path, "features")
        label_path = self._validate_csv_path(command.label_path, "labels")
        features = self._read_csv(feature_path)
        labels = self._read_csv(label_path)

        sample_id_col = self._infer_sample_id_col(
            features,
            labels,
            command.sample_id_col,
        )
        label_col = self._infer_label_col(
            labels,
            sample_id_col,
            command.label_col,
        )
        blockers = self._structural_blockers(
            features,
            labels,
            sample_id_col,
            label_col,
            sample_hint=command.sample_id_col,
            label_hint=command.label_col,
        )

        feature_columns = [
            column for column in features.columns if column != sample_id_col
        ]
        dtypes = {column: str(features[column].dtype) for column in feature_columns}
        missing_rates = {
            column: float(features[column].isna().mean())
            for column in feature_columns
        }
        warnings: list[str] = []
        if any(rate > 0 for rate in missing_rates.values()):
            warnings.append("feature_missing_values")
        if any(
            not pd.api.types.is_numeric_dtype(features[column])
            for column in feature_columns
        ):
            warnings.append("non_numeric_features")

        class_labels: tuple[str, ...] = ()
        class_distribution: dict[str, int] = {}
        task_type = None
        if label_col is not None and label_col in labels and not labels[label_col].isna().any():
            normalized_labels = labels[label_col].map(str)
            class_distribution = {
                label: int(count)
                for label, count in sorted(normalized_labels.value_counts().items())
            }
            class_labels = tuple(class_distribution)
            if len(class_labels) == 2:
                task_type = "binary"
            elif len(class_labels) >= 3:
                task_type = "multiclass"
            else:
                blockers.append("insufficient_classes")

        preview_frame = self._preview_frame(
            features,
            labels,
            sample_id_col,
            label_col,
            blockers,
        )
        unresolved: list[str] = []
        if sample_id_col is None:
            unresolved.append("sample_id_col")
        if label_col is None:
            unresolved.append("label_col")
        if task_type is None:
            unresolved.append("task_type")
        if task_type == "binary":
            unresolved.append("positive_class")
        unresolved.extend(("primary_metric", "split_strategy", "target_metric"))

        return DatasetInspection(
            status="Failed" if blockers else "Pending confirmation",
            feature_path=feature_path,
            label_path=label_path,
            inferred_sample_id_col=sample_id_col,
            inferred_label_col=label_col,
            inferred_task_type=task_type,
            class_labels=class_labels,
            sample_count=len(features),
            feature_count=len(feature_columns),
            dtypes=dtypes,
            missing_rates=missing_rates,
            class_distribution=class_distribution,
            preview=self._bounded_preview(preview_frame),
            unresolved_fields=tuple(unresolved),
            warnings=tuple(warnings),
            blockers=tuple(dict.fromkeys(blockers)),
            elapsed_ms=max(0, round((time.perf_counter() - started) * 1000)),
        )

    def normalize(self, command: ConfirmDatasetCommand) -> NormalizedDataset:
        inspection = self.inspect(
            InspectDatasetCommand(
                feature_path=command.feature_path,
                label_path=command.label_path,
                sample_id_col=command.sample_id_col,
                label_col=command.label_col,
            )
        )
        if inspection.blockers:
            self._raise_blocker(inspection.blockers[0])
        if inspection.inferred_sample_id_col != command.sample_id_col:
            self._raise(
                "invalid_sample_id_column",
                f"Sample ID column is not present in both CSV files: {command.sample_id_col}",
                "Choose one shared sample identifier column from the inspection result.",
            )
        if inspection.inferred_label_col != command.label_col:
            self._raise(
                "invalid_label_column",
                f"Label column is not present in the label CSV: {command.label_col}",
                "Choose a label column from the inspection result.",
            )

        feature_path = command.feature_path.expanduser().resolve()
        label_path = command.label_path.expanduser().resolve()
        features = self._read_csv(feature_path).copy()
        labels = self._read_csv(label_path).copy()
        sample_id_col = command.sample_id_col
        label_col = command.label_col
        features[sample_id_col] = self._normalized_ids(features[sample_id_col])
        labels[sample_id_col] = self._normalized_ids(labels[sample_id_col])
        labels[label_col] = labels[label_col].map(str)
        labels = labels.set_index(sample_id_col).loc[
            features[sample_id_col]
        ].reset_index()

        class_labels = tuple(sorted(labels[label_col].unique()))
        self._validate_task(command, class_labels)
        self._validate_metric_and_target(command)
        split = self._build_split(command, features[sample_id_col], labels[label_col])

        normalized_features = features.reset_index(drop=True)
        normalized_labels = labels[[sample_id_col, label_col]].reset_index(drop=True)
        feature_bytes = self._csv_bytes(normalized_features)
        label_bytes = self._csv_bytes(normalized_labels)
        split_bytes = self._csv_bytes(split)
        content_fingerprint = self._sha256(
            feature_bytes + b"\0" + label_bytes
        )
        split_fingerprint = self._sha256(split_bytes)
        semantic_payload = {
            "content_fingerprint": content_fingerprint,
            "split_fingerprint": split_fingerprint,
            "sample_id_col": sample_id_col,
            "label_col": label_col,
            "task_type": command.task_type,
            "class_labels": class_labels,
            "positive_class": command.positive_class,
            "primary_metric": command.primary_metric,
            "target_metric": float(command.target_metric),
            "split_strategy": command.split_strategy,
            "test_ratio": command.test_ratio,
            "random_seed": command.random_seed,
        }
        version_fingerprint = self._sha256(
            json.dumps(
                semantic_payload,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        )
        feature_columns = [
            column for column in normalized_features.columns if column != sample_id_col
        ]
        dtypes = {
            column: str(normalized_features[column].dtype)
            for column in feature_columns
        }
        missing_rates = {
            column: float(normalized_features[column].isna().mean())
            for column in feature_columns
        }
        class_distribution = {
            label: int(count)
            for label, count in sorted(normalized_labels[label_col].value_counts().items())
        }
        preview_frame = normalized_features.copy()
        preview_frame[label_col] = normalized_labels[label_col]

        return NormalizedDataset(
            feature_bytes=feature_bytes,
            label_bytes=label_bytes,
            split_bytes=split_bytes,
            content_fingerprint=content_fingerprint,
            split_fingerprint=split_fingerprint,
            version_fingerprint=version_fingerprint,
            source_files=(
                {
                    "role": "features",
                    "name": feature_path.name,
                    "sha256": self._sha256(feature_path.read_bytes()),
                },
                {
                    "role": "labels",
                    "name": label_path.name,
                    "sha256": self._sha256(label_path.read_bytes()),
                },
            ),
            sample_id_col=sample_id_col,
            label_col=label_col,
            task_type=command.task_type,
            class_labels=class_labels,
            positive_class=command.positive_class,
            primary_metric=command.primary_metric,
            target_metric=float(command.target_metric),
            split_strategy=command.split_strategy,
            test_ratio=command.test_ratio,
            random_seed=command.random_seed,
            sample_count=len(normalized_features),
            feature_count=len(feature_columns),
            dtypes=dtypes,
            missing_rates=missing_rates,
            class_distribution=class_distribution,
            preview=self._bounded_preview(preview_frame),
            warnings=inspection.warnings,
        )

    @staticmethod
    def _validate_csv_path(path: Path, role: str) -> Path:
        resolved = path.expanduser().resolve()
        if not resolved.is_file() or resolved.suffix.lower() != ".csv":
            DatasetInspector._raise(
                "invalid_dataset_file",
                f"The {role} input must be an existing CSV file: {resolved}",
                "Choose an explicit local CSV file and retry intake-data.",
            )
        return resolved

    @staticmethod
    def _read_csv(path: Path) -> pd.DataFrame:
        try:
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                header = next(csv.reader(handle))
            if not header or len(header) != len(set(header)):
                DatasetInspector._raise(
                    "duplicate_column",
                    f"CSV columns are empty or duplicated: {path.name}",
                    "Rename duplicate columns before confirming the Dataset Version.",
                )
            return pd.read_csv(path)
        except (OSError, UnicodeError, pd.errors.ParserError, StopIteration) as error:
            raise WorkspaceError(
                code="invalid_dataset_file",
                message=f"CSV input cannot be read: {path}",
                next_action="Check CSV encoding, header, and row structure, then retry intake-data.",
            ) from error

    @staticmethod
    def _infer_sample_id_col(
        features: pd.DataFrame,
        labels: pd.DataFrame,
        hint: str | None,
    ) -> str | None:
        if hint is not None:
            return hint if hint in features.columns and hint in labels.columns else None
        common = set(features.columns) & set(labels.columns)
        lowered = {str(column).lower(): str(column) for column in common}
        for candidate in SAMPLE_ID_NAMES:
            if candidate in lowered:
                return lowered[candidate]
        return None

    @staticmethod
    def _infer_label_col(
        labels: pd.DataFrame,
        sample_id_col: str | None,
        hint: str | None,
    ) -> str | None:
        if hint is not None:
            return hint if hint in labels.columns and hint != sample_id_col else None
        candidates = [column for column in labels.columns if column != sample_id_col]
        lowered = {str(column).lower(): str(column) for column in candidates}
        for candidate in LABEL_NAMES:
            if candidate in lowered:
                return lowered[candidate]
        return str(candidates[0]) if len(candidates) == 1 else None

    @staticmethod
    def _structural_blockers(
        features: pd.DataFrame,
        labels: pd.DataFrame,
        sample_id_col: str | None,
        label_col: str | None,
        sample_hint: str | None,
        label_hint: str | None,
    ) -> list[str]:
        blockers: list[str] = []
        if sample_hint is not None and sample_id_col is None:
            blockers.append("invalid_sample_id_column")
        if label_hint is not None and label_col is None:
            blockers.append("invalid_label_column")
        if sample_id_col is not None:
            feature_ids = features[sample_id_col]
            label_ids = labels[sample_id_col]
            if DatasetInspector._has_missing_or_blank(feature_ids) or DatasetInspector._has_missing_or_blank(label_ids):
                blockers.append("missing_sample_id")
            if feature_ids.duplicated().any():
                blockers.append("duplicate_feature_sample_id")
            if label_ids.duplicated().any():
                blockers.append("duplicate_label_sample_id")
            if not blockers and set(feature_ids.map(str)) != set(label_ids.map(str)):
                blockers.append("sample_mismatch")
        if label_col is not None and labels[label_col].isna().any():
            blockers.append("missing_label")
        return blockers

    @staticmethod
    def _preview_frame(
        features: pd.DataFrame,
        labels: pd.DataFrame,
        sample_id_col: str | None,
        label_col: str | None,
        blockers: list[str],
    ) -> pd.DataFrame:
        preview = features.copy()
        if (
            sample_id_col is None
            or label_col is None
            or any(
                blocker
                in {
                    "missing_sample_id",
                    "duplicate_feature_sample_id",
                    "duplicate_label_sample_id",
                    "sample_mismatch",
                }
                for blocker in blockers
            )
        ):
            return preview
        label_lookup = labels.set_index(sample_id_col)[label_col]
        preview[label_col] = features[sample_id_col].map(label_lookup)
        return preview

    @staticmethod
    def _bounded_preview(frame: pd.DataFrame, limit: int = 10) -> DatasetPreview:
        if len(frame) <= limit:
            selected = frame
            omitted = 0
        else:
            edge = limit // 2
            selected = pd.concat([frame.head(edge), frame.tail(limit - edge)])
            omitted = len(frame) - len(selected)
        rows = tuple(
            tuple(DatasetInspector._json_scalar(value) for value in row)
            for row in selected.itertuples(index=False, name=None)
        )
        return DatasetPreview(
            columns=tuple(str(column) for column in frame.columns),
            rows=rows,
            omitted_count=omitted,
        )

    @staticmethod
    def _json_scalar(value: Any) -> Any:
        if pd.isna(value):
            return None
        if hasattr(value, "item"):
            return value.item()
        return value

    @staticmethod
    def _normalized_ids(values: pd.Series) -> pd.Series:
        normalized = values.map(str).str.strip()
        if (normalized == "").any():
            DatasetInspector._raise_blocker("missing_sample_id")
        return normalized

    @staticmethod
    def _validate_task(
        command: ConfirmDatasetCommand,
        class_labels: tuple[str, ...],
    ) -> None:
        if command.task_type not in TASK_METRICS:
            DatasetInspector._raise(
                "unsupported_task",
                f"Task type is outside the v0.4 classification boundary: {command.task_type}",
                "Choose binary or multiclass classification.",
            )
        if command.task_type == "binary":
            if len(class_labels) != 2:
                DatasetInspector._raise(
                    "task_label_mismatch",
                    "Binary classification requires exactly two observed classes.",
                    "Correct the labels or confirm multiclass classification.",
                )
            if command.positive_class not in class_labels:
                DatasetInspector._raise(
                    "invalid_positive_class",
                    "The binary positive class is not one of the observed labels.",
                    "Choose one observed class as the positive class.",
                )
        elif len(class_labels) < 3:
            DatasetInspector._raise(
                "task_label_mismatch",
                "Multiclass classification requires at least three observed classes.",
                "Correct the labels or confirm binary classification.",
            )
        elif command.positive_class is not None:
            DatasetInspector._raise(
                "invalid_positive_class",
                "Multiclass confirmation must not define one positive class.",
                "Remove the positive-class option for multiclass intake.",
            )

    @staticmethod
    def _validate_metric_and_target(command: ConfirmDatasetCommand) -> None:
        if command.primary_metric not in TASK_METRICS.get(command.task_type, set()):
            DatasetInspector._raise(
                "invalid_metric",
                f"Metric {command.primary_metric} is not valid for {command.task_type} classification.",
                "Choose a task-compatible primary metric from the intake guidance.",
            )
        if (
            isinstance(command.target_metric, bool)
            or not isinstance(command.target_metric, (int, float))
            or not 0 <= float(command.target_metric) <= 1
        ):
            DatasetInspector._raise(
                "invalid_target_metric",
                "Target performance must be a number from 0 through 1.",
                "Choose an explicit target value in the inclusive [0, 1] range.",
            )

    @staticmethod
    def _build_split(
        command: ConfirmDatasetCommand,
        sample_ids: pd.Series,
        labels: pd.Series,
    ) -> pd.DataFrame:
        if command.split_strategy == "train_only":
            if command.test_ratio is not None:
                DatasetInspector._raise(
                    "invalid_split",
                    "Train-only intake cannot define a test ratio.",
                    "Remove the test ratio or choose stratified_random.",
                )
            partitions = ["train"] * len(sample_ids)
        elif command.split_strategy == "stratified_random":
            if (
                command.test_ratio is None
                or isinstance(command.test_ratio, bool)
                or not 0 < float(command.test_ratio) < 1
            ):
                DatasetInspector._raise(
                    "invalid_split",
                    "Stratified random split requires a test ratio between 0 and 1.",
                    "Provide --test-ratio with a value that leaves every class in train and test.",
                )
            try:
                _, test_ids = train_test_split(
                    sample_ids.tolist(),
                    test_size=float(command.test_ratio),
                    random_state=command.random_seed,
                    stratify=labels.tolist(),
                )
            except ValueError as error:
                raise WorkspaceError(
                    code="invalid_split",
                    message=f"The requested stratified split is not feasible: {error}",
                    next_action="Increase class sample counts or choose a different test ratio.",
                ) from error
            test_set = set(test_ids)
            partitions = [
                "test" if sample_id in test_set else "train"
                for sample_id in sample_ids
            ]
            partitioned = pd.DataFrame(
                {"label": labels, "partition": partitions}
            )
            coverage = partitioned.groupby("label")["partition"].nunique()
            if (coverage < 2).any():
                DatasetInspector._raise(
                    "invalid_split",
                    "Every class must appear in both train and test partitions.",
                    "Increase class sample counts or choose a different test ratio.",
                )
        else:
            DatasetInspector._raise(
                "invalid_split",
                f"Unsupported split strategy: {command.split_strategy}",
                "Choose train_only or stratified_random.",
            )
        return pd.DataFrame(
            {command.sample_id_col: sample_ids, "partition": partitions}
        )

    @staticmethod
    def _csv_bytes(frame: pd.DataFrame) -> bytes:
        return frame.to_csv(index=False, lineterminator="\n").encode("utf-8")

    @staticmethod
    def _sha256(value: bytes) -> str:
        return hashlib.sha256(value).hexdigest()

    @staticmethod
    def _has_missing_or_blank(values: pd.Series) -> bool:
        return bool(values.isna().any() or values.map(str).str.strip().eq("").any())

    @staticmethod
    def _raise_blocker(code: str) -> None:
        details = {
            "missing_sample_id": (
                "Sample IDs contain missing or blank values.",
                "Fill every sample ID before confirming the Dataset Version.",
            ),
            "duplicate_feature_sample_id": (
                "Feature sample IDs are not unique.",
                "Resolve duplicate feature rows before confirming the Dataset Version.",
            ),
            "duplicate_label_sample_id": (
                "Label sample IDs are not unique.",
                "Resolve duplicate label rows before confirming the Dataset Version.",
            ),
            "sample_mismatch": (
                "Feature and label sample ID sets do not match.",
                "Add the missing rows or select matching feature and label files.",
            ),
            "missing_label": (
                "At least one sample has no classification label.",
                "Fill or remove missing labels before confirming the Dataset Version.",
            ),
            "insufficient_classes": (
                "Classification requires at least two observed classes.",
                "Correct the label column before confirming the task.",
            ),
            "invalid_sample_id_column": (
                "The selected sample ID column is not shared by both CSV files.",
                "Choose one shared sample identifier column.",
            ),
            "invalid_label_column": (
                "The selected label column is not present in the label CSV.",
                "Choose a valid label column from the inspection result.",
            ),
        }
        message, next_action = details.get(
            code,
            (
                f"Dataset confirmation is blocked by {code}.",
                "Resolve the blocker reported by inspection and retry.",
            ),
        )
        DatasetInspector._raise(code, message, next_action)

    @staticmethod
    def _raise(code: str, message: str, next_action: str) -> None:
        raise WorkspaceError(
            code=code,
            message=message,
            next_action=next_action,
        )
