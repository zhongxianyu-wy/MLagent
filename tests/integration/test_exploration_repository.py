import json

import pytest

from src.domain.exploration_repository import ExplorationRepository
from src.domain.memory_repository import MemoryRepository
from src.domain.models import (
    DatasetPreview,
    DatasetVersionSnapshot,
    ExplorationRound,
    RecordExplorationPlanCommand,
    WorkspaceError,
)


@pytest.fixture
def planning_workspace(tmp_path):
    memory_root = tmp_path / "team-memory"
    capacity = MemoryRepository(
        id_factory=lambda: "tmr-1",
        clock=lambda: "2026-07-15T00:00:00Z",
    ).bootstrap(memory_root, actor_id="alice").capacity
    code_root = tmp_path / "code"
    code_root.mkdir()
    (code_root / "train.py").write_text("print('baseline')\n", encoding="utf-8")
    event_ids = iter(("plan-event-1", "plan-event-2", "plan-event-3"))
    approval_ids = iter(("approval-1", "approval-2"))
    repository = ExplorationRepository(
        memory_root,
        event_id_factory=lambda: next(event_ids),
        approval_id_factory=lambda: next(approval_ids),
        audit_id_factory=lambda: "gate-audit-1",
        clock=lambda: "2026-07-15T00:01:00Z",
    )
    return PlanningWorkspace(
        repository=repository,
        memory_root=memory_root,
        code_root=code_root,
        capacity=capacity,
    )


class PlanningWorkspace:
    def __init__(self, repository, memory_root, code_root, capacity):
        self.repository = repository
        self.memory_root = memory_root
        self.code_root = code_root
        self.capacity = capacity

    def command(self, **overrides):
        values = {
            "connection_path": self.memory_root.parent / ".mlagent-workspace.json",
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
                    hypothesis="A regularized baseline is stable",
                    optimization_direction="baseline",
                    intended_changes=("fit logistic regression",),
                ),
                ExplorationRound(
                    round_number=2,
                    hypothesis="Feature selection may improve validation AUC",
                    optimization_direction="feature_selection",
                    intended_changes=("rank features", "refit top features"),
                ),
            ),
            "stop_conditions": ("target reached", "round budget exhausted"),
            "resource_limits": {"max_minutes": 30, "max_parallel_jobs": 1},
            "trusted_experience_ids": ("experience-approved",),
            "pending_experience_ids": (
                "experience-pending",
                "experience-excluded",
            ),
            "excluded_pending_experience_ids": ("experience-excluded",),
            "candidate_code_paths": ("train.py",),
        }
        values.update(overrides)
        return RecordExplorationPlanCommand(**values)

    def record(self, **overrides):
        return self.repository.record_plan(
            self.command(**overrides),
            dataset_snapshot(),
            actor_id="alice",
            capacity=self.capacity,
        )


def test_record_plan_appends_events_without_sop_style_versions(planning_workspace):
    first = planning_workspace.record()
    second = planning_workspace.record(
        user_direction="Add reviewed feature selection",
    )

    assert first.asset_id == "plan-event-1"
    assert second.asset_id == "plan-event-2"
    assert not hasattr(first, "version")
    assert planning_workspace.repository.current("plan-1") == second
    assert planning_workspace.repository.list_plan_events("plan-1") == (
        first,
        second,
    )
    assert len(list((planning_workspace.memory_root / "sops").glob("**/*"))) == 0


def test_record_plan_keeps_experience_confidence_and_exclusions_separate(
    planning_workspace,
):
    plan = planning_workspace.record()

    assert plan.trusted_experience_ids == ("experience-approved",)
    assert plan.pending_experience_ids == (
        "experience-pending",
        "experience-excluded",
    )
    assert plan.excluded_pending_experience_ids == ("experience-excluded",)


def test_record_plan_uses_dataset_metric_and_fingerprints(planning_workspace):
    plan = planning_workspace.record()

    assert plan.dataset_id == "ds-1"
    assert plan.dataset_version == 1
    assert plan.dataset_content_fingerprint == "content-1"
    assert plan.dataset_version_fingerprint == "dataset-version-1"
    assert plan.primary_metric == "roc_auc"
    assert plan.target_metric == 0.91
    assert len(plan.plan_fingerprint) == 64
    assert len(plan.code_fingerprint) == 64


def test_approval_binds_current_plan_dataset_and_code_fingerprints(
    planning_workspace,
):
    plan = planning_workspace.record()
    approval = planning_workspace.repository.approve_current(
        plan.plan_id,
        code_root=planning_workspace.code_root,
        actor_id="alice",
        capacity=planning_workspace.capacity,
    )

    assert approval.asset_id == "approval-1"
    assert approval.plan_event_id == plan.asset_id
    assert approval.dataset_version_fingerprint == plan.dataset_version_fingerprint
    assert approval.plan_fingerprint == plan.plan_fingerprint
    assert approval.code_fingerprint == plan.code_fingerprint
    assert approval.decision == "approved"

    review = planning_workspace.repository.review(
        plan.plan_id,
        planning_workspace.code_root,
    )
    assert review.approval_state == "approved"
    assert review.code_previews[0].content == "print('baseline')\n"
    assert review.code_previews[0].state == "current"


