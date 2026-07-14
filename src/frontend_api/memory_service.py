from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from typing import Protocol

from src.models import MemoryEntry


class SemanticMemoryLike(Protocol):
    def add(self, entry: MemoryEntry) -> None:
        ...

    def search(self, query: str, top_k: int = 5) -> list[MemoryEntry]:
        ...


class MemoryService:
    def __init__(
        self,
        semantic_memory: SemanticMemoryLike,
        id_factory: Callable[[], str] | None = None,
        clock: Callable[[], int] | None = None,
    ) -> None:
        self.semantic_memory = semantic_memory
        self.id_factory = id_factory or (lambda: str(uuid.uuid4()))
        self.clock = clock or (lambda: int(time.time()))

    def search(self, query: str, top_k: int = 5) -> list[MemoryEntry]:
        return self.semantic_memory.search(query, top_k)

    def add_experience(
        self, round_id: str, summary: str, confidence: str
    ) -> MemoryEntry:
        entry = MemoryEntry(
            memory_id=self.id_factory(),
            source="agent",
            text=summary,
            linked_experiment_id=None,
            linked_round_id=round_id,
            linked_skill_id=None,
            confidence=confidence,
            needs_review=False,
            created_at=self.clock(),
        )
        self.semantic_memory.add(entry)
        return entry

    def get_related_context(
        self, dataset_id: str, objective: str, top_k: int = 5
    ) -> list[MemoryEntry]:
        return self.search(f"{dataset_id} {objective}", top_k)
