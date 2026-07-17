from dataclasses import FrozenInstanceError, replace
from pathlib import Path

import pytest

from src.domain.models import (
    CreateSopCandidateCommand,
    FormalModelSnapshot,
    ReproduceSopCandidateCommand,
    ReviewSopCandidateCommand,
    SopCandidateSnapshot,
    SopCandidateStatus,
    SopEvidenceReference,
    SopReproductionGateSnapshot,
    SopReviewOutcome,
    SopVersionSnapshot,
)


SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64


def test_sop_candidate_requires_exactly_one_source_instance_and_serializes():
    candidate = candidate_snapshot()

    assert candidate.source_run_id == "run-source"
    assert candidate.source_instance_id == "instance-source"
    assert candidate.steps == (
        "Load frozen Dataset Version",
        "Execute train.py",
    )
    assert candidate.to_dict()["evidence"][0]["role"] == "dataset"
    with pytest.raises(FrozenInstanceError):
        candidate.source_instance_id = "instance-other"


def test_sop_candidate_rejects_duplicate_or_incomplete_evidence_roles():
    candidate = candidate_snapshot()

    with pytest.raises(ValueError, match="evidence roles"):
        replace(candidate, evidence=candidate.evidence[:-1])
    with pytest.raises(ValueError, match="evidence roles"):
        replace(candidate, evidence=candidate.evidence + (candidate.evidence[0],))


@pytest.mark.parametrize(
    ("updates", "message"),
    (
        ({"source_run_id": "../run"}, "source_run_id"),
        ({"candidate_fingerprint": "not-a-sha"}, "candidate_fingerprint"),
        ({"steps": ()}, "steps"),
        ({"strategy_summary": ""}, "strategy_summary"),
        ({"optimization_background": ""}, "optimization_background"),
        ({"source_metric_value": float("nan")}, "source_metric_value"),
    ),
)
def test_sop_candidate_rejects_unsafe_or_incomplete_contracts(updates, message):
    with pytest.raises(ValueError, match=message):
        replace(candidate_snapshot(), **updates)


def test_passed_gate_requires_distinct_reproduction_and_six_decimal_values():
    gate = gate_snapshot()

    assert gate.source_instance_id != gate.reproduction_instance_id
    assert gate.source_metric_six_decimals == "0.812346"
    assert gate.reproduction_metric_six_decimals == "0.812346"
    assert gate.to_dict()["outcome"] == "passed"


@pytest.mark.parametrize(
    ("updates", "message"),
    (
        ({"reproduction_run_id": "run-source"}, "reproduction_run_id"),
        (
            {"reproduction_instance_id": "instance-source"},
            "reproduction_instance_id",
        ),
        ({"reproduction_metric_value": None}, "reproduction_metric_value"),
        (
            {"reproduction_metric_six_decimals": "0.812345"},
            "six-decimal",
        ),
    ),
)
def test_passed_gate_rejects_non_independent_or_inexact_evidence(updates, message):
    with pytest.raises(ValueError, match=message):
        replace(gate_snapshot(), **updates)


def test_failed_execution_gate_has_no_reproduced_metric():
    gate = replace(
        gate_snapshot(),
        outcome="execution_failed",
        reproduction_metric_value=None,
        reproduction_metric_six_decimals=None,
    )

    assert gate.outcome == "execution_failed"
    with pytest.raises(ValueError, match="reproduction_metric"):
        replace(gate, reproduction_metric_value=0.8)


def test_sop_commands_validate_stable_ids_fingerprints_and_decisions():
    create = CreateSopCandidateCommand(
        connection_path=Path(".mlagent-workspace.json"),
        sop_id="sop-random-forest",
        name="Random forest baseline",
        source_run_id="run-source",
        source_instance_id="instance-source",
        strategy_summary="Fit a calibrated random forest.",
        optimization_background="Improved the approved baseline.",
        steps=("Load data", "Fit model"),
        change_summary="",
    )
    reproduce = ReproduceSopCandidateCommand(
        connection_path=create.connection_path,
        candidate_id="candidate-1",
        expected_candidate_fingerprint=SHA_A,
    )
    review = ReviewSopCandidateCommand(
        connection_path=create.connection_path,
        candidate_id=reproduce.candidate_id,
        expected_candidate_fingerprint=SHA_A,
        expected_gate_fingerprint=SHA_B,
        expected_reviewer_policy_fingerprint=SHA_C,
        decision="approve",
    )

    assert create.steps == ("Load data", "Fit model")
    assert reproduce.candidate_id == review.candidate_id
    with pytest.raises(ValueError, match="decision"):
        replace(review, decision="publish")
    with pytest.raises(ValueError, match="candidate_id"):
        replace(reproduce, candidate_id="../candidate")


def test_version_chain_and_formal_model_preserve_reproduction_provenance():
    version = version_snapshot()
    model = formal_model_snapshot()

    assert version.version == 1
    assert model.sop_version_id == version.asset_id
    assert model.reproduction_instance_id == version.reproduction_instance_id
    assert model.to_dict()["model_path"] == (
        "models/formal/model-sop-random-forest-v0001/model.joblib"
    )
    with pytest.raises(ValueError, match="previous_version"):
        replace(version, version=2)
    with pytest.raises(ValueError, match="change_summary"):
        replace(
            version,
            version=2,
            previous_version_id="sop-random-forest-v0001",
            previous_version_fingerprint=SHA_C,
            change_summary="",
        )


def test_review_outcome_requires_formal_assets_only_for_approval():
    approved = SopReviewOutcome(
        decision="approve",
        candidate_id="candidate-1",
        gate_id="gate-1",
        approval_id="approval-1",
        sop_version=version_snapshot(),
        formal_model=formal_model_snapshot(),
    )

    assert approved.sop_version is not None
    with pytest.raises(ValueError, match="formal assets"):
        replace(approved, formal_model=None)
    rejected = replace(
        approved,
        decision="reject",
        sop_version=None,
        formal_model=None,
    )
    assert rejected.sop_version is None


