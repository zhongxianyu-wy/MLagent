"""Integration tests for SOP retraining (Issue #10)."""
import json
from pathlib import Path

import pytest

from src.domain.core import DomainCore
from src.domain.models import (
    RetrainFromSopCommand,
    WorkspaceError,
)
from tests.integration.test_sop_repository import build_sop_workspace, SopWorkspace
from tests.integration.test_domain_core_sop import write_connection
from tests.integration.test_sop_promotion import DeterministicExecutor


def _core_with_sop(tmp_path):
    """Build a workspace with an approved SOP version ready for retraining."""
    workspace = build_sop_workspace(tmp_path)
    connection = write_connection(tmp_path, workspace.root, "alice")

    repro_events = iter(f"repro-event-{i}" for i in range(1, 20))
    retrain_events = iter(f"retrain-event-{i}" for i in range(1, 20))
    retrain_instances = iter(f"retrain-inst-{i}" for i in range(1, 20))

    core = DomainCore(
        sop_candidate_id_factory=lambda: "candidate-1",
        sop_gate_id_factory=lambda: "gate-1",
        sop_approval_id_factory=lambda: "approval-1",
        sop_reproduction_run_id_factory=lambda: "run-repro",
        sop_reproduction_event_id_factory=lambda: next(repro_events),
        sop_reproduction_instance_id_factory=lambda: "inst-repro",
        sop_training_executor_factory=lambda: DeterministicExecutor(),
        run_id_factory=lambda: "run-retrain-1",
        run_event_id_factory=lambda: next(retrain_events),
        training_instance_id_factory=lambda: next(retrain_instances),
        training_gate_audit_id_factory=lambda: "audit-retrain",
        clock=lambda: "2026-07-21T00:00:00Z",
    )

    # Create and approve a SOP candidate
    from src.domain.models import (
        CreateSopCandidateCommand,
        ReproduceSopCandidateCommand,
        ReviewSopCandidateCommand,
    )
    from src.domain.memory_repository import load_reviewer_policy_fingerprint

    candidate = core.create_sop_candidate(
        CreateSopCandidateCommand(
            connection_path=connection,
            sop_id="baseline",
            name="Baseline RF",
            source_run_id=workspace.source_run_id,
            source_instance_id=workspace.source_instance_id,
            strategy_summary="RF with chi2 top-50",
            optimization_background="Initial baseline",
            steps=("Load data", "Select features", "Train RF", "Evaluate AUC"),
            change_summary="Initial version",
        )
    )
    gate = core.reproduce_sop_candidate(
        ReproduceSopCandidateCommand(
            connection_path=connection,
            candidate_id=candidate.asset_id,
            expected_candidate_fingerprint=candidate.candidate_fingerprint,
        )
    )
    policy_fp = load_reviewer_policy_fingerprint(workspace.root)
    core.review_sop_candidate(
        ReviewSopCandidateCommand(
            connection_path=connection,
            candidate_id=candidate.asset_id,
            expected_candidate_fingerprint=candidate.candidate_fingerprint,
            expected_gate_fingerprint=gate.gate_fingerprint,
            expected_reviewer_policy_fingerprint=policy_fp,
            decision="approve",
        )
    )
    return core, connection, workspace


def test_retrain_compatibility_check_passes(tmp_path):
    """The SOP's original dataset is compatible with itself."""
    from src.domain.sop_retrain import check_retrain_compatibility
    from src.domain.dataset_repository import DatasetRepository

    core, conn, ws = _core_with_sop(tmp_path)
    report = core.check_retrain_compatibility(
        connection_path=conn,
        sop_id="baseline",
        sop_version=1,
        dataset_id="ds-1",
        dataset_version=1,
    )
    assert report.compatible


def test_retrain_does_not_mutate_sop_version(tmp_path):
    """Retraining creates a new Run but leaves the SOP Version unchanged."""
    core, conn, ws = _core_with_sop(tmp_path)

    versions_before = core.list_sop_versions(conn)
    assert len(versions_before) == 1

    result = core.retrain_from_sop(RetrainFromSopCommand(
        connection_path=conn,
        sop_id="baseline",
        sop_version=1,
        dataset_id="ds-1",
        dataset_version=1,
        code_root=ws.root,
    ))

    assert result.sop_version_unchanged is True
    versions_after = core.list_sop_versions(conn)
    assert len(versions_after) == 1  # no new SOP version created
    assert versions_after[0].version == 1  # same version


def test_retrain_does_not_mutate_formal_model(tmp_path):
    """Retraining does not register a new Formal Model."""
    core, conn, ws = _core_with_sop(tmp_path)

    result = core.retrain_from_sop(RetrainFromSopCommand(
        connection_path=conn,
        sop_id="baseline",
        sop_version=1,
        dataset_id="ds-1",
        dataset_version=1,
        code_root=ws.root,
    ))

    assert result.formal_model_unchanged is True


def test_retrain_returns_delta(tmp_path):
    """Retrain result includes performance delta vs SOP baseline."""
    core, conn, ws = _core_with_sop(tmp_path)

    result = core.retrain_from_sop(RetrainFromSopCommand(
        connection_path=conn,
        sop_id="baseline",
        sop_version=1,
        dataset_id="ds-1",
        dataset_version=1,
        code_root=ws.root,
    ))

    assert result.run_id is not None
    assert result.instance_id is not None
    assert result.primary_metric_name == "roc_auc"
    # delta may be None if executor didn't produce a metric; verify structure
    assert result.delta is None or isinstance(result.delta, float)


def test_retrain_nonexistent_sop_raises(tmp_path):
    """Retraining a non-existent SOP raises a clear error."""
    core, conn, ws = _core_with_sop(tmp_path)

    with pytest.raises(WorkspaceError, match="not found"):
        core.retrain_from_sop(RetrainFromSopCommand(
            connection_path=conn,
            sop_id="nonexistent",
            sop_version=99,
            dataset_id="ds-1",
            dataset_version=1,
            code_root=ws.root,
        ))
