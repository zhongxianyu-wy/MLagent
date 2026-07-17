import hashlib
import json
import os
import subprocess
from pathlib import Path

import pytest

from src.domain.local_index import LocalIndex
from src.domain.memory_repository import MemoryRepository
from src.domain.models import (
    CandidateCodeFile,
    CapacityStatus,
    ExperienceCitation,
    TrainingExecutionResult,
    WorkspaceError,
)
from src.domain.run_repository import (
    ALLOWED_EVENT_FIELDS,
    InstancePreparationSpec,
    RunRepository,
    RunStartSpec,
)


@pytest.fixture
def run_workspace(tmp_path):
    memory_root = tmp_path / "team-memory"
    workspace = MemoryRepository(
        id_factory=lambda: "tmr-1",
        clock=lambda: "2026-07-16T00:00:00Z",
    ).bootstrap(memory_root, actor_id="alice")
    event_ids = iter(f"run-event-{index}" for index in range(1, 30))
    instance_ids = iter(f"instance-{index}" for index in range(1, 10))
    timestamps = iter(
        f"2026-07-16T00:00:{index:02d}Z" for index in range(1, 50)
    )
    repository = RunRepository(
        memory_root,
        event_id_factory=lambda: next(event_ids),
        instance_id_factory=lambda: next(instance_ids),
        clock=lambda: next(timestamps),
    )
    code_root = tmp_path / "code"
    code_root.mkdir()
    code_bytes = b"def build_estimator(context):\n    return context\n"
    (code_root / "train.py").write_bytes(code_bytes)
    split_path = tmp_path / "split.csv"
    split_path.write_text(
        "sample_id,partition\ns1,train\ns2,train\n",
        encoding="utf-8",
    )
    return RunWorkspace(
        repository=repository,
        memory_root=memory_root,
        code_root=code_root,
        split_path=split_path,
        capacity=workspace.capacity,
        code_sha=hashlib.sha256(code_bytes).hexdigest(),
    )


class RunWorkspace:
    def __init__(
        self,
        repository,
        memory_root,
        code_root,
        split_path,
        capacity,
        code_sha,
    ):
        self.repository = repository
        self.memory_root = memory_root
        self.code_root = code_root
        self.split_path = split_path
        self.capacity = capacity
        self.code_sha = code_sha

    def start(self, run_id="run-1", experience_citations=()):
        return self.repository.start_run(
            RunStartSpec(
                run_id=run_id,
                dataset_id="ds-1",
                dataset_version=1,
                dataset_content_fingerprint="dataset-content-sha",
                dataset_version_fingerprint="dataset-version-sha",
                plan_id="plan-1",
                plan_event_id="plan-event-1",
                planning_session_id="session-1",
                plan_fingerprint="plan-sha",
                approval_id="approval-1",
                approval_fingerprint="approval-sha",
                code_fingerprint="code-sha",
                user_direction="Improve validation AUC",
                stop_conditions=("target reached", "round budget exhausted"),
                primary_metric_name="roc_auc",
                target_metric_value=0.91,
                expected_round_count=2,
                experience_citations=experience_citations,
            ),
            actor_id="alice",
            capacity=self.capacity,
        )

    def freeze_code(self, run_id="run-1"):
        return self.repository.freeze_code_revision(
            run_id=run_id,
            code_root=self.code_root,
            candidate_code_files=(
                CandidateCodeFile("train.py", self.code_sha, 49),
            ),
            code_fingerprint="code-sha",
            entrypoint_path="train.py",
            actor_id="alice",
            capacity=self.capacity,
        )

    def prepare(
        self,
        run_id="run-1",
        round_number=1,
        parent=None,
        parent_fingerprint=None,
    ):
        code = self.freeze_code(run_id)
        return self.repository.prepare_instance(
            InstancePreparationSpec(
                run_id=run_id,
                round_number=round_number,
                hypothesis=f"Round {round_number} hypothesis",
                optimization_direction=(
                    "baseline" if round_number == 1 else "feature_selection"
                ),
                intended_changes=("fit reviewed estimator",),
                random_seed=42,
                parent_instance_id=parent,
                parent_instance_fingerprint=parent_fingerprint,
                configuration={"worker_contract": 1, "round": round_number},
                environment={"python": "3.13", "sklearn": "1.7"},
            ),
            code_revision=code,
            split_path=self.split_path,
            actor_id="alice",
            capacity=self.capacity,
        )

    def completed_result(self, prepared, metric=0.82, model_size=16):
        output_root = prepared.worker_output_path
        output_root.mkdir(parents=True, exist_ok=True)
        predictions = output_root / "predictions.csv"
        predictions.write_text(
            "sample_id,observed,predicted,probability_case\n"
            "s1,case,case,0.9\n",
            encoding="utf-8",
        )
        model = output_root / "model.joblib"
        model.write_bytes(b"m" * model_size)
        metrics = output_root / "metrics.json"
        metrics.write_text(
            json.dumps({"roc_auc": metric, "accuracy": 0.8}),
            encoding="utf-8",
        )
        return TrainingExecutionResult(
            state="completed",
            primary_metric_name="roc_auc",
            primary_metric_value=metric,
            metrics={"roc_auc": metric, "accuracy": 0.8},
            predictions_path=predictions,
            model_path=model,
            model_fingerprint=hashlib.sha256(model.read_bytes()).hexdigest(),
            error_code=None,
            error_summary=None,
            started_at="2026-07-16T00:00:10Z",
            ended_at="2026-07-16T00:00:12Z",
            duration_ms=2000,
        )


