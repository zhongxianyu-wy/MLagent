from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from src.domain.local_index import LocalIndex
from src.domain.memory_repository import MemoryRepository, RepositoryStatus
from src.domain.models import (
    BootstrapMemoryCommand,
    IndexSummary,
    WorkspaceConnection,
    WorkspaceError,
    WorkspaceSnapshot,
)


class DomainCore:
    def __init__(
        self,
        id_factory: Callable[[], str] | None = None,
        clock: Callable[[], str] | None = None,
    ) -> None:
        self.memory_repository = MemoryRepository(
            id_factory=id_factory,
            clock=clock,
        )

    def bootstrap_memory(
        self,
        command: BootstrapMemoryCommand,
    ) -> WorkspaceSnapshot:
        repository = self.memory_repository.bootstrap(
            command.repository_path,
            actor_id=command.actor_id,
            remote_url=command.remote_url,
        )
        connection_path = (
            command.connection_path or Path.cwd() / ".mlagent-workspace.json"
        )
        self._write_connection(
            connection_path,
            WorkspaceConnection(
                repository_path=repository.repository_path,
                actor_id=command.actor_id,
            ),
        )
        index = LocalIndex(repository.repository_path).rebuild()
        return self._snapshot(repository, index)

    def open_workspace(self, connection_path: Path) -> WorkspaceSnapshot:
        connection = self._load_connection(connection_path)
        repository = self.memory_repository.open(
            connection.repository_path,
            actor_id=connection.actor_id,
        )
        index = LocalIndex(repository.repository_path).rebuild()
        return self._snapshot(repository, index)

    def rebuild_local_index(self, connection_path: Path) -> IndexSummary:
        connection = self._load_connection(connection_path)
        repository = self.memory_repository.open(
            connection.repository_path,
            actor_id=connection.actor_id,
        )
        return LocalIndex(repository.repository_path).rebuild()

    @staticmethod
    def _snapshot(
        repository: RepositoryStatus,
        index: IndexSummary,
    ) -> WorkspaceSnapshot:
        return WorkspaceSnapshot(
            repository_id=repository.repository_id,
            schema_version=repository.schema_version,
            repository_path=repository.repository_path,
            actor_id=repository.actor_id,
            managed_paths=repository.managed_paths,
            index_path=index.index_path,
            indexed_assets=index.asset_count,
            git_state=repository.git_state,
            remote=repository.remote,
            capacity=repository.capacity,
            ready=repository.ready,
            issues=repository.issues,
        )

    @staticmethod
    def _write_connection(
        connection_path: Path,
        connection: WorkspaceConnection,
    ) -> None:
        path = connection_path.expanduser().resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(connection.to_dict(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    @staticmethod
    def _load_connection(connection_path: Path) -> WorkspaceConnection:
        path = connection_path.expanduser().resolve()
        try:
            payload: Any = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise WorkspaceError(
                code="invalid_connection",
                message=f"Workspace connection cannot be read: {path}",
                next_action="Run bootstrap-memory to create a valid local workspace connection.",
            ) from error
        if (
            not isinstance(payload, dict)
            or not isinstance(payload.get("repository_path"), str)
            or not isinstance(payload.get("actor_id"), str)
            or not payload["actor_id"].strip()
        ):
            raise WorkspaceError(
                code="invalid_connection",
                message=f"Workspace connection has invalid fields: {path}",
                next_action="Run bootstrap-memory to recreate the local workspace connection.",
            )
        return WorkspaceConnection(
            repository_path=Path(payload["repository_path"]),
            actor_id=payload["actor_id"],
        )

