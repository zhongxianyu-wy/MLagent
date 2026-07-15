from __future__ import annotations

import hashlib
import json
import math
import re
import uuid
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.domain.models import (
    CandidateCodeFile,
    CandidateCodePreview,
    CapacityStatus,
    DatasetVersionSnapshot,
    ExplorationApprovalSnapshot,
    ExplorationPlanSnapshot,
    ExplorationReviewSnapshot,
    ExplorationRound,
    RecordExplorationPlanCommand,
    WorkspaceError,
)


EXPLORATION_SCHEMA_VERSION = 1
PLAN_ROOT = Path("raw-records/exploration-plans")
APPROVAL_ROOT = Path("approvals/exploration-plans")
GATE_AUDIT_ROOT = Path("approvals/training-gates")
MAX_CODE_FILES = 32
MAX_CODE_FILE_BYTES = 1_000_000
SAFE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")
PLAN_CONTENT_FIELDS = (
    "plan_id",
    "planning_session_id",
    "dataset_id",
    "dataset_version",
    "dataset_content_fingerprint",
    "dataset_version_fingerprint",
    "user_direction",
    "baseline_hypothesis",
    "rounds",
    "primary_metric",
    "target_metric",
    "stop_conditions",
    "resource_limits",
    "trusted_experience_ids",
    "pending_experience_ids",
    "excluded_pending_experience_ids",
    "candidate_code_files",
    "code_fingerprint",
)
APPROVAL_CONTENT_FIELDS = (
    "plan_id",
    "plan_event_id",
    "dataset_id",
    "dataset_version",
    "dataset_version_fingerprint",
    "plan_fingerprint",
    "code_fingerprint",
    "decision",
    "created_at",
    "created_by",
)


