import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest

from src.domain.experience_repository import ExperienceRepository
from src.domain.memory_repository import MemoryRepository
from src.domain.models import ReviewExperienceCommand, WorkspaceError


@pytest.fixture
def experience_workspace(tmp_path):
    root = tmp_path / "team-memory"
    status = MemoryRepository(
        id_factory=lambda: "tmr-experience",
        clock=lambda: "2026-07-17T00:00:00Z",
    ).bootstrap(root, actor_id="alice")
    return ExperienceWorkspace(root, status.capacity)


class ExperienceWorkspace:
    def __init__(self, root, capacity):
        self.root = root
        self.capacity = capacity
        self.clock_value = "2026-07-17T00:01:00Z"
        self.repository = ExperienceRepository(
            root,
            clock=lambda: self.clock_value,
        )
        self.write_dataset()

    def write_dataset(self):
        self.write_json(
            "datasets/dataset-1/v0001/manifest.json",
            {
                "asset_type": "dataset_version",
                "asset_id": "dataset-1:v1",
                "dataset_id": "dataset-1",
                "version": 1,
                "primary_metric": "roc_auc",
                "created_at": "2026-07-17T00:00:00Z",
            },
        )

    def seed_instance(
        self,
        instance_id,
        *,
        metric,
        parent_id=None,
        state="completed",
        direction="feature filtering",
        error_code=None,
        error_summary=None,
    ):
        run_id = "run-1"
        event_prefix = instance_id.replace("instance-", "event-")
        if not (self.root / "raw-records/runs/run-1/event-run-start.json").exists():
            self.write_json(
                "raw-records/runs/run-1/event-run-start.json",
                {
                    "asset_type": "run_event",
                    "asset_id": "event-run-start",
                    "run_id": run_id,
                    "event_type": "run_started",
                    "state": "running",
                    "created_at": "2026-07-17T00:00:00Z",
                },
            )
        instance_root = f"runs/{run_id}/instances/{instance_id}"
        self.write_json(
            f"{instance_root}/input.json",
            {
                "run_id": run_id,
                "instance_id": instance_id,
                "dataset_asset_path": "datasets/dataset-1/v0001/manifest.json",
                "hypothesis": f"Evaluate {direction}",
                "optimization_direction": direction,
                "intended_changes": [direction],
            },
        )
        manifest = {
            "asset_type": "training_instance",
            "asset_id": instance_id,
            "run_id": run_id,
            "round_number": 1 if parent_id is None else 2,
            "state": state,
            "parent_instance_id": parent_id,
            "primary_metric_name": "roc_auc",
            "primary_metric_value": metric if state == "completed" else None,
            "error_code": error_code,
            "error_summary": error_summary,
            "optimization_direction": direction,
            "created_at": self.clock_value,
        }
        self.write_json(f"{instance_root}/manifest.json", manifest)
        self.write_json(
            f"raw-records/runs/{run_id}/{event_prefix}.json",
            {
                "asset_type": "run_event",
                "asset_id": event_prefix,
                "run_id": run_id,
                "event_type": f"instance_{state}",
                "state": state,
                "instance_id": instance_id,
                "created_at": self.clock_value,
            },
        )

    def write_json(self, relative, payload):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


def test_session_boundary_extracts_only_new_metric_improvement(
    experience_workspace,
):
    workspace = experience_workspace
    workspace.seed_instance("instance-old", metric=0.7)
    started = workspace.repository.start_session(
        "session-1",
        actor_id="alice",
        capacity=workspace.capacity,
    )
    workspace.clock_value = "2026-07-17T00:02:00Z"
    workspace.seed_instance(
        "instance-new",
        metric=0.8,
        parent_id="instance-old",
    )

    outcome = workspace.repository.complete_session(
        "session-1",
        actor_id="alice",
        capacity=workspace.capacity,
    )

    assert started.outcome == "started"
    assert outcome.outcome == "created"
    assert outcome.new_instance_ids == ("instance-new",)
    assert "instance-old" not in outcome.new_instance_ids
    candidate = workspace.repository.current(outcome.candidate_ids[0])
    assert candidate.state == "pending"
    assert candidate.source_kind == "metric_improvement"
    assert "roc_auc" in candidate.content.conclusion
    assert "0.700000" in candidate.content.conclusion
    assert "0.800000" in candidate.content.conclusion
    assert {item.role for item in candidate.evidence} == {
        "dataset",
        "run",
        "training_instance",
        "raw_record",
    }
    for item in candidate.evidence:
        raw = (workspace.root / item.asset_path).read_bytes()
        assert item.sha256 == hashlib.sha256(raw).hexdigest()


