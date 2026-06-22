from __future__ import annotations

import sqlite3
from pathlib import Path

from sqlite_utils import Database

from mlagent_memory.constants import INDEX_RELATIVE_PATH
from mlagent_memory.io import read_text, read_yaml
from mlagent_memory.repo import require_memory_repo


def fts5_available() -> bool:
    with sqlite3.connect(":memory:") as conn:
        options = {row[0] for row in conn.execute("PRAGMA compile_options")}
    return "ENABLE_FTS5" in options


def _index_path(root: Path) -> Path:
    return root / INDEX_RELATIVE_PATH


def _collect_documents(root: Path) -> list[dict[str, str]]:
    docs: list[dict[str, str]] = []

    for path in (root / "experience").rglob("*.yaml"):
        data = read_yaml(path)
        docs.append(
            {
                "asset_id": str(data["id"]),
                "asset_type": "experience",
                "source_path": str(path.relative_to(root)),
                "title": str(data.get("summary", data["id"])),
                "content": f"{data.get('summary', '')}\n{data.get('detail', '')}",
            }
        )

    for path in (root / "project_knowledge/notes").rglob("*.md"):
        docs.append(
            {
                "asset_id": path.stem,
                "asset_type": "knowledge",
                "source_path": str(path.relative_to(root)),
                "title": path.stem,
                "content": read_text(path),
            }
        )

    return docs


def rebuild_index(root: Path) -> None:
    require_memory_repo(root)
    if not fts5_available():
        raise RuntimeError("SQLite FTS5 is not available in this Python build")

    index_path = _index_path(root)
    index_path.parent.mkdir(parents=True, exist_ok=True)
    if index_path.exists():
        index_path.unlink()

    db = Database(index_path)
    db["documents"].create(
        {
            "asset_id": str,
            "asset_type": str,
            "source_path": str,
            "title": str,
            "content": str,
        },
        pk=("asset_id", "asset_type"),
    )
    documents = _collect_documents(root)
    if documents:
        db["documents"].insert_all(documents, pk=("asset_id", "asset_type"), replace=True)
    db["documents"].enable_fts(["title", "content"], create_triggers=True)


def search_index(root: Path, query: str, asset_type: str | None = None, limit: int = 10) -> list[dict[str, str]]:
    require_memory_repo(root)
    db = Database(_index_path(root))
    where = "asset_type = :asset_type" if asset_type else None
    where_args = {"asset_type": asset_type} if asset_type else None
    rows = db["documents"].search(query, where=where, where_args=where_args, limit=limit)
    return [dict(row) for row in rows]
