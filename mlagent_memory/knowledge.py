from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from shutil import copy2

from pypdf import PdfReader
from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter

from mlagent_memory.io import read_text, read_yaml, sha256_file, write_text, write_yaml
from mlagent_memory.repo import require_memory_repo
from mlagent_memory.schemas import KnowledgeItem


SUPPORTED_SUFFIXES = {".md", ".markdown", ".txt", ".pdf"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _extract_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".md", ".markdown", ".txt"}:
        return read_text(path)
    if suffix == ".pdf":
        reader = PdfReader(path)
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    raise ValueError(f"Unsupported knowledge file type: {path.suffix}")


def _split_text(path: Path, text: str) -> list[str]:
    if path.suffix.lower() in {".md", ".markdown"}:
        splitter = MarkdownHeaderTextSplitter(headers_to_split_on=[("#", "h1"), ("##", "h2"), ("###", "h3")])
        documents = splitter.split_text(text)
        return [doc.page_content for doc in documents if doc.page_content.strip()]
    splitter = RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=120)
    return [chunk for chunk in splitter.split_text(text) if chunk.strip()]


def import_knowledge_file(root: Path, source: Path, item_type: str, tags: list[str]) -> KnowledgeItem:
    require_memory_repo(root)
    if source.suffix.lower() not in SUPPORTED_SUFFIXES:
        raise ValueError(f"Unsupported knowledge file type: {source.suffix}")

    digest = sha256_file(source)
    stored_name = f"{digest[:12]}_{source.name}"
    stored_path = root / "project_knowledge/originals" / stored_name
    stored_path.parent.mkdir(parents=True, exist_ok=True)
    copy2(source, stored_path)

    text = _extract_text(stored_path)
    chunks = _split_text(stored_path, text)
    item_id = f"know_{digest[:12]}"
    summary = (chunks[0][:240] if chunks else "").replace("\n", " ").strip()

    note_path = root / "project_knowledge/notes" / f"{item_id}.md"
    write_text(
        note_path,
        "\n".join(
            [
                f"# {source.stem}",
                "",
                f"- id: {item_id}",
                f"- type: {item_type}",
                f"- source: {source}",
                f"- sha256: {digest}",
                "",
                "## Summary",
                summary,
                "",
                "## Extracted Text",
                text,
            ]
        ),
    )

    chunks_to_write = chunks if chunks else ([text] if text.strip() else [])
    chunk_dir = root / "project_knowledge/chunks" / item_id
    chunk_dir.mkdir(parents=True, exist_ok=True)
    manifest_chunks = []
    for index, chunk in enumerate(chunks_to_write, 1):
        stem = f"chunk_{index:04d}"
        chunk_path = chunk_dir / f"{stem}.md"
        write_text(chunk_path, chunk)
        manifest_chunks.append(
            {
                "chunk_id": f"{item_id}_{stem}",
                "path": str(chunk_path.relative_to(root)),
                "char_count": len(chunk),
            }
        )
    is_markdown = source.suffix.lower() in {".md", ".markdown"}
    write_yaml(
        chunk_dir / "manifest.yaml",
        {
            "knowledge_id": item_id,
            "original_filename": source.name,
            "sha256": digest,
            "chunking": {
                "strategy": "markdown_headers" if is_markdown else "recursive_character",
                "chunk_size": None if is_markdown else 800,
                "chunk_overlap": None if is_markdown else 120,
            },
            "chunks": manifest_chunks,
        },
    )

    item = KnowledgeItem(
        id=item_id,
        type=item_type,
        title=source.stem,
        original_filename=source.name,
        stored_path=str(stored_path.relative_to(root)),
        source_path=str(source),
        sha256=digest,
        imported_at=_now(),
        summary=summary,
        tags=tags,
        index_status="pending",
    )

    registry_path = root / "project_knowledge/registry.yaml"
    registry = read_yaml(registry_path)
    items = [entry for entry in registry.get("items", []) if entry.get("id") != item.id]
    items.append(item.model_dump())
    write_yaml(registry_path, {"items": items})
    return item