def test_empty_session_records_no_op_without_creating_experience(
    experience_workspace,
):
    workspace = experience_workspace
    workspace.seed_instance("instance-old", metric=0.7)
    workspace.repository.start_session(
        "session-empty",
        actor_id="alice",
        capacity=workspace.capacity,
    )

    outcome = workspace.repository.complete_session(
        "session-empty",
        actor_id="alice",
        capacity=workspace.capacity,
    )

    assert outcome.outcome == "no_op"
    assert outcome.candidate_ids == ()
    assert not any((workspace.root / "experiences").rglob("*.json"))
    stop = json.loads(
        (
            workspace.root
            / "raw-records/sessions/session-empty/stop.json"
        ).read_text(encoding="utf-8")
    )
    assert stop["outcome"] == "no_op"


def test_repeated_stop_reuses_prior_outcome_without_new_files(
    experience_workspace,
):
    workspace = experience_workspace
    workspace.seed_instance("instance-old", metric=0.7)
    workspace.repository.start_session(
        "session-1",
        actor_id="alice",
        capacity=workspace.capacity,
    )
    workspace.seed_instance(
        "instance-new",
        metric=0.8,
        parent_id="instance-old",
    )
    first = workspace.repository.complete_session(
        "session-1",
        actor_id="alice",
        capacity=workspace.capacity,
    )
    before = sorted(
        path.relative_to(workspace.root).as_posix()
        for path in workspace.root.rglob("*.json")
    )

    second = workspace.repository.complete_session(
        "session-1",
        actor_id="alice",
        capacity=workspace.capacity,
    )

    after = sorted(
        path.relative_to(workspace.root).as_posix()
        for path in workspace.root.rglob("*.json")
    )
    assert second.outcome == "already_completed"
    assert second.candidate_ids == ()
    assert first.candidate_ids
    assert after == before


def test_failed_child_creates_bounded_failure_experience(experience_workspace):
    workspace = experience_workspace
    workspace.seed_instance("instance-old", metric=0.7)
    workspace.repository.start_session(
        "session-failure",
        actor_id="alice",
        capacity=workspace.capacity,
    )
    workspace.seed_instance(
        "instance-failed",
        metric=None,
        parent_id="instance-old",
        state="failed",
        direction="batch correction",
        error_code="singular_matrix",
        error_summary="Covariates made the design matrix singular.",
    )

    outcome = workspace.repository.complete_session(
        "session-failure",
        actor_id="alice",
        capacity=workspace.capacity,
    )

    candidate = workspace.repository.current(outcome.candidate_ids[0])
    assert candidate.source_kind == "training_failure"
    assert "singular_matrix" in candidate.content.conclusion
    assert "design matrix singular" in candidate.content.failure_boundary


def test_baseline_stopped_and_timed_out_instances_do_not_create_candidates(
    experience_workspace,
):
    workspace = experience_workspace
    workspace.repository.start_session(
        "session-noise",
        actor_id="alice",
        capacity=workspace.capacity,
    )
    workspace.seed_instance("instance-baseline", metric=0.7)
    workspace.seed_instance(
        "instance-stopped",
        metric=None,
        parent_id="instance-baseline",
        state="stopped",
        error_code="user_stop",
        error_summary="Stopped by user.",
    )
    workspace.seed_instance(
        "instance-timeout",
        metric=None,
        parent_id="instance-baseline",
        state="timed_out",
        error_code="timeout",
        error_summary="Timed out.",
    )

    outcome = workspace.repository.complete_session(
        "session-noise",
        actor_id="alice",
        capacity=workspace.capacity,
    )

    assert outcome.outcome == "no_op"


