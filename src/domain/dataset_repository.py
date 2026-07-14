from __future__ import annotations

import hashlib
import json
import re
import shutil
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

from src.domain.dataset_intake import (
    NormalizedDataset,
    dataset_semantic_fingerprint,
)
from src.domain.models import (
    CapacityStatus,
    DatasetPreview,
    DatasetVersionSnapshot,
    WorkspaceError,
)


DATASET_SCHEMA_VERSION = 1
DATASET_ID_PATTERN = re.compile(r"^ds-[A-Za-z0-9][A-Za-z0-9._-]{0,59}$")
VERSION_DIRECTORY_PATTERN = re.compile(r"^v([0-9]{4})$")
DATASET_FILES = {
    "features": "features.csv",
    "labels": "labels.csv",
    "split": "split.csv",
}


class DatasetRepository:
    def __init__(
        self,
        repository_path: Path,
        id_factory: Callable[[], str] | None = None,
        clock: Callable[[], str] | None = None,
    ) -> None:
        self.repository_path = repository_path.expanduser().resolve()
        self.datasets_path = self.repository_path / "datasets"
        self.id_factory = id_factory or (lambda: f"ds-{uuid.uuid4()}")
        self.clock = clock or _utc_now

    def create_version(
        self,
        normalized: NormalizedDataset,
        actor_id: str,
        capacity: CapacityStatus,
        dataset_id: str | None = None,
    ) -> DatasetVersionSnapshot:
        if not isinstance(actor_id, str) or not actor_id.strip():
            raise WorkspaceError(
                code="missing_actor",
                message="A Dataset Version requires a non-empty creator identity.",
                next_action="Reconnect the workspace with a valid team member identity.",
            )
        resolved_dataset_id = dataset_id or self.id_factory()
        self._validate_dataset_id(resolved_dataset_id)
        existing_versions = self._version_numbers(resolved_dataset_id)
        for version in existing_versions:
            snapshot = self.load(resolved_dataset_id, version)
            if snapshot.version_fingerprint == normalized.version_fingerprint:
                return snapshot

        version = max(existing_versions, default=0) + 1
        created_at = self.clock()
        if not isinstance(created_at, str) or not created_at.strip():
            raise WorkspaceError(
                code="invalid_dataset_version",
                message="Dataset Version creation time is empty or invalid.",
                next_action="Retry with a valid UTC clock before writing authoritative assets.",
            )
        manifest = self._build_manifest(
            normalized,
            dataset_id=resolved_dataset_id,
            version=version,
            actor_id=actor_id,
            created_at=created_at,
        )
        manifest_bytes = self._manifest_bytes(manifest)
        encoded_files = {
            DATASET_FILES["features"]: normalized.feature_bytes,
            DATASET_FILES["labels"]: normalized.label_bytes,
            DATASET_FILES["split"]: normalized.split_bytes,
            "manifest.json": manifest_bytes,
        }
        self._validate_capacity(encoded_files, capacity)

        family_path = self.datasets_path / resolved_dataset_id
        version_name = f"v{version:04d}"
        version_path = family_path / version_name
        if version_path.exists():
            raise WorkspaceError(
                code="dataset_version_exists",
                message=f"Dataset Version path already exists: {version_path}",
                next_action="Reload the existing version or create the next reviewed version.",
            )
        family_path.mkdir(parents=True, exist_ok=True)
        temporary_path = family_path / f".{version_name}.tmp-{uuid.uuid4().hex}"
        try:
            temporary_path.mkdir()
            for filename, content in encoded_files.items():
                (temporary_path / filename).write_bytes(content)
            temporary_path.rename(version_path)
        except OSError as error:
            shutil.rmtree(temporary_path, ignore_errors=True)
            try:
                family_path.rmdir()
            except OSError:
                pass
            raise WorkspaceError(
                code="dataset_write_failed",
                message="The Dataset Version could not be written atomically.",
                next_action="Check Team Memory permissions and free disk space, then retry.",
            ) from error
        return self.load(resolved_dataset_id, version)

    def load(
        self,
        dataset_id: str,
        version: int | None = None,
    ) -> DatasetVersionSnapshot:
        self._validate_dataset_id(dataset_id)
        selected_version = version
        if selected_version is None:
            versions = self._version_numbers(dataset_id)
            if not versions:
                raise WorkspaceError(
                    code="dataset_not_found",
                    message=f"No Dataset Version exists for {dataset_id}.",
                    next_action="Inspect and confirm the dataset before using it.",
                )
            selected_version = versions[-1]
        if type(selected_version) is not int or selected_version <= 0:
            raise WorkspaceError(
                code="invalid_dataset_version",
                message="Dataset version must be a positive integer.",
                next_action="Choose a version listed by Dataset Overview.",
            )

        relative_path = Path(
            "datasets",
            dataset_id,
            f"v{selected_version:04d}",
            "manifest.json",
        )
        manifest_path = self.repository_path / relative_path
        manifest = self._load_manifest(manifest_path)
        self._validate_manifest_identity(
            manifest,
            dataset_id=dataset_id,
            version=selected_version,
        )
        self._validate_manifest_fingerprint(manifest)
        self._validate_data_fingerprints(manifest, manifest_path.parent)
        return self._snapshot(manifest, relative_path.as_posix())

    def latest(self) -> DatasetVersionSnapshot | None:
        snapshots: list[DatasetVersionSnapshot] = []
        if not self.datasets_path.is_dir():
            return None
        for manifest_path in sorted(
            self.datasets_path.glob("*/v[0-9][0-9][0-9][0-9]/manifest.json")
        ):
            dataset_id = manifest_path.parent.parent.name
            match = VERSION_DIRECTORY_PATTERN.fullmatch(manifest_path.parent.name)
            if match is None:
                continue
            snapshots.append(self.load(dataset_id, int(match.group(1))))
        if not snapshots:
            return None
        return max(
            snapshots,
            key=lambda snapshot: (
                snapshot.created_at,
                snapshot.dataset_id,
                snapshot.version,
            ),
        )

    def _version_numbers(self, dataset_id: str) -> list[int]:
        family_path = self.datasets_path / dataset_id
        if not family_path.is_dir():
            return []
        versions = []
        for path in family_path.iterdir():
            match = VERSION_DIRECTORY_PATTERN.fullmatch(path.name)
            if path.is_dir() and match is not None:
                versions.append(int(match.group(1)))
        return sorted(versions)

    @staticmethod
    def _build_manifest(
        normalized: NormalizedDataset,
        dataset_id: str,
        version: int,
        actor_id: str,
        created_at: str,
    ) -> dict[str, Any]:
        file_fingerprints = {
            "features": hashlib.sha256(normalized.feature_bytes).hexdigest(),
            "labels": hashlib.sha256(normalized.label_bytes).hexdigest(),
            "split": hashlib.sha256(normalized.split_bytes).hexdigest(),
        }
        manifest: dict[str, Any] = {
            "asset_type": "dataset_version",
            "asset_id": f"{dataset_id}-v{version:04d}",
            "dataset_id": dataset_id,
            "version": version,
            "state": "confirmed",
            "schema_version": DATASET_SCHEMA_VERSION,
            "created_at": created_at,
            "created_by": actor_id,
            "content_fingerprint": normalized.content_fingerprint,
            "split_fingerprint": normalized.split_fingerprint,
            "version_fingerprint": normalized.version_fingerprint,
            "source_files": list(normalized.source_files),
            "sample_id_col": normalized.sample_id_col,
            "label_col": normalized.label_col,
            "task_type": normalized.task_type,
            "class_labels": list(normalized.class_labels),
            "positive_class": normalized.positive_class,
            "primary_metric": normalized.primary_metric,
            "target_metric": normalized.target_metric,
            "split_strategy": normalized.split_strategy,
            "test_ratio": normalized.test_ratio,
            "random_seed": normalized.random_seed,
            "sample_count": normalized.sample_count,
            "feature_count": normalized.feature_count,
            "dtypes": normalized.dtypes,
            "missing_rates": normalized.missing_rates,
            "class_distribution": normalized.class_distribution,
            "preview": normalized.preview.to_dict(),
            "warnings": list(normalized.warnings),
            "files": dict(DATASET_FILES),
            "file_fingerprints": file_fingerprints,
        }
        manifest["manifest_fingerprint"] = DatasetRepository._manifest_fingerprint(
            manifest
        )
        return manifest

    @staticmethod
    def _manifest_bytes(manifest: dict[str, Any]) -> bytes:
        return (
            json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
        ).encode("utf-8")

    @staticmethod
    def _validate_capacity(
        encoded_files: dict[str, bytes],
        capacity: CapacityStatus,
    ) -> None:
        oversized = [
            filename
            for filename, content in encoded_files.items()
            if len(content) >= capacity.max_file_bytes
        ]
        if oversized:
            raise WorkspaceError(
                code="file_too_large",
                message=f"Dataset Version files reach the single-file limit: {', '.join(oversized)}",
                next_action="Reduce or partition the source before creating a Git-backed Dataset Version.",
            )
        projected_size = capacity.bytes_used + sum(
            len(content) for content in encoded_files.values()
        )
        if projected_size >= capacity.max_repository_bytes:
            raise WorkspaceError(
                code="repository_capacity_exceeded",
                message="The Dataset Version would reach the Team Memory capacity limit.",
                next_action="Archive reviewed assets or choose a smaller dataset before confirming this version.",
            )

    @staticmethod
    def _load_manifest(path: Path) -> dict[str, Any]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise WorkspaceError(
                code="invalid_dataset_version",
                message=f"Dataset Version manifest cannot be read: {path}",
                next_action="Restore the immutable Dataset Version from Git.",
            ) from error
        if not isinstance(payload, dict):
            raise WorkspaceError(
                code="invalid_dataset_version",
                message="Dataset Version manifest must be a JSON object.",
                next_action="Restore the immutable Dataset Version from Git.",
            )
        return payload

    @staticmethod
    def _validate_manifest_identity(
        manifest: dict[str, Any],
        dataset_id: str,
        version: int,
    ) -> None:
        required = {
            "asset_type",
            "asset_id",
            "dataset_id",
            "version",
            "state",
            "schema_version",
            "created_at",
            "created_by",
            "content_fingerprint",
            "split_fingerprint",
            "version_fingerprint",
            "source_files",
            "sample_id_col",
            "label_col",
            "task_type",
            "class_labels",
            "positive_class",
            "primary_metric",
            "target_metric",
            "split_strategy",
            "test_ratio",
            "random_seed",
            "sample_count",
            "feature_count",
            "dtypes",
            "missing_rates",
            "class_distribution",
            "preview",
            "warnings",
            "files",
            "file_fingerprints",
            "manifest_fingerprint",
        }
        if not required.issubset(manifest):
            DatasetRepository._invalid_manifest("required fields are missing")
        if (
            manifest["asset_type"] != "dataset_version"
            or manifest["dataset_id"] != dataset_id
            or manifest["version"] != version
            or manifest["asset_id"] != f"{dataset_id}-v{version:04d}"
            or manifest["state"] != "confirmed"
            or manifest["schema_version"] != DATASET_SCHEMA_VERSION
        ):
            DatasetRepository._invalid_manifest("identity fields do not match the asset path")
        if (
            not isinstance(manifest["created_at"], str)
            or not manifest["created_at"].strip()
            or not isinstance(manifest["created_by"], str)
            or not manifest["created_by"].strip()
            or not isinstance(manifest["source_files"], list)
            or not isinstance(manifest["class_labels"], list)
            or not isinstance(manifest["preview"], dict)
            or not isinstance(manifest["files"], dict)
            or not isinstance(manifest["file_fingerprints"], dict)
        ):
            DatasetRepository._invalid_manifest("field types are invalid")
        if manifest["files"] != DATASET_FILES:
            DatasetRepository._invalid_manifest("file declarations are invalid")

    @staticmethod
    def _validate_manifest_fingerprint(manifest: dict[str, Any]) -> None:
        actual = manifest.get("manifest_fingerprint")
        expected = DatasetRepository._manifest_fingerprint(manifest)
        if actual != expected:
            raise WorkspaceError(
                code="dataset_fingerprint_mismatch",
                message="Dataset Version manifest fingerprint does not match its contents.",
                next_action="Restore the immutable Dataset Version from Git.",
            )

    @staticmethod
    def _validate_data_fingerprints(
        manifest: dict[str, Any],
        version_path: Path,
    ) -> None:
        try:
            feature_bytes = (version_path / DATASET_FILES["features"]).read_bytes()
            label_bytes = (version_path / DATASET_FILES["labels"]).read_bytes()
            split_bytes = (version_path / DATASET_FILES["split"]).read_bytes()
        except OSError as error:
            raise WorkspaceError(
                code="invalid_dataset_version",
                message="A Dataset Version data file is missing or unreadable.",
                next_action="Restore the complete immutable Dataset Version from Git.",
            ) from error
        actual_files = {
            "features": hashlib.sha256(feature_bytes).hexdigest(),
            "labels": hashlib.sha256(label_bytes).hexdigest(),
            "split": hashlib.sha256(split_bytes).hexdigest(),
        }
        content_fingerprint = hashlib.sha256(
            feature_bytes + b"\0" + label_bytes
        ).hexdigest()
        split_fingerprint = hashlib.sha256(split_bytes).hexdigest()
        semantic_payload = {
            "content_fingerprint": content_fingerprint,
            "split_fingerprint": split_fingerprint,
            "sample_id_col": manifest["sample_id_col"],
            "label_col": manifest["label_col"],
            "task_type": manifest["task_type"],
            "class_labels": manifest["class_labels"],
            "positive_class": manifest["positive_class"],
            "primary_metric": manifest["primary_metric"],
            "target_metric": manifest["target_metric"],
            "split_strategy": manifest["split_strategy"],
            "test_ratio": manifest["test_ratio"],
            "random_seed": manifest["random_seed"],
        }
        if (
            actual_files != manifest["file_fingerprints"]
            or content_fingerprint != manifest["content_fingerprint"]
            or split_fingerprint != manifest["split_fingerprint"]
            or dataset_semantic_fingerprint(semantic_payload)
            != manifest["version_fingerprint"]
        ):
            raise WorkspaceError(
                code="dataset_fingerprint_mismatch",
                message="Dataset Version files or confirmed semantics have changed in place.",
                next_action="Restore the immutable Dataset Version from Git and create a new version for changes.",
            )

    @staticmethod
    def _manifest_fingerprint(manifest: dict[str, Any]) -> str:
        payload = {
            key: value
            for key, value in manifest.items()
            if key != "manifest_fingerprint"
        }
        return hashlib.sha256(
            json.dumps(
                payload,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode("utf-8")
        ).hexdigest()

    @staticmethod
    def _snapshot(
        manifest: dict[str, Any],
        asset_path: str,
    ) -> DatasetVersionSnapshot:
        preview = manifest["preview"]
        return DatasetVersionSnapshot(
            asset_id=manifest["asset_id"],
            asset_path=asset_path,
            dataset_id=manifest["dataset_id"],
            version=manifest["version"],
            state=manifest["state"],
            schema_version=manifest["schema_version"],
            created_at=manifest["created_at"],
            created_by=manifest["created_by"],
            content_fingerprint=manifest["content_fingerprint"],
            version_fingerprint=manifest["version_fingerprint"],
            source_files=tuple(dict(item) for item in manifest["source_files"]),
            sample_id_col=manifest["sample_id_col"],
            label_col=manifest["label_col"],
            task_type=manifest["task_type"],
            class_labels=tuple(manifest["class_labels"]),
            positive_class=manifest["positive_class"],
            primary_metric=manifest["primary_metric"],
            target_metric=float(manifest["target_metric"]),
            split_strategy=manifest["split_strategy"],
            test_ratio=(
                None
                if manifest["test_ratio"] is None
                else float(manifest["test_ratio"])
            ),
            random_seed=manifest["random_seed"],
            sample_count=manifest["sample_count"],
            feature_count=manifest["feature_count"],
            dtypes=dict(manifest["dtypes"]),
            missing_rates={
                key: float(value)
                for key, value in manifest["missing_rates"].items()
            },
            class_distribution={
                key: int(value)
                for key, value in manifest["class_distribution"].items()
            },
            preview=DatasetPreview(
                columns=tuple(preview["columns"]),
                rows=tuple(tuple(row) for row in preview["rows"]),
                omitted_count=preview["omitted_count"],
            ),
            warnings=tuple(manifest["warnings"]),
            files=dict(manifest["files"]),
        )

    @staticmethod
    def _validate_dataset_id(dataset_id: Any) -> None:
        if not isinstance(dataset_id, str) or DATASET_ID_PATTERN.fullmatch(dataset_id) is None:
            raise WorkspaceError(
                code="invalid_dataset_id",
                message="Dataset ID is invalid or could escape the managed dataset root.",
                next_action="Use a stable ID beginning with ds- and containing only letters, digits, dot, underscore, or hyphen.",
            )

    @staticmethod
    def _invalid_manifest(reason: str) -> None:
        raise WorkspaceError(
            code="invalid_dataset_version",
            message=f"Dataset Version manifest is invalid: {reason}.",
            next_action="Restore the complete immutable Dataset Version from Git.",
        )


def _utc_now() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