def test_plan_or_code_change_makes_prior_approval_stale(planning_workspace):
    plan = planning_workspace.record()
    planning_workspace.repository.approve_current(
        plan.plan_id,
        planning_workspace.code_root,
        actor_id="alice",
        capacity=planning_workspace.capacity,
    )
    planning_workspace.record(user_direction="Change the current direction")

    review = planning_workspace.repository.review(
        plan.plan_id,
        planning_workspace.code_root,
    )
    assert review.approval_state == "approval_stale"

    planning_workspace.repository.approve_current(
        plan.plan_id,
        planning_workspace.code_root,
        actor_id="alice",
        capacity=planning_workspace.capacity,
    )
    (planning_workspace.code_root / "train.py").write_text(
        "print('changed')\n",
        encoding="utf-8",
    )
    changed_review = planning_workspace.repository.review(
        plan.plan_id,
        planning_workspace.code_root,
    )
    assert changed_review.approval_state == "approval_stale"
    assert changed_review.code_previews[0].state == "changed"


@pytest.mark.parametrize(
    ("overrides", "code"),
    [
        ({"user_direction": ""}, "incomplete_exploration_plan"),
        ({"rounds": ()}, "incomplete_exploration_plan"),
        ({"stop_conditions": ()}, "incomplete_exploration_plan"),
        ({"resource_limits": {}}, "incomplete_exploration_plan"),
        ({"candidate_code_paths": ()}, "incomplete_exploration_plan"),
        (
            {
                "trusted_experience_ids": ("experience-1",),
                "pending_experience_ids": ("experience-1",),
            },
            "invalid_experience_references",
        ),
        (
            {
                "pending_experience_ids": ("experience-1",),
                "excluded_pending_experience_ids": ("experience-2",),
            },
            "invalid_experience_references",
        ),
    ],
)
def test_record_plan_rejects_incomplete_or_ambiguous_structure(
    planning_workspace,
    overrides,
    code,
):
    with pytest.raises(WorkspaceError) as caught:
        planning_workspace.record(**overrides)

    assert caught.value.code == code


@pytest.mark.parametrize("candidate_path", ("../outside.py", "/tmp/outside.py"))
def test_record_plan_rejects_code_paths_outside_code_root(
    planning_workspace,
    candidate_path,
):
    with pytest.raises(WorkspaceError) as caught:
        planning_workspace.record(candidate_code_paths=(candidate_path,))

    assert caught.value.code == "unsafe_candidate_code_path"


def test_record_plan_rejects_symlinked_or_changed_code(planning_workspace, tmp_path):
    outside = tmp_path / "outside.py"
    outside.write_text("print('outside')\n", encoding="utf-8")
    (planning_workspace.code_root / "linked.py").symlink_to(outside)

    with pytest.raises(WorkspaceError) as caught:
        planning_workspace.record(candidate_code_paths=("linked.py",))
    assert caught.value.code == "unsafe_candidate_code_path"

    plan = planning_workspace.record()
    (planning_workspace.code_root / "train.py").write_text(
        "print('changed before approval')\n",
        encoding="utf-8",
    )
    with pytest.raises(WorkspaceError) as changed:
        planning_workspace.repository.approve_current(
            plan.plan_id,
            planning_workspace.code_root,
            actor_id="alice",
            capacity=planning_workspace.capacity,
        )
    assert changed.value.code == "candidate_code_changed"


def test_load_rejects_tampered_plan_fingerprint(planning_workspace):
    plan = planning_workspace.record()
    event_path = planning_workspace.memory_root / plan.asset_path
    payload = json.loads(event_path.read_text(encoding="utf-8"))
    payload["user_direction"] = "tampered"
    event_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(WorkspaceError) as caught:
        planning_workspace.repository.current(plan.plan_id)

    assert caught.value.code == "invalid_exploration_plan"


def dataset_snapshot() -> DatasetVersionSnapshot:
    return DatasetVersionSnapshot(
        asset_id="ds-1-v0001",
        asset_path="datasets/ds-1/v0001/manifest.json",
        dataset_id="ds-1",
        version=1,
        state="confirmed",
        schema_version=1,
        created_at="2026-07-15T00:00:00Z",
        created_by="alice",
        content_fingerprint="content-1",
        version_fingerprint="dataset-version-1",
        source_files=(),
        sample_id_col="sample_id",
        label_col="group",
        task_type="binary",
        class_labels=("case", "control"),
        positive_class="case",
        primary_metric="roc_auc",
        target_metric=0.91,
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
            omitted_count=11,
        ),
        warnings=(),
        files={
            "features": "features.csv",
            "labels": "labels.csv",
            "split": "split.csv",
        },
    )
