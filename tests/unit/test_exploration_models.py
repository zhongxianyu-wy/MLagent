from pathlib import Path

from src.domain.models import (
    ApproveExplorationPlanCommand,
    AuthorizeTrainingCommand,
    CandidateCodeFile,
    CandidateCodePreview,
    ExplorationApprovalSnapshot,
    ExplorationPlanSnapshot,
    ExplorationReviewSnapshot,
    ExplorationRound,
    RecordExplorationPlanCommand,
    TrainingAuthorization,
)


def test_exploration_plan_snapshot_is_json_safe_without_strategy_version():
    snapshot = ExplorationPlanSnapshot(
        asset_id="plan-event-1",
        asset_path="raw-records/exploration-plans/plan-1/plan-event-1.json",
        plan_id="plan-1",
        planning_session_id="session-1",
        dataset_id="ds-1",
        dataset_version=1,
        dataset_content_fingerprint="content-1",
        dataset_version_fingerprint="version-1",
        user_direction="Improve validation AUC",
        baseline_hypothesis="Start with a regularized linear model",
        rounds=(
            ExplorationRound(
                round_number=1,
                hypothesis="Baseline",
                optimization_direction="baseline",
                intended_changes=("fit baseline",),
            ),
        ),
        primary_metric="roc_auc",
        target_metric=0.9,
        stop_conditions=("target reached",),
        risks=("validation overfitting",),
        resource_limits={"max_minutes": 30},
        trusted_experience_ids=("exp-trusted",),
        pending_experience_ids=("exp-pending",),
        excluded_pending_experience_ids=(),
        candidate_code_files=(
            CandidateCodeFile(path="train.py", sha256="sha", size_bytes=12),
        ),
        code_fingerprint="code-sha",
        plan_fingerprint="plan-sha",
        state="pending_review",
        created_at="2026-07-15T00:00:00Z",
        created_by="alice",
    )

    payload = snapshot.to_dict()

    assert "version" not in payload
    assert payload["rounds"][0]["round_number"] == 1
    assert payload["candidate_code_files"][0]["path"] == "train.py"


def test_exploration_commands_and_review_snapshots_keep_paths_typed():
    record = RecordExplorationPlanCommand(
        connection_path=Path("workspace.json"),
        code_root=Path("code"),
        dataset_id="ds-1",
        dataset_version=1,
        plan_id="plan-1",
        planning_session_id="session-1",
        user_direction="Improve validation AUC",
        baseline_hypothesis="Fit baseline",
        rounds=(ExplorationRound(1, "Baseline", "baseline", ("fit",)),),
        stop_conditions=("target reached",),
        risks=("validation overfitting",),
        resource_limits={"max_minutes": 30},
        candidate_code_paths=("train.py",),
    )
    approve = ApproveExplorationPlanCommand(
        connection_path=Path("workspace.json"),
        code_root=Path("code"),
        plan_id="plan-1",
    )
    authorize = AuthorizeTrainingCommand(
        connection_path=Path("workspace.json"),
        code_root=Path("code"),
        entry_point="cli_explore",
        dataset_id="ds-1",
        dataset_version=1,
        plan_id="plan-1",
        approval_id="approval-1",
    )

    assert record.code_root == Path("code")
    assert approve.plan_id == "plan-1"
    assert authorize.approval_id == "approval-1"


def test_review_and_authorization_snapshots_serialize_nested_contracts():
    plan = _plan_snapshot()
    approval = ExplorationApprovalSnapshot(
        asset_id="approval-1",
        asset_path="approvals/exploration-plans/plan-1/approval-1.json",
        plan_id="plan-1",
        plan_event_id=plan.asset_id,
        dataset_id="ds-1",
        dataset_version=1,
        dataset_version_fingerprint="version-1",
        plan_fingerprint="plan-sha",
        code_fingerprint="code-sha",
        decision="approved",
        created_at="2026-07-15T00:01:00Z",
        created_by="alice",
    )
    review = ExplorationReviewSnapshot(
        plan=plan,
        approval=approval,
        approval_state="approved",
        code_previews=(
            CandidateCodePreview(
                path="train.py",
                content="print('train')\n",
                recorded_sha256="sha",
                current_sha256="sha",
                state="current",
            ),
        ),
    )
    authorization = TrainingAuthorization(
        authorized=True,
        entry_point="cli_explore",
        dataset_id="ds-1",
        dataset_version=1,
        dataset_version_fingerprint="version-1",
        plan_id="plan-1",
        plan_event_id="plan-event-1",
        approval_id="approval-1",
        plan_fingerprint="plan-sha",
        code_fingerprint="code-sha",
        round_count=2,
        authorized_at="2026-07-15T00:02:00Z",
        authorized_by="alice",
    )

    assert review.to_dict()["approval"]["decision"] == "approved"
    assert authorization.to_dict()["authorized"] is True
    assert authorization.to_dict()["round_count"] == 2


def _plan_snapshot() -> ExplorationPlanSnapshot:
    return ExplorationPlanSnapshot(
        asset_id="plan-event-1",
        asset_path="raw-records/exploration-plans/plan-1/plan-event-1.json",
        plan_id="plan-1",
        planning_session_id="session-1",
        dataset_id="ds-1",
        dataset_version=1,
        dataset_content_fingerprint="content-1",
        dataset_version_fingerprint="version-1",
        user_direction="Improve validation AUC",
        baseline_hypothesis="Fit baseline",
        rounds=(ExplorationRound(1, "Baseline", "baseline", ("fit",)),),
        primary_metric="roc_auc",
        target_metric=0.9,
        stop_conditions=("target reached",),
        risks=("validation overfitting",),
        resource_limits={"max_minutes": 30},
        trusted_experience_ids=(),
        pending_experience_ids=(),
        excluded_pending_experience_ids=(),
        candidate_code_files=(CandidateCodeFile("train.py", "sha", 12),),
        code_fingerprint="code-sha",
        plan_fingerprint="plan-sha",
        state="pending_review",
        created_at="2026-07-15T00:00:00Z",
        created_by="alice",
    )