def test_run_events_are_append_only_causal_and_minimal(run_workspace):
    started = run_workspace.start()
    stopped = run_workspace.repository.request_stop(
        "run-1",
        reason="user_stop",
        actor_id="alice",
        capacity=run_workspace.capacity,
    )

    events = run_workspace.repository.list_events("run-1")

    assert events == (started, stopped)
    assert stopped.previous_event_id == started.asset_id
    payload = json.loads(
        (run_workspace.memory_root / stopped.asset_path).read_text(encoding="utf-8")
    )
    assert set(payload) <= ALLOWED_EVENT_FIELDS
    assert set(payload).isdisjoint(
        {"prompt", "conversation", "stdout", "stderr", "stack_trace"}
    )


def test_code_revision_freezes_exact_approved_files(run_workspace):
    run_workspace.start()
    revision = run_workspace.freeze_code()
    frozen = run_workspace.memory_root / revision.asset_path

    assert revision.code_fingerprint == "code-sha"
    assert revision.entrypoint_path == "train.py"
    assert (frozen.parent / "files" / "train.py").read_bytes() == (
        run_workspace.code_root / "train.py"
    ).read_bytes()

    (run_workspace.code_root / "train.py").write_text(
        "raise RuntimeError('changed')\n",
        encoding="utf-8",
    )
    assert "build_estimator" in (
        frozen.parent / "files" / "train.py"
    ).read_text(encoding="utf-8")


def test_completed_instance_seals_once_and_reloads_with_all_evidence(
    run_workspace,
):
    run_workspace.start()
    prepared = run_workspace.prepare()
    result = run_workspace.completed_result(prepared)

    sealed = run_workspace.repository.seal_instance(
        prepared,
        result,
        retention_reasons=("baseline",),
        actor_id="alice",
        capacity=run_workspace.capacity,
    )

    assert sealed.state == "completed"
    assert sealed.sop_source_eligible is True
    assert sealed.dataset_content_fingerprint == "dataset-content-sha"
    assert sealed.plan_fingerprint == "plan-sha"
    assert sealed.approval_fingerprint == "approval-sha"
    assert sealed.model_retention_reasons == ("baseline",)
    assert sealed.model_path is not None
    assert run_workspace.repository.load_instance("run-1", sealed.asset_id) == sealed
    assert not prepared.pending_path.exists()

    with pytest.raises(WorkspaceError) as caught:
        run_workspace.repository.seal_instance(
            prepared,
            result,
            retention_reasons=("baseline",),
            actor_id="alice",
            capacity=run_workspace.capacity,
        )
    assert caught.value.code == "training_instance_exists"


