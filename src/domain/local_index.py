from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any

from src.domain.memory_repository import MANIFEST_PATH
from src.domain.models import IndexSummary, WorkspaceError


class LocalIndex:
    def __init__(self, repository_path: Path, index_path: Path | None = None) -> None:
        self.repository_path = repository_path.expanduser().resolve()
        self.path = (
            index_path.expanduser().resolve()
            if index_path is not None
            else self.repository_path / ".mlagent-local/index.sqlite3"
        )

    def rebuild(self) -> IndexSummary:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            asset_count = self._rebuild_once()
        except sqlite3.DatabaseError:
            self.path.unlink(missing_ok=True)
            asset_count = self._rebuild_once()
        return IndexSummary(index_path=self.path, asset_count=asset_count)

    def list_assets(self) -> list[dict[str, Any]]:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        try:
            rows = connection.execute(
                """
                SELECT path, content_sha256, asset_type, asset_id,
                       version, status, created_at
                FROM assets
                ORDER BY path
                """
            ).fetchall()
        finally:
            connection.close()
        return [dict(row) for row in rows]

    def _rebuild_once(self) -> int:
        assets = [self._read_asset(path) for path in self._asset_paths()]
        connection = sqlite3.connect(self.path)
        try:
            with connection:
                connection.executescript(
                    """
                    DROP TABLE IF EXISTS assets;
                    CREATE TABLE assets (
                        path TEXT PRIMARY KEY,
                        content_sha256 TEXT NOT NULL,
                        asset_type TEXT NOT NULL,
                        asset_id TEXT NOT NULL,
                        version TEXT,
                        status TEXT,
                        created_at TEXT
                    );
                    """
                )
                connection.executemany(
                    """
                    INSERT INTO assets (
                        path, content_sha256, asset_type, asset_id,
                        version, status, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    assets,
                )
        finally:
            connection.close()
        return len(assets)

    def _asset_paths(self) -> list[Path]:
        manifest_path = self.repository_path / MANIFEST_PATH
        manifest = self._load_json(manifest_path)
        managed_paths = manifest.get("managed_paths")
        if not isinstance(managed_paths, list):
            raise WorkspaceError(
                code="invalid_manifest",
                message="Team Memory manifest does not declare managed_paths.",
                next_action="Restore the repository manifest from Git before rebuilding the index.",
            )

        paths = [manifest_path]
        for managed_path in managed_paths:
            root = self.repository_path / str(managed_path)
            if root.is_dir():
                paths.extend(root.rglob("*.json"))
        return sorted(set(paths))

    def _read_asset(self, path: Path) -> tuple[str, str, str, str, str | None, str | None, str | None]:
        raw = path.read_bytes()
        payload = self._load_json(path, raw=raw)
        is_manifest = path == self.repository_path / MANIFEST_PATH
        asset_type = payload.get("asset_type")
        asset_id = payload.get("repository_id") if is_manifest else payload.get("asset_id")
        version = payload.get("schema_version") if is_manifest else payload.get("version")
        status = "active" if is_manifest else payload.get("status")
        created_at = payload.get("created_at")
        if not isinstance(asset_type, str) or not isinstance(asset_id, str):
            relative = path.relative_to(self.repository_path)
            raise WorkspaceError(
                code="invalid_asset",
                message=f"Authoritative asset lacks asset_type or stable ID: {relative}",
                next_action="Restore or correct the asset through the Domain Core before rebuilding the index.",
            )
        return (
            str(path.relative_to(self.repository_path)),
            hashlib.sha256(raw).hexdigest(),
            asset_type,
            asset_id,
            None if version is None else str(version),
            None if status is None else str(status),
            None if created_at is None else str(created_at),
        )

    @staticmethod
    def _load_json(path: Path, raw: bytes | None = None) -> dict[str, Any]:
        try:
            payload = json.loads((raw if raw is not None else path.read_bytes()).decode("utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise WorkspaceError(
                code="invalid_asset",
                message=f"Authoritative JSON asset cannot be indexed: {path}",
                next_action="Restore or correct the asset through the Domain Core before rebuilding the index.",
            ) from error
        if not isinstance(payload, dict):
            raise WorkspaceError(
                code="invalid_asset",
                message=f"Authoritative JSON asset must be an object: {path}",
                next_action="Restore or correct the asset through the Domain Core before rebuilding the index.",
            )
        return payload
