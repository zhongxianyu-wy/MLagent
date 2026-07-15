from pathlib import Path

from src.domain.models import (
    CandidateCodeFile,
    CandidateCodePreview,
    CapacityStatus,
    DatasetInspection,
    DatasetPreview,
    DatasetVersionSnapshot,
    ExplorationPlanSnapshot,
    ExplorationReviewSnapshot,
    ExplorationRound,
    RemoteStatus,
    WorkspaceSnapshot,
)
from src.ui.app import _module_anchor
from src.ui.shell import GLOBAL_STATUS_VOCABULARY, NAVIGATION, build_shell_state


def workspace_snapshot() -> WorkspaceSnapshot:
    return WorkspaceSnapshot(
        repository_id="tmr-1",
        schema_version=1,
        repository_path=Path("/tmp/team-memory"),
        actor_id="alice",
        managed_paths=("datasets", "runs"),
        index_path=Path("/tmp/team-memory/.mlagent-local/index.sqlite3"),
        indexed_assets=1,
        git_state="initialized",
        remote=RemoteStatus(
            state="reachable",
            url="/tmp/team-memory.git",
            message="Origin is reachable.",
        ),
        capacity=CapacityStatus(
            state="ok",
            bytes_used=120,
            largest_file_bytes=80,
            max_file_bytes=100_000_000,
            max_repository_bytes=20_000_000_000,
        ),
        ready=True,
        issues=(),
    )


def dataset_version() -> DatasetVersionSnapshot:
    return DatasetVersionSnapshot(
        asset_id="ds-1-v0001",
        asset_path="datasets/ds-1/v0001/manifest.json",
        dataset_id="ds-1",
        version=1,
        state="confirmed",
        schema_version=1,
        created_at="2026-07-14T00:00:00Z",
        created_by="alice",
        content_fingerprint="content-sha",
        version_fingerprint="version-sha",
        source_files=(),
        sample_id_col="sample_id",
        label_col="group",
        task_type="binary",
        class_labels=("case", "control"),
        positive_class="case",
        primary_metric="roc_auc",
        target_metric=0.9,
        split_strategy="train_only",
        test_ratio=None,
        random_seed=42,
        sample_count=12,
        feature_count=2,
        dtypes={"f1": "float64", "f2": "int64"},
        missing_rates={"f1": 0.0, "f2": 0.0},
        class_distribution={"case": 6, "control": 6},
        preview=DatasetPreview(
            columns=("sample_id", "f1", "f2", "group"),
            rows=(("s1", 0.1, 1, "case"),),
            omitted_count=2,
        ),
        warnings=(),
        files={
            "features": "features.csv",
            "labels": "labels.csv",
            "split": "split.csv",
        },
    )


def dataset_inspection() -> DatasetInspection:
    return DatasetInspection(
        status="Pending confirmation",
        feature_path=Path("features.csv"),
        label_path=Path("labels.csv"),
        content_fingerprint="inspection-sha",
        inferred_sample_id_col="sample_id",
        inferred_label_col="group",
        inferred_task_type="binary",
        class_labels=("case", "control"),
        sample_count=12,
        feature_count=2,
        dtypes={"f1": "float64", "f2": "int64"},
        missing_rates={"f1": 0.0, "f2": 0.0},
        class_distribution={"case": 6, "control": 6},
        preview=DatasetPreview(
            columns=("sample_id", "f1", "f2", "group"),
            rows=(("s1", 0.1, 1, "case"),),
            omitted_count=2,
        ),
        unresolved_fields=(
            "positive_class",
            "primary_metric",
            "split_strategy",
            "target_metric",
        ),
        warnings=(),
        blockers=(),
        elapsed_ms=4,
    )


def test_shell_has_exactly_six_primary_modules_and_context_fields():
    shell = build_shell_state(workspace_snapshot())

    assert NAVIGATION == (
        "Code Review",
        "Dataset Overview",
        "Run Status",
        "SOP Overview",
        "Experience Review",
        "Lineage Trace",
    )
    assert shell.navigation == NAVIGATION
    assert tuple(shell.context) == ("workspace", "dataset", "run", "git", "writer")
    assert shell.context == {
        "workspace": "tmr-1",
        "dataset": "Not started",
        "run": "Not started",
        "git": "Success",
        "writer": "alice",
    }
    assert shell.module_status["Dataset Overview"] == "Not started"


def test_module_heading_anchor_tracks_the_selected_module():
    assert _module_anchor("Code Review") == "code-review"
    assert _module_anchor("Run Status") == "run-status"


def test_shell_uses_real_pending_inspection_in_context_and_module_status():
    shell = build_shell_state(
        workspace_snapshot(),
        inspection=dataset_inspection(),
    )

    assert shell.context["dataset"] == "Pending confirmation"
    assert shell.module_status["Dataset Overview"] == "Pending confirmation"
    assert shell.inspection == dataset_inspection()


def test_shell_exposes_the_approved_global_status_vocabulary():
    assert GLOBAL_STATUS_VOCABULARY == (
        "Not started",
        "Pending confirmation",
        "Running",
        "Success",
        "Failed",
        "Pending review",
        "Approved",
        "Rejected",
        "Pending sync",
        "Conflict",
    )


def test_shell_uses_confirmed_dataset_version_in_context_and_module_status():
    shell = build_shell_state(workspace_snapshot(), dataset_version())

    assert shell.context["dataset"] == "ds-1 v1"
    assert shell.module_status["Dataset Overview"] == "Success"
    assert shell.dataset == dataset_version()


def test_shell_uses_exploration_review_in_run_context_and_module_status():
    review = exploration_review("pending_review")

    shell = build_shell_state(
        workspace_snapshot(),
        dataset_version(),
        exploration_review=review,
    )

    assert shell.context["run"] == "Pending review"
    assert shell.module_status["Run Status"] == "Pending review"
    assert shell.exploration_review == review


def exploration_review(state: str) -> ExplorationReviewSnapshot:
    plan = ExplorationPlanSnapshot(
        asset_id="plan-event-1",
        asset_path="raw-records/exploration-plans/plan-1/plan-event-1.json",
        plan_id="plan-1",
        planning_session_id="session-1",
        dataset_id="ds-1",
        dataset_version=1,
        dataset_content_fingerprint="content-sha",
        dataset_version_fingerprint="version-sha",
        user_direction="Improve validation AUC",
        baseline_hypothesis="Fit baseline",
        rounds=(ExplorationRound(1, "Baseline", "baseline", ("fit",)),),
        primary_metric="roc_auc",
        target_metric=0.9,
        stop_conditions=("target reached",),
        risks=("validation overfitting",),
        resource_limits={"max_minutes": 30},
        trusted_experience_ids=("experience-approved",),
        pending_experience_ids=("experience-pending",),
        excluded_pending_experience_ids=(),
        candidate_code_files=(CandidateCodeFile("train.py", "sha", 12),),
        code_fingerprint="code-sha",
        plan_fingerprint="plan-sha",
        state="pending_review",
        created_at="2026-07-15T00:00:00Z",
        created_by="alice",
    )
    return ExplorationReviewSnapshot(
        plan=plan,
        approval=None,
        approval_state=state,
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