class ExplorationRepository:
    def __init__(
        self,
        repository_path: Path,
        event_id_factory: Callable[[], str] | None = None,
        approval_id_factory: Callable[[], str] | None = None,
        audit_id_factory: Callable[[], str] | None = None,
        clock: Callable[[], str] | None = None,
    ) -> None:
        self.repository_path = repository_path.expanduser().resolve()
        self.event_id_factory = event_id_factory or (
            lambda: f"plan-event-{uuid.uuid4()}"
        )
        self.approval_id_factory = approval_id_factory or (
            lambda: f"plan-approval-{uuid.uuid4()}"
        )
        self.audit_id_factory = audit_id_factory or (
            lambda: f"gate-audit-{uuid.uuid4()}"
        )
        self.clock = clock or _utc_now

    def record_plan(
        self,
        command: RecordExplorationPlanCommand,
        dataset: DatasetVersionSnapshot,
        actor_id: str,
        capacity: CapacityStatus,
    ) -> ExplorationPlanSnapshot:
        self._validate_actor(actor_id)
        self._validate_plan(command, dataset)
        code_files = self._read_code_files(
            command.code_root,
            command.candidate_code_paths,
        )
        event_id = self._new_id(self.event_id_factory, "plan event")
        created_at = self._timestamp()
        payload: dict[str, Any] = {
            "asset_type": "exploration_plan_event",
            "asset_id": event_id,
            "schema_version": EXPLORATION_SCHEMA_VERSION,
            "event_type": "plan_recorded",
            "state": "pending_review",
            "plan_id": command.plan_id,
            "planning_session_id": command.planning_session_id,
            "dataset_id": dataset.dataset_id,
            "dataset_version": dataset.version,
            "dataset_content_fingerprint": dataset.content_fingerprint,
            "dataset_version_fingerprint": dataset.version_fingerprint,
            "user_direction": command.user_direction.strip(),
            "baseline_hypothesis": command.baseline_hypothesis.strip(),
            "rounds": [
                {
                    "round_number": item.round_number,
                    "hypothesis": item.hypothesis.strip(),
                    "optimization_direction": item.optimization_direction.strip(),
                    "intended_changes": [
                        change.strip() for change in item.intended_changes
                    ],
                }
                for item in command.rounds
            ],
            "primary_metric": dataset.primary_metric,
            "target_metric": dataset.target_metric,
            "stop_conditions": [item.strip() for item in command.stop_conditions],
            "resource_limits": dict(command.resource_limits),
            "trusted_experience_ids": list(command.trusted_experience_ids),
            "pending_experience_ids": list(command.pending_experience_ids),
            "excluded_pending_experience_ids": list(
                command.excluded_pending_experience_ids
            ),
            "candidate_code_files": [
                _code_file_payload(item) for item in code_files
            ],
            "code_fingerprint": _code_fingerprint(code_files),
            "created_at": created_at,
            "created_by": actor_id,
        }
        payload["plan_fingerprint"] = _fingerprint(
            {field: payload[field] for field in PLAN_CONTENT_FIELDS}
        )
        relative_path = PLAN_ROOT / command.plan_id / f"{event_id}.json"
        self._write_json(relative_path, payload, capacity)
        return self._plan_snapshot(payload, relative_path)

    def current(self, plan_id: str) -> ExplorationPlanSnapshot:
        events = self.list_plan_events(plan_id)
        if not events:
            raise WorkspaceError(
                code="exploration_plan_not_found",
                message=f"No exploration plan record exists for {plan_id}.",
                next_action="Record the Claude-completed exploration plan before review.",
            )
        return max(events, key=lambda item: (item.created_at, item.asset_id))

    def latest(self) -> ExplorationPlanSnapshot | None:
        root = self.repository_path / PLAN_ROOT
        self._validate_memory_path(root)
        if not root.is_dir():
            return None
        plans: list[ExplorationPlanSnapshot] = []
        for family in sorted(root.iterdir()):
            self._validate_memory_path(family)
            if family.is_dir() and SAFE_ID_PATTERN.fullmatch(family.name):
                plans.extend(self.list_plan_events(family.name))
        if not plans:
            return None
        return max(plans, key=lambda item: (item.created_at, item.asset_id))

    def list_plan_events(
        self,
        plan_id: str,
    ) -> tuple[ExplorationPlanSnapshot, ...]:
        self._validate_id(plan_id, "plan ID")
        family = self.repository_path / PLAN_ROOT / plan_id
        self._validate_memory_path(family)
        if not family.is_dir():
            return ()
        events = []
        for path in sorted(family.iterdir()):
            self._validate_memory_path(path)
            if path.is_file() and path.suffix == ".json":
                events.append(self._load_plan(path, plan_id))
        return tuple(sorted(events, key=lambda item: (item.created_at, item.asset_id)))

    def approve_current(
        self,
        plan_id: str,
        code_root: Path,
        actor_id: str,
        capacity: CapacityStatus,
    ) -> ExplorationApprovalSnapshot:
        self._validate_actor(actor_id)
        plan = self.current(plan_id)
        current_files = self._read_code_files(
            code_root,
            tuple(item.path for item in plan.candidate_code_files),
        )
        if (
            current_files != plan.candidate_code_files
            or _code_fingerprint(current_files) != plan.code_fingerprint
        ):
            raise WorkspaceError(
                code="candidate_code_changed",
                message="Candidate code changed after the current plan was recorded.",
                next_action="Record the updated plan and code fingerprints before approval.",
            )
        approval_id = self._new_id(self.approval_id_factory, "approval")
        created_at = self._timestamp()
        payload: dict[str, Any] = {
            "asset_type": "exploration_plan_approval",
            "asset_id": approval_id,
            "schema_version": EXPLORATION_SCHEMA_VERSION,
            "plan_id": plan.plan_id,
            "plan_event_id": plan.asset_id,
            "dataset_id": plan.dataset_id,
            "dataset_version": plan.dataset_version,
            "dataset_version_fingerprint": plan.dataset_version_fingerprint,
            "plan_fingerprint": plan.plan_fingerprint,
            "code_fingerprint": plan.code_fingerprint,
            "decision": "approved",
            "created_at": created_at,
            "created_by": actor_id,
        }
        payload["approval_fingerprint"] = _fingerprint(
            {field: payload[field] for field in APPROVAL_CONTENT_FIELDS}
        )
        relative_path = APPROVAL_ROOT / plan.plan_id / f"{approval_id}.json"
        self._write_json(relative_path, payload, capacity)
        return self._approval_snapshot(payload, relative_path)

    def load_approval(
        self,
        plan_id: str,
        approval_id: str,
    ) -> ExplorationApprovalSnapshot:
        self._validate_id(plan_id, "plan ID")
        self._validate_id(approval_id, "approval ID")
        relative_path = APPROVAL_ROOT / plan_id / f"{approval_id}.json"
        path = self.repository_path / relative_path
        self._validate_memory_path(path)
        if not path.is_file():
            raise WorkspaceError(
                code="plan_approval_not_found",
                message=f"Exploration plan approval does not exist: {approval_id}.",
                next_action="Approve the current plan and candidate code before training.",
            )
        return self._load_approval(path, plan_id, approval_id)

    def review(
        self,
        plan_id: str,
        code_root: Path,
    ) -> ExplorationReviewSnapshot:
        plan = self.current(plan_id)
        previews = self._code_previews(code_root, plan.candidate_code_files)
        approvals = self._list_approvals(plan_id)
        approval = approvals[-1] if approvals else None
        code_is_current = all(item.state == "current" for item in previews)
        if approval is None:
            state = "pending_review"
        elif (
            approval.plan_event_id == plan.asset_id
            and approval.dataset_version_fingerprint
            == plan.dataset_version_fingerprint
            and approval.plan_fingerprint == plan.plan_fingerprint
            and approval.code_fingerprint == plan.code_fingerprint
            and code_is_current
        ):
            state = "approved"
        else:
            state = "approval_stale"
        return ExplorationReviewSnapshot(
            plan=plan,
            approval=approval,
            approval_state=state,
            code_previews=previews,
        )

    def _list_approvals(
        self,
        plan_id: str,
    ) -> tuple[ExplorationApprovalSnapshot, ...]:
        self._validate_id(plan_id, "plan ID")
        family = self.repository_path / APPROVAL_ROOT / plan_id
        self._validate_memory_path(family)
        if not family.is_dir():
            return ()
        approvals = []
        for path in sorted(family.iterdir()):
            self._validate_memory_path(path)
            if path.is_file() and path.suffix == ".json":
                approvals.append(self._load_approval(path, plan_id, path.stem))
        return tuple(
            sorted(approvals, key=lambda item: (item.created_at, item.asset_id))
        )

    def _load_plan(self, path: Path, plan_id: str) -> ExplorationPlanSnapshot:
        payload = self._load_json(path, "invalid_exploration_plan")
        required = {
            "asset_type",
            "asset_id",
            "schema_version",
            "event_type",
            "state",
            "plan_fingerprint",
            "created_at",
            "created_by",
            *PLAN_CONTENT_FIELDS,
        }
        if not required.issubset(payload):
            self._invalid_plan("required fields are missing")
        if (
            payload["asset_type"] != "exploration_plan_event"
            or payload["schema_version"] != EXPLORATION_SCHEMA_VERSION
            or payload["event_type"] != "plan_recorded"
            or payload["state"] != "pending_review"
            or payload["plan_id"] != plan_id
            or payload["asset_id"] != path.stem
        ):
            self._invalid_plan("identity fields are invalid")
        self._validate_stored_plan_types(payload)
        expected = _fingerprint(
            {field: payload[field] for field in PLAN_CONTENT_FIELDS}
        )
        if payload["plan_fingerprint"] != expected:
            self._invalid_plan("content fingerprint does not match")
        code_files = tuple(
            CandidateCodeFile(
                path=item["path"],
                sha256=item["sha256"],
                size_bytes=item["size_bytes"],
            )
            for item in payload["candidate_code_files"]
        )
        if payload["code_fingerprint"] != _code_fingerprint(code_files):
            self._invalid_plan("code fingerprint does not match")
        relative_path = path.relative_to(self.repository_path)
        return self._plan_snapshot(payload, relative_path)

    def _load_approval(
        self,
        path: Path,
        plan_id: str,
        approval_id: str,
    ) -> ExplorationApprovalSnapshot:
        payload = self._load_json(path, "invalid_plan_approval")
        required = {
            "asset_type",
            "asset_id",
            "schema_version",
            "approval_fingerprint",
            *APPROVAL_CONTENT_FIELDS,
        }
        if not required.issubset(payload):
            self._invalid_approval("required fields are missing")
        if (
            payload["asset_type"] != "exploration_plan_approval"
            or payload["schema_version"] != EXPLORATION_SCHEMA_VERSION
            or payload["asset_id"] != approval_id
            or payload["plan_id"] != plan_id
            or payload["decision"] != "approved"
        ):
            self._invalid_approval("identity fields are invalid")
        if not all(
            isinstance(payload[field], str) and payload[field].strip()
            for field in (
                "plan_event_id",
                "dataset_id",
                "dataset_version_fingerprint",
                "plan_fingerprint",
                "code_fingerprint",
                "created_at",
                "created_by",
            )
        ) or type(payload["dataset_version"]) is not int:
            self._invalid_approval("field types are invalid")
        expected = _fingerprint(
            {field: payload[field] for field in APPROVAL_CONTENT_FIELDS}
        )
        if payload["approval_fingerprint"] != expected:
            self._invalid_approval("content fingerprint does not match")
        return self._approval_snapshot(
            payload,
            path.relative_to(self.repository_path),
        )

    @staticmethod
    def _validate_plan(
        command: RecordExplorationPlanCommand,
        dataset: DatasetVersionSnapshot,
    ) -> None:
        ExplorationRepository._validate_id(command.plan_id, "plan ID")
        ExplorationRepository._validate_id(
            command.planning_session_id,
            "planning session ID",
        )
        if (
            dataset.state != "confirmed"
            or command.dataset_id != dataset.dataset_id
            or command.dataset_version != dataset.version
        ):
            raise WorkspaceError(
                code="exploration_dataset_mismatch",
                message="The exploration plan does not match the confirmed Dataset Version.",
                next_action="Record the plan against the exact Dataset Version under review.",
            )
        required_text = (
            command.user_direction,
            command.baseline_hypothesis,
        )
        if (
            not all(isinstance(item, str) and item.strip() for item in required_text)
            or not command.rounds
            or not command.stop_conditions
            or not command.resource_limits
            or not command.candidate_code_paths
        ):
            ExplorationRepository._incomplete_plan()
        for expected_number, item in enumerate(command.rounds, start=1):
            if (
                not isinstance(item, ExplorationRound)
                or item.round_number != expected_number
                or not item.hypothesis.strip()
                or not item.optimization_direction.strip()
                or not item.intended_changes
                or not all(change.strip() for change in item.intended_changes)
            ):
                ExplorationRepository._incomplete_plan()
        if not all(
            isinstance(item, str) and item.strip()
            for item in command.stop_conditions
        ):
            ExplorationRepository._incomplete_plan()
        for key, value in command.resource_limits.items():
            valid_value = (
                isinstance(value, str)
                and bool(value.strip())
                or type(value) in {int, float}
                and math.isfinite(value)
            )
            if not isinstance(key, str) or not key.strip() or not valid_value:
                ExplorationRepository._incomplete_plan()
        ExplorationRepository._validate_experience_references(command)

    @staticmethod
    def _validate_experience_references(
        command: RecordExplorationPlanCommand,
    ) -> None:
        groups = (
            command.trusted_experience_ids,
            command.pending_experience_ids,
            command.excluded_pending_experience_ids,
        )
        if any(
            len(group) != len(set(group))
            or any(not isinstance(item, str) or not item.strip() for item in group)
            for group in groups
        ):
            ExplorationRepository._invalid_experience_references()
        trusted = set(command.trusted_experience_ids)
        pending = set(command.pending_experience_ids)
        excluded = set(command.excluded_pending_experience_ids)
        if trusted & pending or not excluded.issubset(pending):
            ExplorationRepository._invalid_experience_references()

    def _read_code_files(
        self,
        code_root: Path,
        relative_paths: tuple[str, ...],
    ) -> tuple[CandidateCodeFile, ...]:
        if not relative_paths or len(relative_paths) > MAX_CODE_FILES:
            self._incomplete_plan()
        root = code_root.expanduser()
        if root.is_symlink() or not root.is_dir():
            self._unsafe_code_path()
        resolved_root = root.resolve()
        files: list[CandidateCodeFile] = []
        seen: set[str] = set()
        for raw_path in relative_paths:
            if not isinstance(raw_path, str) or not raw_path.strip():
                self._unsafe_code_path()
            relative = Path(raw_path)
            if relative.is_absolute() or ".." in relative.parts:
                self._unsafe_code_path()
            normalized = relative.as_posix()
            if normalized in seen:
                raise WorkspaceError(
                    code="duplicate_candidate_code_path",
                    message=f"Candidate code path is listed more than once: {normalized}.",
                    next_action="Keep each candidate code file once in the exploration plan.",
                )
            seen.add(normalized)
            target = root / relative
            self._validate_code_path(target, root, resolved_root)
            try:
                raw = target.read_bytes()
            except OSError as error:
                raise WorkspaceError(
                    code="candidate_code_not_found",
                    message=f"Candidate code cannot be read: {normalized}.",
                    next_action="Restore the generated code inside the managed code root.",
                ) from error
            if len(raw) >= MAX_CODE_FILE_BYTES:
                raise WorkspaceError(
                    code="candidate_code_too_large",
                    message=f"Candidate code exceeds the review limit: {normalized}.",
                    next_action="Split the candidate training code into smaller reviewable files.",
                )
            try:
                raw.decode("utf-8")
            except UnicodeDecodeError as error:
                raise WorkspaceError(
                    code="candidate_code_not_text",
                    message=f"Candidate code is not UTF-8 text: {normalized}.",
                    next_action="Generate reviewable UTF-8 source code before approval.",
                ) from error
            files.append(
                CandidateCodeFile(
                    path=normalized,
                    sha256=hashlib.sha256(raw).hexdigest(),
                    size_bytes=len(raw),
                )
            )
        return tuple(sorted(files, key=lambda item: item.path))

    def _code_previews(
        self,
        code_root: Path,
        recorded_files: tuple[CandidateCodeFile, ...],
    ) -> tuple[CandidateCodePreview, ...]:
        previews = []
        for recorded in recorded_files:
            try:
                current = self._read_code_files(code_root, (recorded.path,))[0]
                content = (code_root.expanduser() / recorded.path).read_text(
                    encoding="utf-8"
                )
            except WorkspaceError as error:
                state = (
                    "unsafe"
                    if error.code == "unsafe_candidate_code_path"
                    else "missing"
                )
                previews.append(
                    CandidateCodePreview(
                        path=recorded.path,
                        content="",
                        recorded_sha256=recorded.sha256,
                        current_sha256=None,
                        state=state,
                    )
                )
                continue
            previews.append(
                CandidateCodePreview(
                    path=recorded.path,
                    content=content,
                    recorded_sha256=recorded.sha256,
                    current_sha256=current.sha256,
                    state=(
                        "current" if current == recorded else "changed"
                    ),
                )
            )
        return tuple(previews)

    @staticmethod
    def _validate_code_path(target: Path, root: Path, resolved_root: Path) -> None:
        current = root
        for part in target.relative_to(root).parts:
            current = current / part
            if current.is_symlink():
                ExplorationRepository._unsafe_code_path()
        try:
            target.resolve(strict=False).relative_to(resolved_root)
        except ValueError:
            ExplorationRepository._unsafe_code_path()
        if not target.is_file():
            raise WorkspaceError(
                code="candidate_code_not_found",
                message=f"Candidate code file does not exist: {target.name}.",
                next_action="Generate the candidate code inside the managed code root.",
            )

    def _write_json(
        self,
        relative_path: Path,
        payload: dict[str, Any],
        capacity: CapacityStatus,
    ) -> None:
        raw = (
            json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
        ).encode("utf-8")
        if len(raw) >= capacity.max_file_bytes:
            raise WorkspaceError(
                code="file_too_large",
                message="The exploration record reaches the Team Memory file limit.",
                next_action="Reduce redundant plan text before recording it.",
            )
        if capacity.bytes_used + len(raw) >= capacity.max_repository_bytes:
            raise WorkspaceError(
                code="repository_capacity_exceeded",
                message="The exploration record would reach the Team Memory capacity limit.",
                next_action="Archive reviewed assets before adding this record.",
            )
        target = self.repository_path / relative_path
        self._validate_memory_path(target)
        if target.exists():
            raise WorkspaceError(
                code="immutable_event_exists",
                message=f"An authoritative event already exists: {relative_path.as_posix()}.",
                next_action="Retry with a new event identity; never overwrite history.",
            )
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            self._validate_memory_path(target.parent)
            temporary = target.parent / f".{target.name}.tmp-{uuid.uuid4().hex}"
            temporary.write_bytes(raw)
            temporary.rename(target)
        except OSError as error:
            if "temporary" in locals():
                temporary.unlink(missing_ok=True)
            raise WorkspaceError(
                code="exploration_record_write_failed",
                message="The exploration record could not be written atomically.",
                next_action="Check Team Memory permissions and retry without changing prior events.",
            ) from error

    def _validate_memory_path(self, path: Path) -> None:
        try:
            relative = path.relative_to(self.repository_path)
        except ValueError:
            self._unsafe_memory_path()
            return
        if not relative.parts or relative.parts[0] not in {
            "raw-records",
            "approvals",
        }:
            self._unsafe_memory_path()
        current = self.repository_path
        for part in relative.parts:
            current = current / part
            if current.is_symlink():
                self._unsafe_memory_path()
        try:
            path.resolve(strict=False).relative_to(self.repository_path)
        except ValueError:
            self._unsafe_memory_path()

    @staticmethod
    def _load_json(path: Path, error_code: str) -> dict[str, Any]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise WorkspaceError(
                code=error_code,
                message=f"Authoritative exploration record cannot be read: {path.name}.",
                next_action="Restore the append-only record from Git.",
            ) from error
        if not isinstance(payload, dict):
            raise WorkspaceError(
                code=error_code,
                message="Authoritative exploration records must be JSON objects.",
                next_action="Restore the append-only record from Git.",
            )
        return payload

    @staticmethod
    def _validate_stored_plan_types(payload: dict[str, Any]) -> None:
        string_fields = (
            "asset_id",
            "plan_id",
            "planning_session_id",
            "dataset_id",
            "dataset_content_fingerprint",
            "dataset_version_fingerprint",
            "user_direction",
            "baseline_hypothesis",
            "primary_metric",
            "code_fingerprint",
            "plan_fingerprint",
            "created_at",
            "created_by",
        )
        if not all(
            isinstance(payload[field], str) and payload[field].strip()
            for field in string_fields
        ):
            ExplorationRepository._invalid_plan("string fields are invalid")
        if (
            type(payload["dataset_version"]) is not int
            or type(payload["target_metric"]) not in {int, float}
            or not isinstance(payload["rounds"], list)
            or not payload["rounds"]
            or not isinstance(payload["stop_conditions"], list)
            or not isinstance(payload["resource_limits"], dict)
            or not isinstance(payload["candidate_code_files"], list)
            or not payload["candidate_code_files"]
        ):
            ExplorationRepository._invalid_plan("structured fields are invalid")
        list_fields = (
            "trusted_experience_ids",
            "pending_experience_ids",
            "excluded_pending_experience_ids",
            "stop_conditions",
        )
        if any(
            not isinstance(payload[field], list)
            or not all(isinstance(item, str) for item in payload[field])
            for field in list_fields
        ):
            ExplorationRepository._invalid_plan("list fields are invalid")
        for item in payload["rounds"]:
            if (
                not isinstance(item, dict)
                or set(item)
                != {
                    "round_number",
                    "hypothesis",
                    "optimization_direction",
                    "intended_changes",
                }
                or type(item["round_number"]) is not int
                or not isinstance(item["hypothesis"], str)
                or not isinstance(item["optimization_direction"], str)
                or not isinstance(item["intended_changes"], list)
                or not all(
                    isinstance(change, str) for change in item["intended_changes"]
                )
            ):
                ExplorationRepository._invalid_plan("round fields are invalid")
        for item in payload["candidate_code_files"]:
            if (
                not isinstance(item, dict)
                or set(item) != {"path", "sha256", "size_bytes"}
                or not isinstance(item["path"], str)
                or not isinstance(item["sha256"], str)
                or type(item["size_bytes"]) is not int
            ):
                ExplorationRepository._invalid_plan("code file fields are invalid")

    @staticmethod
    def _plan_snapshot(
        payload: dict[str, Any],
        relative_path: Path,
    ) -> ExplorationPlanSnapshot:
        return ExplorationPlanSnapshot(
            asset_id=payload["asset_id"],
            asset_path=relative_path.as_posix(),
            plan_id=payload["plan_id"],
            planning_session_id=payload["planning_session_id"],
            dataset_id=payload["dataset_id"],
            dataset_version=payload["dataset_version"],
            dataset_content_fingerprint=payload["dataset_content_fingerprint"],
            dataset_version_fingerprint=payload["dataset_version_fingerprint"],
            user_direction=payload["user_direction"],
            baseline_hypothesis=payload["baseline_hypothesis"],
            rounds=tuple(
                ExplorationRound(
                    round_number=item["round_number"],
                    hypothesis=item["hypothesis"],
                    optimization_direction=item["optimization_direction"],
                    intended_changes=tuple(item["intended_changes"]),
                )
                for item in payload["rounds"]
            ),
            primary_metric=payload["primary_metric"],
            target_metric=payload["target_metric"],
            stop_conditions=tuple(payload["stop_conditions"]),
            resource_limits=dict(payload["resource_limits"]),
            trusted_experience_ids=tuple(payload["trusted_experience_ids"]),
            pending_experience_ids=tuple(payload["pending_experience_ids"]),
            excluded_pending_experience_ids=tuple(
                payload["excluded_pending_experience_ids"]
            ),
            candidate_code_files=tuple(
                CandidateCodeFile(
                    path=item["path"],
                    sha256=item["sha256"],
                    size_bytes=item["size_bytes"],
                )
                for item in payload["candidate_code_files"]
            ),
            code_fingerprint=payload["code_fingerprint"],
            plan_fingerprint=payload["plan_fingerprint"],
            state=payload["state"],
            created_at=payload["created_at"],
            created_by=payload["created_by"],
        )

    @staticmethod
    def _approval_snapshot(
        payload: dict[str, Any],
        relative_path: Path,
    ) -> ExplorationApprovalSnapshot:
        return ExplorationApprovalSnapshot(
            asset_id=payload["asset_id"],
            asset_path=relative_path.as_posix(),
            plan_id=payload["plan_id"],
            plan_event_id=payload["plan_event_id"],
            dataset_id=payload["dataset_id"],
            dataset_version=payload["dataset_version"],
            dataset_version_fingerprint=payload["dataset_version_fingerprint"],
            plan_fingerprint=payload["plan_fingerprint"],
            code_fingerprint=payload["code_fingerprint"],
            decision=payload["decision"],
            created_at=payload["created_at"],
            created_by=payload["created_by"],
        )

    @staticmethod
    def _new_id(factory: Callable[[], str], label: str) -> str:
        value = factory()
        if not isinstance(value, str) or SAFE_ID_PATTERN.fullmatch(value) is None:
            raise WorkspaceError(
                code="invalid_exploration_event_id",
                message=f"The generated {label} ID is empty or invalid.",
                next_action="Retry with a stable alphanumeric event ID generator.",
            )
        return value

    def _timestamp(self) -> str:
        value = self.clock()
        if not isinstance(value, str) or not value.strip():
            raise WorkspaceError(
                code="invalid_exploration_timestamp",
                message="The exploration event time is empty or invalid.",
                next_action="Retry with a valid UTC clock.",
            )
        return value

    @staticmethod
    def _validate_id(value: str, label: str) -> None:
        if not isinstance(value, str) or SAFE_ID_PATTERN.fullmatch(value) is None:
            raise WorkspaceError(
                code="invalid_exploration_id",
                message=f"The {label} is empty or invalid.",
                next_action="Use a stable alphanumeric ID without path separators.",
            )

    @staticmethod
    def _validate_actor(actor_id: str) -> None:
        if not isinstance(actor_id, str) or not actor_id.strip():
            raise WorkspaceError(
                code="missing_actor",
                message="An exploration event requires a non-empty actor identity.",
                next_action="Reconnect the workspace with a valid team member identity.",
            )

    @staticmethod
    def _incomplete_plan() -> None:
        raise WorkspaceError(
            code="incomplete_exploration_plan",
            message="The exploration plan is missing a required review section.",
            next_action="Complete direction, baseline, rounds, stops, resources, and candidate code before recording.",
        )

    @staticmethod
    def _invalid_experience_references() -> None:
        raise WorkspaceError(
            code="invalid_experience_references",
            message="Trusted, Pending, and excluded experience references are inconsistent.",
            next_action="Keep Trusted and Pending references separate, and exclude only Pending references.",
        )

    @staticmethod
    def _unsafe_code_path() -> None:
        raise WorkspaceError(
            code="unsafe_candidate_code_path",
            message="A candidate code path escapes the managed code root or uses a symbolic link.",
            next_action="Use real relative files located inside the selected code root.",
        )

    @staticmethod
    def _unsafe_memory_path() -> None:
        raise WorkspaceError(
            code="unsafe_exploration_record_path",
            message="An exploration record path escapes Team Memory or uses a symbolic link.",
            next_action="Restore managed raw-records and approvals directories inside Team Memory.",
        )

    @staticmethod
    def _invalid_plan(reason: str) -> None:
        raise WorkspaceError(
            code="invalid_exploration_plan",
            message=f"The exploration plan record is invalid: {reason}.",
            next_action="Restore the append-only plan event from Git.",
        )

    @staticmethod
    def _invalid_approval(reason: str) -> None:
        raise WorkspaceError(
            code="invalid_plan_approval",
            message=f"The exploration approval record is invalid: {reason}.",
            next_action="Restore the append-only approval event from Git.",
        )


def _code_fingerprint(files: tuple[CandidateCodeFile, ...]) -> str:
    return _fingerprint([_code_file_payload(item) for item in files])


def _code_file_payload(item: CandidateCodeFile) -> dict[str, str | int]:
    return {
        "path": item.path,
        "sha256": item.sha256,
        "size_bytes": item.size_bytes,
    }


def _fingerprint(payload: Any) -> str:
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
