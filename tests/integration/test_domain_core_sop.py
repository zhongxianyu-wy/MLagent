import json
from pathlib import Path

import pytest

from src.domain.core import DomainCore
from src.domain.models import (
    CreateSopCandidateCommand,
    ReproduceSopCandidateCommand,
    ReviewSopCandidateCommand,
    WorkspaceError,
)
from tests.integration.test_sop_promotion import DeterministicExecutor
from tests.integration.test_sop_repository import build_sop_workspace


def test_domain_core_promotes_one_training_instance_end_to_end(tmp_path):
    workspace = build_sop_workspace(tmp_path)
    connection = write_connection(tmp_path, workspace.root, "alice")
    event_ids = iter(f"reproduction-event-{index}" for index in range(1, 10))
    core = DomainCore(
        sop_candidate_id_factory=lambda: "candidate-1",
        sop_gate_id_factory=lambda: "gate-1",
        sop_approval_id_factory=lambda: "sop-approval-1",
        sop_reproduction_run_id_factory=lambda: "run-reproduction",
        sop_reproduction_event_id_factory=lambda: next(event_ids),
        sop_reproduction_instance_id_factory=(
            lambda: "instance-reproduction"
        ),
        sop_training_executor_factory=lambda: DeterministicExecutor(),
        clock=lambda: "2026-07-17T00:10:00Z",
    )

    candidate = core.create_sop_candidate(
        candidate_command(connection)
    )
    gate = core.reproduce_sop_candidate(
        ReproduceSopCandidateCommand(
            connection_path=connection,
            candidate_id=candidate.asset_id,
            expected_candidate_fingerprint=candidate.candidate_fingerprint,
        )
    )
    approved = core.review_sop_candidate(
        ReviewSopCandidateCommand(
            connection_path=connection,
            candidate_id=candidate.asset_id,
            expected_candidate_fingerprint=candidate.candidate_fingerprint,
            expected_gate_fingerprint=gate.gate_fingerprint,
            decision="approve",
        )
    )

    assert approved.sop_version is not None
    assert approved.formal_model is not None
    assert core.list_sop_versions(connection) == (approved.sop_version,)
    assert core.get_formal_model(
        connection,
        approved.formal_model.asset_id,
    ) == approved.formal_model
    assert core.list_sop_candidates(connection) == (candidate,)


def test_domain_core_rejects_experience_id_as_sop_source(tmp_path):
    workspace = build_sop_workspace(tmp_path)
    connection = write_connection(tmp_path, workspace.root, "alice")
    core = DomainCore(
        sop_candidate_id_factory=lambda: "candidate-1",
        clock=lambda: "2026-07-17T00:10:00Z",
    )
    command = candidate_command(connection)
    invalid = CreateSopCandidateCommand(
        connection_path=connection,
        sop_id=command.sop_id,
        name=command.name,
        source_run_id="experience-1",
        source_instance_id="experience-event-1",
        strategy_summary=command.strategy_summary,
        optimization_background=command.optimization_background,
        steps=command.steps,
        change_summary=command.change_summary,
    )

    with pytest.raises(WorkspaceError) as caught:
        core.create_sop_candidate(invalid)

    assert caught.value.code == "training_instance_not_found"
    assert not list((workspace.root / "sops/candidates").rglob("*.json"))


def candidate_command(connection: Path) -> CreateSopCandidateCommand:
    return CreateSopCandidateCommand(
        connection_path=connection,
        sop_id="sop-random-forest",
        name="Random forest baseline",
        source_run_id="run-source",
        source_instance_id="instance-source",
        strategy_summary="Fit a reviewed random forest baseline.",
        optimization_background="Selected after improving validation AUC.",
        steps=(
            "Load the frozen Dataset Version and split",
            "Execute the frozen train.py entrypoint",
        ),
        change_summary="",
    )


def write_connection(
    tmp_path: Path,
    repository_path: Path,
    actor_id: str,
) -> Path:
    connection = tmp_path / ".mlagent-workspace.json"
    connection.write_text(
        json.dumps(
            {
                "repository_path": str(repository_path),
                "actor_id": actor_id,
            }
        ),
        encoding="utf-8",
    )
    return connection
