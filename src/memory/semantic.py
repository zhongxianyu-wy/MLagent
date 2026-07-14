from __future__ import annotations

from typing import Protocol

from src.memory.metadata_index import MetadataIndex
from src.models import MemoryEntry


class VectorStore(Protocol):
    def add(self, memory_id: str, text: str) -> None:
        ...

    def search(self, query: str, top_k: int) -> list[dict[str, str]]:
        ...


class SemanticMemory:
    def __init__(self, vector_store: VectorStore, metadata_index: MetadataIndex) -> None:
        self.vector_store = vector_store
        self.metadata_index = metadata_index

    def add(self, entry: MemoryEntry) -> None:
        self.vector_store.add(entry.memory_id, entry.text)
        self.metadata_index.add(entry, chroma_id=entry.memory_id)

    def search(self, query: str, top_k: int = 5) -> list[MemoryEntry]:
        matches = self.vector_store.search(query, top_k)
        return [
            self.metadata_index.get(match["memory_id"], text=match["text"])
            for match in matches
        ]