def test_missing_session_marker_fails_without_fabricating_records(
    experience_workspace,
):
    with pytest.raises(WorkspaceError, match="SessionStart"):
        experience_workspace.repository.complete_session(
            "missing-session",
            actor_id="alice",
            capacity=experience_workspace.capacity,
        )

    assert not (
        experience_workspace.root
        / "raw-records/sessions/missing-session"
    ).exists()


def test_approval_appends_trusted_event_and_preserves_candidate_wording(
    experience_workspace,
):
    workspace = experience_workspace
    pending = create_pending(workspace, "session-review", "instance-review")
    original = pending.content
    revised = replace(
        original,
        conclusion="Reviewed feature filtering improvement.",
        confidence=0.9,
    )

    trusted = workspace.repository.review(
        ReviewExperienceCommand(
            connection_path=Path("unused.json"),
            experience_id=pending.asset_id,
            decision="approve",
            content=revised,
        ),
        actor_id="reviewer",
        capacity=workspace.capacity,
    )

    assert trusted.state == "trusted"
    assert trusted.previous_event_id == pending.event_id
    assert trusted.content == revised
    assert trusted.reviewed_by == "reviewer"
    history = workspace.repository.history(pending.asset_id)
    assert tuple(item.state for item in history) == ("pending", "trusted")
    assert history[0].content == original
    assert history[0].reviewed_by is None


def test_pending_can_be_rejected_or_marked_conflict(experience_workspace):
    workspace = experience_workspace
    first = create_pending(workspace, "session-first", "instance-first")
    second = create_pending(
        workspace,
        "session-second",
        "instance-second",
        parent_id="instance-first",
        parent_metric=0.8,
        metric=0.85,
    )

    conflict = workspace.repository.review(
        ReviewExperienceCommand(
            connection_path=Path("unused.json"),
            experience_id=first.asset_id,
            decision="conflict",
            content=first.content,
            related_experience_id=second.asset_id,
        ),
        actor_id="reviewer",
        capacity=workspace.capacity,
    )
    rejected = workspace.repository.review(
        ReviewExperienceCommand(
            connection_path=Path("unused.json"),
            experience_id=second.asset_id,
            decision="reject",
            content=second.content,
        ),
        actor_id="reviewer",
        capacity=workspace.capacity,
    )

    assert conflict.state == "conflict"
    assert conflict.relation_type == "conflicts_with"
    assert conflict.related_experience_id == second.asset_id
    assert rejected.state == "rejected"


def test_conflict_can_be_resolved_by_approval(experience_workspace):
    workspace = experience_workspace
    first = create_pending(workspace, "session-first", "instance-first")
    second = create_pending(
        workspace,
        "session-second",
        "instance-second",
        parent_id="instance-first",
        parent_metric=0.8,
        metric=0.85,
    )
    workspace.repository.review(
        ReviewExperienceCommand(
            connection_path=Path("unused.json"),
            experience_id=first.asset_id,
            decision="conflict",
            content=first.content,
            related_experience_id=second.asset_id,
        ),
        actor_id="reviewer",
        capacity=workspace.capacity,
    )

    trusted = workspace.repository.review(
        ReviewExperienceCommand(
            connection_path=Path("unused.json"),
            experience_id=first.asset_id,
            decision="approve",
            content=replace(first.content, confidence=0.85),
        ),
        actor_id="reviewer-2",
        capacity=workspace.capacity,
    )

    assert trusted.state == "trusted"
    assert trusted.relation_type is None
    assert tuple(
        item.state for item in workspace.repository.history(first.asset_id)
    ) == ("pending", "conflict", "trusted")


