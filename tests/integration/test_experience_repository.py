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

    def write_dataset(self, dataset_id="dataset-1"):
        payload = {
            "asset_type": "dataset_version",
            "asset_id": f"{dataset_id}:v1",
            "dataset_id": dataset_id,
            "version": 1,
            "schema_version": 1,
            "content_fingerprint": f"{dataset_id}-content-sha",
            "version_fingerprint": f"{dataset_id}-version-sha",
            "primary_metric": "roc_auc",
            "created_at": "2026-07-17T00:00:00Z",
        }
        payload["manifest_fingerprint"] = governed_payload_fingerprint(
            payload
        )
        self.write_json(
            f"datasets/{dataset_id}/v0001/manifest.json",
            payload,
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
        planning_session_id="session-historical",
        dataset_id="dataset-1",
    ):
        run_id = f"run-{planning_session_id}"
        event_prefix = instance_id.replace("instance-", "event-")
        start_event_id = f"event-{run_id}-start"
        if not (
            self.root / f"raw-records/runs/{run_id}/{start_event_id}.json"
        ).exists():
            write_sealed_run_event(
                self.root
                / f"raw-records/runs/{run_id}/{start_event_id}.json",
                {
                    "asset_type": "run_event",
                    "asset_id": start_event_id,
                    "run_id": run_id,
                    "event_type": "run_started",
                    "state": "running",
                    "dataset_id": dataset_id,
                    "dataset_version": 1,
                    "dataset_content_fingerprint": (
                        f"{dataset_id}-content-sha"
                    ),
                    "dataset_version_fingerprint": (
                        f"{dataset_id}-version-sha"
                    ),
                    "planning_session_id": planning_session_id,
                    "created_at": "2026-07-17T00:00:00Z",
                },
            )
        instance_root = f"runs/{run_id}/instances/{instance_id}"
        input_relative = f"{instance_root}/input.json"
        self.write_json(
            input_relative,
            {
                "run_id": run_id,
                "instance_id": instance_id,
                "dataset_id": dataset_id,
                "dataset_version": 1,
                "dataset_asset_path": (
                    f"datasets/{dataset_id}/v0001/manifest.json"
                ),
                "dataset_content_fingerprint": f"{dataset_id}-content-sha",
                "dataset_version_fingerprint": f"{dataset_id}-version-sha",
                "planning_session_id": planning_session_id,
                "hypothesis": f"Evaluate {direction}",
                "optimization_direction": direction,
                "intended_changes": [direction],
            },
        )
        manifest = {
            "asset_type": "training_instance",
            "asset_id": instance_id,
            "run_id": run_id,
            "dataset_content_fingerprint": f"{dataset_id}-content-sha",
            "dataset_version_fingerprint": f"{dataset_id}-version-sha",
            "round_number": 1 if parent_id is None else 2,
            "state": state,
            "parent_instance_id": parent_id,
            "primary_metric_name": "roc_auc",
            "primary_metric_value": metric if state == "completed" else None,
            "error_code": error_code,
            "error_summary": error_summary,
            "optimization_direction": direction,
            "created_at": self.clock_value,
            "schema_version": 3,
            "files": {"input": "input.json"},
            "file_fingerprints": {
                "input": hashlib.sha256(
                    (self.root / input_relative).read_bytes()
                ).hexdigest()
            },
        }
        manifest["manifest_fingerprint"] = governed_payload_fingerprint(
            manifest
        )
        self.write_json(f"{instance_root}/manifest.json", manifest)
        write_sealed_run_event(
            self.root / f"raw-records/runs/{run_id}/{event_prefix}.json",
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
    workspace.seed_instance(
        "instance-old",
        metric=0.7,
        planning_session_id="session-1",
    )
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
        planning_session_id="session-1",
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
    candidate_payload = json.loads(
        (workspace.root / candidate.asset_path).read_text(encoding="utf-8")
    )
    assert candidate_payload["schema_version"] == 2
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


def test_extraction_accepts_unicode_in_governed_training_evidence(
    experience_workspace,
):
    workspace = experience_workspace
    workspace.seed_instance(
        "instance-parent",
        metric=0.7,
        direction="特征筛选",
        planning_session_id="session-unicode",
    )
    workspace.repository.start_session(
        "session-unicode",
        actor_id="alice",
        capacity=workspace.capacity,
    )
    workspace.seed_instance(
        "instance-child",
        metric=0.8,
        parent_id="instance-parent",
        direction="特征筛选",
        planning_session_id="session-unicode",
    )

    outcome = workspace.repository.complete_session(
        "session-unicode",
        actor_id="alice",
        capacity=workspace.capacity,
    )

    assert outcome.outcome == "created"
    assert "特征筛选" in workspace.repository.current(
        outcome.candidate_ids[0]
    ).content.conclusion


def test_empty_session_records_no_op_without_creating_experience(
    experience_workspace,
):
    workspace = experience_workspace
    workspace.seed_instance(
        "instance-old",
        metric=0.7,
        planning_session_id="session-empty",
    )
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
    workspace.seed_instance(
        "instance-old",
        metric=0.7,
        planning_session_id="session-1",
    )
    workspace.repository.start_session(
        "session-1",
        actor_id="alice",
        capacity=workspace.capacity,
    )
    workspace.seed_instance(
        "instance-new",
        metric=0.8,
        parent_id="instance-old",
        planning_session_id="session-1",
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
    assert second == first
    assert after == before


def test_stop_retry_reuses_candidate_written_before_interruption(
    experience_workspace,
    monkeypatch,
):
    workspace = experience_workspace
    workspace.seed_instance(
        "instance-old",
        metric=0.7,
        planning_session_id="session-retry",
    )
    workspace.repository.start_session(
        "session-retry",
        actor_id="alice",
        capacity=workspace.capacity,
    )
    workspace.seed_instance(
        "instance-new",
        metric=0.8,
        parent_id="instance-old",
        planning_session_id="session-retry",
    )
    original_write = workspace.repository._write_new
    interrupted = False

    def interrupt_before_stop(relative, payload, capacity):
        nonlocal interrupted
        if (
            relative.as_posix()
            == "raw-records/sessions/session-retry/stop.json"
            and not interrupted
        ):
            interrupted = True
            raise WorkspaceError(
                code="simulated_stop_interruption",
                message="Stop write was interrupted.",
                next_action="Retry Stop.",
            )
        return original_write(relative, payload, capacity)

    monkeypatch.setattr(
        workspace.repository,
        "_write_new",
        interrupt_before_stop,
    )
    with pytest.raises(WorkspaceError, match="interrupted"):
        workspace.repository.complete_session(
            "session-retry",
            actor_id="alice",
            capacity=workspace.capacity,
        )
    candidate_files = tuple(
        (workspace.root / "experiences").rglob("*.json")
    )
    assert len(candidate_files) == 1

    monkeypatch.setattr(workspace.repository, "_write_new", original_write)
    recovered = workspace.repository.complete_session(
        "session-retry",
        actor_id="alice",
        capacity=workspace.capacity,
    )

    assert recovered.outcome == "created"
    assert len(recovered.candidate_ids) == 1
    assert tuple((workspace.root / "experiences").rglob("*.json")) == (
        candidate_files[0],
    )


def test_concurrent_session_does_not_extract_another_sessions_instance(
    experience_workspace,
):
    workspace = experience_workspace
    workspace.seed_instance(
        "instance-parent",
        metric=0.7,
        planning_session_id="session-a",
    )
    workspace.repository.start_session(
        "session-a",
        actor_id="alice",
        capacity=workspace.capacity,
    )
    workspace.repository.start_session(
        "session-b",
        actor_id="bob",
        capacity=workspace.capacity,
    )
    workspace.seed_instance(
        "instance-a",
        metric=0.8,
        parent_id="instance-parent",
        planning_session_id="session-a",
    )

    unrelated = workspace.repository.complete_session(
        "session-b",
        actor_id="bob",
        capacity=workspace.capacity,
    )
    owned = workspace.repository.complete_session(
        "session-a",
        actor_id="alice",
        capacity=workspace.capacity,
    )

    assert unrelated.outcome == "no_op"
    assert owned.outcome == "created"
    assert len(owned.candidate_ids) == 1


def test_session_ownership_rejects_tampered_frozen_instance_input(
    experience_workspace,
):
    workspace = experience_workspace
    workspace.seed_instance(
        "instance-parent",
        metric=0.7,
        planning_session_id="session-a",
    )
    workspace.repository.start_session(
        "session-a",
        actor_id="alice",
        capacity=workspace.capacity,
    )
    workspace.seed_instance(
        "instance-b",
        metric=0.8,
        parent_id="instance-parent",
        planning_session_id="session-b",
    )
    input_path = (
        workspace.root
        / "runs/run-session-b/instances/instance-b/input.json"
    )
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    payload["planning_session_id"] = "session-a"
    input_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(WorkspaceError, match="evidence"):
        workspace.repository.complete_session(
            "session-a",
            actor_id="alice",
            capacity=workspace.capacity,
        )

    assert not any((workspace.root / "experiences").rglob("*.json"))


def test_stop_preflights_session_lineage_before_writing_any_assets(
    experience_workspace,
):
    workspace = experience_workspace
    workspace.seed_instance(
        "instance-parent",
        metric=0.7,
        planning_session_id="session-preflight",
    )
    workspace.repository.start_session(
        "session-preflight",
        actor_id="alice",
        capacity=workspace.capacity,
    )
    workspace.seed_instance(
        "instance-child",
        metric=0.8,
        parent_id="instance-parent",
        planning_session_id="session-preflight",
    )
    run_start = (
        workspace.root
        / "raw-records/runs/run-session-preflight/"
        "event-run-session-preflight-start.json"
    )
    payload = json.loads(run_start.read_text(encoding="utf-8"))
    payload["planning_session_id"] = "another-session"
    write_sealed_run_event(run_start, payload)

    with pytest.raises(WorkspaceError, match="evidence"):
        workspace.repository.complete_session(
            "session-preflight",
            actor_id="alice",
            capacity=workspace.capacity,
        )

    assert not any((workspace.root / "experiences").rglob("*.json"))
    assert not (
        workspace.root
        / "raw-records/sessions/session-preflight/stop.json"
    ).exists()


def test_stop_rejects_tampered_run_start_fingerprint_before_writing(
    experience_workspace,
):
    workspace = experience_workspace
    workspace.seed_instance(
        "instance-parent",
        metric=0.7,
        planning_session_id="session-run-seal",
    )
    workspace.repository.start_session(
        "session-run-seal",
        actor_id="alice",
        capacity=workspace.capacity,
    )
    workspace.seed_instance(
        "instance-child",
        metric=0.8,
        parent_id="instance-parent",
        planning_session_id="session-run-seal",
    )
    run_start = (
        workspace.root
        / "raw-records/runs/run-session-run-seal/"
        "event-run-session-run-seal-start.json"
    )
    payload = json.loads(run_start.read_text(encoding="utf-8"))
    payload["dataset_version"] = 2
    workspace.write_json(
        run_start.relative_to(workspace.root).as_posix(),
        payload,
    )

    with pytest.raises(WorkspaceError, match="evidence"):
        workspace.repository.complete_session(
            "session-run-seal",
            actor_id="alice",
            capacity=workspace.capacity,
        )

    assert not any((workspace.root / "experiences").rglob("*.json"))
    assert not (
        workspace.root
        / "raw-records/sessions/session-run-seal/stop.json"
    ).exists()


def test_stop_rejects_dataset_version_mismatch_before_writing(
    experience_workspace,
):
    workspace = experience_workspace
    workspace.seed_instance(
        "instance-parent",
        metric=0.7,
        planning_session_id="session-dataset-lineage",
    )
    workspace.repository.start_session(
        "session-dataset-lineage",
        actor_id="alice",
        capacity=workspace.capacity,
    )
    workspace.seed_instance(
        "instance-child",
        metric=0.8,
        parent_id="instance-parent",
        planning_session_id="session-dataset-lineage",
    )
    run_start = (
        workspace.root
        / "raw-records/runs/run-session-dataset-lineage/"
        "event-run-session-dataset-lineage-start.json"
    )
    payload = json.loads(run_start.read_text(encoding="utf-8"))
    payload["dataset_version"] = 2
    write_sealed_run_event(run_start, payload)

    with pytest.raises(WorkspaceError, match="evidence"):
        workspace.repository.complete_session(
            "session-dataset-lineage",
            actor_id="alice",
            capacity=workspace.capacity,
        )

    assert not any((workspace.root / "experiences").rglob("*.json"))
    assert not (
        workspace.root
        / "raw-records/sessions/session-dataset-lineage/stop.json"
    ).exists()


def test_failed_child_creates_bounded_failure_experience(experience_workspace):
    workspace = experience_workspace
    workspace.seed_instance(
        "instance-old",
        metric=0.7,
        planning_session_id="session-failure",
    )
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
        planning_session_id="session-failure",
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
    workspace.seed_instance(
        "instance-baseline",
        metric=0.7,
        planning_session_id="session-noise",
    )
    workspace.seed_instance(
        "instance-stopped",
        metric=None,
        parent_id="instance-baseline",
        state="stopped",
        error_code="user_stop",
        error_summary="Stopped by user.",
        planning_session_id="session-noise",
    )
    workspace.seed_instance(
        "instance-timeout",
        metric=None,
        parent_id="instance-baseline",
        state="timed_out",
        error_code="timeout",
        error_summary="Timed out.",
        planning_session_id="session-noise",
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
    first = create_pending(
        workspace,
        "session-isolation-first",
        "instance-isolation-first",
    )
    replacement = approve(
        workspace,
        create_pending(
            workspace,
            "session-isolation-replacement",
            "instance-isolation-replacement",
        ),
    )
    trusted = approve(workspace, first)
    assert governed_bytes(workspace.root, ("sops", "models")) == before

    workspace.repository.review(
        ReviewExperienceCommand(
            Path("unused.json"),
            trusted.asset_id,
            "supersede",
            trusted.content,
            replacement.asset_id,
        ),
        actor_id="reviewer",
        capacity=workspace.capacity,
    )
    rejected = create_pending(
        workspace,
        "session-isolation-rejected",
        "instance-isolation-rejected",
    )
    workspace.repository.review(
        ReviewExperienceCommand(
            Path("unused.json"),
            rejected.asset_id,
            "reject",
            rejected.content,
        ),
        actor_id="reviewer",
        capacity=workspace.capacity,
    )
    conflicted = create_pending(
        workspace,
        "session-isolation-conflict",
        "instance-isolation-conflict",
    )
    workspace.repository.review(
        ReviewExperienceCommand(
            Path("unused.json"),
            conflicted.asset_id,
            "conflict",
            conflicted.content,
            replacement.asset_id,
        ),
        actor_id="reviewer",
        capacity=workspace.capacity,
    )

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


def test_evidence_role_must_match_the_cited_asset_identity(
    experience_workspace,
):
    workspace = experience_workspace
    pending = create_pending(
        workspace,
        "session-evidence-identity",
        "instance-evidence-identity",
    )
    event_path = workspace.root / pending.asset_path
    payload = json.loads(event_path.read_text(encoding="utf-8"))
    run_evidence = next(
        item for item in payload["evidence"] if item["role"] == "run"
    )
    run_evidence["asset_id"] = "run-other"
    write_sealed_event(event_path, payload)

    with pytest.raises(WorkspaceError, match="evidence"):
        workspace.repository.current(pending.asset_id)


def test_direct_evidence_assets_must_form_one_run_instance_chain(
    experience_workspace,
):
    workspace = experience_workspace
    first = create_pending(
        workspace,
        "session-chain-first",
        "instance-chain-first",
    )
    second = create_pending(
        workspace,
        "session-chain-second",
        "instance-chain-second",
    )
    first_path = workspace.root / first.asset_path
    first_payload = json.loads(first_path.read_text(encoding="utf-8"))
    second_payload = json.loads(
        (workspace.root / second.asset_path).read_text(encoding="utf-8")
    )
    first_payload["evidence"] = [
        (
            next(
                item
                for item in second_payload["evidence"]
                if item["role"] == "raw_record"
            )
            if item["role"] == "raw_record"
            else item
        )
        for item in first_payload["evidence"]
    ]
    write_sealed_event(first_path, first_payload)

    with pytest.raises(WorkspaceError, match="evidence"):
        workspace.repository.current(first.asset_id)


def test_history_rejects_a_linear_but_illegal_state_transition(
    experience_workspace,
):
    workspace = experience_workspace
    pending = create_pending(
        workspace,
        "session-illegal-chain",
        "instance-illegal-chain",
    )
    trusted = approve(workspace, pending)
    trusted_path = workspace.root / trusted.asset_path
    payload = json.loads(trusted_path.read_text(encoding="utf-8"))
    payload.update(
        {
            "asset_id": "experience-event-illegal-chain",
            "previous_event_id": trusted.event_id,
            "previous_event_fingerprint": trusted.event_fingerprint,
            "created_at": "2026-07-17T00:03:00Z",
            "reviewed_at": "2026-07-17T00:03:00Z",
        }
    )
    write_sealed_event(
        trusted_path.with_name("experience-event-illegal-chain.json"),
        payload,
    )

    with pytest.raises(WorkspaceError, match="invalid"):
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
    write_sealed_event(
        workspace.root
        / f"experiences/{pending.asset_id}/experience-event-concurrent.json",
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


def test_dataset_filter_matches_exact_dataset_identity(
    experience_workspace,
):
    workspace = experience_workspace
    workspace.write_dataset("dataset-10")
    pending = create_pending(
        workspace,
        "session-dataset-10",
        "instance-dataset-10",
        dataset_id="dataset-10",
    )
    approve(workspace, pending)

    trusted, _ = workspace.repository.search(
        "feature filtering",
        dataset_id="dataset-1",
        include_pending=False,
    )

    assert trusted == ()


def create_pending(
    workspace,
    session_id,
    instance_id,
    *,
    parent_id="instance-parent",
    parent_metric=0.7,
    metric=0.8,
    dataset_id="dataset-1",
):
    if not (
        tuple(
            workspace.root.glob(
                f"runs/*/instances/{parent_id}/manifest.json"
            )
        )
    ):
        workspace.seed_instance(
            parent_id,
            metric=parent_metric,
            planning_session_id=session_id,
            dataset_id=dataset_id,
        )
    workspace.repository.start_session(
        session_id,
        actor_id="alice",
        capacity=workspace.capacity,
    )
    workspace.seed_instance(
        instance_id,
        metric=metric,
        parent_id=parent_id,
        planning_session_id=session_id,
        dataset_id=dataset_id,
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


def write_sealed_event(path, payload):
    canonical = dict(payload)
    canonical.pop("event_fingerprint", None)
    payload["event_fingerprint"] = payload_fingerprint(canonical)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def write_sealed_run_event(path, payload):
    canonical = dict(payload)
    canonical.pop("event_fingerprint", None)
    canonical["schema_version"] = 3
    canonical["event_fingerprint"] = governed_payload_fingerprint(canonical)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(canonical, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def payload_fingerprint(payload):
    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def governed_payload_fingerprint(payload):
    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()
