from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import shutil
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.domain.dataset_repository import DatasetRepository
from src.domain.memory_repository import load_authorized_reviewers
from src.domain.models import (
    CapacityStatus,
    FormalModelSnapshot,
    SopCandidateSnapshot,
    SopEvidenceReference,
    SopReproductionGateSnapshot,
    SopReviewOutcome,
    SopVersionSnapshot,
    WorkspaceError,
)
from src.domain.run_repository import RunRepository


SOP_SCHEMA_VERSION = 1
SOP_CANDIDATE_ROOT = Path("sops/candidates")
SOP_REPRODUCTION_ROOT = Path("approvals/sop-reproductions")
SOP_APPROVAL_ROOT = Path("approvals/sops")
FORMAL_MODEL_ROOT = Path("models/formal")
SAFE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")
INSTANCE_FILE_ROLES = {
    "input": "input",
    "environment": "environment",
    "split": "split",
    "metrics": "metrics",
    "predictions": "predictions",
    "model": "source_model",
}


@dataclass(frozen=True)
class SopCandidateSpec:
    sop_id: str
    name: str
    source_run_id: str
    source_instance_id: str
    strategy_summary: str
    optimization_background: str
    steps: tuple[str, ...]
    change_summary: str

    def __post_init__(self) -> None:
        for field_name in ("sop_id", "source_run_id", "source_instance_id"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or SAFE_ID_PATTERN.fullmatch(value) is None:
                raise ValueError(f"{field_name} must be a safe stable ID")
        for field_name in (
            "name",
            "strategy_summary",
            "optimization_background",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must be non-empty")
        if (
            not isinstance(self.steps, tuple)
            or not self.steps
            or any(not isinstance(step, str) or not step.strip() for step in self.steps)
        ):
            raise ValueError("steps must be a non-empty tuple of text")
        if not isinstance(self.change_summary, str):
            raise ValueError("change_summary must be a string")


@dataclass(frozen=True)
class SopReproductionGateSpec:
    candidate_id: str
    candidate_fingerprint: str
    outcome: str
    source_run_id: str
    source_instance_id: str
    source_instance_fingerprint: str
    reproduction_run_id: str
    reproduction_instance_id: str
    reproduction_instance_fingerprint: str
    source_metric_value: float
    reproduction_metric_value: float | None
    source_metric_six_decimals: str
    reproduction_metric_six_decimals: str | None
    reproduction_model_path: str | None
    reproduction_model_fingerprint: str | None
    comparisons: dict[str, bool]


@dataclass(frozen=True)
class SopReviewSpec:
    candidate_id: str
    expected_candidate_fingerprint: str
    expected_gate_fingerprint: str
    decision: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.candidate_id, str)
            or SAFE_ID_PATTERN.fullmatch(self.candidate_id) is None
        ):
            raise ValueError("candidate_id must be a safe stable ID")
        for field_name in (
            "expected_candidate_fingerprint",
            "expected_gate_fingerprint",
        ):
            value = getattr(self, field_name)
            if (
                not isinstance(value, str)
                or len(value) != 64
                or any(character not in "0123456789abcdef" for character in value)
            ):
                raise ValueError(f"{field_name} must be a SHA-256 digest")
        if self.decision not in {"approve", "reject"}:
            raise ValueError("decision must be approve or reject")