def test_trusted_experience_can_be_superseded_only_by_another_trusted_head(
    experience_workspace,
):
    workspace = experience_workspace
    old = approve(
        workspace,
        create_pending(workspace, "session-old", "instance-old-new"),
    )
    replacement = approve(
        workspace,
        create_pending(
            workspace,
            "session-replacement",
            "instance-replacement",
            parent_id="instance-old-new",
            parent_metric=0.8,
            metric=0.9,
        ),
    )

    superseded = workspace.repository.review(
        ReviewExperienceCommand(
            connection_path=Path("unused.json"),
            experience_id=old.asset_id,
            decision="supersede",
            content=old.content,
            related_experience_id=replacement.asset_id,
        ),
        actor_id="reviewer",
        capacity=workspace.capacity,
    )

    assert superseded.state == "superseded"
    assert superseded.relation_type == "superseded_by"
    assert superseded.related_experience_id == replacement.asset_id
    assert workspace.repository.current(replacement.asset_id).state == "trusted"


@pytest.mark.parametrize(
    ("start_state", "decision"),
    (
        ("trusted", "reject"),
        ("rejected", "approve"),
        ("rejected", "conflict"),
        ("superseded", "approve"),
    ),
)
def test_illegal_review_transitions_write_no_event(
    experience_workspace,
    start_state,
    decision,
):
    workspace = experience_workspace
    pending = create_pending(workspace, "session-illegal", "instance-illegal")
    if start_state == "trusted":
        current = approve(workspace, pending)
    elif start_state == "rejected":
        current = workspace.repository.review(
            ReviewExperienceCommand(
                Path("unused.json"),
                pending.asset_id,
                "reject",
                pending.content,
            ),
            actor_id="reviewer",
            capacity=workspace.capacity,
        )
    else:
        current = approve(workspace, pending)
        replacement = approve(
            workspace,
            create_pending(
                workspace,
                "session-replacement",
                "instance-replacement",
                parent_id="instance-illegal",
                parent_metric=0.8,
                metric=0.9,
            ),
        )
        current = workspace.repository.review(
            ReviewExperienceCommand(
                Path("unused.json"),
                current.asset_id,
                "supersede",
                current.content,
                replacement.asset_id,
            ),
            actor_id="reviewer",
            capacity=workspace.capacity,
        )
    before = tuple(workspace.repository.history(current.asset_id))
    related = (
        create_pending(
            workspace,
            "session-related",
            "instance-related",
            parent_id="instance-replacement"
            if start_state == "superseded"
            else "instance-illegal",
            parent_metric=0.9 if start_state == "superseded" else 0.8,
            metric=0.95,
        ).asset_id
        if decision == "conflict"
        else None
    )

    with pytest.raises(WorkspaceError, match="transition"):
        workspace.repository.review(
            ReviewExperienceCommand(
                Path("unused.json"),
                current.asset_id,
                decision,
                current.content,
                related,
            ),
            actor_id="reviewer",
            capacity=workspace.capacity,
        )

    assert tuple(workspace.repository.history(current.asset_id)) == before


def test_experience_lifecycle_never_changes_sop_or_model_assets(
    experience_workspace,
):
    workspace = experience_workspace
    workspace.write_json(
        "sops/sop-1/v0001/manifest.json",
        {"asset_type": "sop_version", "asset_id": "sop-1:v1"},
    )
    model_path = workspace.root / "models/model-1/model.joblib"
    model_path.parent.mkdir(parents=True, exist_ok=True)
    model_path.write_bytes(b"formal-model")
    before = governed_bytes(workspace.root, ("sops", "models"))
    pending = create_pending(workspace, "session-isolation", "instance-isolation")
    trusted = approve(workspace, pending)

    assert trusted.state == "trusted"
    assert governed_bytes(workspace.root, ("sops", "models")) == before


