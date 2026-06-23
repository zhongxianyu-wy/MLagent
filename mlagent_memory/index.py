from __future__ import annotations

import sqlite3
from pathlib import Path

from sqlite_utils import Database

from mlagent_memory.constants import INDEX_RELATIVE_PATH
from mlagent_memory.io import read_text, read_yaml, write_yaml
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
                "confidence": str(data.get("confidence", "")),
                "needs_review": str(bool(data.get("needs_review", False))).lower(),
                "exp_type": str(data.get("type", "")),
                "superseded_by": str(data.get("superseded_by") or ""),
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
                "confidence": "",
                "needs_review": "",
                "exp_type": "",
                "superseded_by": "",
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
            "confidence": str,
            "needs_review": str,
            "exp_type": str,
            "superseded_by": str,
        },
        pk=("asset_id", "asset_type"),
    )
    documents = _collect_documents(root)
    if documents:
        db["documents"].insert_all(documents, pk=("asset_id", "asset_type"), replace=True)
    db["documents"].enable_fts(["title", "content"], create_triggers=True)

    registry_path = root / "project_knowledge/registry.yaml"
    if registry_path.exists():
        registry = read_yaml(registry_path)
        items = registry.get("items", [])
        for item in items:
            item["index_status"] = "indexed"
        write_yaml(registry_path, {"items": items})


def search_index(
    root: Path,
    query: str,
    asset_type: str | None = None,
    limit: int = 10,
    confidence_levels: list[str] | None = None,
    exclude_unreviewed: bool = False,
    exclude_superseded: bool = False,
) -> list[dict[str, str]]:
    require_memory_repo(root)
    index_path = _index_path(root)
    if not index_path.exists():
        return []
    db = Database(index_path)
    if not db["documents"].exists() or not db["documents"].detect_fts():
        return []
    where_parts: list[str] = []
    args: dict[str, object] = {}
    if asset_type:
        where_parts.append("asset_type = :asset_type")
        args["asset_type"] = asset_type
    if confidence_levels:
        ph = ",".join(f":cl{i}" for i in range(len(confidence_levels)))
        where_parts.append(f"confidence IN ({ph})")
        for i, c in enumerate(confidence_levels):
            args[f"cl{i}"] = c
    if exclude_unreviewed:
        where_parts.append("needs_review = 'false'")
    if exclude_superseded:
        where_parts.append("(superseded_by = '' OR superseded_by IS NULL)")
    where = " AND ".join(where_parts) if where_parts else None
    rows = db["documents"].search(query, where=where, where_args=(args if args else None), limit=limit)
    return [dict(row) for row in rows]