class SopRepository:
    def __init__(
        self,
        repository_path: Path,
        candidate_id_factory: Callable[[], str] | None = None,
        gate_id_factory: Callable[[], str] | None = None,
        approval_id_factory: Callable[[], str] | None = None,
        clock: Callable[[], str] | None = None,
    ) -> None:
        unresolved = repository_path.expanduser()
        if unresolved.is_symlink():
            self._unsafe_path()
        self.repository_path = unresolved.resolve()
        self.candidate_id_factory = candidate_id_factory or (
            lambda: f"candidate-{uuid.uuid4()}"
        )
        self.gate_id_factory = gate_id_factory or (
            lambda: f"sop-gate-{uuid.uuid4()}"
        )
        self.approval_id_factory = approval_id_factory or (
            lambda: f"sop-approval-{uuid.uuid4()}"
        )
        self.clock = clock or _utc_now

    def create_candidate(
        self,
        spec: SopCandidateSpec,
        actor_id: str,
        capacity: CapacityStatus,
    ) -> SopCandidateSnapshot:
        self._validate_actor(actor_id)
        if not isinstance(spec, SopCandidateSpec):
            raise WorkspaceError(
                code="invalid_sop_candidate",
                message="SOP candidate input does not match the governed contract.",
                next_action="Choose one Training Instance and complete the SOP method fields.",
            )
        with self._lock():
            source = self._collect_source(spec)
            equivalent = self._find_equivalent_candidate(spec)
            if equivalent is not None:
                return equivalent
            candidate_id = self._new_candidate_id()
            relative = SOP_CANDIDATE_ROOT / candidate_id / "manifest.json"
            created_at = self._timestamp()
            payload: dict[str, Any] = {
                "asset_type": "sop_candidate",
                "asset_id": candidate_id,
                "schema_version": SOP_SCHEMA_VERSION,
                "state": "pending_reproduction",
                "sop_id": spec.sop_id,
                "name": spec.name,
                "source_run_id": spec.source_run_id,
                "source_instance_id": spec.source_instance_id,
                "source_instance_fingerprint": source[
                    "source_instance_fingerprint"
                ],
                "dataset_id": source["dataset"].dataset_id,
                "dataset_version": source["dataset"].version,
                "dataset_content_fingerprint": source[
                    "dataset"
                ].content_fingerprint,
                "dataset_version_fingerprint": source[
                    "dataset"
                ].version_fingerprint,
                "code_fingerprint": source["instance"].code_fingerprint,
                "configuration_fingerprint": source[
                    "instance"
                ].configuration_fingerprint,
                "environment_fingerprint": source[
                    "instance"
                ].environment_fingerprint,
                "split_fingerprint": source["instance"].split_fingerprint,
                "random_seed": source["instance"].random_seed,
                "primary_metric_name": source[
                    "instance"
                ].primary_metric_name,
                "source_metric_value": source[
                    "instance"
                ].primary_metric_value,
                "source_model_fingerprint": source[
                    "instance"
                ].model_fingerprint,
                "plan_id": source["run_start"]["plan_id"],
                "plan_event_id": source["run_start"]["plan_event_id"],
                "plan_fingerprint": source["run_start"]["plan_fingerprint"],
                "approval_id": source["run_start"]["approval_id"],
                "approval_fingerprint": source[
                    "run_start"
                ]["approval_fingerprint"],
                "entrypoint_path": source["code_revision"].entrypoint_path,
                "strategy_summary": spec.strategy_summary,
                "optimization_background": spec.optimization_background,
                "steps": list(spec.steps),
                "change_summary": spec.change_summary,
                "evidence": [item.to_dict() for item in source["evidence"]],
                "created_at": created_at,
                "created_by": actor_id,
            }
            payload["candidate_fingerprint"] = _fingerprint(payload)
            raw = _json_bytes(payload)
            target = self.repository_path / relative
            if target.exists():
                existing = self.load_candidate(candidate_id)
                if self._matches_spec(existing, spec):
                    return existing
                raise WorkspaceError(
                    code="sop_candidate_exists",
                    message=f"SOP candidate ID already exists: {candidate_id}.",
                    next_action="Retry with a new candidate identity.",
                )
            self._write_candidate(target, raw, capacity)
            return self.load_candidate(candidate_id)

    def load_candidate(self, candidate_id: str) -> SopCandidateSnapshot:
        self._validate_id(candidate_id, "candidate_id")
        relative = SOP_CANDIDATE_ROOT / candidate_id / "manifest.json"
        path = self.repository_path / relative
        payload = self._load_json(path, "invalid_sop_candidate")
        canonical = dict(payload)
        fingerprint = canonical.pop("candidate_fingerprint", None)
        if (
            payload.get("asset_type") != "sop_candidate"
            or payload.get("asset_id") != candidate_id
            or payload.get("schema_version") != SOP_SCHEMA_VERSION
            or payload.get("state") != "pending_reproduction"
            or fingerprint != _fingerprint(canonical)
        ):
            self._invalid_candidate(candidate_id)
        actual_files = {
            item.relative_to(path.parent).as_posix()
            for item in path.parent.rglob("*")
            if item.is_file()
        }
        if actual_files != {"manifest.json"}:
            self._invalid_candidate(candidate_id)
        try:
            return SopCandidateSnapshot(
                asset_id=payload["asset_id"],
                asset_path=relative.as_posix(),
                sop_id=payload["sop_id"],
                name=payload["name"],
                source_run_id=payload["source_run_id"],
                source_instance_id=payload["source_instance_id"],
                candidate_fingerprint=payload["candidate_fingerprint"],
                dataset_id=payload["dataset_id"],
                dataset_version=payload["dataset_version"],
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
                random_seed=payload["random_seed"],
                primary_metric_name=payload["primary_metric_name"],
                source_metric_value=float(payload["source_metric_value"]),
                source_model_fingerprint=payload[
                    "source_model_fingerprint"
                ],
                strategy_summary=payload["strategy_summary"],
                optimization_background=payload[
                    "optimization_background"
                ],
                steps=tuple(payload["steps"]),
                change_summary=payload["change_summary"],
                evidence=tuple(
                    SopEvidenceReference(**item) for item in payload["evidence"]
                ),
                created_at=payload["created_at"],
                created_by=payload["created_by"],
            )
        except (KeyError, TypeError, ValueError) as error:
            raise WorkspaceError(
                code="invalid_sop_candidate",
                message=f"SOP candidate does not match its schema: {candidate_id}.",
                next_action="Restore the immutable candidate from Git.",
            ) from error

    def list_candidates(self) -> tuple[SopCandidateSnapshot, ...]:
        root = self.repository_path / SOP_CANDIDATE_ROOT
        self._validate_path(root)
        if not root.is_dir():
            return ()
        candidates = []
        for directory in sorted(root.iterdir()):
            if not directory.is_dir():
                self._invalid_candidate(directory.name)
            candidates.append(self.load_candidate(directory.name))
        return tuple(
            sorted(
                candidates,
                key=lambda item: (item.created_at, item.asset_id),
                reverse=True,
            )
        )

    def validate_candidate_source(
        self,
        candidate_id: str,
        expected_fingerprint: str | None = None,
    ) -> SopCandidateSnapshot:
        candidate = self.load_candidate(candidate_id)
        if (
            expected_fingerprint is not None
            and candidate.candidate_fingerprint != expected_fingerprint
        ):
            raise WorkspaceError(
                code="stale_sop_candidate",
                message="SOP candidate fingerprint changed before reproduction.",
                next_action="Reload the candidate and review its evidence again.",
            )
        spec = SopCandidateSpec(
            sop_id=candidate.sop_id,
            name=candidate.name,
            source_run_id=candidate.source_run_id,
            source_instance_id=candidate.source_instance_id,
            strategy_summary=candidate.strategy_summary,
            optimization_background=candidate.optimization_background,
            steps=candidate.steps,
            change_summary=candidate.change_summary,
        )
        source = self._collect_source(spec)
        payload = self._load_json(
            self.repository_path / candidate.asset_path,
            "invalid_sop_candidate",
        )
        expected = {
            "source_instance_fingerprint": source[
                "source_instance_fingerprint"
            ],
            "dataset_id": source["dataset"].dataset_id,
            "dataset_version": source["dataset"].version,
            "dataset_content_fingerprint": source[
                "dataset"
            ].content_fingerprint,
            "dataset_version_fingerprint": source[
                "dataset"
            ].version_fingerprint,
            "code_fingerprint": source["instance"].code_fingerprint,
            "configuration_fingerprint": source[
                "instance"
            ].configuration_fingerprint,
            "environment_fingerprint": source[
                "instance"
            ].environment_fingerprint,
            "split_fingerprint": source["instance"].split_fingerprint,
            "random_seed": source["instance"].random_seed,
            "primary_metric_name": source["instance"].primary_metric_name,
            "source_metric_value": source["instance"].primary_metric_value,
            "source_model_fingerprint": source[
                "instance"
            ].model_fingerprint,
            "evidence": [item.to_dict() for item in source["evidence"]],
        }
        if any(payload.get(key) != value for key, value in expected.items()):
            raise WorkspaceError(
                code="invalid_sop_candidate_evidence",
                message="SOP candidate no longer matches its source evidence.",
                next_action="Restore the candidate and source assets from Git.",
            )
        return candidate

    def record_reproduction_gate(
        self,
        spec: SopReproductionGateSpec,
        actor_id: str,
        capacity: CapacityStatus,
    ) -> SopReproductionGateSnapshot:
        self._validate_actor(actor_id)
        candidate = self.validate_candidate_source(
            spec.candidate_id,
            spec.candidate_fingerprint,
        )
        if candidate.source_run_id != spec.source_run_id or (
            candidate.source_instance_id != spec.source_instance_id
        ):
            raise WorkspaceError(
                code="invalid_sop_reproduction",
                message="Reproduction gate source does not match the candidate.",
                next_action="Discard the gate attempt and reproduce the selected candidate.",
            )
        with self._lock():
            existing = self.load_gate_for_candidate(spec.candidate_id)
            if existing is not None:
                if (
                    existing.candidate_fingerprint == spec.candidate_fingerprint
                    and existing.source_run_id == spec.source_run_id
                    and existing.source_instance_id == spec.source_instance_id
                    and existing.reproduction_run_id == spec.reproduction_run_id
                    and existing.reproduction_instance_id
                    == spec.reproduction_instance_id
                    and existing.outcome == spec.outcome
                ):
                    return existing
                raise WorkspaceError(
                    code="sop_gate_exists",
                    message="A different reproduction gate already exists for this candidate.",
                    next_action="Create a new SOP candidate before another reproduction.",
                )
            gate_id = self._new_gate_id()
            relative = (
                SOP_REPRODUCTION_ROOT
                / spec.candidate_id
                / f"{gate_id}.json"
            )
            payload: dict[str, Any] = {
                "asset_type": "sop_reproduction_gate",
                "asset_id": gate_id,
                "schema_version": SOP_SCHEMA_VERSION,
                "candidate_id": spec.candidate_id,
                "candidate_fingerprint": spec.candidate_fingerprint,
                "outcome": spec.outcome,
                "source_run_id": spec.source_run_id,
                "source_instance_id": spec.source_instance_id,
                "source_instance_fingerprint": spec.source_instance_fingerprint,
                "reproduction_run_id": spec.reproduction_run_id,
                "reproduction_instance_id": spec.reproduction_instance_id,
                "reproduction_instance_fingerprint": (
                    spec.reproduction_instance_fingerprint
                ),
                "source_metric_value": spec.source_metric_value,
                "reproduction_metric_value": spec.reproduction_metric_value,
                "source_metric_six_decimals": (
                    spec.source_metric_six_decimals
                ),
                "reproduction_metric_six_decimals": (
                    spec.reproduction_metric_six_decimals
                ),
                "reproduction_model_path": spec.reproduction_model_path,
                "reproduction_model_fingerprint": (
                    spec.reproduction_model_fingerprint
                ),
                "comparisons": dict(sorted(spec.comparisons.items())),
                "created_at": self._timestamp(),
                "created_by": actor_id,
            }
            payload["gate_fingerprint"] = _fingerprint(payload)
            raw = _json_bytes(payload)
            self._write_new_file(
                self.repository_path / relative,
                raw,
                capacity,
            )
            return self.load_gate(gate_id, spec.candidate_id)

    def load_gate(
        self,
        gate_id: str,
        candidate_id: str,
    ) -> SopReproductionGateSnapshot:
        self._validate_id(gate_id, "gate_id")
        self._validate_id(candidate_id, "candidate_id")
        relative = SOP_REPRODUCTION_ROOT / candidate_id / f"{gate_id}.json"
        payload = self._load_json(
            self.repository_path / relative,
            "invalid_sop_reproduction_gate",
        )
        canonical = dict(payload)
        fingerprint = canonical.pop("gate_fingerprint", None)
        if (
            payload.get("asset_type") != "sop_reproduction_gate"
            or payload.get("asset_id") != gate_id
            or payload.get("candidate_id") != candidate_id
            or payload.get("schema_version") != SOP_SCHEMA_VERSION
            or fingerprint != _fingerprint(canonical)
            or not isinstance(payload.get("comparisons"), dict)
            or any(
                not isinstance(value, bool)
                for value in payload.get("comparisons", {}).values()
            )
        ):
            self._invalid_gate(gate_id)
        try:
            return SopReproductionGateSnapshot(
                asset_id=payload["asset_id"],
                asset_path=relative.as_posix(),
                candidate_id=payload["candidate_id"],
                candidate_fingerprint=payload["candidate_fingerprint"],
                gate_fingerprint=payload["gate_fingerprint"],
                outcome=payload["outcome"],
                source_run_id=payload["source_run_id"],
                source_instance_id=payload["source_instance_id"],
                reproduction_run_id=payload["reproduction_run_id"],
                reproduction_instance_id=payload[
                    "reproduction_instance_id"
                ],
                source_metric_value=float(payload["source_metric_value"]),
                reproduction_metric_value=(
                    None
                    if payload["reproduction_metric_value"] is None
                    else float(payload["reproduction_metric_value"])
                ),
                source_metric_six_decimals=payload[
                    "source_metric_six_decimals"
                ],
                reproduction_metric_six_decimals=payload[
                    "reproduction_metric_six_decimals"
                ],
                created_at=payload["created_at"],
                created_by=payload["created_by"],
            )
        except (KeyError, TypeError, ValueError) as error:
            raise WorkspaceError(
                code="invalid_sop_reproduction_gate",
                message=f"SOP reproduction gate is invalid: {gate_id}.",
                next_action="Restore the immutable gate from Git.",
            ) from error

    def load_gate_for_candidate(
        self,
        candidate_id: str,
    ) -> SopReproductionGateSnapshot | None:
        self._validate_id(candidate_id, "candidate_id")
        root = self.repository_path / SOP_REPRODUCTION_ROOT / candidate_id
        self._validate_path(root)
        if not root.is_dir():
            return None
        paths = sorted(root.glob("*.json"))
        if len(paths) != 1:
            raise WorkspaceError(
                code="invalid_sop_reproduction_gate",
                message="A candidate must have at most one reproduction gate.",
                next_action="Restore the append-only gate history from Git.",
            )
        return self.load_gate(paths[0].stem, candidate_id)

    def review_candidate(
        self,
        spec: SopReviewSpec,
        actor_id: str,
        capacity: CapacityStatus,
    ) -> SopReviewOutcome:
        self._validate_actor(actor_id)
        if actor_id not in load_authorized_reviewers(self.repository_path):
            raise WorkspaceError(
                code="unauthorized_sop_reviewer",
                message=f"Team member is not authorized to review SOPs: {actor_id}.",
                next_action="Use an identity listed in approvals/reviewer-policy.json.",
            )
        candidate, gate, chain = self._validated_review_chain(spec)
        if gate.outcome != "passed":
            raise WorkspaceError(
                code="sop_gate_not_passed",
                message=f"SOP reproduction gate did not pass: {gate.outcome}.",
                next_action="Create a new candidate and complete an exact independent reproduction.",
            )
        with self._lock():
            existing = self._find_candidate_review(candidate.asset_id)
            if existing is not None:
                if existing["decision"] != spec.decision:
                    raise WorkspaceError(
                        code="sop_review_exists",
                        message="This SOP candidate already has a different review decision.",
                        next_action="Keep the immutable decision or create a new candidate.",
                    )
                return self._review_outcome(existing)
            approval_id = self._new_approval_id()
            if spec.decision == "reject":
                relative = (
                    SOP_APPROVAL_ROOT
                    / candidate.sop_id
                    / "rejections"
                    / f"{approval_id}.json"
                )
                payload: dict[str, Any] = {
                    "asset_type": "sop_review",
                    "asset_id": approval_id,
                    "schema_version": SOP_SCHEMA_VERSION,
                    "decision": "reject",
                    "candidate_id": candidate.asset_id,
                    "candidate_fingerprint": candidate.candidate_fingerprint,
                    "gate_id": gate.asset_id,
                    "gate_fingerprint": gate.gate_fingerprint,
                    "sop_id": candidate.sop_id,
                    "created_at": self._timestamp(),
                    "created_by": actor_id,
                }
                payload["approval_fingerprint"] = _fingerprint(payload)
                self._write_new_file(
                    self.repository_path / relative,
                    _json_bytes(payload),
                    capacity,
                )
                return self._review_outcome(payload)

            version = self._next_version(candidate.sop_id)
            previous = (
                None
                if version == 1
                else self.load_sop_version(candidate.sop_id, version - 1)
            )
            if version > 1 and not candidate.change_summary.strip():
                raise WorkspaceError(
                    code="missing_sop_change_summary",
                    message="A new SOP Version requires a change summary.",
                    next_action="Create a new candidate describing the version change.",
                )
            version_name = f"v{version:04d}"
            sop_version_id = f"{candidate.sop_id}-{version_name}"
            formal_model_id = f"model-{candidate.sop_id}-{version_name}"
            sop_relative = (
                Path("sops")
                / candidate.sop_id
                / version_name
                / "manifest.json"
            )
            model_relative = FORMAL_MODEL_ROOT / formal_model_id / "model.joblib"
            model_manifest_relative = (
                FORMAL_MODEL_ROOT / formal_model_id / "manifest.json"
            )
            approval_relative = (
                SOP_APPROVAL_ROOT
                / candidate.sop_id
                / version_name
                / f"{approval_id}.json"
            )
            created_at = self._timestamp()
            model_bytes = chain["reproduction_model_path"].read_bytes()
            model_fingerprint = _sha256(model_bytes)
            model_manifest: dict[str, Any] = {
                "asset_type": "formal_model",
                "asset_id": formal_model_id,
                "schema_version": SOP_SCHEMA_VERSION,
                "model_path": model_relative.as_posix(),
                "model_fingerprint": model_fingerprint,
                "sop_version_id": sop_version_id,
                "source_instance_id": candidate.source_instance_id,
                "reproduction_instance_id": gate.reproduction_instance_id,
                "dataset_id": candidate.dataset_id,
                "dataset_version": candidate.dataset_version,
                "primary_metric_name": candidate.primary_metric_name,
                "primary_metric_value": gate.reproduction_metric_value,
                "strategy_summary": candidate.strategy_summary,
                "optimization_background": candidate.optimization_background,
                "approval_id": approval_id,
                "created_at": created_at,
                "created_by": actor_id,
            }
            model_manifest["manifest_fingerprint"] = _fingerprint(
                model_manifest
            )
            sop_manifest: dict[str, Any] = {
                "asset_type": "sop_version",
                "asset_id": sop_version_id,
                "schema_version": SOP_SCHEMA_VERSION,
                "sop_id": candidate.sop_id,
                "name": candidate.name,
                "version": version,
                "previous_version_id": (
                    None if previous is None else previous.asset_id
                ),
                "previous_version_fingerprint": (
                    None
                    if previous is None
                    else previous.version_fingerprint
                ),
                "candidate_id": candidate.asset_id,
                "candidate_fingerprint": candidate.candidate_fingerprint,
                "gate_id": gate.asset_id,
                "gate_fingerprint": gate.gate_fingerprint,
                "source_run_id": candidate.source_run_id,
                "source_instance_id": candidate.source_instance_id,
                "reproduction_run_id": gate.reproduction_run_id,
                "reproduction_instance_id": gate.reproduction_instance_id,
                "dataset_id": candidate.dataset_id,
                "dataset_version": candidate.dataset_version,
                "primary_metric_name": candidate.primary_metric_name,
                "primary_metric_value": gate.reproduction_metric_value,
                "strategy_summary": candidate.strategy_summary,
                "optimization_background": candidate.optimization_background,
                "steps": list(candidate.steps),
                "change_summary": candidate.change_summary,
                "approval_id": approval_id,
                "formal_model_id": formal_model_id,
                "created_at": created_at,
                "created_by": actor_id,
            }
            sop_manifest["version_fingerprint"] = _fingerprint(sop_manifest)
            approval: dict[str, Any] = {
                "asset_type": "sop_review",
                "asset_id": approval_id,
                "schema_version": SOP_SCHEMA_VERSION,
                "decision": "approve",
                "candidate_id": candidate.asset_id,
                "candidate_fingerprint": candidate.candidate_fingerprint,
                "gate_id": gate.asset_id,
                "gate_fingerprint": gate.gate_fingerprint,
                "sop_id": candidate.sop_id,
                "sop_version_id": sop_version_id,
                "sop_version_fingerprint": sop_manifest[
                    "version_fingerprint"
                ],
                "formal_model_id": formal_model_id,
                "formal_model_manifest_fingerprint": model_manifest[
                    "manifest_fingerprint"
                ],
                "model_fingerprint": model_fingerprint,
                "created_at": created_at,
                "created_by": actor_id,
            }
            approval["approval_fingerprint"] = _fingerprint(approval)
            encoded = {
                self.repository_path / model_relative: model_bytes,
                self.repository_path / model_manifest_relative: _json_bytes(
                    model_manifest
                ),
                self.repository_path / sop_relative: _json_bytes(sop_manifest),
                self.repository_path / approval_relative: _json_bytes(approval),
            }
            self._validate_publication_capacity(encoded, capacity)
            for target in (
                self.repository_path / model_relative,
                self.repository_path / model_manifest_relative,
                self.repository_path / sop_relative,
            ):
                self._publish_exact_file(target, encoded[target])
            self._publish_exact_file(
                self.repository_path / approval_relative,
                encoded[self.repository_path / approval_relative],
            )
            return SopReviewOutcome(
                decision="approve",
                candidate_id=candidate.asset_id,
                gate_id=gate.asset_id,
                approval_id=approval_id,
                sop_version=self.load_sop_version(
                    candidate.sop_id,
                    version,
                ),
                formal_model=self.get_formal_model(formal_model_id),
            )

    def list_sop_versions(
        self,
        sop_id: str | None = None,
    ) -> tuple[SopVersionSnapshot, ...]:
        roots: list[Path]
        if sop_id is not None:
            self._validate_id(sop_id, "sop_id")
            roots = [self.repository_path / "sops" / sop_id]
        else:
            sop_root = self.repository_path / "sops"
            self._validate_path(sop_root)
            roots = [
                path
                for path in sorted(sop_root.iterdir())
                if path.is_dir() and path.name != "candidates"
            ] if sop_root.is_dir() else []
        versions = []
        for root in roots:
            self._validate_path(root)
            if not root.is_dir():
                continue
            for directory in sorted(root.iterdir()):
                match = re.fullmatch(r"v([0-9]{4})", directory.name)
                if not directory.is_dir() or match is None:
                    continue
                manifest = directory / "manifest.json"
                if not manifest.is_file():
                    continue
                payload = self._load_json(manifest, "invalid_sop_version")
                approval_id = payload.get("approval_id")
                if not isinstance(approval_id, str):
                    continue
                approval = (
                    self.repository_path
                    / SOP_APPROVAL_ROOT
                    / root.name
                    / directory.name
                    / f"{approval_id}.json"
                )
                if approval.is_file():
                    versions.append(
                        self.load_sop_version(root.name, int(match.group(1)))
                    )
        return tuple(
            sorted(versions, key=lambda item: (item.sop_id, item.version))
        )

    def load_sop_version(
        self,
        sop_id: str,
        version: int,
    ) -> SopVersionSnapshot:
        self._validate_id(sop_id, "sop_id")
        if isinstance(version, bool) or not isinstance(version, int) or version < 1:
            raise WorkspaceError(
                code="invalid_sop_version",
                message="SOP Version number must be positive.",
                next_action="Choose a version listed by SOP Overview.",
            )
        version_name = f"v{version:04d}"
        relative = Path("sops") / sop_id / version_name / "manifest.json"
        payload = self._load_json(
            self.repository_path / relative,
            "invalid_sop_version",
        )
        canonical = dict(payload)
        fingerprint = canonical.pop("version_fingerprint", None)
        if (
            payload.get("asset_type") != "sop_version"
            or payload.get("sop_id") != sop_id
            or payload.get("version") != version
            or payload.get("schema_version") != SOP_SCHEMA_VERSION
            or fingerprint != _fingerprint(canonical)
        ):
            self._invalid_version(sop_id, version)
        approval = self._load_approval(
            sop_id,
            version_name,
            payload.get("approval_id"),
        )
        model = self.get_formal_model(payload.get("formal_model_id"))
        model_manifest = self._load_json(
            self.repository_path / model.asset_path,
            "invalid_formal_model",
        )
        candidate = self.load_candidate(payload.get("candidate_id"))
        gate = self.load_gate(
            payload.get("gate_id"),
            candidate.asset_id,
        )
        if (
            approval.get("decision") != "approve"
            or approval.get("candidate_id") != candidate.asset_id
            or approval.get("candidate_fingerprint")
            != candidate.candidate_fingerprint
            or approval.get("gate_id") != gate.asset_id
            or approval.get("gate_fingerprint") != gate.gate_fingerprint
            or approval.get("sop_version_id") != payload.get("asset_id")
            or approval.get("sop_version_fingerprint") != fingerprint
            or approval.get("formal_model_id") != model.asset_id
            or approval.get("formal_model_manifest_fingerprint")
            != model_manifest.get("manifest_fingerprint")
            or approval.get("model_fingerprint") != model.model_fingerprint
            or payload.get("candidate_fingerprint")
            != candidate.candidate_fingerprint
            or payload.get("gate_fingerprint") != gate.gate_fingerprint
            or gate.outcome != "passed"
            or model.sop_version_id != payload.get("asset_id")
            or model.approval_id != payload.get("approval_id")
            or model.source_instance_id
            != payload.get("source_instance_id")
            or model.reproduction_instance_id
            != payload.get("reproduction_instance_id")
            or model.dataset_id != payload.get("dataset_id")
            or model.dataset_version != payload.get("dataset_version")
        ):
            self._invalid_version(sop_id, version)
        if version > 1:
            previous = self.load_sop_version(sop_id, version - 1)
            if (
                payload.get("previous_version_id") != previous.asset_id
                or payload.get("previous_version_fingerprint")
                != previous.version_fingerprint
            ):
                self._invalid_version(sop_id, version)
        try:
            return SopVersionSnapshot(
                asset_id=payload["asset_id"],
                asset_path=relative.as_posix(),
                sop_id=payload["sop_id"],
                version=payload["version"],
                version_fingerprint=payload["version_fingerprint"],
                previous_version_id=payload["previous_version_id"],
                previous_version_fingerprint=payload[
                    "previous_version_fingerprint"
                ],
                candidate_id=payload["candidate_id"],
                source_run_id=payload["source_run_id"],
                source_instance_id=payload["source_instance_id"],
                reproduction_run_id=payload["reproduction_run_id"],
                reproduction_instance_id=payload[
                    "reproduction_instance_id"
                ],
                dataset_id=payload["dataset_id"],
                dataset_version=payload["dataset_version"],
                primary_metric_name=payload["primary_metric_name"],
                primary_metric_value=float(payload["primary_metric_value"]),
                strategy_summary=payload["strategy_summary"],
                optimization_background=payload[
                    "optimization_background"
                ],
                steps=tuple(payload["steps"]),
                change_summary=payload["change_summary"],
                approval_id=payload["approval_id"],
                formal_model_id=payload["formal_model_id"],
                created_at=payload["created_at"],
                created_by=payload["created_by"],
            )
        except (KeyError, TypeError, ValueError) as error:
            raise WorkspaceError(
                code="invalid_sop_version",
                message=f"SOP Version is invalid: {sop_id} {version_name}.",
                next_action="Restore the complete approved version from Git.",
            ) from error

    def get_formal_model(self, model_id: str) -> FormalModelSnapshot:
        self._validate_id(model_id, "model_id")
        relative = FORMAL_MODEL_ROOT / model_id / "manifest.json"
        payload = self._load_json(
            self.repository_path / relative,
            "invalid_formal_model",
        )
        canonical = dict(payload)
        fingerprint = canonical.pop("manifest_fingerprint", None)
        model_path_value = payload.get("model_path")
        if not isinstance(model_path_value, str):
            self._invalid_model(model_id)
        model_path = self.repository_path / model_path_value
        self._validate_path(model_path)
        if (
            payload.get("asset_type") != "formal_model"
            or payload.get("asset_id") != model_id
            or payload.get("schema_version") != SOP_SCHEMA_VERSION
            or fingerprint != _fingerprint(canonical)
            or model_path.is_symlink()
            or not model_path.is_file()
            or payload.get("model_fingerprint")
            != _sha256(model_path.read_bytes())
        ):
            self._invalid_model(model_id)
        try:
            return FormalModelSnapshot(
                asset_id=payload["asset_id"],
                asset_path=relative.as_posix(),
                model_path=payload["model_path"],
                model_fingerprint=payload["model_fingerprint"],
                sop_version_id=payload["sop_version_id"],
                source_instance_id=payload["source_instance_id"],
                reproduction_instance_id=payload[
                    "reproduction_instance_id"
                ],
                dataset_id=payload["dataset_id"],
                dataset_version=payload["dataset_version"],
                primary_metric_name=payload["primary_metric_name"],
                primary_metric_value=float(payload["primary_metric_value"]),
                strategy_summary=payload["strategy_summary"],
                optimization_background=payload[
                    "optimization_background"
                ],
                approval_id=payload["approval_id"],
                created_at=payload["created_at"],
                created_by=payload["created_by"],
            )
        except (KeyError, TypeError, ValueError) as error:
            raise WorkspaceError(
                code="invalid_formal_model",
                message=f"Formal Model is invalid: {model_id}.",
                next_action="Restore the complete Formal Model from Git.",
            ) from error

    def _validated_review_chain(
        self,
        spec: SopReviewSpec,
    ) -> tuple[
        SopCandidateSnapshot,
        SopReproductionGateSnapshot,
        dict[str, Any],
    ]:
        candidate = self.validate_candidate_source(
            spec.candidate_id,
            spec.expected_candidate_fingerprint,
        )
        gate = self.load_gate_for_candidate(candidate.asset_id)
        if gate is None:
            raise WorkspaceError(
                code="sop_gate_not_passed",
                message="SOP candidate has no independent reproduction gate.",
                next_action="Run independent reproduction before review.",
            )
        if gate.gate_fingerprint != spec.expected_gate_fingerprint:
            raise WorkspaceError(
                code="stale_sop_review",
                message="SOP reproduction gate changed before review.",
                next_action="Reload the candidate and gate before deciding.",
            )
        if (
            gate.candidate_id != candidate.asset_id
            or gate.candidate_fingerprint != candidate.candidate_fingerprint
            or gate.source_run_id != candidate.source_run_id
            or gate.source_instance_id != candidate.source_instance_id
        ):
            raise WorkspaceError(
                code="invalid_sop_reproduction_gate",
                message="SOP reproduction gate does not belong to the candidate.",
                next_action="Restore the candidate and gate from Git.",
            )
        if gate.outcome != "passed":
            return candidate, gate, {}
        gate_payload = self._load_json(
            self.repository_path / gate.asset_path,
            "invalid_sop_reproduction_gate",
        )
        comparisons = gate_payload.get("comparisons")
        if (
            not isinstance(comparisons, dict)
            or not comparisons
            or not all(value is True for value in comparisons.values())
        ):
            self._invalid_gate(gate.asset_id)
        run_repository = RunRepository(self.repository_path)
        source = run_repository.load_instance(
            gate.source_run_id,
            gate.source_instance_id,
        )
        reproduction = run_repository.load_instance(
            gate.reproduction_run_id,
            gate.reproduction_instance_id,
        )
        if (
            source.run_id == reproduction.run_id
            or source.asset_id == reproduction.asset_id
            or reproduction.state != "completed"
            or reproduction.model_retention_reasons
            != ("sop_reproduction",)
        ):
            self._invalid_gate(gate.asset_id)
        reproduction_model = run_repository.load_instance_file(
            reproduction.run_id,
            reproduction.asset_id,
            "model",
        )
        expected_model_path = reproduction_model.relative_to(
            self.repository_path
        ).as_posix()
        if (
            gate_payload.get("source_instance_fingerprint")
            != run_repository.instance_fingerprint(source)
            or gate_payload.get("reproduction_instance_fingerprint")
            != run_repository.instance_fingerprint(reproduction)
            or gate_payload.get("reproduction_model_path")
            != expected_model_path
            or gate_payload.get("reproduction_model_fingerprint")
            != reproduction.model_fingerprint
            or reproduction.model_fingerprint
            != _sha256(reproduction_model.read_bytes())
            or gate.reproduction_metric_value
            != reproduction.primary_metric_value
            or gate.source_metric_value != source.primary_metric_value
            or gate.source_metric_six_decimals
            != gate.reproduction_metric_six_decimals
        ):
            self._invalid_gate(gate.asset_id)
        return candidate, gate, {
            "source": source,
            "reproduction": reproduction,
            "reproduction_model_path": reproduction_model,
            "gate_payload": gate_payload,
        }

    def _find_candidate_review(
        self,
        candidate_id: str,
    ) -> dict[str, Any] | None:
        root = self.repository_path / SOP_APPROVAL_ROOT
        self._validate_path(root)
        if not root.is_dir():
            return None
        matches = []
        for path in root.rglob("*.json"):
            payload = self._load_review_payload(path)
            if payload.get("candidate_id") == candidate_id:
                matches.append(payload)
        if len(matches) > 1:
            raise WorkspaceError(
                code="invalid_sop_review",
                message="SOP candidate has multiple immutable review decisions.",
                next_action="Restore the approved review history from Git.",
            )
        return None if not matches else matches[0]

    def _load_review_payload(self, path: Path) -> dict[str, Any]:
        payload = self._load_json(path, "invalid_sop_review")
        canonical = dict(payload)
        fingerprint = canonical.pop("approval_fingerprint", None)
        if (
            payload.get("asset_type") != "sop_review"
            or payload.get("schema_version") != SOP_SCHEMA_VERSION
            or payload.get("decision") not in {"approve", "reject"}
            or fingerprint != _fingerprint(canonical)
        ):
            raise WorkspaceError(
                code="invalid_sop_review",
                message=f"SOP review record is invalid: {path.name}.",
                next_action="Restore the immutable review record from Git.",
            )
        return payload

    def _review_outcome(self, payload: dict[str, Any]) -> SopReviewOutcome:
        if payload["decision"] == "reject":
            return SopReviewOutcome(
                decision="reject",
                candidate_id=payload["candidate_id"],
                gate_id=payload["gate_id"],
                approval_id=payload["asset_id"],
                sop_version=None,
                formal_model=None,
            )
        match = re.search(r"-v([0-9]{4})$", payload["sop_version_id"])
        if match is None:
            raise WorkspaceError(
                code="invalid_sop_review",
                message="Approved SOP review has an invalid version identity.",
                next_action="Restore the immutable review record from Git.",
            )
        return SopReviewOutcome(
            decision="approve",
            candidate_id=payload["candidate_id"],
            gate_id=payload["gate_id"],
            approval_id=payload["asset_id"],
            sop_version=self.load_sop_version(
                payload["sop_id"],
                int(match.group(1)),
            ),
            formal_model=self.get_formal_model(payload["formal_model_id"]),
        )

    def _next_version(self, sop_id: str) -> int:
        versions = self.list_sop_versions(sop_id)
        return max((item.version for item in versions), default=0) + 1

    def _load_approval(
        self,
        sop_id: str,
        version_name: str,
        approval_id: Any,
    ) -> dict[str, Any]:
        if not isinstance(approval_id, str):
            self._invalid_version(sop_id, int(version_name[1:]))
        path = (
            self.repository_path
            / SOP_APPROVAL_ROOT
            / sop_id
            / version_name
            / f"{approval_id}.json"
        )
        return self._load_review_payload(path)

    def _validate_publication_capacity(
        self,
        encoded: dict[Path, bytes],
        capacity: CapacityStatus,
    ) -> None:
        additions = 0
        for target, raw in encoded.items():
            self._validate_path(target)
            if len(raw) >= capacity.max_file_bytes:
                raise WorkspaceError(
                    code="sop_publication_too_large",
                    message=f"Formal SOP asset reaches the file limit: {target.name}.",
                    next_action="Use an approved artifact storage policy before publication.",
                )
            if target.exists():
                if target.is_symlink() or target.read_bytes() != raw:
                    raise WorkspaceError(
                        code="sop_publication_conflict",
                        message=f"Formal SOP asset path contains different bytes: {target}.",
                        next_action="Restore the immutable version before retrying.",
                    )
            else:
                additions += len(raw)
        used = sum(
            path.stat().st_size
            for path in self.repository_path.rglob("*")
            if path.is_file()
            and ".git" not in path.parts
            and ".mlagent-local" not in path.parts
        )
        if used + additions >= capacity.max_repository_bytes:
            raise WorkspaceError(
                code="repository_capacity_exceeded",
                message="Team Memory has no capacity for the approved SOP assets.",
                next_action="Archive approved large assets before retrying.",
            )

    def _publish_exact_file(self, target: Path, raw: bytes) -> None:
        self._validate_path(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            if target.is_symlink() or target.read_bytes() != raw:
                raise WorkspaceError(
                    code="sop_publication_conflict",
                    message=f"Formal SOP asset differs at {target}.",
                    next_action="Restore the immutable version before retrying.",
                )
            return
        temporary = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
        try:
            temporary.write_bytes(raw)
            os.replace(temporary, target)
        except OSError as error:
            temporary.unlink(missing_ok=True)
            raise WorkspaceError(
                code="sop_publication_failed",
                message="Approved SOP assets could not be published atomically.",
                next_action="Check Team Memory permissions and retry the same review.",
            ) from error

    def _collect_source(self, spec: SopCandidateSpec) -> dict[str, Any]:
        raw_manifest = self._preflight_instance(spec)
        run_repository = RunRepository(self.repository_path)
        instance = self._source_role(
            "training_instance",
            lambda: run_repository.load_instance(
                spec.source_run_id,
                spec.source_instance_id,
            ),
        )
        if instance.state != "completed" or not instance.sop_source_eligible:
            self._source_incomplete(
                ("training_instance",),
                "the selected Training Instance is not successful",
            )
        run_start = self._source_role(
            "run",
            lambda: run_repository.load_run_start(spec.source_run_id),
        )
        instance_input = self._source_role(
            "input",
            lambda: run_repository.load_instance_input(
                spec.source_run_id,
                spec.source_instance_id,
            ),
        )
        environment = self._source_role(
            "environment",
            lambda: run_repository.load_instance_environment(
                spec.source_run_id,
                spec.source_instance_id,
            ),
        )
        paths = {
            role: self._source_role(
                evidence_role,
                lambda role=role: run_repository.load_instance_file(
                    spec.source_run_id,
                    spec.source_instance_id,
                    role,
                ),
            )
            for role, evidence_role in INSTANCE_FILE_ROLES.items()
        }
        code_revision = self._source_role(
            "code_revision",
            lambda: run_repository.load_code_revision_for_instance(
                spec.source_run_id,
                spec.source_instance_id,
            ),
        )
        try:
            dataset_id = instance_input["dataset_id"]
            dataset_version = instance_input["dataset_version"]
        except (KeyError, TypeError) as error:
            raise self._source_incomplete_error(
                ("dataset",),
                "dataset identity is missing from the frozen input",
            ) from error
        dataset = self._source_role(
            "dataset",
            lambda: DatasetRepository(self.repository_path).load(
                dataset_id,
                dataset_version,
            ),
        )
        metrics = self._source_role(
            "metrics",
            lambda: self._load_json(paths["metrics"], "sop_source_incomplete"),
        )
        self._validate_source_coherence(
            instance=instance,
            run_start=run_start,
            instance_input=instance_input,
            environment=environment,
            paths=paths,
            code_revision=code_revision,
            dataset=dataset,
            metrics=metrics,
        )
        run_path = (
            Path("raw-records/runs")
            / spec.source_run_id
            / f"{run_start['asset_id']}.json"
        )
        instance_path = Path(
            "runs",
            spec.source_run_id,
            "instances",
            spec.source_instance_id,
            "manifest.json",
        )
        code_path = Path(code_revision.asset_path)
        evidence = (
            self._evidence("dataset", dataset.asset_id, Path(dataset.asset_path)),
            self._evidence("run", run_start["asset_id"], run_path),
            self._evidence(
                "training_instance",
                instance.asset_id,
                instance_path,
            ),
            self._evidence("input", f"{instance.asset_id}-input", paths["input"]),
            self._evidence(
                "environment",
                f"{instance.asset_id}-environment",
                paths["environment"],
            ),
            self._evidence("split", f"{instance.asset_id}-split", paths["split"]),
            self._evidence(
                "code_revision",
                code_revision.asset_id,
                code_path,
            ),
            self._evidence(
                "metrics",
                f"{instance.asset_id}-metrics",
                paths["metrics"],
            ),
            self._evidence(
                "predictions",
                f"{instance.asset_id}-predictions",
                paths["predictions"],
            ),
            self._evidence(
                "source_model",
                f"{instance.asset_id}-model",
                paths["model"],
            ),
        )
        return {
            "instance": instance,
            "run_start": run_start,
            "dataset": dataset,
            "code_revision": code_revision,
            "source_instance_fingerprint": raw_manifest[
                "manifest_fingerprint"
            ],
            "evidence": evidence,
        }

    def _preflight_instance(self, spec: SopCandidateSpec) -> dict[str, Any]:
        manifest_path = self.repository_path / Path(
            "runs",
            spec.source_run_id,
            "instances",
            spec.source_instance_id,
            "manifest.json",
        )
        self._validate_path(manifest_path)
        if not manifest_path.is_file():
            raise WorkspaceError(
                code="training_instance_not_found",
                message=(
                    "Training Instance does not exist: "
                    f"{spec.source_run_id}/{spec.source_instance_id}."
                ),
                next_action="Choose one successful Training Instance listed by Run Status.",
            )
        payload = self._load_json(manifest_path, "sop_source_incomplete")
        if payload.get("state") != "completed":
            self._source_incomplete(
                ("training_instance",),
                "the selected Training Instance is not successful",
            )
        files = payload.get("files")
        fingerprints = payload.get("file_fingerprints")
        if not isinstance(files, dict) or not isinstance(fingerprints, dict):
            self._source_incomplete(
                ("training_instance",),
                "the instance file declarations are missing",
            )
        missing: list[str] = []
        changed: list[str] = []
        for file_role, evidence_role in INSTANCE_FILE_ROLES.items():
            filename = files.get(file_role)
            if not isinstance(filename, str):
                missing.append(evidence_role)
                continue
            relative = Path(filename)
            if relative.is_absolute() or ".." in relative.parts:
                changed.append(evidence_role)
                continue
            path = manifest_path.parent / relative
            self._validate_path(path)
            if path.is_symlink() or not path.is_file():
                missing.append(evidence_role)
            elif fingerprints.get(file_role) != _sha256(path.read_bytes()):
                changed.append(evidence_role)
        if missing or changed:
            detail = "missing or changed source evidence"
            self._source_incomplete(tuple(sorted(set(missing + changed))), detail)
        return payload

    def _validate_source_coherence(
        self,
        *,
        instance,
        run_start: dict[str, Any],
        instance_input: dict[str, Any],
        environment: dict[str, Any],
        paths: dict[str, Path],
        code_revision,
        dataset,
        metrics: dict[str, Any],
    ) -> None:
        mismatches = []

        def require(label: str, condition: bool) -> None:
            if not condition:
                mismatches.append(label)

        require("Run identity", instance_input.get("run_id") == instance.run_id)
        require(
            "Training Instance identity",
            instance_input.get("instance_id") == instance.asset_id,
        )
        require(
            "Dataset identity",
            instance_input.get("dataset_id") == dataset.dataset_id
            and run_start.get("dataset_id") == dataset.dataset_id
            and instance_input.get("dataset_version") == dataset.version
            and run_start.get("dataset_version") == dataset.version,
        )
        require(
            "Dataset content fingerprint",
            instance.dataset_content_fingerprint == dataset.content_fingerprint
            == instance_input.get("dataset_content_fingerprint")
            == run_start.get("dataset_content_fingerprint"),
        )
        require(
            "Dataset Version fingerprint",
            instance.dataset_version_fingerprint == dataset.version_fingerprint
            == instance_input.get("dataset_version_fingerprint")
            == run_start.get("dataset_version_fingerprint"),
        )
        require(
            "Dataset asset path",
            instance_input.get("dataset_asset_path") == dataset.asset_path,
        )
        require(
            "code revision",
            instance.code_fingerprint == code_revision.code_fingerprint
            == instance_input.get("code_fingerprint")
            == run_start.get("code_fingerprint")
            and instance_input.get("code_revision_path")
            == code_revision.asset_path,
        )
        require(
            "configuration fingerprint",
            instance.configuration_fingerprint
            == instance_input.get("configuration_fingerprint")
            == _fingerprint(instance_input.get("configuration")),
        )
        require(
            "environment fingerprint",
            instance.environment_fingerprint
            == instance_input.get("environment_fingerprint")
            == _fingerprint(environment),
        )
        dataset_split_path = (
            self.repository_path
            / Path(dataset.asset_path).parent
            / dataset.files["split"]
        )
        self._validate_path(dataset_split_path)
        require(
            "split fingerprint",
            instance.split_fingerprint
            == instance_input.get("split_fingerprint")
            == _sha256(dataset_split_path.read_bytes())
            == _sha256(paths["split"].read_bytes()),
        )
        require(
            "random seed",
            instance.random_seed == instance_input.get("random_seed"),
        )
        require(
            "plan fingerprint",
            instance.plan_fingerprint == instance_input.get("plan_fingerprint")
            == run_start.get("plan_fingerprint"),
        )
        require(
            "approval fingerprint",
            instance.approval_fingerprint
            == instance_input.get("approval_fingerprint")
            == run_start.get("approval_fingerprint"),
        )
        metric_value = metrics.get(instance.primary_metric_name)
        require(
            "primary metric",
            instance.primary_metric_name
            == instance_input.get("primary_metric_name")
            == run_start.get("primary_metric_name")
            == dataset.primary_metric
            and isinstance(metric_value, (int, float))
            and not isinstance(metric_value, bool)
            and float(metric_value) == float(instance.primary_metric_value),
        )
        require(
            "predictions fingerprint",
            instance.predictions_fingerprint
            == _sha256(paths["predictions"].read_bytes()),
        )
        require(
            "source model fingerprint",
            instance.model_fingerprint == _sha256(paths["model"].read_bytes()),
        )
        if mismatches:
            raise WorkspaceError(
                code="sop_source_mismatch",
                message=(
                    "SOP source evidence is not coherent: "
                    + ", ".join(mismatches)
                    + "."
                ),
                next_action="Restore the exact governed source evidence before creating a candidate.",
            )

    def _find_equivalent_candidate(
        self,
        spec: SopCandidateSpec,
    ) -> SopCandidateSnapshot | None:
        for candidate in self.list_candidates():
            if self._matches_spec(candidate, spec):
                return candidate
        return None

    @staticmethod
    def _matches_spec(
        candidate: SopCandidateSnapshot,
        spec: SopCandidateSpec,
    ) -> bool:
        return (
            candidate.sop_id == spec.sop_id
            and candidate.name == spec.name
            and candidate.source_run_id == spec.source_run_id
            and candidate.source_instance_id == spec.source_instance_id
            and candidate.strategy_summary == spec.strategy_summary
            and candidate.optimization_background == spec.optimization_background
            and candidate.steps == spec.steps
            and candidate.change_summary == spec.change_summary
        )

    def _evidence(
        self,
        role: str,
        asset_id: str,
        path: Path,
    ) -> SopEvidenceReference:
        absolute = path if path.is_absolute() else self.repository_path / path
        self._validate_path(absolute)
        if absolute.is_symlink() or not absolute.is_file():
            self._source_incomplete((role,), "evidence file is unavailable")
        return SopEvidenceReference(
            role=role,
            asset_id=asset_id,
            asset_path=absolute.relative_to(self.repository_path).as_posix(),
            sha256=_sha256(absolute.read_bytes()),
        )

    def _source_role(self, role: str, loader: Callable[[], Any]) -> Any:
        try:
            return loader()
        except WorkspaceError as error:
            raise self._source_incomplete_error((role,), error.message) from error
        except (OSError, KeyError, TypeError, ValueError) as error:
            raise self._source_incomplete_error(
                (role,),
                "evidence could not be validated",
            ) from error

    def _source_incomplete(self, roles: tuple[str, ...], detail: str) -> None:
        raise self._source_incomplete_error(roles, detail)

    @staticmethod
    def _source_incomplete_error(
        roles: tuple[str, ...],
        detail: str,
    ) -> WorkspaceError:
        return WorkspaceError(
            code="sop_source_incomplete",
            message=(
                "SOP source is incomplete for "
                + ", ".join(roles)
                + f": {detail}."
            ),
            next_action="Choose or restore one successful, fully retained Training Instance.",
        )

    def _write_candidate(
        self,
        target: Path,
        raw: bytes,
        capacity: CapacityStatus,
    ) -> None:
        self._validate_path(target)
        self._validate_capacity(target, raw, capacity)
        target.parent.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.parent.with_name(
            f".{target.parent.name}.{uuid.uuid4().hex}.tmp"
        )
        try:
            temporary.mkdir()
            (temporary / "manifest.json").write_bytes(raw)
            temporary.rename(target.parent)
        except OSError as error:
            shutil.rmtree(temporary, ignore_errors=True)
            raise WorkspaceError(
                code="sop_candidate_write_failed",
                message="SOP candidate could not be written atomically.",
                next_action="Check Team Memory permissions and retry candidate creation.",
            ) from error

    def _write_new_file(
        self,
        target: Path,
        raw: bytes,
        capacity: CapacityStatus,
    ) -> None:
        self._validate_path(target)
        self._validate_capacity(target, raw, capacity)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            raise WorkspaceError(
                code="sop_asset_exists",
                message=f"SOP asset already exists: {target.name}.",
                next_action="Load the existing immutable asset.",
            )
        temporary = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
        try:
            temporary.write_bytes(raw)
            os.replace(temporary, target)
        except OSError as error:
            temporary.unlink(missing_ok=True)
            raise WorkspaceError(
                code="sop_asset_write_failed",
                message="SOP asset could not be written atomically.",
                next_action="Check Team Memory permissions and retry.",
            ) from error

    def _validate_capacity(
        self,
        target: Path,
        raw: bytes,
        capacity: CapacityStatus,
    ) -> None:
        if len(raw) >= capacity.max_file_bytes:
            raise WorkspaceError(
                code="sop_candidate_too_large",
                message=f"SOP candidate exceeds the file limit: {target.name}.",
                next_action="Reduce the bounded SOP method text before retrying.",
            )
        used = sum(
            path.stat().st_size
            for path in self.repository_path.rglob("*")
            if path.is_file()
            and ".git" not in path.parts
            and ".mlagent-local" not in path.parts
        )
        if used + len(raw) >= capacity.max_repository_bytes:
            raise WorkspaceError(
                code="repository_capacity_exceeded",
                message="Team Memory has no capacity for the SOP candidate.",
                next_action="Archive approved large assets before retrying.",
            )

    def _load_json(self, path: Path, code: str) -> dict[str, Any]:
        self._validate_path(path)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise WorkspaceError(
                code=code,
                message=f"Governed SOP evidence cannot be read: {path.name}.",
                next_action="Restore the exact evidence from Git.",
            ) from error
        if not isinstance(payload, dict):
            raise WorkspaceError(
                code=code,
                message=f"Governed SOP evidence is not an object: {path.name}.",
                next_action="Restore the exact evidence from Git.",
            )
        return payload

    def _validate_path(self, path: Path) -> None:
        try:
            relative = path.relative_to(self.repository_path)
        except ValueError:
            self._unsafe_path()
            return
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
    def _validate_actor(actor_id: str) -> None:
        if not isinstance(actor_id, str) or not actor_id.strip():
            raise WorkspaceError(
                code="missing_actor",
                message="SOP actions require a team member identity.",
                next_action="Reconnect Team Memory with a non-empty actor.",
            )

    @staticmethod
    def _validate_id(value: str, label: str) -> None:
        if not isinstance(value, str) or SAFE_ID_PATTERN.fullmatch(value) is None:
            raise WorkspaceError(
                code="invalid_sop_id",
                message=f"{label} is invalid.",
                next_action="Use letters, digits, dots, underscores, or hyphens.",
            )

    def _new_candidate_id(self) -> str:
        value = self.candidate_id_factory()
        self._validate_id(value, "candidate_id")
        return value

    def _new_gate_id(self) -> str:
        value = self.gate_id_factory()
        self._validate_id(value, "gate_id")
        return value

    def _new_approval_id(self) -> str:
        value = self.approval_id_factory()
        self._validate_id(value, "approval_id")
        return value

    def _timestamp(self) -> str:
        value = self.clock()
        if not isinstance(value, str) or not value.strip():
            raise WorkspaceError(
                code="invalid_sop_clock",
                message="SOP timestamp source returned an invalid value.",
                next_action="Retry with a valid UTC clock.",
            )
        return value

    @contextmanager
    def _lock(self) -> Iterator[None]:
        path = self.repository_path / ".mlagent-local/sop.lock"
        self._validate_path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a+", encoding="utf-8") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    @staticmethod
    def _invalid_candidate(candidate_id: str) -> None:
        raise WorkspaceError(
            code="invalid_sop_candidate",
            message=f"SOP candidate is invalid: {candidate_id}.",
            next_action="Restore the immutable candidate from Git.",
        )

    @staticmethod
    def _invalid_gate(gate_id: str) -> None:
        raise WorkspaceError(
            code="invalid_sop_reproduction_gate",
            message=f"SOP reproduction gate is invalid: {gate_id}.",
            next_action="Restore the immutable gate from Git.",
        )

    @staticmethod
    def _invalid_version(sop_id: str, version: int) -> None:
        raise WorkspaceError(
            code="invalid_sop_version",
            message=f"SOP Version is invalid: {sop_id} v{version:04d}.",
            next_action="Restore the complete approved SOP Version from Git.",
        )

    @staticmethod
    def _invalid_model(model_id: str) -> None:
        raise WorkspaceError(
            code="invalid_formal_model",
            message=f"Formal Model is invalid: {model_id}.",
            next_action="Restore the complete approved Formal Model from Git.",
        )

    @staticmethod
    def _unsafe_path() -> None:
        raise WorkspaceError(
            code="unsafe_sop_path",
            message="SOP evidence is symbolic or outside Team Memory.",
            next_action="Use real files under the managed Team Memory paths.",
        )


def _json_bytes(payload: Any) -> bytes:
    return (
        json.dumps(
            payload,
            indent=2,
            sort_keys=True,
            ensure_ascii=True,
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


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _utc_now() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