def test_changed_direct_evidence_invalidates_experience_projection(
    experience_workspace,
):
    workspace = experience_workspace
    pending = create_pending(workspace, "session-tamper", "instance-tamper")
    dataset_path = (
        workspace.root / "datasets/dataset-1/v0001/manifest.json"
    )
    dataset_path.write_text('{"tampered": true}\n', encoding="utf-8")

    with pytest.raises(WorkspaceError, match="missing or changed"):
        workspace.repository.current(pending.asset_id)


def test_concurrent_review_heads_fail_closed(experience_workspace):
    workspace = experience_workspace
    pending = create_pending(
        workspace,
        "session-concurrent",
        "instance-concurrent",
    )
    trusted = approve(workspace, pending)
    trusted_path = workspace.root / trusted.asset_path
    concurrent = json.loads(trusted_path.read_text(encoding="utf-8"))
    concurrent["asset_id"] = "experience-event-concurrent"
    concurrent["state"] = "rejected"
    concurrent["decision"] = "reject"
    concurrent["content"]["conclusion"] = "Concurrent rejection."
    workspace.write_json(
        (
            f"experiences/{pending.asset_id}/"
            "experience-event-concurrent.json"
        ),
        concurrent,
    )

    with pytest.raises(WorkspaceError, match="concurrent heads"):
        workspace.repository.current(pending.asset_id)


def test_search_partitions_trusted_and_optional_low_confidence_guidance(
    experience_workspace,
):
    workspace = experience_workspace
    pending = create_pending(
        workspace,
        "session-search-pending",
        "instance-search-pending",
    )
    trusted_pending = create_pending(
        workspace,
        "session-search-trusted",
        "instance-search-trusted",
        parent_id="instance-search-pending",
        parent_metric=0.8,
        metric=0.9,
    )
    trusted = approve(workspace, trusted_pending)
    rejected_pending = create_pending(
        workspace,
        "session-search-rejected",
        "instance-search-rejected",
        parent_id="instance-search-trusted",
        parent_metric=0.9,
        metric=0.95,
    )
    workspace.repository.review(
        ReviewExperienceCommand(
            Path("unused.json"),
            rejected_pending.asset_id,
            "reject",
            rejected_pending.content,
        ),
        actor_id="reviewer",
        capacity=workspace.capacity,
    )

    trusted_results, pending_results = workspace.repository.search(
        "feature filtering roc_auc",
        dataset_id="dataset-1",
        include_pending=True,
    )

    assert {item.experience.asset_id for item in trusted_results} == {
        trusted.asset_id
    }
    assert {item.experience.asset_id for item in pending_results} == {
        pending.asset_id
    }
    assert all(
        item.why_applicable
        for item in (*trusted_results, *pending_results)
    )
    without_pending = workspace.repository.search(
        "feature filtering roc_auc",
        include_pending=False,
    )
    assert without_pending[1] == ()


def create_pending(
    workspace,
    session_id,
    instance_id,
    *,
    parent_id="instance-parent",
    parent_metric=0.7,
    metric=0.8,
):
    if not (
        workspace.root
        / f"runs/run-1/instances/{parent_id}/manifest.json"
    ).exists():
        workspace.seed_instance(parent_id, metric=parent_metric)
    workspace.repository.start_session(
        session_id,
        actor_id="alice",
        capacity=workspace.capacity,
    )
    workspace.seed_instance(
        instance_id,
        metric=metric,
        parent_id=parent_id,
    )
    outcome = workspace.repository.complete_session(
        session_id,
        actor_id="alice",
        capacity=workspace.capacity,
    )
    return workspace.repository.current(outcome.candidate_ids[0])


def approve(workspace, pending):
    return workspace.repository.review(
        ReviewExperienceCommand(
            Path("unused.json"),
            pending.asset_id,
            "approve",
            replace(pending.content, confidence=0.9),
        ),
        actor_id="reviewer",
        capacity=workspace.capacity,
    )


def governed_bytes(root, managed):
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for name in managed
        for path in (root / name).rglob("*")
        if path.is_file()
    }
