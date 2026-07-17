from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import shutil
import uuid
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.domain.memory_repository import MANAGED_PATHS
from src.domain.models import (
    CandidateCodeFile,
    CapacityStatus,
    ExperienceCitation,
    RunPerformancePoint,
    RunRoundSnapshot,
    RunStatusSnapshot,
    TrainingExecutionResult,
    TrainingInstanceSnapshot,
    WorkspaceError,
)


RUN_SCHEMA_VERSION = 2
RUN_EVENT_ROOT = Path("raw-records/runs")
RUN_ROOT = Path("runs")
SAFE_ID_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9._-]{0,79}$")
SAFE_PATH_TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")
TERMINAL_RUN_STATES = {"completed", "failed", "timed_out", "stopped"}
TERMINAL_INSTANCE_STATES = {"completed", "failed", "timed_out", "stopped"}
MODEL_RETENTION_REASONS = {"baseline", "stage_best", "human_marked"}
ALLOWED_EVENT_FIELDS = {
    "asset_type",
    "asset_id",
    "schema_version",
    "run_id",
    "event_type",
    "state",
    "previous_event_id",
    "dataset_id",
    "dataset_version",
    "dataset_content_fingerprint",
    "dataset_version_fingerprint",
    "plan_id",
    "plan_event_id",
    "plan_fingerprint",
    "approval_id",
    "approval_fingerprint",
    "code_fingerprint",
    "user_direction",
    "stop_conditions",
    "primary_metric_name",
    "target_metric_value",
    "expected_round_count",
    "human_marked_rounds",
    "experience_citations",
    "instance_id",
    "round_number",
    "parent_instance_id",
    "hypothesis",
    "optimization_direction",
    "primary_metric_value",
    "input_fingerprint",
    "model_retention_reasons",
    "reason_code",
    "error_summary",
    "evidence_refs",
    "next_action",
    "created_at",
    "created_by",
    "event_fingerprint",
}


@dataclass(frozen=True)
class RunStartSpec:
    run_id: str
    dataset_id: str
    dataset_version: int
    dataset_content_fingerprint: str
    dataset_version_fingerprint: str
    plan_id: str
    plan_event_id: str
    plan_fingerprint: str
    approval_id: str
    approval_fingerprint: str
    code_fingerprint: str
    user_direction: str
    stop_conditions: tuple[str, ...]
    primary_metric_name: str
    target_metric_value: float
    expected_round_count: int
    human_marked_rounds: tuple[int, ...] = ()
    experience_citations: tuple[ExperienceCitation, ...] = ()


@dataclass(frozen=True)
class InstancePreparationSpec:
    run_id: str
    round_number: int
    hypothesis: str
    optimization_direction: str
    intended_changes: tuple[str, ...]
    random_seed: int
    parent_instance_id: str | None
    parent_instance_fingerprint: str | None
    configuration: dict[str, Any]
    environment: dict[str, Any]


@dataclass(frozen=True)
class RunEventSnapshot:
    asset_id: str
    asset_path: str
    run_id: str
    event_type: str
    state: str
    previous_event_id: str | None
    created_at: str
    created_by: str


@dataclass(frozen=True)
class FrozenCodeRevisionSnapshot:
    asset_id: str
    asset_path: str
    run_id: str
    code_fingerprint: str
    entrypoint_path: str
    files: tuple[CandidateCodeFile, ...]
    created_at: str
    created_by: str


@dataclass(frozen=True)
class PreparedTrainingInstance:
    instance_id: str
    run_id: str
    round_number: int
    pending_path: Path
    worker_output_path: Path
    input_path: Path
    environment_path: Path
    split_path: Path
    code_revision: FrozenCodeRevisionSnapshot
    dataset_content_fingerprint: str
    dataset_version_fingerprint: str
    plan_fingerprint: str
    approval_fingerprint: str
    configuration_fingerprint: str
    environment_fingerprint: str
    split_fingerprint: str
    random_seed: int
    parent_instance_id: str | None
    parent_instance_fingerprint: str | None
    hypothesis: str
    optimization_direction: str
    intended_changes: tuple[str, ...]
    experience_citations: tuple[ExperienceCitation, ...]


