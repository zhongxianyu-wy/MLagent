"""Integration tests for DomainCore.get_run_replay (Issue #13)."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from src.domain.core import DomainCore
from src.domain.memory_repository import MemoryRepository
from src.domain.models import WorkspaceError
from src.domain.run_repository import (
    InstancePreparationSpec,
    RunRepository,
    RunStartSpec,
    TrainingExecutionResult,
)
from src.domain.models import CandidateCodeFile
from tests.integration.test_sop_repository import build_sop_workspace
from tests.integration.test_domain_core_sop import write_connection


def _core() -> DomainCore:
    return DomainCore(clock=lambda: "2026-07-23T00:00:00Z")


def _snapshot_files(root: Path) -> dict[str, str]:
    snap: dict[str, str] = {}
    if not root.exists():
        return snap
    for path in sorted(root.rglob("*")):
        if path.is_file():
            snap[path.relative_to(root).as_posix()] = hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
    return snap


def test_get_run_replay_returns_aggregated_snapshot(tmp_path):
    workspace = build_sop_workspace(tmp_path)
    connection = write_connection(tmp_path, workspace.root, "alice")
    core = _core()
    replay = core.get_run_replay(connection, workspace.source_run_id)

    assert replay.run.run_id == workspace.source_run_id
    assert replay.run.primary_metric_name == "roc_auc"
    # plan/code linkage derived from run_started
    assert replay.code_revision_fingerprint is not None
    # at least one round present
    assert replay.run.rounds
    # best/target surfaced
    assert replay.run.target_metric_value == pytest.approx(0.9)


def test_sop_baselines_matched_by_metric_and_dataset(tmp_path):
    from tests.integration.test_retrain_from_sop import _core_with_sop

    core, connection, workspace = _core_with_sop(tmp_path)
    replay = core.get_run_replay(connection, workspace.source_run_id)

    assert replay.sop_baselines, "expected at least one matching SOP baseline"
    for version in replay.sop_baselines:
        assert version.primary_metric_name == replay.run.primary_metric_name
        assert version.dataset_id == replay.run.dataset_id
        assert version.dataset_version == replay.run.dataset_version


def test_replay_does_not_mutate_run_or_instance_files(tmp_path):
    workspace = build_sop_workspace(tmp_path)
    connection = write_connection(tmp_path, workspace.root, "alice")
    core = _core()
    runs_dir = workspace.root / "raw-records" / "runs"
    before = _snapshot_files(runs_dir)

    core.get_run_replay(connection, workspace.source_run_id)
    core.get_run_replay(connection, workspace.source_run_id)  # call twice

    after = _snapshot_files(runs_dir)
    assert before == after


def _failed_round_workspace(tmp_path):
    """A run with a single failed instance (missing metric, AC#6)."""
    root = tmp_path / "tm-fail"
    status = MemoryRepository(
        id_factory=lambda: "tmr-fail", clock=lambda: "2026-07-23T00:00:00Z"
    ).bootstrap(root, actor_id="alice")
    code_root = tmp_path / "code-fail"
    code_root.mkdir()
    code_bytes = b"def build_estimator(c):\n    return c\n"
    (code_root / "train.py").write_bytes(code_bytes)
    split_path = tmp_path / "split-fail.csv"
    split_path.write_text("sample_id,partition\ns1,train\n")
    event_ids = iter(f"fail-e-{i}" for i in range(1, 20))
    inst_ids = iter(f"fail-inst-{i}" for i in range(1, 20))
    repo = RunRepository(
        root,
        event_id_factory=lambda: next(event_ids),
        instance_id_factory=lambda: next(inst_ids),
        clock=lambda: "2026-07-23T00:00:00Z",
    )
    repo.start_run(
        RunStartSpec(
            run_id="run-fail",
            dataset_id="ds-1",
            dataset_version=1,
            dataset_content_fingerprint="dc",
            dataset_version_fingerprint="dv",
            plan_id="plan-fail",
            plan_event_id="plan-event-fail",
            planning_session_id="sess-fail",
            plan_fingerprint="p",
            approval_id="appr-fail",
            approval_fingerprint="a",
            code_fingerprint="code-fail",
            user_direction="fail exploration",
            stop_conditions=("budget",),
            primary_metric_name="roc_auc",
            target_metric_value=0.9,
            expected_round_count=1,
        ),
        actor_id="alice",
        capacity=status.capacity,
    )
    code = repo.freeze_code_revision(
        run_id="run-fail",
        code_root=code_root,
        candidate_code_files=(
            CandidateCodeFile("train.py", hashlib.sha256(code_bytes).hexdigest(), len(code_bytes)),
        ),
        code_fingerprint="code-fail",
        entrypoint_path="train.py",
        actor_id="alice",
        capacity=status.capacity,
    )
    prepared = repo.prepare_instance(
        InstancePreparationSpec(
            run_id="run-fail",
            round_number=1,
            hypothesis="will fail",
            optimization_direction="baseline",
            intended_changes=("fit",),
            random_seed=42,
            parent_instance_id=None,
            parent_instance_fingerprint=None,
            configuration={"worker_contract": 1},
            environment={"python": "3.13"},
        ),
        code_revision=code,
        split_path=split_path,
        actor_id="alice",
        capacity=status.capacity,
    )
    result = TrainingExecutionResult(
        state="failed",
        primary_metric_name="roc_auc",
        primary_metric_value=None,
        metrics={},
        predictions_path=None,
        model_path=None,
        model_fingerprint=None,
        error_code="training_boom",
        error_summary="estimator raised",
        started_at="2026-07-23T00:00:10Z",
        ended_at="2026-07-23T00:00:12Z",
        duration_ms=2000,
    )
    repo.seal_instance(
        prepared,
        result,
        retention_reasons=("baseline",),
        actor_id="alice",
        capacity=status.capacity,
    )
    connection = tmp_path / ".mlagent-workspace-fail.json"
    connection.write_text(
        json.dumps({"repository_path": str(root), "actor_id": "alice"})
    )
    return connection, root


def test_failed_round_shows_missing_metric_not_inferred(tmp_path):
    connection, root = _failed_round_workspace(tmp_path)
    core = _core()
    replay = core.get_run_replay(connection, "run-fail")

    failed_rounds = [
        r for r in replay.run.rounds if r.instance_state != "completed"
    ]
    assert failed_rounds, "expected a failed round"
    for rnd in failed_rounds:
        assert rnd.primary_metric_value is None  # not inferred
        assert rnd.error_code  # missing segment surfaced
    # best is None because no completed round
    assert replay.run.best_primary_metric_value is None


def test_replay_for_unknown_run_raises(tmp_path):
    workspace = build_sop_workspace(tmp_path)
    connection = write_connection(tmp_path, workspace.root, "alice")
    core = _core()
    with pytest.raises(WorkspaceError):
        core.get_run_replay(connection, "nonexistent-run")