def test_run_and_instance_freeze_included_experience_usage(run_workspace):
    citations = (
        ExperienceCitation(
            "experience-trusted",
            "experience-event-trusted",
            "trusted",
            "Same Dataset and metric.",
        ),
        ExperienceCitation(
            "experience-pending",
            "experience-event-pending",
            "pending",
            "Matching optimization direction.",
        ),
    )
    run_workspace.start(experience_citations=citations)
    start = run_workspace.repository.load_run_start("run-1")
    prepared = run_workspace.prepare()
    input_payload = json.loads(
        prepared.input_path.read_text(encoding="utf-8")
    )
    sealed = run_workspace.repository.seal_instance(
        prepared,
        run_workspace.completed_result(prepared),
        retention_reasons=("baseline",),
        actor_id="alice",
        capacity=run_workspace.capacity,
    )
    manifest = json.loads(
        (
            run_workspace.memory_root / sealed.asset_path
        ).read_text(encoding="utf-8")
    )

    expected = [item.to_dict() for item in citations]
    assert start["experience_citations"] == expected
    assert start["planning_session_id"] == "session-1"
    assert input_payload["experience_citations"] == expected
    assert input_payload["planning_session_id"] == "session-1"
    assert manifest["experience_citations"] == expected
    assert sealed.experience_citations == citations
    assert "experience-excluded" not in json.dumps(manifest)


def test_instance_reload_detects_changed_or_extra_evidence(run_workspace):
    run_workspace.start()
    prepared = run_workspace.prepare()
    sealed = run_workspace.repository.seal_instance(
        prepared,
        run_workspace.completed_result(prepared),
        retention_reasons=("baseline",),
        actor_id="alice",
        capacity=run_workspace.capacity,
    )
    instance_root = (
        run_workspace.memory_root / sealed.asset_path
    ).parent
    (instance_root / "predictions.csv").write_text("tampered\n", encoding="utf-8")

    with pytest.raises(WorkspaceError) as changed:
        run_workspace.repository.load_instance("run-1", sealed.asset_id)
    assert changed.value.code == "invalid_training_instance"

    (instance_root / "predictions.csv").write_text(
        "sample_id,observed,predicted,probability_case\n"
        "s1,case,case,0.9\n",
        encoding="utf-8",
    )
    (instance_root / "undeclared.txt").write_text("extra", encoding="utf-8")
    with pytest.raises(WorkspaceError) as extra:
        run_workspace.repository.load_instance("run-1", sealed.asset_id)
    assert extra.value.code == "invalid_training_instance"


def test_parent_instance_reference_requires_exact_parent_fingerprint(
    run_workspace,
):
    run_workspace.start()
    first_prepared = run_workspace.prepare()
    first = run_workspace.repository.seal_instance(
        first_prepared,
        run_workspace.completed_result(first_prepared),
        retention_reasons=("baseline",),
        actor_id="alice",
        capacity=run_workspace.capacity,
    )
    first_fingerprint = run_workspace.repository.instance_fingerprint(first)
    second_prepared = run_workspace.prepare(
        round_number=2,
        parent=first.asset_id,
        parent_fingerprint=first_fingerprint,
    )
    second = run_workspace.repository.seal_instance(
        second_prepared,
        run_workspace.completed_result(second_prepared, metric=0.84),
        retention_reasons=("stage_best",),
        actor_id="alice",
        capacity=run_workspace.capacity,
    )

    assert second.parent_instance_id == first.asset_id
    assert second.parent_instance_fingerprint == first_fingerprint


def test_unselected_model_is_hashed_but_not_retained(run_workspace):
    run_workspace.start()
    prepared = run_workspace.prepare()
    sealed = run_workspace.repository.seal_instance(
        prepared,
        run_workspace.completed_result(prepared),
        retention_reasons=(),
        actor_id="alice",
        capacity=run_workspace.capacity,
    )

    assert sealed.model_fingerprint is not None
    assert sealed.model_path is None
    assert sealed.model_retention_reasons == ()