def test_candidate_status_rejects_state_gate_mismatch():
    pending = SopCandidateStatus(
        candidate=candidate_snapshot(),
        gate=None,
        state="pending_reproduction",
    )

    assert pending.gate is None
    with pytest.raises(ValueError, match="gate"):
        replace(pending, state="pending_review")


def candidate_snapshot(**updates) -> SopCandidateSnapshot:
    values = {
        "asset_id": "candidate-1",
        "asset_path": "sops/candidates/candidate-1/manifest.json",
        "sop_id": "sop-random-forest",
        "name": "Random forest baseline",
        "source_run_id": "run-source",
        "source_instance_id": "instance-source",
        "candidate_fingerprint": SHA_A,
        "dataset_id": "dataset-1",
        "dataset_version": 1,
        "dataset_content_fingerprint": SHA_A,
        "dataset_version_fingerprint": SHA_B,
        "code_fingerprint": SHA_A,
        "configuration_fingerprint": SHA_B,
        "environment_fingerprint": SHA_C,
        "split_fingerprint": SHA_A,
        "random_seed": 42,
        "primary_metric_name": "roc_auc",
        "source_metric_value": 0.81234551,
        "source_model_fingerprint": SHA_C,
        "strategy_summary": "Fit a calibrated random forest.",
        "optimization_background": "Improved the approved baseline.",
        "steps": ("Load frozen Dataset Version", "Execute train.py"),
        "change_summary": "",
        "evidence": evidence_references(),
        "created_at": "2026-07-17T00:00:00Z",
        "created_by": "alice",
    }
    values.update(updates)
    return SopCandidateSnapshot(**values)


def evidence_references() -> tuple[SopEvidenceReference, ...]:
    roles = (
        "dataset",
        "run",
        "training_instance",
        "input",
        "environment",
        "split",
        "code_revision",
        "metrics",
        "predictions",
        "source_model",
    )
    return tuple(
        SopEvidenceReference(
            role=role,
            asset_id=f"{role}-1",
            asset_path=f"runs/run-source/{role}.json",
            sha256=SHA_A,
        )
        for role in roles
    )


def gate_snapshot(**updates) -> SopReproductionGateSnapshot:
    values = {
        "asset_id": "gate-1",
        "asset_path": (
            "approvals/sop-reproductions/candidate-1/gate-1.json"
        ),
        "candidate_id": "candidate-1",
        "candidate_fingerprint": SHA_A,
        "gate_fingerprint": SHA_B,
        "outcome": "passed",
        "source_run_id": "run-source",
        "source_instance_id": "instance-source",
        "reproduction_run_id": "run-reproduction",
        "reproduction_instance_id": "instance-reproduction",
        "source_metric_value": 0.81234551,
        "reproduction_metric_value": 0.81234552,
        "source_metric_six_decimals": "0.812346",
        "reproduction_metric_six_decimals": "0.812346",
        "created_at": "2026-07-17T00:01:00Z",
        "created_by": "alice",
    }
    values.update(updates)
    return SopReproductionGateSnapshot(**values)


def version_snapshot(**updates) -> SopVersionSnapshot:
    values = {
        "asset_id": "sop-random-forest-v0001",
        "asset_path": "sops/sop-random-forest/v0001/manifest.json",
        "sop_id": "sop-random-forest",
        "version": 1,
        "version_fingerprint": SHA_A,
        "previous_version_id": None,
        "previous_version_fingerprint": None,
        "candidate_id": "candidate-1",
        "gate_id": "gate-1",
        "gate_fingerprint": SHA_B,
        "source_run_id": "run-source",
        "source_instance_id": "instance-source",
        "reproduction_run_id": "run-reproduction",
        "reproduction_instance_id": "instance-reproduction",
        "dataset_id": "dataset-1",
        "dataset_version": 1,
        "primary_metric_name": "roc_auc",
        "primary_metric_value": 0.81234552,
        "source_metric_value": 0.81234551,
        "reproduction_metric_value": 0.81234552,
        "environment": {"python": "3.13", "sklearn": "1.7"},
        "strategy_summary": "Fit a calibrated random forest.",
        "optimization_background": "Improved the approved baseline.",
        "steps": ("Load frozen Dataset Version", "Execute train.py"),
        "change_summary": "Initial approved version.",
        "approval_id": "approval-1",
        "formal_model_id": "model-sop-random-forest-v0001",
        "created_at": "2026-07-17T00:02:00Z",
        "created_by": "alice",
    }
    values.update(updates)
    return SopVersionSnapshot(**values)


def formal_model_snapshot(**updates) -> FormalModelSnapshot:
    values = {
        "asset_id": "model-sop-random-forest-v0001",
        "asset_path": (
            "models/formal/model-sop-random-forest-v0001/manifest.json"
        ),
        "model_path": (
            "models/formal/model-sop-random-forest-v0001/model.joblib"
        ),
        "model_fingerprint": SHA_C,
        "sop_version_id": "sop-random-forest-v0001",
        "source_instance_id": "instance-source",
        "reproduction_instance_id": "instance-reproduction",
        "dataset_id": "dataset-1",
        "dataset_version": 1,
        "primary_metric_name": "roc_auc",
        "primary_metric_value": 0.81234552,
        "strategy_summary": "Fit a calibrated random forest.",
        "optimization_background": "Improved the approved baseline.",
        "approval_id": "approval-1",
        "created_at": "2026-07-17T00:02:00Z",
        "created_by": "alice",
    }
    values.update(updates)
    return FormalModelSnapshot(**values)
