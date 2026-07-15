import json
from pathlib import Path

import pandas as pd
import pytest

from src.domain.core import DomainCore
from src.domain.models import (
    ApproveExplorationPlanCommand,
    AuthorizeTrainingCommand,
    BootstrapMemoryCommand,
    ConfirmDatasetCommand,
    ExplorationRound,
    RecordExplorationPlanCommand,
    WorkspaceError,
)


@pytest.fixture
def exploration_workspace(tmp_path):
    event_ids = iter(("plan-event-1", "plan-event-2", "plan-event-3"))
    approval_ids = iter(("approval-1", "approval-2", "approval-3"))
    audit_ids = iter(
        (
            "gate-audit-1",
            "gate-audit-2",
            "gate-audit-3",
            "gate-audit-4",
        )
    )
    core = DomainCore(
        id_factory=lambda: "tmr-1",
        dataset_id_factory=lambda: "ds-1",
        exploration_event_id_factory=lambda: next(event_ids),
        exploration_approval_id_factory=lambda: next(approval_ids),
        training_gate_audit_id_factory=lambda: next(audit_ids),
        clock=lambda: "2026-07-15T00:00:00Z",
    )
    connection_path = tmp_path / ".mlagent-workspace.json"
    memory_root = tmp_path / "team-memory"
    core.bootstrap_memory(
        BootstrapMemoryCommand(
            repository_path=memory_root,
            actor_id="alice",
            connection_path=connection_path,
        )
    )
    feature_path, label_path = write_pair(tmp_path)
    core.confirm_dataset(
        ConfirmDatasetCommand(
            connection_path=connection_path,
            feature_path=feature_path,
            label_path=label_path,
            sample_id_col="sample_id",
            label_col="group",
            task_type="binary",
            positive_class="case",
            primary_metric="roc_auc",
            split_strategy="train_only",
            target_metric=0.91,
        )
    )
    code_root = tmp_path / "code"
    code_root.mkdir()
    (code_root / "train.py").write_text("print('baseline')\n", encoding="utf-8")
    return ExplorationWorkspace(
        core=core,
        connection_path=connection_path,
        memory_root=memory_root,
        code_root=code_root,
    )


class ExplorationWorkspace:
    def __init__(self, core, connection_path, memory_root, code_root):
        self.core = core
        self.connection_path = connection_path
        self.memory_root = memory_root
        self.code_root = code_root

    def plan_command(self, **overrides):
        values = {
            "connection_path": self.connection_path,
            "code_root": self.code_root,
            "dataset_id": "ds-1",
            "dataset_version": 1,
            "plan_id": "plan-1",
            "planning_session_id": "session-1",
            "user_direction": "Improve validation AUC",
            "baseline_hypothesis": "Fit a regularized baseline",
            "rounds": (
                ExplorationRound(
                    round_number=1,
                    hypothesis="The baseline is stable",
                    optimization_direction="baseline",
                    intended_changes=("fit logistic regression",),
                ),
            ),
            "stop_conditions": ("target reached",),
            "risks": ("validation overfitting",),
            "resource_limits": {"max_minutes": 30},
            "trusted_experience_ids": ("experience-approved",),
            "pending_experience_ids": ("experience-pending",),
            "excluded_pending_experience_ids": (),
            "candidate_code_paths": ("train.py",),
        }
        values.update(overrides)
        return RecordExplorationPlanCommand(**values)

    def record(self, **overrides):
        return self.core.record_exploration_plan(self.plan_command(**overrides))

    def approve(self, plan_id="plan-1"):
        return self.core.approve_exploration_plan(
            ApproveExplorationPlanCommand(
                connection_path=self.connection_path,
                code_root=self.code_root,
                plan_id=plan_id,
            )
        )

    def authorization_command(self, **overrides):
        values = {
            "connection_path": self.connection_path,
            "code_root": self.code_root,
            "entry_point": "cli_explore",
            "dataset_id": "ds-1",
            "dataset_version": 1,
            "plan_id": "plan-1",
            "approval_id": "approval-1",
        }
        values.update(overrides)
        return AuthorizeTrainingCommand(**values)

    def authorize(self, **overrides):
        return self.core.authorize_training(
            self.authorization_command(**overrides)
        )

    def audits(self):
        audit_root = self.memory_root / "approvals" / "training-gates"
        return [
            json.loads(path.read_text(encoding="utf-8"))
            for path in sorted(audit_root.glob("*.json"))
        ]