def test_model_at_single_file_limit_is_not_retained(run_workspace):
    run_workspace.start()
    prepared = run_workspace.prepare()
    limited = CapacityStatus(
        state="ready",
        bytes_used=run_workspace.capacity.bytes_used,
        largest_file_bytes=run_workspace.capacity.largest_file_bytes,
        max_file_bytes=4096,
        max_repository_bytes=run_workspace.capacity.max_repository_bytes,
    )
    sealed = run_workspace.repository.seal_instance(
        prepared,
        run_workspace.completed_result(prepared, model_size=4096),
        retention_reasons=("baseline",),
        actor_id="alice",
        capacity=limited,
    )

    assert sealed.model_path is None
    assert sealed.model_retention_reasons == ("rejected_too_large",)


@pytest.mark.parametrize("state", ("failed", "timed_out", "stopped"))
def test_unsuccessful_attempt_seals_without_success_claim(run_workspace, state):
    run_workspace.start()
    prepared = run_workspace.prepare()
    result = TrainingExecutionResult(
        state=state,
        primary_metric_name="roc_auc",
        primary_metric_value=None,
        metrics={},
        predictions_path=None,
        model_path=None,
        model_fingerprint=None,
        error_code=f"worker_{state}",
        error_summary=f"Worker {state}",
        started_at="2026-07-16T00:00:10Z",
        ended_at="2026-07-16T00:00:12Z",
        duration_ms=2000,
    )

    sealed = run_workspace.repository.seal_instance(
        prepared,
        result,
        retention_reasons=(),
        actor_id="alice",
        capacity=run_workspace.capacity,
    )

    assert sealed.state == state
    assert sealed.reproducible_evidence is False
    assert sealed.sop_source_eligible is False
    assert sealed.primary_metric_value is None


def test_pending_instance_without_live_owner_requires_recovery(run_workspace):
    run_workspace.start()
    prepared = run_workspace.prepare()

    status = run_workspace.repository.status("run-1")

    assert prepared.pending_path.is_dir()
    assert status.state == "recovery_required"
    assert status.recovery_reason == "unsealed_instance"
    assert status.recovery_actions == ("resume", "close")


