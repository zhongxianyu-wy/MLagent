from pathlib import Path

from src.domain.models import CapacityStatus, RemoteStatus, WorkspaceSnapshot
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

