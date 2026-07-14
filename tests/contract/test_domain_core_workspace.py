import json

import pytest

from src.domain.core import DomainCore
from src.domain.models import BootstrapMemoryCommand, WorkspaceError


def test_domain_core_bootstrap_writes_local_connection_and_builds_index(tmp_path):
    repository_path = tmp_path / "team-memory"
    connection_path = tmp_path / ".mlagent-workspace.json"
    core = DomainCore(
        id_factory=lambda: "tmr-1",
        clock=lambda: "2026-07-14T00:00:00Z",
    )

    snapshot = core.bootstrap_memory(
        BootstrapMemoryCommand(
            repository_path=repository_path,
            actor_id="alice",
            connection_path=connection_path,
        )
    )

    assert snapshot.ready is True
    assert snapshot.indexed_assets == 1
    assert json.loads(connection_path.read_text()) == {
        "actor_id": "alice",
        "repository_path": str(repository_path.resolve()),
    }
    assert "remote_url" not in connection_path.read_text()


def test_domain_core_reopens_connection_and_rebuilds_deleted_index(tmp_path):
    connection_path = tmp_path / ".mlagent-workspace.json"
    core = DomainCore(
        id_factory=lambda: "tmr-1",
        clock=lambda: "2026-07-14T00:00:00Z",
    )
    created = core.bootstrap_memory(
        BootstrapMemoryCommand(
            repository_path=tmp_path / "team-memory",
            actor_id="alice",
            connection_path=connection_path,
        )
    )
    created.index_path.unlink()

    reopened = core.open_workspace(connection_path)
    rebuilt = core.rebuild_local_index(connection_path)

    assert reopened.repository_id == "tmr-1"
    assert reopened.indexed_assets == 1
    assert rebuilt.asset_count == 1
    assert rebuilt.index_path.is_file()


def test_domain_core_rejects_visible_connection_file_inside_team_repository(
    tmp_path,
):
    repository_path = tmp_path / "team-memory"
    core = DomainCore()
    core.bootstrap_memory(
        BootstrapMemoryCommand(
            repository_path=repository_path,
            actor_id="alice",
            connection_path=tmp_path / ".mlagent-workspace.json",
        )
    )

    with pytest.raises(WorkspaceError) as caught:
        core.bootstrap_memory(
            BootstrapMemoryCommand(
                repository_path=repository_path,
                actor_id="alice",
                connection_path=repository_path / "local-config.json",
            )
        )

    assert caught.value.code == "connection_inside_repository"
    assert not (repository_path / "local-config.json").exists()