def test_domain_core_records_plan_against_exact_confirmed_dataset(
    exploration_workspace,
):
    plan = exploration_workspace.record()

    assert plan.dataset_id == "ds-1"
    assert plan.dataset_version == 1
    assert plan.primary_metric == "roc_auc"
    assert plan.target_metric == 0.91

    with pytest.raises(WorkspaceError) as caught:
        exploration_workspace.record(dataset_version=99)
    assert caught.value.code == "dataset_version_not_found"


def test_domain_core_reviews_and_approves_current_plan(exploration_workspace):
    plan = exploration_workspace.record()
    pending = exploration_workspace.core.get_exploration_review(
        exploration_workspace.connection_path,
        exploration_workspace.code_root,
        plan.plan_id,
    )
    assert pending.approval_state == "pending_review"

    approval = exploration_workspace.approve()
    approved = exploration_workspace.core.get_exploration_review(
        exploration_workspace.connection_path,
        exploration_workspace.code_root,
        plan.plan_id,
    )
    assert approval.plan_event_id == plan.asset_id
    assert approved.approval_state == "approved"


def test_authorization_rejects_missing_approval_and_appends_minimal_audit(
    exploration_workspace,
):
    exploration_workspace.record()

    with pytest.raises(WorkspaceError) as caught:
        exploration_workspace.authorize(approval_id=None)

    assert caught.value.code == "plan_approval_required"
    audits = exploration_workspace.audits()
    assert len(audits) == 1
    assert audits[0]["reason_code"] == "plan_approval_required"
    assert audits[0]["entry_point"] == "cli_explore"
    assert "prompt" not in audits[0]
    assert "command_output" not in audits[0]
    assert list((exploration_workspace.memory_root / "runs").glob("**/*")) == []
    assert list((exploration_workspace.memory_root / "models").glob("**/*")) == []


def test_exact_approval_returns_binding_without_creating_run(
    exploration_workspace,
):
    plan = exploration_workspace.record()
    approval = exploration_workspace.approve()

    authorization = exploration_workspace.authorize(
        approval_id=approval.asset_id,
    )

    assert authorization.authorized is True
    assert authorization.plan_event_id == plan.asset_id
    assert authorization.approval_id == approval.asset_id
    assert authorization.plan_fingerprint == plan.plan_fingerprint
    assert authorization.code_fingerprint == plan.code_fingerprint
    assert authorization.round_count == len(plan.rounds)
    assert list((exploration_workspace.memory_root / "runs").glob("**/*")) == []
    assert list((exploration_workspace.memory_root / "models").glob("**/*")) == []


def test_review_reports_domain_training_readiness_without_writing_gate_audit(
    exploration_workspace,
):
    exploration_workspace.record()
    pending = exploration_workspace.core.get_exploration_review(
        exploration_workspace.connection_path,
        exploration_workspace.code_root,
    )
    exploration_workspace.approve()
    approved = exploration_workspace.core.get_exploration_review(
        exploration_workspace.connection_path,
        exploration_workspace.code_root,
    )

    assert pending.training_gate_state == "blocked"
    assert pending.training_gate_reason == "pending_review"
    assert approved.training_gate_state == "authorized"
    assert approved.training_gate_reason is None
    assert exploration_workspace.audits() == []


def test_plan_update_invalidates_prior_approval(exploration_workspace):
    exploration_workspace.record()
    approval = exploration_workspace.approve()
    exploration_workspace.record(user_direction="Try feature selection")

    with pytest.raises(WorkspaceError) as caught:
        exploration_workspace.authorize(approval_id=approval.asset_id)

    assert caught.value.code == "approval_stale"
    assert exploration_workspace.audits()[-1]["reason_code"] == "approval_stale"


