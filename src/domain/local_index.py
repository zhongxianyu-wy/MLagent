from __future__ import annotations

import hashlib
import json
import sqlite3
import subprocess
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
                       version, state, created_at
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
                        state TEXT,
                        created_at TEXT
                    );
                    """
                )
                connection.executemany(
                    """
                    INSERT INTO assets (
                        path, content_sha256, asset_type, asset_id,
                        version, state, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    assets,
                )
        finally:
            connection.close()
        return len(assets)

    def _asset_paths(self) -> list[str]:
        manifest_relative = MANIFEST_PATH.as_posix()
        manifest = self._load_json(
            manifest_relative,
            self._committed_bytes(manifest_relative),
        )
        managed_paths = manifest.get("managed_paths")
        if not isinstance(managed_paths, list) or not all(
            isinstance(path, str) for path in managed_paths
        ):
            raise WorkspaceError(
                code="invalid_manifest",
                message="Team Memory manifest does not declare managed_paths.",
                next_action="Restore the repository manifest from Git before rebuilding the index.",
            )

        result = subprocess.run(
            [
                "git",
                "ls-tree",
                "-r",
                "--name-only",
                "-z",
                "HEAD",
                "--",
                manifest_relative,
                *managed_paths,
            ],
            cwd=self.repository_path,
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            raise WorkspaceError(
                code="invalid_repository",
                message="Committed Team Memory assets cannot be enumerated.",
                next_action="Restore a valid Git HEAD before rebuilding the Local Index.",
            )
        json_paths = (
            path.decode("utf-8")
            for path in result.stdout.split(b"\0")
            if path and path.endswith(b".json")
        )
        return sorted(
            path for path in json_paths if self._is_indexable_asset_path(path)
        )

    @staticmethod
    def _is_indexable_asset_path(relative: str) -> bool:
        if relative.startswith("runs/"):
            return relative.endswith("/manifest.json")
        if relative.startswith("datasets/"):
            return relative.endswith("/manifest.json")
        return True

    def _read_asset(self, relative: str) -> tuple[str, str, str, str, str | None, str | None, str | None]:
        raw = self._committed_bytes(relative)
        payload = self._load_json(relative, raw)
        is_manifest = relative == MANIFEST_PATH.as_posix()
        asset_type = payload.get("asset_type")
        asset_id = payload.get("repository_id") if is_manifest else payload.get("asset_id")
        version = payload.get("schema_version") if is_manifest else payload.get("version")
        state = (
            "active"
            if is_manifest
            else payload.get("state", payload.get("status"))
        )
        created_at = payload.get("created_at")
        if not isinstance(asset_type, str) or not isinstance(asset_id, str):
            raise WorkspaceError(
                code="invalid_asset",
                message=f"Authoritative asset lacks asset_type or stable ID: {relative}",
                next_action="Restore or correct the asset through the Domain Core before rebuilding the index.",
            )
        return (
            relative,
            hashlib.sha256(raw).hexdigest(),
            asset_type,
            asset_id,
            None if version is None else str(version),
            None if state is None else str(state),
            None if created_at is None else str(created_at),
        )

    def _committed_bytes(self, relative: str) -> bytes:
        result = subprocess.run(
            ["git", "show", f"HEAD:{relative}"],
            cwd=self.repository_path,
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            raise WorkspaceError(
                code="invalid_repository",
                message=f"Committed Team Memory asset cannot be read: {relative}",
                next_action="Restore the committed asset from Git before rebuilding the Local Index.",
            )
        return result.stdout

    @staticmethod
    def _load_json(path: str, raw: bytes) -> dict[str, Any]:
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
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
