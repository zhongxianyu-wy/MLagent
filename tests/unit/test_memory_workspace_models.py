from pathlib import Path

from src.domain.models import (
    CapacityStatus,
    RemoteStatus,
    SyncStatusSnapshot,
    WorkspaceError,
    WorkspaceIssue,
    WorkspaceSnapshot,
)


def test_workspace_snapshot_serializes_nested_statuses():
    snapshot = WorkspaceSnapshot(
        repository_id="tmr-1",
        schema_version=1,
        repository_path=Path("/tmp/team-memory"),
        actor_id="alice",
        managed_paths=("datasets", "runs"),
        index_path=Path("/tmp/team-memory/.mlagent-local/index.sqlite3"),
        indexed_assets=1,
        git_state="initialized",
        remote=RemoteStatus(
            state="not_configured",
            url=None,
            message="No origin remote configured.",
        ),
        capacity=CapacityStatus(
            state="ok",
            bytes_used=120,
            largest_file_bytes=80,
            max_file_bytes=100_000_000,
            max_repository_bytes=20_000_000_000,
        ),
        sync=SyncStatusSnapshot(
            state="not_configured",
            branch="main",
            local_head="local-sha",
            remote_head=None,
            ahead_count=0,
            behind_count=0,
            changed_managed_paths=(),
            conflict_paths=(),
            last_attempt_at=None,
            last_success_at=None,
            sync_commit=None,
            message="No origin remote configured.",
            next_action="Configure the Team Memory origin.",
        ),
        ready=True,
        issues=(),
    )

    payload = snapshot.to_dict()

    assert payload["repository_path"] == "/tmp/team-memory"
    assert payload["managed_paths"] == ["datasets", "runs"]
    assert payload["remote"]["state"] == "not_configured"
    assert payload["capacity"]["bytes_used"] == 120
    assert payload["sync"]["state"] == "not_configured"


def test_workspace_error_exposes_stable_actionable_payload():
    error = WorkspaceError(
        code="unsupported_schema",
        message="Schema version 2 is not supported.",
        next_action="Use a repository with schema version 1.",
    )

    assert error.to_dict() == {
        "code": "unsupported_schema",
        "message": "Schema version 2 is not supported.",
        "next_action": "Use a repository with schema version 1.",
    }
    assert str(error) == "Schema version 2 is not supported."


def test_workspace_issue_exposes_stable_actionable_payload():
    issue = WorkspaceIssue(
        code="repository_capacity_warning",
        message="Team Memory is approaching its capacity limit.",
        next_action="Archive approved assets before the hard limit.",
    )

    assert issue.to_dict() == {
        "code": "repository_capacity_warning",
        "message": "Team Memory is approaching its capacity limit.",
        "next_action": "Archive approved assets before the hard limit.",
    }