def test_pending_input_is_pinned_by_its_started_event(run_workspace):
    run_workspace.start()
    prepared = run_workspace.prepare()
    payload = json.loads(prepared.input_path.read_text(encoding="utf-8"))
    payload["configuration"]["round"] = 99
    payload["configuration_fingerprint"] = hashlib.sha256(
        json.dumps(
            payload["configuration"],
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    prepared.input_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(WorkspaceError) as caught:
        run_workspace.repository.recover_run(
            "run-1",
            action="close",
            actor_id="alice",
            capacity=run_workspace.capacity,
        )

    assert caught.value.code == "invalid_training_instance"


def test_active_owner_keeps_unsealed_run_in_running_state(run_workspace):
    run_workspace.start()
    run_workspace.prepare()
    run_workspace.repository.activate_run("run-1")

    try:
        status = run_workspace.repository.status("run-1")
    finally:
        run_workspace.repository.deactivate_run("run-1")

    assert status.state == "running"
    assert status.recovery_reason is None


def test_recovery_close_seals_pending_instance_as_interrupted(run_workspace):
    run_workspace.start()
    pending = run_workspace.prepare()

    run_workspace.repository.recover_run(
        "run-1",
        action="close",
        actor_id="alice",
        capacity=run_workspace.capacity,
    )
    status = run_workspace.repository.status("run-1")
    sealed = run_workspace.repository.load_instance(
        "run-1", pending.instance_id
    )

    assert status.state == "failed"
    assert status.stop_reason == "interrupted"
    assert sealed.state == "failed"
    assert sealed.error_code == "interrupted"
    assert sealed.sop_source_eligible is False
    assert not pending.pending_path.exists()


def test_recovery_resume_records_retry_without_mutating_interrupted_attempt(
    run_workspace,
):
    run_workspace.start()
    pending = run_workspace.prepare()

    resumed = run_workspace.repository.recover_run(
        "run-1",
        action="resume",
        actor_id="alice",
        capacity=run_workspace.capacity,
    )
    interrupted = run_workspace.repository.load_instance(
        "run-1", pending.instance_id
    )

    assert resumed.event_type == "run_resumed"
    assert resumed.state == "running"
    assert interrupted.state == "failed"
    assert interrupted.error_code == "interrupted"


def test_run_status_projects_rounds_best_target_and_terminal_state(run_workspace):
    run_workspace.start()
    first_prepared = run_workspace.prepare()
    first = run_workspace.repository.seal_instance(
        first_prepared,
        run_workspace.completed_result(first_prepared, metric=0.82),
        retention_reasons=("baseline",),
        actor_id="alice",
        capacity=run_workspace.capacity,
    )
    second_prepared = run_workspace.prepare(
        round_number=2,
        parent=first.asset_id,
        parent_fingerprint=run_workspace.repository.instance_fingerprint(first),
    )
    run_workspace.repository.seal_instance(
        second_prepared,
        run_workspace.completed_result(second_prepared, metric=0.84),
        retention_reasons=("stage_best",),
        actor_id="alice",
        capacity=run_workspace.capacity,
    )
    run_workspace.repository.finish_run(
        "run-1",
        state="completed",
        reason="plan_complete",
        actor_id="alice",
        capacity=run_workspace.capacity,
    )

    status = run_workspace.repository.status("run-1")

    assert status.state == "completed"
    assert status.current_round == 2
    assert status.best_primary_metric_value == 0.84
    assert status.best_instance_id == "instance-2"
    assert status.target_gap == pytest.approx(0.07)
    assert [point.round_number for point in status.performance_points] == [1, 2]


def test_local_index_ignores_instance_component_json(run_workspace):
    run_workspace.start()
    prepared = run_workspace.prepare()
    run_workspace.repository.seal_instance(
        prepared,
        run_workspace.completed_result(prepared),
        retention_reasons=("baseline",),
        actor_id="alice",
        capacity=run_workspace.capacity,
    )
    subprocess.run(
        ["git", "add", "--", "raw-records", "runs"],
        cwd=run_workspace.memory_root,
        check=True,
    )
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=alice",
            "-c",
            "user.email=alice@example.test",
            "commit",
            "-m",
            "test: add run",
        ],
        cwd=run_workspace.memory_root,
        check=True,
        capture_output=True,
    )

    assets = LocalIndex(run_workspace.memory_root).rebuild()
    indexed = LocalIndex(run_workspace.memory_root).list_assets()

    assert assets.asset_count == len(indexed)
    paths = {item["path"] for item in indexed}
    assert any(path.endswith("/manifest.json") for path in paths)
    assert not any(path.endswith("/input.json") for path in paths)
    assert not any(path.endswith("/environment.json") for path in paths)
    assert not any(path.endswith("/metrics.json") for path in paths)


def test_concurrent_event_heads_fail_closed(run_workspace):
    run_workspace.start()
    run_workspace.repository.request_stop(
        "run-1",
        reason="user_stop",
        actor_id="alice",
        capacity=run_workspace.capacity,
    )
    event_path = next(
        (run_workspace.memory_root / "raw-records/runs/run-1").glob(
            "run-event-2.json"
        )
    )
    payload = json.loads(event_path.read_text(encoding="utf-8"))
    payload["previous_event_id"] = None
    payload["event_fingerprint"] = RunRepository.event_fingerprint(payload)
    event_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(WorkspaceError) as caught:
        run_workspace.repository.status("run-1")
    assert caught.value.code == "run_event_conflict"


def test_run_lock_file_is_persistent_and_local(run_workspace):
    run_workspace.start()

    lock_path = (
        run_workspace.memory_root
        / ".mlagent-local"
        / "run-locks"
        / "run-1.lock"
    )
    assert lock_path.is_file()
    assert os.path.getsize(lock_path) == 0
    assert subprocess.run(
        ["git", "check-ignore", "-q", str(lock_path)],
        cwd=run_workspace.memory_root,
        check=False,
    ).returncode == 0