def test_code_update_invalidates_prior_approval(exploration_workspace):
    exploration_workspace.record()
    approval = exploration_workspace.approve()
    (exploration_workspace.code_root / "train.py").write_text(
        "print('changed')\n",
        encoding="utf-8",
    )

    with pytest.raises(WorkspaceError) as caught:
        exploration_workspace.authorize(approval_id=approval.asset_id)

    assert caught.value.code == "approval_stale"


def test_requested_dataset_must_match_approved_dataset(exploration_workspace):
    exploration_workspace.record()
    approval = exploration_workspace.approve()
    exploration_workspace.core.confirm_dataset(
        ConfirmDatasetCommand(
            connection_path=exploration_workspace.connection_path,
            feature_path=exploration_workspace.connection_path.parent
            / "features.csv",
            label_path=exploration_workspace.connection_path.parent / "labels.csv",
            sample_id_col="sample_id",
            label_col="group",
            task_type="binary",
            positive_class="case",
            primary_metric="roc_auc",
            split_strategy="train_only",
            target_metric=0.91,
            dataset_id="ds-2",
        )
    )

    with pytest.raises(WorkspaceError) as caught:
        exploration_workspace.authorize(
            dataset_id="ds-2",
            approval_id=approval.asset_id,
        )

    assert caught.value.code == "approved_dataset_mismatch"


def test_approval_record_tampering_blocks_authorization(exploration_workspace):
    exploration_workspace.record()
    approval = exploration_workspace.approve()
    approval_path = exploration_workspace.memory_root / approval.asset_path
    payload = json.loads(approval_path.read_text(encoding="utf-8"))
    payload["code_fingerprint"] = "tampered"
    approval_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(WorkspaceError) as caught:
        exploration_workspace.authorize(approval_id=approval.asset_id)

    assert caught.value.code == "invalid_plan_approval"
    assert exploration_workspace.audits()[-1]["reason_code"] == "invalid_plan_approval"


def test_invalid_plan_reference_is_audited_without_becoming_a_path(
    exploration_workspace,
):
    exploration_workspace.record()

    with pytest.raises(WorkspaceError) as caught:
        exploration_workspace.authorize(
            plan_id="../outside",
            approval_id="approval-1",
        )

    assert caught.value.code == "invalid_exploration_id"
    audit = exploration_workspace.audits()[-1]
    assert audit["reason_code"] == "invalid_exploration_id"
    assert audit["plan_id"] == "../outside"
    assert not (exploration_workspace.memory_root.parent / "outside").exists()


def test_domain_core_rejects_code_root_outside_local_workspace(
    exploration_workspace,
    tmp_path,
):
    outside_root = tmp_path.parent / f"{tmp_path.name}-outside-code"
    outside_root.mkdir()
    (outside_root / "train.py").write_text("print('outside')\n", encoding="utf-8")

    with pytest.raises(WorkspaceError) as caught:
        exploration_workspace.record(code_root=outside_root)

    assert caught.value.code == "unmanaged_code_root"


def test_training_gate_audits_approved_request_with_unmanaged_code_root(
    exploration_workspace,
    tmp_path,
):
    plan = exploration_workspace.record()
    approval = exploration_workspace.approve()
    outside_root = tmp_path.parent / f"{tmp_path.name}-outside-approved-code"
    outside_root.mkdir()
    (outside_root / "train.py").write_text("print('outside')\n", encoding="utf-8")

    with pytest.raises(WorkspaceError) as caught:
        exploration_workspace.authorize(
            plan_id=plan.plan_id,
            approval_id=approval.asset_id,
            code_root=outside_root,
        )

    assert caught.value.code == "unmanaged_code_root"
    assert exploration_workspace.audits()[-1]["reason_code"] == "unmanaged_code_root"


def write_pair(root: Path):
    sample_ids = [f"s{index:02d}" for index in range(12)]
    feature_path = root / "features.csv"
    label_path = root / "labels.csv"
    pd.DataFrame(
        {
            "sample_id": sample_ids,
            "f1": [index / 10 for index in range(12)],
            "f2": list(range(12)),
        }
    ).to_csv(feature_path, index=False)
    pd.DataFrame(
        {
            "sample_id": sample_ids,
            "group": ["case"] * 6 + ["control"] * 6,
        }
    ).to_csv(label_path, index=False)
    return feature_path, label_path
