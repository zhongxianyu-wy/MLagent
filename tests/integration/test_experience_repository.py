import hashlib
import json
from pathlib import Path

import pytest

from src.domain.experience_repository import ExperienceRepository
from src.domain.memory_repository import MemoryRepository
from src.domain.models import WorkspaceError


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