class RunRepository:
    def __init__(
        self,
        repository_path: Path,
        event_id_factory: Callable[[], str] | None = None,
        instance_id_factory: Callable[[], str] | None = None,
        clock: Callable[[], str] | None = None,
    ) -> None:
        unresolved = repository_path.expanduser()
        if unresolved.is_symlink():
            self._unsafe_path()
        self.repository_path = unresolved.resolve()
        self.event_id_factory = event_id_factory or (
            lambda: f"run-event-{uuid.uuid4()}"
        )
        self.instance_id_factory = instance_id_factory or (
            lambda: f"instance-{uuid.uuid4()}"
        )
        self.clock = clock or _utc_now

    def start_run(
        self,
        spec: RunStartSpec,
        actor_id: str,
        capacity: CapacityStatus,
    ) -> RunEventSnapshot:
        self._validate_run_start(spec)
        return self._append_event(
            spec.run_id,
            event_type="run_started",
            state="running",
            actor_id=actor_id,
            capacity=capacity,
            details={
                "dataset_id": spec.dataset_id,
                "dataset_version": spec.dataset_version,
                "dataset_content_fingerprint": spec.dataset_content_fingerprint,
                "dataset_version_fingerprint": spec.dataset_version_fingerprint,
                "plan_id": spec.plan_id,
                "plan_event_id": spec.plan_event_id,
                "plan_fingerprint": spec.plan_fingerprint,
                "approval_id": spec.approval_id,
                "approval_fingerprint": spec.approval_fingerprint,
                "code_fingerprint": spec.code_fingerprint,
                "user_direction": spec.user_direction,
                "stop_conditions": list(spec.stop_conditions),
                "primary_metric_name": spec.primary_metric_name,
                "target_metric_value": float(spec.target_metric_value),
                "expected_round_count": spec.expected_round_count,
                "human_marked_rounds": list(spec.human_marked_rounds),
                "experience_citations": [
                    item.to_dict() for item in spec.experience_citations
                ],
                "evidence_refs": [],
            },
        )

    def freeze_code_revision(
        self,
        run_id: str,
        code_root: Path,
        candidate_code_files: tuple[CandidateCodeFile, ...],
        code_fingerprint: str,
        entrypoint_path: str,
        actor_id: str,
        capacity: CapacityStatus,
    ) -> FrozenCodeRevisionSnapshot:
        self._validate_id(run_id, "Run ID")
        self._validate_path_token(code_fingerprint, "code fingerprint")
        self._validate_actor(actor_id)
        if not candidate_code_files:
            self._invalid_code_revision("approved code file list is empty")
        recorded_paths = {item.path for item in candidate_code_files}
        if entrypoint_path not in recorded_paths or not entrypoint_path.endswith(".py"):
            self._invalid_code_revision(
                "entrypoint is not an approved Python code file"
            )
        relative_root = RUN_ROOT / run_id / "code-revisions" / code_fingerprint
        final_root = self.repository_path / relative_root
        manifest_path = final_root / "manifest.json"
        with self._run_lock(run_id):
            if manifest_path.is_file():
                return self._load_code_revision(manifest_path, run_id)
            source_root = code_root.expanduser()
            if source_root.is_symlink() or not source_root.is_dir():
                self._invalid_code_revision("code root is missing or symbolic")
            resolved_source_root = source_root.resolve()
            encoded: dict[Path, bytes] = {}
            normalized_files: list[CandidateCodeFile] = []
            for recorded in sorted(candidate_code_files, key=lambda item: item.path):
                relative = self._safe_relative(recorded.path, "approved code path")
                source = source_root / relative
                self._validate_source_file(source, source_root, resolved_source_root)
                raw = source.read_bytes()
                digest = _sha256(raw)
                if digest != recorded.sha256 or len(raw) != recorded.size_bytes:
                    raise WorkspaceError(
                        code="approved_code_changed",
                        message=f"Approved code changed before freeze: {recorded.path}.",
                        next_action="Restore the approved code or approve the new content.",
                    )
                encoded[Path("files") / relative] = raw
                normalized_files.append(recorded)
            created_at = self._timestamp()
            manifest: dict[str, Any] = {
                "asset_type": "run_code_revision",
                "asset_id": f"{run_id}-{code_fingerprint}",
                "schema_version": RUN_SCHEMA_VERSION,
                "run_id": run_id,
                "state": "frozen",
                "code_fingerprint": code_fingerprint,
                "entrypoint_path": entrypoint_path,
                "files": [
                    {
                        "path": item.path,
                        "sha256": item.sha256,
                        "size_bytes": item.size_bytes,
                    }
                    for item in normalized_files
                ],
                "created_at": created_at,
                "created_by": actor_id,
            }
            manifest["manifest_fingerprint"] = _fingerprint(manifest)
            encoded[Path("manifest.json")] = _json_bytes(manifest)
            self._publish_directory(final_root, encoded, capacity)
            return self._load_code_revision(manifest_path, run_id)

    def load_code_revision(
        self,
        run_id: str,
        code_fingerprint: str,
    ) -> FrozenCodeRevisionSnapshot:
        self._validate_id(run_id, "Run ID")
        self._validate_path_token(code_fingerprint, "code fingerprint")
        manifest_path = (
            self.repository_path
            / RUN_ROOT
            / run_id
            / "code-revisions"
            / code_fingerprint
            / "manifest.json"
        )
        return self._load_code_revision(manifest_path, run_id)

    def prepare_instance(
        self,
        spec: InstancePreparationSpec,
        code_revision: FrozenCodeRevisionSnapshot,
        split_path: Path,
        actor_id: str,
        capacity: CapacityStatus,
    ) -> PreparedTrainingInstance:
        self._validate_id(spec.run_id, "Run ID")
        self._validate_actor(actor_id)
        if spec.round_number < 1:
            self._invalid_instance("round number must be positive")
        if code_revision.run_id != spec.run_id:
            self._invalid_instance("code revision belongs to another Run")
        start = self._start_payload(spec.run_id)
        if start["code_fingerprint"] != code_revision.code_fingerprint:
            self._invalid_instance("code revision does not match the approved Run")
        self._validate_parent(
            spec.run_id,
            spec.parent_instance_id,
            spec.parent_instance_fingerprint,
        )
        split_source = split_path.expanduser()
        if split_source.is_symlink() or not split_source.is_file():
            self._invalid_instance("frozen split is missing or symbolic")
        split_bytes = split_source.read_bytes()
        instance_id = self._new_id(self.instance_id_factory, "instance")
        relative_pending = RUN_ROOT / spec.run_id / "pending" / instance_id
        pending_path = self.repository_path / relative_pending
        final_path = (
            self.repository_path
            / RUN_ROOT
            / spec.run_id
            / "instances"
            / instance_id
        )
        configuration_fingerprint = _fingerprint(spec.configuration)
        environment_fingerprint = _fingerprint(spec.environment)
        split_fingerprint = _sha256(split_bytes)
        input_payload = {
            "run_id": spec.run_id,
            "instance_id": instance_id,
            "round_number": spec.round_number,
            "dataset_id": start["dataset_id"],
            "dataset_version": start["dataset_version"],
            "dataset_asset_path": (
                f"datasets/{start['dataset_id']}/"
                f"v{start['dataset_version']:04d}/manifest.json"
            ),
            "dataset_content_fingerprint": start["dataset_content_fingerprint"],
            "dataset_version_fingerprint": start[
                "dataset_version_fingerprint"
            ],
            "plan_id": start["plan_id"],
            "plan_event_id": start["plan_event_id"],
            "plan_fingerprint": start["plan_fingerprint"],
            "approval_id": start["approval_id"],
            "approval_fingerprint": start["approval_fingerprint"],
            "code_revision_path": code_revision.asset_path,
            "code_fingerprint": code_revision.code_fingerprint,
            "entrypoint_path": code_revision.entrypoint_path,
            "configuration": spec.configuration,
            "configuration_fingerprint": configuration_fingerprint,
            "environment_fingerprint": environment_fingerprint,
            "split_fingerprint": split_fingerprint,
            "random_seed": spec.random_seed,
            "parent_instance_id": spec.parent_instance_id,
            "parent_instance_fingerprint": spec.parent_instance_fingerprint,
            "hypothesis": spec.hypothesis,
            "optimization_direction": spec.optimization_direction,
            "intended_changes": list(spec.intended_changes),
            "primary_metric_name": start["primary_metric_name"],
            "target_metric_value": start["target_metric_value"],
            "experience_citations": start["experience_citations"],
        }
        encoded = {
            Path("input.json"): _json_bytes(input_payload),
            Path("environment.json"): _json_bytes(spec.environment),
            Path("split.csv"): split_bytes,
        }
        with self._run_lock(spec.run_id):
            if pending_path.exists() or final_path.exists():
                raise WorkspaceError(
                    code="training_instance_exists",
                    message=f"Training Instance path already exists: {instance_id}.",
                    next_action="Load the existing instance instead of overwriting it.",
                )
            self._publish_directory(pending_path, encoded, capacity)
            self._append_event_locked(
                spec.run_id,
                event_type="instance_started",
                state="running",
                actor_id=actor_id,
                capacity=capacity,
                details={
                    "instance_id": instance_id,
                    "round_number": spec.round_number,
                    "parent_instance_id": spec.parent_instance_id,
                    "hypothesis": spec.hypothesis,
                    "optimization_direction": spec.optimization_direction,
                    "primary_metric_name": start["primary_metric_name"],
                    "input_fingerprint": _fingerprint(input_payload),
                    "evidence_refs": [
                        (relative_pending / "input.json").as_posix(),
                        code_revision.asset_path,
                    ],
                },
            )
        worker_output_path = (
            self.repository_path
            / ".mlagent-local"
            / "run-work"
            / spec.run_id
            / instance_id
        )
        self._validate_path(worker_output_path, managed=False)
        return PreparedTrainingInstance(
            instance_id=instance_id,
            run_id=spec.run_id,
            round_number=spec.round_number,
            pending_path=pending_path,
            worker_output_path=worker_output_path,
            input_path=pending_path / "input.json",
            environment_path=pending_path / "environment.json",
            split_path=pending_path / "split.csv",
            code_revision=code_revision,
            dataset_content_fingerprint=start["dataset_content_fingerprint"],
            dataset_version_fingerprint=start["dataset_version_fingerprint"],
            plan_fingerprint=start["plan_fingerprint"],
            approval_fingerprint=start["approval_fingerprint"],
            configuration_fingerprint=configuration_fingerprint,
            environment_fingerprint=environment_fingerprint,
            split_fingerprint=split_fingerprint,
            random_seed=spec.random_seed,
            parent_instance_id=spec.parent_instance_id,
            parent_instance_fingerprint=spec.parent_instance_fingerprint,
            hypothesis=spec.hypothesis,
            optimization_direction=spec.optimization_direction,
            intended_changes=spec.intended_changes,
            experience_citations=tuple(
                ExperienceCitation(**item)
                for item in start["experience_citations"]
            ),
        )

    def seal_instance(
        self,
        prepared: PreparedTrainingInstance,
        result: TrainingExecutionResult,
        retention_reasons: tuple[str, ...],
        actor_id: str,
        capacity: CapacityStatus,
    ) -> TrainingInstanceSnapshot:
        self._validate_actor(actor_id)
        final_root = (
            self.repository_path
            / RUN_ROOT
            / prepared.run_id
            / "instances"
            / prepared.instance_id
        )
        with self._run_lock(prepared.run_id):
            if final_root.exists() or not prepared.pending_path.is_dir():
                raise WorkspaceError(
                    code="training_instance_exists",
                    message=(
                        "Training Instance is already sealed or its pending "
                        f"package is unavailable: {prepared.instance_id}."
                    ),
                    next_action="Load the sealed instance or start a new attempt.",
                )
            self._validate_prepared(prepared)
            files = {
                "input": "input.json",
                "environment": "environment.json",
                "split": "split.csv",
            }
            new_files: dict[str, bytes] = {}
            model_path: str | None = None
            prediction_path: str | None = None
            prediction_fingerprint: str | None = None
            resolved_retention: tuple[str, ...] = ()
            error_summary = result.error_summary
            if result.state == "completed":
                self._validate_retention_reasons(retention_reasons)
                predictions = self._read_worker_file(
                    prepared,
                    result.predictions_path,
                    "predictions",
                )
                model = self._read_worker_file(
                    prepared,
                    result.model_path,
                    "model",
                )
                if _sha256(model) != result.model_fingerprint:
                    self._invalid_instance("worker model fingerprint does not match")
                metrics_bytes = _json_bytes(dict(result.metrics))
                self._require_regular_file_size(
                    "metrics.json", metrics_bytes, capacity
                )
                self._require_regular_file_size(
                    "predictions.csv", predictions, capacity
                )
                new_files["metrics.json"] = metrics_bytes
                new_files["predictions.csv"] = predictions
                files["metrics"] = "metrics.json"
                files["predictions"] = "predictions.csv"
                prediction_path = "predictions.csv"
                prediction_fingerprint = _sha256(predictions)
                if retention_reasons:
                    if len(model) >= capacity.max_file_bytes:
                        resolved_retention = ("rejected_too_large",)
                    else:
                        new_files["model.joblib"] = model
                        files["model"] = "model.joblib"
                        model_path = "model.joblib"
                        resolved_retention = tuple(dict.fromkeys(retention_reasons))
            else:
                bounded = (result.error_summary or "training failed")[:2000]
                error_bytes = (bounded + "\n").encode("utf-8")
                self._require_regular_file_size(
                    "error-evidence.txt", error_bytes, capacity
                )
                new_files["error-evidence.txt"] = error_bytes
                files["error_evidence"] = "error-evidence.txt"
                error_summary = bounded

            for filename, raw in new_files.items():
                self._require_regular_file_size(filename, raw, capacity)
            existing_file_bytes = {
                name: (prepared.pending_path / name).read_bytes()
                for name in ("input.json", "environment.json", "split.csv")
            }
            fingerprints = {
                role: _sha256(
                    new_files.get(filename, existing_file_bytes.get(filename, b""))
                )
                for role, filename in files.items()
            }
            ended_at = result.ended_at
            manifest: dict[str, Any] = {
                "asset_type": "training_instance",
                "asset_id": prepared.instance_id,
                "schema_version": RUN_SCHEMA_VERSION,
                "run_id": prepared.run_id,
                "round_number": prepared.round_number,
                "state": result.state,
                "reproducible_evidence": result.state == "completed",
                "dataset_content_fingerprint": prepared.dataset_content_fingerprint,
                "dataset_version_fingerprint": prepared.dataset_version_fingerprint,
                "code_fingerprint": prepared.code_revision.code_fingerprint,
                "configuration_fingerprint": prepared.configuration_fingerprint,
                "environment_fingerprint": prepared.environment_fingerprint,
                "split_fingerprint": prepared.split_fingerprint,
                "plan_fingerprint": prepared.plan_fingerprint,
                "approval_fingerprint": prepared.approval_fingerprint,
                "random_seed": prepared.random_seed,
                "parent_instance_id": prepared.parent_instance_id,
                "parent_instance_fingerprint": prepared.parent_instance_fingerprint,
                "hypothesis": prepared.hypothesis,
                "optimization_direction": prepared.optimization_direction,
                "intended_changes": list(prepared.intended_changes),
                "primary_metric_name": result.primary_metric_name,
                "primary_metric_value": result.primary_metric_value,
                "metrics": dict(result.metrics),
                "predictions_path": prediction_path,
                "predictions_fingerprint": prediction_fingerprint,
                "model_fingerprint": result.model_fingerprint,
                "model_retention_reasons": list(resolved_retention),
                "model_path": model_path,
                "error_code": result.error_code,
                "error_summary": error_summary,
                "experience_citations": [
                    item.to_dict()
                    for item in prepared.experience_citations
                ],
                "started_at": result.started_at,
                "ended_at": ended_at,
                "duration_ms": result.duration_ms,
                "created_at": ended_at,
                "created_by": actor_id,
                "files": files,
                "file_fingerprints": fingerprints,
            }
            manifest["manifest_fingerprint"] = _fingerprint(manifest)
            manifest_bytes = _json_bytes(manifest)
            self._require_regular_file_size(
                "manifest.json", manifest_bytes, capacity
            )
            with self._capacity_lock():
                self._validate_projected_capacity(
                    {**new_files, "manifest.json": manifest_bytes},
                    capacity,
                )
                for filename, raw in new_files.items():
                    target = prepared.pending_path / filename
                    if target.exists():
                        self._invalid_instance(
                            f"pending output already exists: {filename}"
                        )
                    target.write_bytes(raw)
                (prepared.pending_path / "manifest.json").write_bytes(
                    manifest_bytes
                )
                final_root.parent.mkdir(parents=True, exist_ok=True)
                prepared.pending_path.rename(final_root)
            relative_manifest = (
                RUN_ROOT
                / prepared.run_id
                / "instances"
                / prepared.instance_id
                / "manifest.json"
            )
            self._append_event_locked(
                prepared.run_id,
                event_type=f"instance_{result.state}",
                state="running",
                actor_id=actor_id,
                capacity=capacity,
                details={
                    "instance_id": prepared.instance_id,
                    "round_number": prepared.round_number,
                    "parent_instance_id": prepared.parent_instance_id,
                    "hypothesis": prepared.hypothesis,
                    "optimization_direction": prepared.optimization_direction,
                    "primary_metric_name": result.primary_metric_name,
                    "primary_metric_value": result.primary_metric_value,
                    "model_retention_reasons": list(resolved_retention),
                    "reason_code": result.error_code,
                    "error_summary": error_summary,
                    "evidence_refs": [relative_manifest.as_posix()],
                },
            )
        return self.load_instance(prepared.run_id, prepared.instance_id)

    def load_instance(
        self,
        run_id: str,
        instance_id: str,
    ) -> TrainingInstanceSnapshot:
        self._validate_id(run_id, "Run ID")
        self._validate_id(instance_id, "Training Instance ID")
        relative = (
            RUN_ROOT / run_id / "instances" / instance_id / "manifest.json"
        )
        path = self.repository_path / relative
        self._validate_path(path, managed=True)
        payload = self._load_json(path, "invalid_training_instance")
        if (
            payload.get("asset_type") != "training_instance"
            or payload.get("asset_id") != instance_id
            or payload.get("run_id") != run_id
        ):
            self._invalid_instance("manifest identity does not match its path")
        expected_fingerprint = payload.get("manifest_fingerprint")
        canonical = dict(payload)
        canonical.pop("manifest_fingerprint", None)
        if expected_fingerprint != _fingerprint(canonical):
            self._invalid_instance("manifest fingerprint does not match")
        files = payload.get("files")
        fingerprints = payload.get("file_fingerprints")
        if not isinstance(files, dict) or not isinstance(fingerprints, dict):
            self._invalid_instance("file evidence is incomplete")
        expected_files = {"manifest.json", *files.values()}
        actual_files = {
            item.relative_to(path.parent).as_posix()
            for item in path.parent.rglob("*")
            if item.is_file()
        }
        if actual_files != expected_files:
            self._invalid_instance("instance contains missing or undeclared files")
        for role, filename in files.items():
            evidence = path.parent / filename
            self._validate_path(evidence, managed=True)
            if evidence.is_symlink() or not evidence.is_file():
                self._invalid_instance(f"evidence is unavailable: {filename}")
            if fingerprints.get(role) != _sha256(evidence.read_bytes()):
                self._invalid_instance(f"evidence fingerprint changed: {filename}")
        try:
            return TrainingInstanceSnapshot(
                asset_id=instance_id,
                asset_path=relative.as_posix(),
                run_id=run_id,
                round_number=payload["round_number"],
                state=payload["state"],
                reproducible_evidence=payload["reproducible_evidence"],
                dataset_content_fingerprint=payload[
                    "dataset_content_fingerprint"
                ],
                dataset_version_fingerprint=payload[
                    "dataset_version_fingerprint"
                ],
                code_fingerprint=payload["code_fingerprint"],
                configuration_fingerprint=payload[
                    "configuration_fingerprint"
                ],
                environment_fingerprint=payload["environment_fingerprint"],
                split_fingerprint=payload["split_fingerprint"],
                plan_fingerprint=payload["plan_fingerprint"],
                approval_fingerprint=payload["approval_fingerprint"],
                random_seed=payload["random_seed"],
                parent_instance_id=payload["parent_instance_id"],
                parent_instance_fingerprint=payload[
                    "parent_instance_fingerprint"
                ],
                optimization_direction=payload["optimization_direction"],
                primary_metric_name=payload["primary_metric_name"],
                primary_metric_value=payload["primary_metric_value"],
                metrics=payload["metrics"],
                predictions_path=payload["predictions_path"],
                predictions_fingerprint=payload["predictions_fingerprint"],
                model_fingerprint=payload["model_fingerprint"],
                model_retention_reasons=tuple(
                    payload["model_retention_reasons"]
                ),
                model_path=payload["model_path"],
                error_code=payload["error_code"],
                error_summary=payload["error_summary"],
                started_at=payload["started_at"],
                ended_at=payload["ended_at"],
                duration_ms=payload["duration_ms"],
                experience_citations=tuple(
                    ExperienceCitation(**item)
                    for item in payload["experience_citations"]
                ),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise WorkspaceError(
                code="invalid_training_instance",
                message=f"Training Instance is invalid: {instance_id}.",
                next_action="Restore the sealed instance from Git.",
            ) from error

    def instance_fingerprint(self, instance: TrainingInstanceSnapshot) -> str:
        payload = self._load_json(
            self.repository_path / instance.asset_path,
            "invalid_training_instance",
        )
        value = payload.get("manifest_fingerprint")
        if not isinstance(value, str) or not value:
            self._invalid_instance("manifest fingerprint is missing")
        return value

    def request_stop(
        self,
        run_id: str,
        reason: str,
        actor_id: str,
        capacity: CapacityStatus,
    ) -> RunEventSnapshot:
        if not isinstance(reason, str) or not reason.strip():
            raise WorkspaceError(
                code="invalid_stop_reason",
                message="Run stop reason is empty.",
                next_action="Provide a concise reason for stopping the Run.",
            )
        return self._append_event(
            run_id,
            event_type="stop_requested",
            state="running",
            actor_id=actor_id,
            capacity=capacity,
            details={
                "reason_code": reason,
                "evidence_refs": [],
            },
        )

    def stop_requested(self, run_id: str) -> bool:
        events = self._ordered_event_payloads(run_id)
        terminal = bool(events and events[-1]["state"] in TERMINAL_RUN_STATES)
        return not terminal and any(
            event["event_type"] == "stop_requested" for event in events
        )

    def finish_run(
        self,
        run_id: str,
        state: str,
        reason: str,
        actor_id: str,
        capacity: CapacityStatus,
    ) -> RunEventSnapshot:
        if state not in TERMINAL_RUN_STATES:
            raise WorkspaceError(
                code="invalid_run_state",
                message=f"Run cannot finish with state: {state}.",
                next_action="Use completed, failed, timed_out, or stopped.",
            )
        event = self._append_event(
            run_id,
            event_type="run_finished",
            state=state,
            actor_id=actor_id,
            capacity=capacity,
            details={
                "reason_code": reason,
                "evidence_refs": [],
            },
        )
        self.deactivate_run(run_id)
        return event

    def activate_run(self, run_id: str) -> None:
        self._validate_id(run_id, "Run ID")
        path = self._active_path(run_id)
        self._validate_path(path, managed=False)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"run_id": run_id, "pid": os.getpid()}),
            encoding="utf-8",
        )

    def deactivate_run(self, run_id: str) -> None:
        self._active_path(run_id).unlink(missing_ok=True)

    @contextmanager
    def active_run(self, run_id: str) -> Iterator[None]:
        self.activate_run(run_id)
        try:
            yield
        finally:
            self.deactivate_run(run_id)

    def status(self, run_id: str) -> RunStatusSnapshot:
        payloads = self._ordered_event_payloads(run_id)
        if not payloads:
            raise WorkspaceError(
                code="run_not_found",
                message=f"Run does not exist: {run_id}.",
                next_action="Choose a Run listed by Run Status.",
            )
        start = payloads[0]
        latest = payloads[-1]
        instances = self._instances(run_id)
        instance_payloads = {
            instance.asset_id: self._load_json(
                self.repository_path / instance.asset_path,
                "invalid_training_instance",
            )
            for instance in instances
        }
        rounds = tuple(
            RunRoundSnapshot(
                round_number=instance.round_number,
                instance_id=instance.asset_id,
                hypothesis=instance_payloads[instance.asset_id]["hypothesis"],
                optimization_direction=instance.optimization_direction,
                parent_instance_id=instance.parent_instance_id,
                instance_state=instance.state,
                duration_ms=instance.duration_ms,
                primary_metric_value=instance.primary_metric_value,
                model_retention_reasons=instance.model_retention_reasons,
                error_code=instance.error_code,
                error_summary=instance.error_summary,
            )
            for instance in instances
        )
        completed = [
            instance for instance in instances if instance.state == "completed"
        ]
        best = max(
            completed,
            key=lambda item: (item.primary_metric_value, -item.round_number),
            default=None,
        )
        points = tuple(
            RunPerformancePoint(
                round_number=instance.round_number,
                instance_id=instance.asset_id,
                primary_metric_value=instance.primary_metric_value,
            )
            for instance in completed
        )
        state = latest["state"]
        recovery_reason = None
        recovery_actions: tuple[str, ...] = ()
        pending_root = self.repository_path / RUN_ROOT / run_id / "pending"
        has_pending = pending_root.is_dir() and any(pending_root.iterdir())
        if state not in TERMINAL_RUN_STATES and not self._is_active(run_id):
            state = "recovery_required"
            recovery_reason = "unsealed_instance" if has_pending else "interrupted_run"
            recovery_actions = ("resume", "close")
        started_at = start["created_at"]
        ended_at = (
            latest["created_at"] if latest["state"] in TERMINAL_RUN_STATES else None
        )
        updated_at = latest["created_at"]
        elapsed_end = ended_at or self._timestamp()
        elapsed_ms = max(0, _milliseconds_between(started_at, elapsed_end))
        best_value = None if best is None else best.primary_metric_value
        target = float(start["target_metric_value"])
        return RunStatusSnapshot(
            run_id=run_id,
            plan_id=start["plan_id"],
            approval_id=start["approval_id"],
            dataset_id=start["dataset_id"],
            dataset_version=start["dataset_version"],
            user_direction=start["user_direction"],
            stop_conditions=tuple(start["stop_conditions"]),
            primary_metric_name=start["primary_metric_name"],
            target_metric_value=target,
            state=state,
            current_round=max(
                (instance.round_number for instance in instances),
                default=0,
            ),
            rounds=rounds,
            performance_points=points,
            best_instance_id=None if best is None else best.asset_id,
            best_primary_metric_value=best_value,
            target_gap=(
                None if best_value is None else max(0.0, target - best_value)
            ),
            started_at=started_at,
            ended_at=ended_at,
            elapsed_ms=elapsed_ms,
            updated_at=updated_at,
            stop_reason=(
                latest.get("reason_code")
                if latest["state"] in TERMINAL_RUN_STATES
                else None
            ),
            stop_requested=self.stop_requested(run_id),
            recovery_reason=recovery_reason,
            recovery_actions=recovery_actions,
        )

    def list_statuses(self) -> tuple[RunStatusSnapshot, ...]:
        root = self.repository_path / RUN_EVENT_ROOT
        self._validate_path(root, managed=True)
        if not root.is_dir():
            return ()
        run_ids = []
        for path in sorted(root.iterdir()):
            if not path.is_dir() or SAFE_ID_PATTERN.fullmatch(path.name) is None:
                raise WorkspaceError(
                    code="invalid_run_event",
                    message="Run event directory contains an invalid Run identity.",
                    next_action="Restore the append-only Run records from Git.",
                )
            run_ids.append(path.name)
        statuses = [self.status(run_id) for run_id in run_ids]
        return tuple(
            sorted(
                statuses,
                key=lambda item: (item.updated_at, item.run_id),
                reverse=True,
            )
        )

    def load_run_start(self, run_id: str) -> dict[str, Any]:
        return json.loads(json.dumps(self._start_payload(run_id)))

    def list_instances(
        self,
        run_id: str,
    ) -> tuple[TrainingInstanceSnapshot, ...]:
        self._start_payload(run_id)
        return self._instances(run_id)

    def recover_run(
        self,
        run_id: str,
        action: str,
        actor_id: str,
        capacity: CapacityStatus,
    ) -> RunEventSnapshot:
        self._validate_id(run_id, "Run ID")
        self._validate_actor(actor_id)
        if action not in {"resume", "close"}:
            raise WorkspaceError(
                code="invalid_recovery_action",
                message=f"Run recovery action is invalid: {action}.",
                next_action="Use resume or close.",
            )
        if self._is_active(run_id):
            raise WorkspaceError(
                code="run_is_active",
                message=f"Run still has a live owner: {run_id}.",
                next_action="Stop the active owner before recovering the Run.",
            )

        events = self._ordered_event_payloads(run_id)
        if not events:
            raise WorkspaceError(
                code="run_not_found",
                message=f"Run does not exist: {run_id}.",
                next_action="Choose a Run listed by Run Status.",
            )
        if events[-1]["state"] in TERMINAL_RUN_STATES:
            raise WorkspaceError(
                code="run_already_finished",
                message=f"Run is already sealed: {run_id}.",
                next_action="Create a new Run instead of changing terminal history.",
            )

        for prepared in self._pending_instances(run_id):
            recovered_at = self._timestamp()
            self.seal_instance(
                prepared,
                TrainingExecutionResult(
                    state="failed",
                    primary_metric_name=self._pending_primary_metric(prepared),
                    primary_metric_value=None,
                    metrics={},
                    predictions_path=None,
                    model_path=None,
                    model_fingerprint=None,
                    error_code="interrupted",
                    error_summary=(
                        "Training process ended before the instance was sealed."
                    ),
                    started_at=recovered_at,
                    ended_at=recovered_at,
                    duration_ms=0,
                ),
                retention_reasons=(),
                actor_id=actor_id,
                capacity=capacity,
            )

        if action == "close":
            return self.finish_run(
                run_id,
                state="failed",
                reason="interrupted",
                actor_id=actor_id,
                capacity=capacity,
            )
        return self._append_event(
            run_id,
            event_type="run_resumed",
            state="running",
            actor_id=actor_id,
            capacity=capacity,
            details={
                "reason_code": "interrupted_retry",
                "evidence_refs": [],
            },
        )

    def list_events(self, run_id: str) -> tuple[RunEventSnapshot, ...]:
        return tuple(
            self._event_snapshot(
                payload,
                RUN_EVENT_ROOT / run_id / f"{payload['asset_id']}.json",
            )
            for payload in self._ordered_event_payloads(run_id)
        )

    @staticmethod
    def event_fingerprint(payload: Mapping[str, Any]) -> str:
        canonical = dict(payload)
        canonical.pop("event_fingerprint", None)
        return _fingerprint(canonical)

    def _append_event(
        self,
        run_id: str,
        event_type: str,
        state: str,
        actor_id: str,
        capacity: CapacityStatus,
        details: dict[str, Any],
    ) -> RunEventSnapshot:
        self._validate_id(run_id, "Run ID")
        with self._run_lock(run_id):
            return self._append_event_locked(
                run_id,
                event_type,
                state,
                actor_id,
                capacity,
                details,
            )

    def _append_event_locked(
        self,
        run_id: str,
        event_type: str,
        state: str,
        actor_id: str,
        capacity: CapacityStatus,
        details: dict[str, Any],
    ) -> RunEventSnapshot:
        self._validate_actor(actor_id)
        existing = self._ordered_event_payloads(run_id)
        if event_type == "run_started" and existing:
            raise WorkspaceError(
                code="run_exists",
                message=f"Run already exists: {run_id}.",
                next_action="Resume the existing Run or create a new Run ID.",
            )
        if event_type != "run_started" and not existing:
            raise WorkspaceError(
                code="run_not_found",
                message=f"Run does not exist: {run_id}.",
                next_action="Start the Run before recording events.",
            )
        if existing and existing[-1]["state"] in TERMINAL_RUN_STATES:
            raise WorkspaceError(
                code="run_already_finished",
                message=f"Run is already sealed: {run_id}.",
                next_action="Create a new Run instead of changing terminal history.",
            )
        event_id = self._new_id(self.event_id_factory, "Run event")
        payload: dict[str, Any] = {
            "asset_type": "run_event",
            "asset_id": event_id,
            "schema_version": RUN_SCHEMA_VERSION,
            "run_id": run_id,
            "event_type": event_type,
            "state": state,
            "previous_event_id": (
                None if not existing else existing[-1]["asset_id"]
            ),
            **{key: value for key, value in details.items() if value is not None},
            "created_at": self._timestamp(),
            "created_by": actor_id,
        }
        if not set(payload) <= ALLOWED_EVENT_FIELDS:
            raise WorkspaceError(
                code="invalid_run_event",
                message="Run event contains fields outside the minimal Raw Record schema.",
                next_action="Record only approved critical training facts.",
            )
        payload["event_fingerprint"] = self.event_fingerprint(payload)
        relative = RUN_EVENT_ROOT / run_id / f"{event_id}.json"
        target = self.repository_path / relative
        raw = _json_bytes(payload)
        with self._capacity_lock():
            self._validate_projected_capacity({target.name: raw}, capacity)
            self._atomic_write_new(target, raw)
        return self._event_snapshot(payload, relative)

    def _ordered_event_payloads(self, run_id: str) -> list[dict[str, Any]]:
        self._validate_id(run_id, "Run ID")
        root = self.repository_path / RUN_EVENT_ROOT / run_id
        self._validate_path(root, managed=True)
        if not root.is_dir():
            return []
        payloads = []
        for path in sorted(root.glob("*.json")):
            self._validate_path(path, managed=True)
            payload = self._load_json(path, "invalid_run_event")
            self._validate_event_payload(payload, run_id, path.stem)
            payloads.append(payload)
        if not payloads:
            return []
        by_id = {payload["asset_id"]: payload for payload in payloads}
        predecessors = set()
        for payload in payloads:
            predecessor = payload["previous_event_id"]
            if predecessor is not None:
                if predecessor not in by_id:
                    self._event_conflict(run_id)
                predecessors.add(predecessor)
        heads = [
            payload for payload in payloads if payload["asset_id"] not in predecessors
        ]
        if len(heads) != 1:
            self._event_conflict(run_id)
        ordered_reverse = []
        visited = set()
        cursor = heads[0]
        while cursor is not None:
            if cursor["asset_id"] in visited:
                self._event_conflict(run_id)
            visited.add(cursor["asset_id"])
            ordered_reverse.append(cursor)
            predecessor = cursor["previous_event_id"]
            cursor = None if predecessor is None else by_id[predecessor]
        if len(visited) != len(payloads):
            self._event_conflict(run_id)
        return list(reversed(ordered_reverse))

    def _start_payload(self, run_id: str) -> dict[str, Any]:
        events = self._ordered_event_payloads(run_id)
        if not events or events[0]["event_type"] != "run_started":
            raise WorkspaceError(
                code="run_not_found",
                message=f"Run start record is missing: {run_id}.",
                next_action="Restore the Run events from Git.",
            )
        return events[0]

    def _instances(self, run_id: str) -> tuple[TrainingInstanceSnapshot, ...]:
        root = self.repository_path / RUN_ROOT / run_id / "instances"
        self._validate_path(root, managed=True)
        if not root.is_dir():
            return ()
        instances = [
            self.load_instance(run_id, path.name)
            for path in sorted(root.iterdir())
            if path.is_dir() and SAFE_ID_PATTERN.fullmatch(path.name)
        ]
        return tuple(sorted(instances, key=lambda item: item.round_number))

    def _pending_instances(
        self,
        run_id: str,
    ) -> tuple[PreparedTrainingInstance, ...]:
        root = self.repository_path / RUN_ROOT / run_id / "pending"
        self._validate_path(root, managed=True)
        if not root.is_dir():
            return ()
        pending = []
        for path in sorted(root.iterdir()):
            if not path.is_dir() or SAFE_ID_PATTERN.fullmatch(path.name) is None:
                self._invalid_instance("pending package path is invalid")
            pending.append(self._load_pending_instance(run_id, path.name))
        return tuple(pending)

    def _load_pending_instance(
        self,
        run_id: str,
        instance_id: str,
    ) -> PreparedTrainingInstance:
        self._validate_id(instance_id, "instance ID")
        pending_path = self.repository_path / RUN_ROOT / run_id / "pending" / instance_id
        self._validate_path(pending_path, managed=True)
        input_path = pending_path / "input.json"
        environment_path = pending_path / "environment.json"
        split_path = pending_path / "split.csv"
        payload = self._load_json(input_path, "invalid_training_instance")
        try:
            code_manifest = self.repository_path / self._safe_relative(
                payload["code_revision_path"],
                "code revision path",
            )
            code_revision = self._load_code_revision(code_manifest, run_id)
            prepared = PreparedTrainingInstance(
                instance_id=instance_id,
                run_id=run_id,
                round_number=payload["round_number"],
                pending_path=pending_path,
                worker_output_path=(
                    self.repository_path
                    / ".mlagent-local"
                    / "run-work"
                    / run_id
                    / instance_id
                ),
                input_path=input_path,
                environment_path=environment_path,
                split_path=split_path,
                code_revision=code_revision,
                dataset_content_fingerprint=payload[
                    "dataset_content_fingerprint"
                ],
                dataset_version_fingerprint=payload[
                    "dataset_version_fingerprint"
                ],
                plan_fingerprint=payload["plan_fingerprint"],
                approval_fingerprint=payload["approval_fingerprint"],
                configuration_fingerprint=payload[
                    "configuration_fingerprint"
                ],
                environment_fingerprint=payload["environment_fingerprint"],
                split_fingerprint=payload["split_fingerprint"],
                random_seed=payload["random_seed"],
                parent_instance_id=payload["parent_instance_id"],
                parent_instance_fingerprint=payload[
                    "parent_instance_fingerprint"
                ],
                hypothesis=payload["hypothesis"],
                optimization_direction=payload["optimization_direction"],
                intended_changes=tuple(payload["intended_changes"]),
                experience_citations=tuple(
                    ExperienceCitation(**item)
                    for item in payload["experience_citations"]
                ),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise WorkspaceError(
                code="invalid_training_instance",
                message=f"Pending Training Instance is invalid: {instance_id}.",
                next_action="Restore the pending evidence from Git before recovery.",
            ) from error
        if payload.get("instance_id") != instance_id or payload.get("run_id") != run_id:
            self._invalid_instance("pending package identity does not match its path")
        self._validate_path(prepared.worker_output_path, managed=False)
        self._validate_prepared(prepared)
        return prepared

    def _pending_primary_metric(
        self,
        prepared: PreparedTrainingInstance,
    ) -> str:
        payload = self._load_json(
            prepared.input_path,
            "invalid_training_instance",
        )
        metric = payload.get("primary_metric_name")
        if not isinstance(metric, str) or not metric.strip():
            self._invalid_instance("pending primary metric is missing")
        return metric

    def _load_code_revision(
        self,
        manifest_path: Path,
        run_id: str,
    ) -> FrozenCodeRevisionSnapshot:
        self._validate_path(manifest_path, managed=True)
        payload = self._load_json(manifest_path, "invalid_code_revision")
        canonical = dict(payload)
        fingerprint = canonical.pop("manifest_fingerprint", None)
        if (
            payload.get("asset_type") != "run_code_revision"
            or payload.get("run_id") != run_id
            or fingerprint != _fingerprint(canonical)
        ):
            self._invalid_code_revision("manifest is invalid")
        files = []
        expected = {"manifest.json"}
        for item in payload.get("files", []):
            try:
                relative = self._safe_relative(item["path"], "frozen code path")
                code_path = manifest_path.parent / "files" / relative
                self._validate_path(code_path, managed=True)
                raw = code_path.read_bytes()
                candidate = CandidateCodeFile(
                    path=relative.as_posix(),
                    sha256=item["sha256"],
                    size_bytes=item["size_bytes"],
                )
            except (KeyError, OSError, TypeError, ValueError) as error:
                raise WorkspaceError(
                    code="invalid_code_revision",
                    message="Frozen code evidence is invalid.",
                    next_action="Restore the code revision from Git.",
                ) from error
            if _sha256(raw) != candidate.sha256 or len(raw) != candidate.size_bytes:
                self._invalid_code_revision("frozen code fingerprint changed")
            files.append(candidate)
            expected.add((Path("files") / relative).as_posix())
        actual = {
            item.relative_to(manifest_path.parent).as_posix()
            for item in manifest_path.parent.rglob("*")
            if item.is_file()
        }
        if actual != expected:
            self._invalid_code_revision("package has missing or undeclared files")
        return FrozenCodeRevisionSnapshot(
            asset_id=payload["asset_id"],
            asset_path=manifest_path.relative_to(self.repository_path).as_posix(),
            run_id=run_id,
            code_fingerprint=payload["code_fingerprint"],
            entrypoint_path=payload["entrypoint_path"],
            files=tuple(files),
            created_at=payload["created_at"],
            created_by=payload["created_by"],
        )

    def _validate_prepared(self, prepared: PreparedTrainingInstance) -> None:
        expected = {
            "input.json": _fingerprint_bytes(prepared.input_path.read_bytes()),
            "environment.json": _fingerprint_bytes(
                prepared.environment_path.read_bytes()
            ),
            "split.csv": _sha256(prepared.split_path.read_bytes()),
        }
        input_payload = self._load_json(
            prepared.input_path,
            "invalid_training_instance",
        )
        started_events = [
            event
            for event in self._ordered_event_payloads(prepared.run_id)
            if event.get("event_type") == "instance_started"
            and event.get("instance_id") == prepared.instance_id
        ]
        prepared_values = {
            "run_id": prepared.run_id,
            "instance_id": prepared.instance_id,
            "round_number": prepared.round_number,
            "dataset_content_fingerprint": prepared.dataset_content_fingerprint,
            "dataset_version_fingerprint": prepared.dataset_version_fingerprint,
            "plan_fingerprint": prepared.plan_fingerprint,
            "approval_fingerprint": prepared.approval_fingerprint,
            "code_revision_path": prepared.code_revision.asset_path,
            "code_fingerprint": prepared.code_revision.code_fingerprint,
            "configuration_fingerprint": prepared.configuration_fingerprint,
            "environment_fingerprint": prepared.environment_fingerprint,
            "split_fingerprint": prepared.split_fingerprint,
            "random_seed": prepared.random_seed,
            "parent_instance_id": prepared.parent_instance_id,
            "parent_instance_fingerprint": prepared.parent_instance_fingerprint,
            "hypothesis": prepared.hypothesis,
            "optimization_direction": prepared.optimization_direction,
            "intended_changes": list(prepared.intended_changes),
            "experience_citations": [
                item.to_dict() for item in prepared.experience_citations
            ],
        }
        if (
            len(started_events) != 1
            or started_events[0].get("input_fingerprint")
            != expected["input.json"]
            or input_payload.get("configuration_fingerprint")
            != _fingerprint(input_payload.get("configuration"))
            or any(
                input_payload.get(key) != value
                for key, value in prepared_values.items()
            )
            or expected["environment.json"] != prepared.environment_fingerprint
            or expected["split.csv"] != prepared.split_fingerprint
        ):
            self._invalid_instance("pending frozen inputs changed")
        self._load_code_revision(
            self.repository_path / prepared.code_revision.asset_path,
            prepared.run_id,
        )

    def _validate_parent(
        self,
        run_id: str,
        parent_id: str | None,
        parent_fingerprint: str | None,
    ) -> None:
        if (parent_id is None) != (parent_fingerprint is None):
            self._invalid_instance("parent ID and fingerprint must be paired")
        if parent_id is None:
            return
        parent = self.load_instance(run_id, parent_id)
        if self.instance_fingerprint(parent) != parent_fingerprint:
            self._invalid_instance("parent instance fingerprint does not match")

    def _validate_event_payload(
        self,
        payload: dict[str, Any],
        run_id: str,
        event_id: str,
    ) -> None:
        if (
            not set(payload) <= ALLOWED_EVENT_FIELDS
            or payload.get("asset_type") != "run_event"
            or payload.get("asset_id") != event_id
            or payload.get("run_id") != run_id
            or payload.get("schema_version") != RUN_SCHEMA_VERSION
            or payload.get("event_fingerprint")
            != self.event_fingerprint(payload)
        ):
            raise WorkspaceError(
                code="invalid_run_event",
                message=f"Run event is invalid: {event_id}.",
                next_action="Restore the append-only event from Git.",
            )

    def _validate_run_start(self, spec: RunStartSpec) -> None:
        for value, label in (
            (spec.run_id, "Run ID"),
            (spec.dataset_id, "Dataset ID"),
            (spec.plan_id, "plan ID"),
            (spec.plan_event_id, "plan event ID"),
            (spec.approval_id, "approval ID"),
        ):
            self._validate_id(value, label)
        for value, label in (
            (spec.dataset_content_fingerprint, "dataset content fingerprint"),
            (spec.dataset_version_fingerprint, "dataset version fingerprint"),
            (spec.plan_fingerprint, "plan fingerprint"),
            (spec.approval_fingerprint, "approval fingerprint"),
            (spec.code_fingerprint, "code fingerprint"),
            (spec.user_direction, "user direction"),
            (spec.primary_metric_name, "primary metric"),
        ):
            if not isinstance(value, str) or not value.strip():
                raise WorkspaceError(
                    code="invalid_run_start",
                    message=f"Run {label} is empty.",
                    next_action="Restore the approved Run binding before execution.",
                )
        if (
            spec.dataset_version < 1
            or spec.expected_round_count < 1
            or not spec.stop_conditions
            or not 0 <= float(spec.target_metric_value) <= 1
            or len(set(spec.human_marked_rounds))
            != len(spec.human_marked_rounds)
            or any(
                type(round_number) is not int
                or not 1 <= round_number <= spec.expected_round_count
                for round_number in spec.human_marked_rounds
            )
            or len(spec.experience_citations)
            != len(
                {
                    item.experience_id
                    for item in spec.experience_citations
                }
            )
        ):
            raise WorkspaceError(
                code="invalid_run_start",
                message="Run start structure is incomplete.",
                next_action="Use the exact approved plan and Dataset Version.",
            )

    @staticmethod
    def _validate_retention_reasons(reasons: tuple[str, ...]) -> None:
        if any(reason not in MODEL_RETENTION_REASONS for reason in reasons):
            raise WorkspaceError(
                code="invalid_model_retention",
                message="Run model retention reason is invalid.",
                next_action="Use baseline, stage_best, or human_marked.",
            )

    def _read_worker_file(
        self,
        prepared: PreparedTrainingInstance,
        path: Path | None,
        role: str,
    ) -> bytes:
        if path is None:
            self._invalid_instance(f"worker {role} output is missing")
        candidate = path.expanduser()
        if candidate.is_symlink() or not candidate.is_file():
            self._invalid_instance(f"worker {role} output is invalid")
        try:
            candidate.resolve().relative_to(prepared.worker_output_path.resolve())
        except ValueError:
            self._invalid_instance(f"worker {role} output is outside local work")
        return candidate.read_bytes()

    def _publish_directory(
        self,
        final_root: Path,
        encoded: Mapping[Path, bytes],
        capacity: CapacityStatus,
    ) -> None:
        self._validate_path(final_root, managed=True)
        if final_root.exists():
            raise WorkspaceError(
                code="asset_exists",
                message=f"Authoritative package already exists: {final_root}.",
                next_action="Load the existing immutable package.",
            )
        for relative, raw in encoded.items():
            self._safe_relative(relative.as_posix(), "package file")
            self._require_regular_file_size(relative.as_posix(), raw, capacity)
        final_root.parent.mkdir(parents=True, exist_ok=True)
        temporary = final_root.parent / f".{final_root.name}.tmp-{uuid.uuid4().hex}"
        self._validate_path(temporary, managed=True)
        with self._capacity_lock():
            self._validate_projected_capacity(
                {path.as_posix(): raw for path, raw in encoded.items()},
                capacity,
            )
            try:
                temporary.mkdir()
                for relative, raw in encoded.items():
                    target = temporary / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(raw)
                temporary.rename(final_root)
            except OSError as error:
                shutil.rmtree(temporary, ignore_errors=True)
                raise WorkspaceError(
                    code="run_write_failed",
                    message="Run package could not be published atomically.",
                    next_action="Check Team Memory permissions and retry.",
                ) from error

    def _atomic_write_new(self, target: Path, raw: bytes) -> None:
        self._validate_path(target, managed=True)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.parent / f".{target.name}.tmp-{uuid.uuid4().hex}"
        try:
            temporary.write_bytes(raw)
            os.link(temporary, target)
        except FileExistsError as error:
            raise WorkspaceError(
                code="run_event_exists",
                message=f"Run event already exists: {target.name}.",
                next_action="Retry with a unique event ID.",
            ) from error
        except OSError as error:
            raise WorkspaceError(
                code="run_write_failed",
                message="Run event could not be written atomically.",
                next_action="Check Team Memory permissions and retry.",
            ) from error
        finally:
            temporary.unlink(missing_ok=True)

    def _validate_projected_capacity(
        self,
        encoded: Mapping[str, bytes],
        capacity: CapacityStatus,
    ) -> None:
        actual = 0
        for managed in MANAGED_PATHS:
            root = self.repository_path / managed
            self._validate_path(root, managed=True)
            if not root.exists():
                continue
            for path in root.rglob("*"):
                self._validate_path(path, managed=True)
                if path.is_file():
                    actual += path.stat().st_size
        projected = actual + sum(len(raw) for raw in encoded.values())
        if projected >= capacity.max_repository_bytes:
            raise WorkspaceError(
                code="repository_capacity_exceeded",
                message="Run assets would reach the Team Memory capacity limit.",
                next_action="Archive reviewed assets before sealing this Run.",
            )

    @staticmethod
    def _require_regular_file_size(
        name: str,
        raw: bytes,
        capacity: CapacityStatus,
    ) -> None:
        if len(raw) >= capacity.max_file_bytes:
            raise WorkspaceError(
                code="file_too_large",
                message=f"Run evidence reaches the single-file limit: {name}.",
                next_action="Reduce or partition the evidence before sealing.",
            )

    @contextmanager
    def _run_lock(self, run_id: str) -> Iterator[None]:
        self._validate_id(run_id, "Run ID")
        path = (
            self.repository_path
            / ".mlagent-local"
            / "run-locks"
            / f"{run_id}.lock"
        )
        self._validate_path(path, managed=False)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a+b") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    @contextmanager
    def _capacity_lock(self) -> Iterator[None]:
        path = self.repository_path / ".mlagent-local" / "capacity.lock"
        self._validate_path(path, managed=False)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a+b") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def _active_path(self, run_id: str) -> Path:
        return (
            self.repository_path
            / ".mlagent-local"
            / "active-runs"
            / f"{run_id}.json"
        )

    def _is_active(self, run_id: str) -> bool:
        path = self._active_path(run_id)
        if not path.is_file():
            return False
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            pid = payload["pid"]
            if not isinstance(pid, int) or pid < 1:
                return False
            os.kill(pid, 0)
        except (OSError, KeyError, TypeError, json.JSONDecodeError):
            return False
        return True

    def _validate_path(self, path: Path, managed: bool) -> None:
        try:
            relative = path.relative_to(self.repository_path)
        except ValueError:
            self._unsafe_path()
            return
        if managed and (not relative.parts or relative.parts[0] not in MANAGED_PATHS):
            self._unsafe_path()
        current = self.repository_path
        for part in relative.parts:
            current = current / part
            if current.is_symlink():
                self._unsafe_path()
        try:
            path.resolve(strict=False).relative_to(self.repository_path)
        except ValueError:
            self._unsafe_path()

    @staticmethod
    def _validate_source_file(
        target: Path,
        root: Path,
        resolved_root: Path,
    ) -> None:
        try:
            relative = target.relative_to(root)
        except ValueError:
            RunRepository._invalid_code_revision("code path escaped its root")
            return
        current = root
        for part in relative.parts:
            current = current / part
            if current.is_symlink():
                RunRepository._invalid_code_revision(
                    "code path contains a symbolic link"
                )
        try:
            target.resolve(strict=True).relative_to(resolved_root)
        except (OSError, ValueError):
            RunRepository._invalid_code_revision(
                "code path is unavailable or outside its root"
            )
        if not target.is_file():
            RunRepository._invalid_code_revision("code path is not a file")

    @staticmethod
    def _safe_relative(value: str, label: str) -> Path:
        if not isinstance(value, str) or not value.strip():
            RunRepository._invalid_code_revision(f"{label} is empty")
        relative = Path(value)
        if relative.is_absolute() or ".." in relative.parts:
            RunRepository._invalid_code_revision(f"{label} is unsafe")
        return relative

    @staticmethod
    def _validate_id(value: str, label: str) -> None:
        if not isinstance(value, str) or SAFE_ID_PATTERN.fullmatch(value) is None:
            raise WorkspaceError(
                code="invalid_run_id",
                message=f"{label} is invalid: {value!r}.",
                next_action="Use a stable ID with letters, numbers, dots, underscores, or hyphens.",
            )

    @staticmethod
    def _validate_path_token(value: str, label: str) -> None:
        if (
            not isinstance(value, str)
            or SAFE_PATH_TOKEN_PATTERN.fullmatch(value) is None
        ):
            raise WorkspaceError(
                code="invalid_run_path_token",
                message=f"{label} is invalid: {value!r}.",
                next_action="Use a stable alphanumeric fingerprint or path token.",
            )

    @staticmethod
    def _validate_actor(actor_id: str) -> None:
        if not isinstance(actor_id, str) or not actor_id.strip():
            raise WorkspaceError(
                code="missing_actor",
                message="Run records require a non-empty actor.",
                next_action="Reconnect Team Memory with a valid member identity.",
            )

    def _new_id(self, factory: Callable[[], str], label: str) -> str:
        value = factory()
        self._validate_id(value, label)
        return value

    def _timestamp(self) -> str:
        value = self.clock()
        if not isinstance(value, str) or not value.strip():
            raise WorkspaceError(
                code="invalid_run_clock",
                message="Run timestamp is empty.",
                next_action="Retry with a valid UTC clock.",
            )
        return value

    @staticmethod
    def _load_json(path: Path, code: str) -> dict[str, Any]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise WorkspaceError(
                code=code,
                message=f"Authoritative Run JSON cannot be read: {path}.",
                next_action="Restore the file from Git.",
            ) from error
        if not isinstance(payload, dict):
            raise WorkspaceError(
                code=code,
                message=f"Authoritative Run JSON must be an object: {path}.",
                next_action="Restore the file from Git.",
            )
        return payload

    @staticmethod
    def _event_snapshot(
        payload: Mapping[str, Any],
        relative: Path,
    ) -> RunEventSnapshot:
        return RunEventSnapshot(
            asset_id=payload["asset_id"],
            asset_path=relative.as_posix(),
            run_id=payload["run_id"],
            event_type=payload["event_type"],
            state=payload["state"],
            previous_event_id=payload["previous_event_id"],
            created_at=payload["created_at"],
            created_by=payload["created_by"],
        )

    @staticmethod
    def _event_conflict(run_id: str) -> None:
        raise WorkspaceError(
            code="run_event_conflict",
            message=f"Run {run_id} has conflicting event heads.",
            next_action="Reconcile append-only Run events before continuing.",
        )

    @staticmethod
    def _invalid_instance(detail: str) -> None:
        raise WorkspaceError(
            code="invalid_training_instance",
            message=f"Training Instance evidence is invalid: {detail}.",
            next_action="Restore the frozen evidence or start a new instance.",
        )

    @staticmethod
    def _invalid_code_revision(detail: str) -> None:
        raise WorkspaceError(
            code="invalid_code_revision",
            message=f"Frozen code revision is invalid: {detail}.",
            next_action="Restore the approved code and freeze it again.",
        )

    @staticmethod
    def _unsafe_path() -> None:
        raise WorkspaceError(
            code="unsafe_run_path",
            message="Run path is symbolic or outside Team Memory.",
            next_action="Use real files under the managed Run directories.",
        )


def _json_bytes(payload: Any) -> bytes:
    return (
        json.dumps(
            payload,
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
        )
        + "\n"
    ).encode("utf-8")


def _fingerprint(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()


def _fingerprint_bytes(raw: bytes) -> str:
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return ""
    return _fingerprint(payload)


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _milliseconds_between(start: str, end: str) -> int:
    try:
        started = datetime.fromisoformat(start.replace("Z", "+00:00"))
        ended = datetime.fromisoformat(end.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return 0
    return int((ended - started).total_seconds() * 1000)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
