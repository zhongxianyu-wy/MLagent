from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any

from src.domain.dataset_repository import DatasetRepository
from src.domain.models import (
    CapacityStatus,
    ExperienceCitation,
    SopCandidateSnapshot,
    SopReproductionGateSnapshot,
    TrainingExecutionResult,
    WorkspaceError,
)
from src.domain.run_repository import (
    InstancePreparationSpec,
    RunRepository,
    RunStartSpec,
)
from src.domain.sop_repository import (
    SopRepository,
    SopReproductionGateSpec,
)


SIX_PLACES = Decimal("0.000001")


def metric_at_six_places(value: float) -> str:
    return format(
        Decimal(str(value)).quantize(SIX_PLACES, rounding=ROUND_HALF_UP),
        ".6f",
    )


def compare_reproduction_metric(source: float, reproduced: float) -> str:
    return (
        "passed"
        if metric_at_six_places(source) == metric_at_six_places(reproduced)
        else "metric_mismatch"
    )


class SopPromotionCoordinator:
    def __init__(
        self,
        *,
        sop_repository: SopRepository,
        run_repository: RunRepository,
        executor: Any,
        capacity: CapacityStatus,
        actor_id: str,
        reproduction_run_id_factory: Callable[[], str] | None = None,
        clock: Callable[[], str] | None = None,
    ) -> None:
        self.sop_repository = sop_repository
        self.run_repository = run_repository
        self.executor = executor
        self.capacity = capacity
        self.actor_id = actor_id
        self.reproduction_run_id_factory = reproduction_run_id_factory or (
            lambda: f"sop-reproduction-{uuid.uuid4()}"
        )
        self.clock = clock or _utc_now

    def reproduce(
        self,
        candidate: SopCandidateSnapshot,
    ) -> SopReproductionGateSnapshot:
        current = self.sop_repository.validate_candidate_source(
            candidate.asset_id,
            candidate.candidate_fingerprint,
        )
        if current != candidate:
            raise WorkspaceError(
                code="stale_sop_candidate",
                message="SOP candidate changed before independent reproduction.",
                next_action="Reload and review the current candidate.",
            )
        existing = self.sop_repository.load_gate_for_candidate(
            candidate.asset_id
        )
        if existing is not None:
            if existing.candidate_fingerprint != candidate.candidate_fingerprint:
                raise WorkspaceError(
                    code="sop_gate_exists",
                    message="A gate exists for a different candidate fingerprint.",
                    next_action="Restore the candidate history or create a new candidate.",
                )
            return existing

        source = self.run_repository.load_instance(
            candidate.source_run_id,
            candidate.source_instance_id,
        )
        source_start = self.run_repository.load_run_start(
            candidate.source_run_id
        )
        source_input = self.run_repository.load_instance_input(
            candidate.source_run_id,
            candidate.source_instance_id,
        )
        source_environment = self.run_repository.load_instance_environment(
            candidate.source_run_id,
            candidate.source_instance_id,
        )
        source_split = self.run_repository.load_instance_file(
            candidate.source_run_id,
            candidate.source_instance_id,
            "split",
        )
        source_code = self.run_repository.load_code_revision_for_instance(
            candidate.source_run_id,
            candidate.source_instance_id,
        )
        dataset = DatasetRepository(self.run_repository.repository_path).load(
            candidate.dataset_id,
            candidate.dataset_version,
        )
        reproduction_run_id = self.reproduction_run_id_factory()
        if reproduction_run_id == candidate.source_run_id:
            raise WorkspaceError(
                code="invalid_sop_reproduction",
                message="Independent reproduction requires a distinct Run ID.",
                next_action="Retry with a new reproduction Run identity.",
            )
        self.run_repository.start_run(
            RunStartSpec(
                run_id=reproduction_run_id,
                dataset_id=dataset.dataset_id,
                dataset_version=dataset.version,
                dataset_content_fingerprint=dataset.content_fingerprint,
                dataset_version_fingerprint=dataset.version_fingerprint,
                plan_id=source_start["plan_id"],
                plan_event_id=source_start["plan_event_id"],
                planning_session_id=source_start["planning_session_id"],
                plan_fingerprint=source_start["plan_fingerprint"],
                approval_id=source_start["approval_id"],
                approval_fingerprint=source_start["approval_fingerprint"],
                code_fingerprint=source_start["code_fingerprint"],
                user_direction=source_start["user_direction"],
                stop_conditions=tuple(source_start["stop_conditions"]),
                primary_metric_name=source_start["primary_metric_name"],
                target_metric_value=float(source_start["target_metric_value"]),
                expected_round_count=1,
                human_marked_rounds=(),
                experience_citations=tuple(
                    ExperienceCitation(**item)
                    for item in source_start.get("experience_citations", [])
                ),
            ),
            actor_id=self.actor_id,
            capacity=self.capacity,
        )
        try:
            code_root = (
                self.run_repository.repository_path
                / Path(source_code.asset_path).parent
                / "files"
            )
            reproduction_code = self.run_repository.freeze_code_revision(
                run_id=reproduction_run_id,
                code_root=code_root,
                candidate_code_files=source_code.files,
                code_fingerprint=source_code.code_fingerprint,
                entrypoint_path=source_code.entrypoint_path,
                actor_id=self.actor_id,
                capacity=self.capacity,
            )
            prepared = self.run_repository.prepare_instance(
                InstancePreparationSpec(
                    run_id=reproduction_run_id,
                    round_number=source_input["round_number"],
                    hypothesis=source_input["hypothesis"],
                    optimization_direction=source_input[
                        "optimization_direction"
                    ],
                    intended_changes=tuple(source_input["intended_changes"]),
                    random_seed=source_input["random_seed"],
                    parent_instance_id=None,
                    parent_instance_fingerprint=None,
                    configuration=dict(source_input["configuration"]),
                    environment=dict(source_environment),
                ),
                code_revision=reproduction_code,
                split_path=source_split,
                actor_id=self.actor_id,
                capacity=self.capacity,
            )
            result = self._execute(prepared, source.primary_metric_name)
            reproduction = self.run_repository.seal_instance(
                prepared,
                result,
                retention_reasons=(
                    ("sop_reproduction",)
                    if result.state == "completed"
                    else ()
                ),
                actor_id=self.actor_id,
                capacity=self.capacity,
            )
            self.run_repository.finish_run(
                reproduction_run_id,
                state=reproduction.state,
                reason=(
                    "sop_reproduction_completed"
                    if reproduction.state == "completed"
                    else reproduction.error_code or "sop_reproduction_failed"
                ),
                actor_id=self.actor_id,
                capacity=self.capacity,
            )
        except WorkspaceError as error:
            self._finish_failed_run(reproduction_run_id, error.code)
            raise
        except Exception as error:
            self._finish_failed_run(reproduction_run_id, "coordinator_failed")
            raise WorkspaceError(
                code="sop_reproduction_failed",
                message=(
                    "Independent SOP reproduction could not be completed: "
                    f"{type(error).__name__}."
                ),
                next_action="Inspect the reproduction Run and create a new candidate before retrying.",
            ) from error

        comparisons = {
            "approval_fingerprint": (
                reproduction.approval_fingerprint
                == source.approval_fingerprint
            ),
            "code_fingerprint": (
                reproduction.code_fingerprint == source.code_fingerprint
            ),
            "configuration_fingerprint": (
                reproduction.configuration_fingerprint
                == source.configuration_fingerprint
            ),
            "dataset_content_fingerprint": (
                reproduction.dataset_content_fingerprint
                == source.dataset_content_fingerprint
            ),
            "dataset_version_fingerprint": (
                reproduction.dataset_version_fingerprint
                == source.dataset_version_fingerprint
            ),
            "environment_fingerprint": (
                reproduction.environment_fingerprint
                == source.environment_fingerprint
            ),
            "plan_fingerprint": (
                reproduction.plan_fingerprint == source.plan_fingerprint
            ),
            "random_seed": reproduction.random_seed == source.random_seed,
            "split_fingerprint": (
                reproduction.split_fingerprint == source.split_fingerprint
            ),
        }
        if reproduction.state != "completed":
            outcome = "execution_failed"
        elif not all(comparisons.values()):
            outcome = "evidence_mismatch"
        else:
            outcome = compare_reproduction_metric(
                source.primary_metric_value,
                reproduction.primary_metric_value,
            )
        reproduction_model_path = (
            None
            if reproduction.model_path is None
            else (
                Path(reproduction.asset_path).parent / reproduction.model_path
            ).as_posix()
        )
        return self.sop_repository.record_reproduction_gate(
            SopReproductionGateSpec(
                candidate_id=candidate.asset_id,
                candidate_fingerprint=candidate.candidate_fingerprint,
                outcome=outcome,
                source_run_id=source.run_id,
                source_instance_id=source.asset_id,
                source_instance_fingerprint=(
                    self.run_repository.instance_fingerprint(source)
                ),
                reproduction_run_id=reproduction.run_id,
                reproduction_instance_id=reproduction.asset_id,
                reproduction_instance_fingerprint=(
                    self.run_repository.instance_fingerprint(reproduction)
                ),
                source_metric_value=source.primary_metric_value,
                reproduction_metric_value=reproduction.primary_metric_value,
                source_metric_six_decimals=metric_at_six_places(
                    source.primary_metric_value
                ),
                reproduction_metric_six_decimals=(
                    None
                    if reproduction.primary_metric_value is None
                    else metric_at_six_places(
                        reproduction.primary_metric_value
                    )
                ),
                reproduction_model_path=reproduction_model_path,
                reproduction_model_fingerprint=reproduction.model_fingerprint,
                comparisons=comparisons,
            ),
            actor_id=self.actor_id,
            capacity=self.capacity,
        )

    def _execute(self, prepared, primary_metric: str) -> TrainingExecutionResult:
        timeout_seconds = _timeout_seconds(prepared)
        try:
            return self.executor.execute(
                prepared,
                stop_requested=lambda: False,
                timeout_seconds=timeout_seconds,
            )
        except Exception as error:
            now = self.clock()
            return TrainingExecutionResult(
                state="failed",
                primary_metric_name=primary_metric,
                primary_metric_value=None,
                metrics={},
                predictions_path=None,
                model_path=None,
                model_fingerprint=None,
                error_code="reproduction_executor_failed",
                error_summary=(
                    "Independent reproduction executor failed: "
                    f"{type(error).__name__}."
                ),
                started_at=now,
                ended_at=now,
                duration_ms=0,
            )

    def _finish_failed_run(self, run_id: str, reason: str) -> None:
        try:
            status = self.run_repository.status(run_id)
            if status.state not in {"completed", "failed", "timed_out", "stopped"}:
                self.run_repository.finish_run(
                    run_id,
                    state="failed",
                    reason=reason,
                    actor_id=self.actor_id,
                    capacity=self.capacity,
                )
        except WorkspaceError:
            pass


def _timeout_seconds(prepared) -> float:
    try:
        import json

        payload = json.loads(prepared.input_path.read_text(encoding="utf-8"))
        raw = payload["configuration"].get("timeout_seconds", 1800)
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as error:
        raise WorkspaceError(
            code="invalid_sop_reproduction",
            message="Frozen reproduction timeout cannot be read.",
            next_action="Restore the source Training Instance input.",
        ) from error
    if isinstance(raw, bool) or not isinstance(raw, (int, float)) or raw <= 0:
        raise WorkspaceError(
            code="invalid_sop_reproduction",
            message="Frozen reproduction timeout must be positive.",
            next_action="Create a new governed source instance with a valid timeout.",
        )
    return float(raw)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
