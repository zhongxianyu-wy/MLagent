from pathlib import Path

from src.domain.models import (
    CapacityStatus,
    RemoteStatus,
    WorkspaceError,
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
        ready=True,
        issues=(),
    )

    payload = snapshot.to_dict()

    assert payload["repository_path"] == "/tmp/team-memory"
    assert payload["managed_paths"] == ["datasets", "runs"]
    assert payload["remote"]["state"] == "not_configured"
    assert payload["capacity"]["bytes_used"] == 120


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
